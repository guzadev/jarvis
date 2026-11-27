"""Local-only 'Jarvis' detector. Audio remains in memory on this PC."""
import json
import logging
import queue
import threading
import time
from pathlib import Path
from windows_audio import capture_inventory, ranked_inputs, is_monitor
from whisper_wake import WhisperWake, WhisperWakeError

DEVICE_LOCK = threading.RLock()
_QUERY_ENDPOINTS = object()

MODEL_NAME = "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"


def make_spotter(root):
    return WhisperWake(root)


class WakeListener:
    def __init__(self, root, open_interface=None):
        self.root = Path(root)
        self.config_path = self.root / ".wake-config.json"
        self.lock = threading.RLock()
        self.shutdown = threading.Event()
        self.mic_closed = threading.Event()
        self.mic_closed.set()
        self.thread = None
        self.spotter = None
        self.open_interface = open_interface
        self.clients = {}
        self.foreground_clients = {}
        self.owner = None
        self.owner_until = 0
        self.pending = 0
        self.pending_until = 0
        self.sequence = 0
        self.cooldown_until = 0
        self.opened_sequence = 0
        self.version = 0
        self.config = {"enabled": False, "microphone": "auto"}
        if self.config_path.exists():
            self.config.update(json.loads(self.config_path.read_text(encoding="utf-8")))
        # Listening is a deliberate action in the current open UI, not a login task.
        self.config['enabled']=False
        self.state = "loading" if self.config["enabled"] else "paused"
        self.error = ""
        self.microphone = ""
        self.last_detected = None
        self.audio_level = 0
        self.refresh_devices = False

    def start(self):
        if not self.thread or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._run, name="jarvis-local-wake", daemon=True)
            self.thread.start()

    def close(self):
        self.shutdown.set()
        if self.thread:
            self.thread.join(timeout=4)
        if self.spotter is not None:
            self.spotter.close()

    def _expire(self):
        now = time.monotonic()
        if self.owner and self.owner_until < now:
            self.owner = None
            self.cooldown_until = now + 3
        if self.pending and self.pending_until < now:
            self.pending = 0
            self.cooldown_until = now + 3
        self.clients = {key: value for key, value in self.clients.items() if now - value < 30}
        # The focused page polls every second. Hidden or closed tabs quickly lose priority.
        self.foreground_clients = {key: seen for key, seen in self.foreground_clients.items() if now - seen < 5}
        if not self.foreground_clients and self.pending:
            self.pending=0
            self.cooldown_until=now+3

    def _listening_allowed(self):
        with self.lock:
            self._expire()
            return (self.config["enabled"] and bool(self.foreground_clients) and not self.owner and not self.pending
                    and time.monotonic() >= self.cooldown_until)

    def status(self):
        with self.lock:
            self._expire()
            state = ("conversation" if self.owner else "detected" if self.pending
                     else "paused" if not self.config["enabled"] or not self.foreground_clients else self.state)
            if state=='listening' and self.spotter is not None and not self.spotter.ready.is_set():state='loading'
            return {"enabled": self.config["enabled"], "state": state,
                    "keyword": "Jarvis", "microphone": self.microphone,
                    "preferred_microphone": self.config["microphone"],
                    "error": self.error, "last_detected": self.last_detected,
                    "level": round(self.audio_level, 3), "local_only": True,
                    "detector_ready":bool(self.spotter is not None and self.spotter.ready.is_set() and not self.spotter.failed.is_set()),
                    "clips_processed":getattr(self.spotter,'processed',0),"keyword_hits":getattr(self.spotter,'hits',0),
                    "last_processing_ms":getattr(self.spotter,'last_processing_ms',0)}

    def configure(self, enabled, microphone=None):
        with self.lock:
            self.config["enabled"] = enabled
            if microphone is not None:
                self.config["microphone"] = microphone
            self.version += 1
            self.error = ""
            self.state = "loading" if enabled else "paused"
            self.pending = 0
            temporary = self.config_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.config, indent=2), encoding="utf-8")
            temporary.replace(self.config_path)
        return self.status()

    def hold(self, client, pending_sequence=None):
        with self.lock:
            self._expire()
            if pending_sequence is not None and self.pending != pending_sequence:
                raise ValueError("Esta activación ya fue atendida.")
            if self.owner and self.owner != client:
                raise ValueError("La voz ya está activa en otra ventana de Jarvis.")
            self.owner = client
            self.owner_until = time.monotonic() + 18
            self.pending = 0
        # Release the native microphone before the browser opens it.
        if not self.mic_closed.wait(timeout=4):
            self.release(client)
            raise ValueError("El micrófono está tardando en liberarse. Volvé a intentar.")

    def release(self, client):
        with self.lock:
            self.foreground_clients.pop(client,None)
            if self.owner == client:
                self.owner = None
                self.cooldown_until = time.monotonic() + 3

    def poll(self, client, active, foreground=False):
        claim = None
        activate = False
        with self.lock:
            self._expire()
            now = time.monotonic()
            self.clients[client] = now
            if foreground:
                self.foreground_clients[client] = now
            else:
                self.foreground_clients.pop(client, None)
            if self.owner == client:
                if active:
                    self.owner_until = time.monotonic() + 18
                else:
                    self.release(client)
            elif foreground and self.pending and not self.owner:
                claim = self.pending
        if claim is not None:
            # hold() checks ownership again under the lock: only one tab wins.
            try:
                self.hold(client, pending_sequence=claim)
                activate = True
            except ValueError:
                activate = False
        result = self.status()
        result["activate"] = activate
        return result

    @staticmethod
    def devices(inventory=_QUERY_ENDPOINTS):
        import sounddevice as sd
        if inventory is _QUERY_ENDPOINTS:inventory=capture_inventory()
        with DEVICE_LOCK:
            apis = sd.query_hostapis()
            raw_devices = list(sd.query_devices())
        result = []
        for index, device in enumerate(raw_devices):
            if device["max_input_channels"]:
                name = " ".join(device["name"].split())
                if is_monitor(name):continue
                result.append({"id": index, "name": name,
                               "hostapi": apis[device["hostapi"]]["name"],
                               "sample_rate": int(device["default_samplerate"])})
        return ranked_inputs(result, inventory, -1)

    def _candidates(self, inventory):
        import sounddevice as sd
        with self.lock:
            hint = self.config["microphone"]
        indexed = self.devices(inventory=None)
        with DEVICE_LOCK:
            try: default_index = int(sd.default.device[0])
            except (ValueError, TypeError, IndexError): default_index = -1
        return ranked_inputs(indexed, inventory, default_index, hint)

    def _detected(self):
        with self.lock:
            if not self._listening_allowed():
                return
            self.sequence += 1
            self.pending = self.sequence
            self.pending_until = time.monotonic() + 40
            self.last_detected = time.time()
        self._open_pending_interface()

    def _open_pending_interface(self):
        # A closed/hidden UI must never be resurrected by ambient speech.
        with self.lock:
            self._expire()

    def _run(self):
        import numpy as np
        import sounddevice as sd
        unavailable = {}
        while not self.shutdown.is_set():
            if not self._listening_allowed():
                self._open_pending_interface()
                with self.lock:
                    self.audio_level = 0
                self.shutdown.wait(.15)
                continue
            with self.lock:
                self.state = "loading"
                self.error = ""
                version = self.version
            try:
                if self.spotter is None:
                    self.spotter = make_spotter(self.root)
                if self.refresh_devices:
                    # PortAudio caches devices. Refresh only after our stream is closed.
                    with DEVICE_LOCK:
                        sd._terminate()
                        sd._initialize()
                    self.refresh_devices = False
                inventory = capture_inventory()
                unavailable = {key:until for key,until in unavailable.items() if until > time.monotonic()}
                candidates = [d for d in self._candidates(inventory) if (d['id'],d['name']) not in unavailable]
                if not candidates:
                    raise RuntimeError("No hay una entrada de micrófono disponible.")
                default_checked_at = time.monotonic()
                frames = queue.Queue(maxsize=25)
                def callback(data, count, timing, status):
                    try:
                        frames.put_nowait(data[:, 0].copy())
                    except queue.Full:
                        pass
                stream = self.spotter.create_stream()
                # Reserve the capture before opening: the browser then waits for our close.
                with self.lock:
                    if not self._listening_allowed():continue
                    self.mic_closed.clear()
                try:
                    from contextlib import ExitStack
                    with ExitStack() as inputs:
                        for device in candidates:
                            if not self._listening_allowed():break
                            rate = device["sample_rate"]
                            try:
                                inputs.enter_context(sd.InputStream(device=device["id"], channels=1,
                                    dtype="float32", samplerate=rate, blocksize=int(rate * .08), callback=callback))
                                break
                            except sd.PortAudioError:
                                unavailable[(device["id"],device["name"])]=time.monotonic()+10
                                continue
                        else:raise RuntimeError("No se pudo abrir ninguna entrada de micrófono disponible.")
                        if not self._listening_allowed():continue
                        with self.lock:
                            self.microphone = device["name"]
                            self.state = "listening"
                        last_frame = time.monotonic()
                        while (not self.shutdown.is_set() and self._listening_allowed()
                               and version == self.version):
                            if self.config["microphone"] == "auto" and time.monotonic() - default_checked_at > 3:
                                default_checked_at = time.monotonic()
                                if capture_inventory() != inventory:
                                    unavailable.clear()
                                    self.refresh_devices = True
                                    break
                            try:
                                samples = frames.get(timeout=.2)
                            except queue.Empty:
                                # Silence still produces PCM frames. A stopped callback is a
                                # device failure, even if PortAudio still lists its endpoint.
                                if time.monotonic() - last_frame > 3:
                                    unavailable[(device["id"],device["name"])]=time.monotonic()+10
                                    self.refresh_devices=True
                                    break
                                continue
                            last_frame = time.monotonic()
                            with self.lock:
                                self.audio_level = min(1., float(np.sqrt(np.mean(samples ** 2))) * 8)
                            stream.accept_waveform(rate, samples)
                            while self.spotter.is_ready(stream):
                                self.spotter.decode_stream(stream)
                                result = self.spotter.get_result(stream)
                                if result.strip() == "JARVIS":
                                    self.spotter.reset_stream(stream)
                                    self._detected()
                                    break
                finally:
                    self.mic_closed.set()
                    with self.lock:
                        self.audio_level = 0
            except Exception as error:
                if isinstance(error, WhisperWakeError) and self.spotter is not None:
                    self.spotter.close()
                    self.spotter=None
                logging.getLogger(__name__).warning("Detector de Jarvis: %s", error)
                with self.lock:
                    self.state = "error"
                    self.error = str(error) if isinstance(error,WhisperWakeError) else ("No hay un micrófono disponible en este momento. Conectá o encendé uno; Jarvis lo detecta automáticamente."
                                  if not isinstance(error, FileNotFoundError) else
                                  "Falta completar la instalación del reconocimiento local de Jarvis en esta PC.")
                self.mic_closed.set()
                self.refresh_devices = True
                # Retry disconnected devices without a busy loop, but react to settings.
                for _ in range(50):
                    if self.shutdown.wait(.2) or version != self.version or not self.config["enabled"]:
                        break
