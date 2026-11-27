"""A small energy gate feeds a single, asynchronous Spanish Whisper worker."""
import base64
from collections import deque
import io
import json
from pathlib import Path
import queue
import subprocess
import threading
import time
import wave

import numpy as np

import app_runtime


class WhisperWakeError(RuntimeError):
    pass


class Capture:
    def __init__(self):
        self.preroll = deque(maxlen=3)
        self.blocks = []
        self.voiced = self.quiet = self.duration = 0.
        self.rate = 0
        self.pending = None
        self.hit = False

    def accept_waveform(self, rate, samples):
        if not len(samples):return
        if rate <= 0 or rate > 384000:raise ValueError('Frecuencia de micrófono no admitida.')
        if self.rate and self.rate != rate:self.__init__()
        self.rate = rate
        seconds = len(samples)/rate
        speech = float(np.sqrt(np.mean(np.square(samples)))) >= .003
        if not self.blocks:
            if not speech:
                self.preroll.append(samples.copy())
                return
            self.blocks.extend(self.preroll)
            self.preroll.clear()
        self.blocks.append(samples.copy())
        self.duration += seconds
        self.voiced += seconds if speech else 0.
        self.quiet = 0. if speech else self.quiet + seconds
        if self.quiet < .36 and self.duration < 3.6:return
        long_phrase = self.quiet < .36
        if self.voiced >= .2:
            self.pending = (rate,np.concatenate(self.blocks))
        tail = self.blocks[-5:] if long_phrase else []
        self.blocks = list(tail)
        self.duration = sum(len(b)/rate for b in tail)
        self.voiced = self.quiet = 0.


class WhisperWake:
    def __init__(self,root,storage=None,python=None):
        storage = Path(storage or app_runtime.settings()['storage_dir'])
        model = storage/'models/whisper-small'
        if not (model/'model.bin').is_file():raise FileNotFoundError('Falta preparar Whisper Small en español.')
        env={k:v for k,v in app_runtime.environment().items() if not any(w in k.upper() for w in ('KEY','TOKEN','PASSWORD','SECRET'))}
        env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
        self.process=subprocess.Popen([str(python or app_runtime.agent_python()),str(Path(root)/'wake_transcriber.py'),str(model)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, text=True,
            encoding='utf8',creationflags=subprocess.CREATE_NO_WINDOW)
        self.jobs=queue.Queue(maxsize=1)
        self.results=queue.Queue(maxsize=1)
        self.ready=threading.Event()
        self.failed=threading.Event()
        self.closed=threading.Event()
        self.active=None
        self.busy=False
        self.serial=0
        self.started=time.monotonic()
        self.submitted=0.
        self.processed=0
        self.hits=0
        self.last_processing_ms=0
        self.thread=threading.Thread(target=self._communicate,name='jarvis-whisper-wake',daemon=True)
        self.thread.start()

    def _communicate(self):
        try:
            if not json.loads(self.process.stdout.readline()).get('ready'):raise ValueError()
            self.ready.set()
            while not self.closed.is_set():
                job=self.jobs.get()
                if job is None:return
                serial,stream,rate,samples=job
                buffer=io.BytesIO()
                with wave.open(buffer,'wb') as out:
                    out.setparams((1,2,rate,0,'NONE',''))
                    out.writeframes((np.clip(samples,-1,1)*32767).astype('<i2').tobytes())
                line=json.dumps({'id':serial,'wav':base64.b64encode(buffer.getvalue()).decode('ascii')})
                self.process.stdin.write(line+'\n');self.process.stdin.flush()
                decoding=time.monotonic()
                result=json.loads(self.process.stdout.readline())
                if result.get('id')!=serial:raise ValueError()
                self.processed+=1
                self.hits+=int(result['hit'] is True)
                self.last_processing_ms=round((time.monotonic()-decoding)*1000)
                self.results.put_nowait((stream,result['hit'] is True))
        except (OSError,ValueError,KeyError,queue.Full):
            if not self.closed.is_set():self.failed.set()
        finally:self.ready.set()

    def create_stream(self):
        self.active=Capture()
        return self.active

    def is_ready(self,stream):
        now=time.monotonic()
        if (self.failed.is_set() or self.process.poll() is not None or
                (not self.ready.is_set() and now-self.started>60) or
                (self.busy and self.ready.is_set() and self.results.empty() and now-self.submitted>30)):
            raise WhisperWakeError('El detector Whisper de español no respondió. Verificá el modelo y su entorno local.')
        # Keep the latest completed phrase while Whisper decodes the previous one.
        # Clearing it while busy can discard the user's entire wake invocation.
        return stream is self.active and (not self.results.empty() or (stream.pending is not None and not self.busy))

    def decode_stream(self,stream):
        try:
            owner,hit=self.results.get_nowait()
            self.busy=False
            stream.hit=(owner is stream and hit)
        except queue.Empty:pass
        if stream.pending is not None and not stream.hit and not self.busy:
            rate,samples=stream.pending
            stream.pending=None
            self.serial+=1
            self.submitted=time.monotonic()
            self.busy=True
            self.jobs.put_nowait((self.serial,stream,rate,samples))

    def get_result(self,stream):
        return 'JARVIS' if stream.hit and stream is self.active else ''

    def reset_stream(self,stream):
        if self.active is stream:self.active=None
        stream.hit=False
        stream.pending=None

    def close(self):
        if self.closed.is_set():return
        self.closed.set()
        try:self.jobs.put_nowait(None)
        except queue.Full:pass
        if self.process.poll() is None:self.process.terminate()
        try:self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=2)
        self.thread.join(timeout=1)
        self.process.stdin.close()
        self.process.stdout.close()
