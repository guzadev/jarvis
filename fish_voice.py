"""Only the selected Jarvis voice on Fish's explicitly free TTS model."""
import base64
import ctypes
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT=Path(__file__).resolve().parent
CONFIG_PATH=ROOT/'.jarvis-fish.json'
VOICE_ID='21adf3cda02a4aa88dc593353cc9d715'
VOICE_NAME='Jarvis — español latino · muestra 1 verde'
MODEL='s2.1-pro-free'
ENDPOINT='https://api.fish.audio/v1/tts'
# Fish's changelog guarantees the free offer through November 30, 2026.
# Stop conservatively at UTC midnight; extending requires rechecking the price.
FREE_UNTIL=datetime(2026,12,1,tzinfo=timezone.utc)
TEST_PHRASE='Buenos días, señor. Soy Jarvis. Estoy listo para ayudarlo. ¿Por dónde comenzamos?'
LOCK=threading.RLock()
SYNTHESIS_SLOT=threading.BoundedSemaphore(1)
MAX_AUDIO_BYTES=20_000_000

class FishVoiceError(Exception):
    def __init__(self,status_code,message):
        super().__init__(message);self.status_code=status_code

def now():return datetime.now(timezone.utc)

def _state():
    try:return json.loads(CONFIG_PATH.read_text(encoding='utf-8')) if CONFIG_PATH.exists() else {}
    except (OSError,ValueError):raise FishVoiceError(409,'No pude leer la configuración de Fish. Volvé a guardar su clave.') from None

def _write(state):
    temporary=CONFIG_PATH.with_suffix('.tmp')
    temporary.write_text(json.dumps(state,indent=2,ensure_ascii=False),encoding='utf-8')
    temporary.replace(CONFIG_PATH)

