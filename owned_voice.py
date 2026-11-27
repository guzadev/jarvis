"""Local Jarvis voice profile. No hosted provider or API credential is used."""
import json
import hashlib
import secrets
import socket
import subprocess
import threading
import time
from pathlib import Path
from contextlib import contextmanager

import httpx
import app_runtime

URL='http://127.0.0.1:8797'
LOCK=threading.RLock()
SERVICE_HTTP=httpx.Client(trust_env=False,follow_redirects=False,timeout=240)
QWEN_ENGINE='Qwen3-TTS-12Hz-1.7B-Base'
SAMPLE_PHRASE='Buenos días, señor. Soy Jarvis. Estoy listo para ayudarlo. ¿Por dónde comenzamos?'

def folder():return Path(app_runtime.settings()['storage_dir'])/'models/jarvis-owned'

def status():
    path=folder()/'profile.json'
    try:data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    except (OSError,ValueError):data={}
    engine=data.get('engine',QWEN_ENGINE)
    models=Path(app_runtime.settings()['storage_dir'])/'models'
    if engine==QWEN_ENGINE:
        weights=models/'qwen3-tts-1.7b-base'
        required=json.loads((Path(__file__).parent/'qwen-voice-weights.json').read_text(encoding='utf-8-sig'))['files'] if data.get('prepared') else ()
    else:weights,required=models/'xtts-v2',('model.pth','config.json','vocab.json')
    profile=folder()/'voice.pth'
    demo=folder()/'samples/demo.wav'
    prepared=bool(engine in (QWEN_ENGINE,'XTTS-v2') and data.get('prepared') and profile.is_file() and data.get('profile_sha256')==hashlib.sha256(profile.read_bytes()).hexdigest()
                  and demo.is_file() and data.get('sample_sha256')==hashlib.sha256(demo.read_bytes()).hexdigest()
                  and all((weights/name).is_file() for name in required))
    return {'engine':engine,'name':'Jarvis · perfil propio local','prepared':prepared,
            'approved':prepared and data.get('approved') is True,'requires_internet':False,
            'profile_sha256':data.get('profile_sha256') if prepared else None,'sample_sha256':data.get('sample_sha256') if prepared else None,
            'sample_ready':prepared,'profile_path':str(folder()),
            'message':'Perfil local listo para escuchar.' if prepared else 'Preparando el perfil local de Jarvis; podés seguir usando texto.'}

def approve(value,profile_sha256=None,sample_sha256=None):
    with LOCK:
        path=folder()/'profile.json'
        current=status()
        if not current['prepared']:raise RuntimeError('Primero hay que preparar la muestra local.')
        if value and (profile_sha256!=current['profile_sha256'] or sample_sha256!=current['sample_sha256']):raise RuntimeError('La muestra cambió desde que la escuchaste. Escuchá la nueva antes de elegirla.')
        data=json.loads(path.read_text(encoding='utf-8'));data['approved']=bool(value)
        temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8');temp.replace(path)
    return status()

