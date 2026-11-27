"""Provider-independent configuration. Large models can live on another drive."""
import json
import os
import subprocess
import threading
import time
from pathlib import Path

import httpx

ROOT=Path(__file__).resolve().parent
CONFIG_PATH=ROOT/'.jarvis-app.json'
LOCK=threading.RLock()
WARMUP_LOCK=threading.Lock()
DEFAULTS={
    'provider':'openai','conversation_provider':'auto','openai_model':'gpt-5.4-mini','local_model':'qwen3:8b',
    'storage_dir':str(ROOT/'.agent-data'),'projects_dir':'','ollama_url':'http://127.0.0.1:11435',
    'voice':'local','tts_engine':'jarvis_local','tts_url':'http://127.0.0.1:8799',
    'max_turns':20,'task_timeout':1200,'local_context':8192,'realtime_owned_enabled':True,
}

def settings():
    with LOCK:
        return {**DEFAULTS,**(json.loads(CONFIG_PATH.read_text(encoding='utf-8')) if CONFIG_PATH.exists() else {})}

def validate_settings(values):
    current=settings();current.update(values)
    if current['provider'] not in ('openai','claude','local'):raise ValueError('Motor no válido')
    if current['conversation_provider'] not in ('auto','openai','local'):raise ValueError('Motor de conversación no válido')
    if current['voice'] not in ('auto','local','openai','fish','owned'):raise ValueError('Voz no válida')
    return current


def save_settings(values):
    with LOCK:
        current=validate_settings(values)
        CONFIG_PATH.write_text(json.dumps(current,indent=2,ensure_ascii=False),encoding='utf-8')
        return current

def agent_python():
    configured=Path(settings()['storage_dir'])/'.agent-venv/Scripts/python.exe'
    return configured if configured.exists() else ROOT/'.agent-venv/Scripts/python.exe'

def documents_folder():
    if os.name=='nt':
        import ctypes
        buffer=ctypes.create_unicode_buffer(32768)
        # CSIDL_PERSONAL follows the user's Documents folder, including redirection.
        if ctypes.windll.shell32.SHGetFolderPathW(None,5,None,0,buffer)==0 and buffer.value:
            return Path(buffer.value)
    return Path.home()/'Documents'

def projects_folder():
    configured=settings().get('projects_dir')
    if configured:return Path(configured).expanduser()
    legacy=Path(settings()['storage_dir'])/'projects'
    return legacy if legacy.is_dir() else documents_folder()/'Jarvis'

def legacy_projects_layout():
    config=settings()
    return not config.get('projects_dir') and (Path(config['storage_dir'])/'projects').is_dir()

def environment():
    result=os.environ.copy()
    storage=Path(settings()['storage_dir'])
    for directory in ('tmp','cache','models','logs'):(storage/directory).mkdir(parents=True,exist_ok=True)
    result.update(TEMP=str(storage/'tmp'),TMP=str(storage/'tmp'),HF_HOME=str(storage/'cache/huggingface'),
                  MPLCONFIGDIR=str(storage/'cache/matplotlib'),PIP_CACHE_DIR=str(storage/'cache/pip'),
                  OLLAMA_MODELS=str(storage/'models/ollama'),OLLAMA_HOST=settings()['ollama_url'],
                  PYTHONIOENCODING='utf-8',PYTHONUTF8='1')
    result['JARVIS_NUM_CTX']=str(max(4096,min(int(settings()['local_context']),131072)))
    return result

def ensure_ollama():
    config=settings()
    try:
        if httpx.get(config['ollama_url']+'/api/tags',timeout=1).is_success:return True
    except httpx.HTTPError:pass
    binary=Path(config['storage_dir'])/'tools/ollama/ollama.exe'
    if not binary.exists():return False
    storage=Path(config['storage_dir']);(storage/'logs').mkdir(parents=True,exist_ok=True)
    with (storage/'logs/ollama.log').open('ab') as log:
        subprocess.Popen([str(binary),'serve'],env=environment(),stdout=log,stderr=log,
                         creationflags=subprocess.CREATE_NO_WINDOW,cwd=str(binary.parent))
    return True

def warm_local_model():
    """Load the selected installed model in the background before the first question."""
    if not WARMUP_LOCK.acquire(blocking=False):return
    def prepare():
        try:
            config=settings()
            if config['provider']!='local' or not ensure_ollama():return
            with httpx.Client(trust_env=False,timeout=300) as client:
                deadline=time.monotonic()+10
                while True:
                    try:
                        tags=client.get(config['ollama_url']+'/api/tags',timeout=1).json();break
                    except httpx.HTTPError:
                        if time.monotonic()>=deadline:raise
                        time.sleep(.25)
                if config['local_model'] not in [item['name'] for item in tags.get('models',[])]:return
                client.post(config['ollama_url']+'/api/generate',json={
                    'model':config['local_model'],'keep_alive':'15m','stream':False,
                    'options':{'num_ctx':max(4096,min(int(config['local_context']),131072))}}).raise_for_status()
        except (httpx.HTTPError,ValueError,KeyError):
            # A mission reports its own actionable failure; startup stays responsive.
            pass
        finally:WARMUP_LOCK.release()
    threading.Thread(target=prepare,daemon=True).start()

def conversation_provider(config=None):
    config=settings() if config is None else config
    selected=config.get('conversation_provider','auto')
    return ('openai' if config['provider']=='openai' else 'local') if selected=='auto' else selected

def voice_mode():
    config=settings()
    if config['voice']=='owned':return 'owned'
    if config['voice']=='fish':return 'fish'
    # A provider choice never silently adds another paid provider.
    return 'local' if conversation_provider(config)!='openai' or config['voice']=='local' else 'openai'

def status():
    config=settings()
    if config['voice']=='fish':
        import fish_voice
        fish=fish_voice.status()
    else:fish=None
    if config['voice']=='owned':
        import owned_voice
        owned=owned_voice.status()
    else:owned=None
    local_models=[]
    try:
        response=httpx.get(config['ollama_url']+'/api/tags',timeout=1)
        local_models=[model['name'] for model in response.json().get('models',[])] if response.is_success else []
    except (httpx.HTTPError,ValueError):pass
    return {**{key:config[key] for key in ('provider','openai_model','local_model','voice','max_turns')},
            'voice_mode':voice_mode(),'conversation_provider':conversation_provider(config),'openai_configured':bool(os.environ.get('OPENAI_API_KEY')),
            'realtime_owned_enabled':config.get('realtime_owned_enabled',False),
            'openjarvis_installed':agent_python().exists(),'local_models':local_models,
            'local_ready':config['local_model'] in local_models,
            'speech_ready':(Path(config['storage_dir'])/'models/whisper-small/model.bin').exists(),
            'tts_ready':(owned['approved'] if voice_mode()=='owned' else fish['key_configured'] and fish['test_passed'] and fish['free_available'] if voice_mode()=='fish' else (Path(config['storage_dir'])/'models/jarvis-voice-ready.json').exists() if config['tts_engine']=='jarvis_local' else (Path(config['storage_dir'])/'models/vits-piper-es_MX-ald-medium').exists()),
            'fish':fish,
            'owned':owned,
            'tts_engine':config['tts_engine'],
            'storage_dir':config['storage_dir'],'projects_dir':str(projects_folder())}