def _protect(data,decode=False):
    """Windows DPAPI: this user's key stays encrypted on disk."""
    if os.name!='nt':raise FishVoiceError(503,'El almacenamiento de claves de esta versión requiere Windows.')
    from ctypes import wintypes as w
    class Blob(ctypes.Structure):_fields_=[('size',w.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=ctypes.create_string_buffer(data)
    source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes=[w.HLOCAL];kernel.LocalFree.restype=w.HLOCAL
    if decode:
        function=crypt.CryptUnprotectData
        function.argtypes=[ctypes.POINTER(Blob),ctypes.POINTER(w.LPWSTR),ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,w.DWORD,ctypes.POINTER(Blob)]
    else:
        function=crypt.CryptProtectData
        function.argtypes=[ctypes.POINTER(Blob),w.LPCWSTR,ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,w.DWORD,ctypes.POINTER(Blob)]
    function.restype=w.BOOL
    # CRYPTPROTECT_UI_FORBIDDEN. Scope is the current user, not the machine.
    if not function(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):
        raise FishVoiceError(409,'Windows no pudo abrir o proteger la clave de Fish. Guardala nuevamente en esta PC.')
    try:return ctypes.string_at(target.data,target.size)
    finally:kernel.LocalFree(ctypes.cast(target.data,w.HLOCAL))

def save_key(value):
    value=value.strip()
    if not 16<=len(value)<=4096 or any(not 33<=ord(char)<=126 for char in value):raise FishVoiceError(400,'Pegá una clave API válida de Fish Audio.')
    if value.startswith(('sk-proj-','sk-ant-')):raise FishVoiceError(400,'Esa clave pertenece a otro proveedor. Necesitás una clave de Fish Audio.')
    protected=base64.b64encode(_protect(value.encode())).decode('ascii')
    with LOCK:_write({'key_dpapi':protected,'voice_id':VOICE_ID,'model':MODEL})

def get_key():
    with LOCK:
        state=_state()
        if state.get('key_dpapi'):
            try:return _protect(base64.b64decode(state['key_dpapi'],validate=True),decode=True).decode('utf-8')
            except FishVoiceError:raise
            except Exception:raise FishVoiceError(409,'No pude abrir la clave de Fish. Guardala nuevamente.') from None
    key=os.environ.get('FISH_API_KEY') or os.environ.get('FISH_AUDIO_API_KEY')
    if key:return key.strip()
    raise FishVoiceError(409,'Falta la clave de Fish Audio. Abrí Conexión → Voz de Jarvis para conectarla.')

def status():
    try:
        with LOCK:state=_state()
        configured=bool(state.get('key_dpapi') or os.environ.get('FISH_API_KEY') or os.environ.get('FISH_AUDIO_API_KEY'))
    except FishVoiceError:state={};configured=False
    saved_test=state.get('last_test')
    public_test=({'success':saved_test.get('success') is True,'at':str(saved_test.get('at',''))[:40],
                  'model':MODEL,'voice_id':VOICE_ID} if isinstance(saved_test,dict) else None)
    return {'voice_id':VOICE_ID,'voice_name':VOICE_NAME,'model':MODEL,'key_configured':configured,
            'test_passed':bool(public_test and public_test['success']),
            'last_test':public_test,'free_available':now()<FREE_UNTIL,
            'free_verified_through':'2026-11-30','requires_internet':True}

def record_test(success):
    with LOCK:
        state=_state();state['last_test']={'success':bool(success),'at':now().isoformat(),'model':MODEL,'voice_id':VOICE_ID}
        _write(state)

def synthesize(text,*,transport=None):
    if not text.strip() or len(text)>1000:raise FishVoiceError(400,'La captura de texto debe tener entre 1 y 1.000 caracteres.')
    if now()>=FREE_UNTIL:raise FishVoiceError(409,'La gratuidad de Fish necesita revalidación después del 30 de noviembre de 2026. No se hizo ninguna llamada ni se activó una opción de pago.')
    key=get_key()
    if not SYNTHESIS_SLOT.acquire(blocking=False):raise FishVoiceError(429,'Jarvis ya está generando una respuesta de voz. Esperá a que termine.')
    try:
        # No caller-supplied URL, model, voice, redirects, retries or fallback.
        with httpx.Client(timeout=httpx.Timeout(120,connect=10),follow_redirects=False,transport=transport) as client:
            with client.stream('POST',ENDPOINT,headers={'Authorization':'Bearer '+key,'model':MODEL,'Content-Type':'application/json'},
                               json={'text':text,'reference_id':VOICE_ID,'format':'wav','sample_rate':44100,
                                     'temperature':.7,'top_p':.7,'language':'es-MX','latency':'normal'}) as response:
                code=response.status_code
                if code!=200:
                    errors={401:(409,'Fish no reconoció la clave. Revisala en Conexión → Voz de Jarvis.'),
                            402:(409,'Fish no habilitó esta llamada gratuita. No se activó ningún modelo de pago.'),
                            403:(403,'Fish no permitió usar esta voz con la cuenta conectada.'),
                            404:(404,'Fish no encontró la voz de Jarvis seleccionada. No se eligió otra.'),
                            429:(429,'Fish limitó temporalmente las solicitudes gratuitas. Intentá de nuevo más tarde.')}
                    status_code,message=errors.get(code,(502,'Fish no pudo generar la voz elegida. No se cambió de voz ni de modelo.'))
                    raise FishVoiceError(status_code,message)
                data=bytearray()
                for chunk in response.iter_bytes():
                    if len(data)+len(chunk)>MAX_AUDIO_BYTES:raise FishVoiceError(502,'El audio de Fish superó el tamaño permitido.')
                    data.extend(chunk)
                if len(data)<44 or data[:4]!=b'RIFF' or data[8:12]!=b'WAVE':raise FishVoiceError(502,'Fish no devolvió un archivo WAV válido. No se usó otra voz.')
                return bytes(data)
    except httpx.TimeoutException:raise FishVoiceError(504,'Fish tardó demasiado en generar la voz. Intentá de nuevo más tarde.') from None
    except httpx.HTTPError:raise FishVoiceError(502,'No pude conectar con Fish Audio. Revisá la conexión a Internet.') from None
    finally:SYNTHESIS_SLOT.release()