def ensure_service(engine):
    storage=Path(app_runtime.settings()['storage_dir']);state_path=storage/'.owned-voice-service.json'
    with LOCK:
        previous=json.loads(state_path.read_text()) if state_path.exists() else {}
        try:
            health=SERVICE_HTTP.get(URL+'/health',timeout=1)
            if health.is_success:
                if health.json().get('engine')!=engine or not previous.get('token'):
                    raise RuntimeError('Hay otro motor de voz en el puerto local. Reinicialo antes de continuar.')
                return previous['token']
        except httpx.HTTPError:pass
        python=storage/'.owned-voice-venv/Scripts/python.exe'
        if not python.exists():raise RuntimeError('El entorno de voz local todavía no está instalado.')
        token=secrets.token_urlsafe(40);env=app_runtime.environment()
        env={key:value for key,value in env.items() if not any(word in key.upper() for word in ('KEY','TOKEN','SECRET','PASSWORD'))}
        env.update(JARVIS_OWNED_STORAGE=str(storage),JARVIS_OWNED_TOKEN=token,HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
        (storage/'logs').mkdir(parents=True,exist_ok=True)
        script='qwen_voice_service.py' if engine==QWEN_ENGINE else 'owned_voice_service.py'
        with (storage/'logs/owned-voice.log').open('ab') as log:
            process=subprocess.Popen([str(python),str(app_runtime.ROOT/script),'--serve'],env=env,
                                     stdout=log,stderr=log,cwd=app_runtime.ROOT,creationflags=subprocess.CREATE_NO_WINDOW)
        state_path.write_text(json.dumps({'pid':process.pid,'token':token}),encoding='utf-8')
        for _ in range(80):
            try:
                health=SERVICE_HTTP.get(URL+'/health',timeout=1)
                if health.is_success and health.json().get('engine')==engine:return token
            except httpx.HTTPError:pass
            if process.poll() is not None:raise RuntimeError('El motor de voz local no pudo iniciarse. Revisá su registro.')
            time.sleep(.25)
        raise RuntimeError('El motor de voz local todavía está iniciándose.')

def synthesize(text):
    current=status()
    if not current['approved']:raise RuntimeError('La voz local está en preparación o pendiente de tu escucha. No se usó Fish ni otra voz.')
    token=ensure_service(current['engine'])
    response=SERVICE_HTTP.post(URL+'/synthesize',headers={'Authorization':'Bearer '+token},json={'text':text})
    if not response.is_success:raise RuntimeError('El perfil local no pudo generar esta frase. El texto sigue disponible; no se usó ningún proveedor externo.')
    data=response.content
    if len(data)<44 or data[:4]!=b'RIFF' or data[8:12]!=b'WAVE':raise RuntimeError('El motor local no devolvió un WAV válido.')
    return data

class VoiceBusyError(RuntimeError):
    retry_after = 1


class VoiceStreamCancelled(RuntimeError):
    pass


@contextmanager
def _stream_request(token, text, cancel_event):
    args = dict(headers={'Authorization':'Bearer '+token}, json={'text':text})
    if cancel_event is None:
        with SERVICE_HTTP.stream('POST',URL+'/synthesize-stream',**args) as response:
            yield response
        return
    if cancel_event.is_set():
        raise VoiceStreamCancelled('Solicitud de voz cancelada.')

    # Own this connection exclusively: interrupting a pooled socket could
    # cancel a different phrase after it returned to the pool.
    finished = threading.Event()
    watcher = None

    def trace(name, info):
        nonlocal watcher
        if name != 'connection.connect_tcp.complete':
            return
        sock = info['return_value'].get_extra_info('socket')
        def interrupt():
            while not finished.wait(.025):
                if cancel_event.is_set():
                    try:sock.shutdown(socket.SHUT_RDWR)
                    except OSError:pass
                    return
        watcher = threading.Thread(target=interrupt, name='jarvis-pcm-cancel', daemon=True)
        watcher.start()

    try:
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=httpx.Timeout(240,connect=2)) as client:
            with client.stream('POST',URL+'/synthesize-stream',extensions={'trace':trace},**args) as response:
                yield response
    except httpx.HTTPError:
        if cancel_event.is_set():
            raise VoiceStreamCancelled('Solicitud de voz cancelada.') from None
        raise
    finally:
        finished.set()
        if watcher is not None:
            watcher.join(timeout=.25)


def synthesize_stream(text,cancel_event=None):
    """Yield signed little-endian mono PCM, closing loopback HTTP on cancellation."""
    if cancel_event is not None and cancel_event.is_set():
        raise VoiceStreamCancelled('Solicitud de voz cancelada.')
    current=status()
    if not current['approved'] or current['engine']!=QWEN_ENGINE:
        raise RuntimeError('El perfil Qwen local debe estar preparado y aprobado.')
    token=ensure_service(current['engine'])
    health=SERVICE_HTTP.get(URL+'/health',timeout=2)
    if not health.is_success or health.json().get('streaming') is not True:
        raise RuntimeError('Reiniciá el servicio de voz local para activar el audio incremental.')
    # A cancelled producer releases the GPU at its next chunk boundary. Only
    # 429 guarantees that this request never started generating the phrase.
    for delay in (0, .12, .25, .5, .75):
        if cancel_event is not None and cancel_event.wait(delay):
            raise VoiceStreamCancelled('Solicitud de voz cancelada.')
        if delay and cancel_event is None:
            time.sleep(delay)
        with _stream_request(token,text,cancel_event) as response:
            if response.status_code==429:
                continue
            if not response.is_success:
                raise RuntimeError('El servicio local no pudo iniciar la voz incremental.')
            if response.headers.get('x-audio-format')!='pcm_s16le' or response.headers.get('x-audio-sample-rate')!='24000':
                raise RuntimeError('El formato de audio local no es válido.')
            for block in response.iter_bytes():
                if cancel_event is not None and cancel_event.is_set():
                    raise VoiceStreamCancelled('Solicitud de voz cancelada.')
                yield block
            if cancel_event is not None and cancel_event.is_set():
                raise VoiceStreamCancelled('Solicitud de voz cancelada.')
            return
    raise VoiceBusyError('La voz local sigue ocupada terminando otra frase.')
