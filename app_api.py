"""Shared API used by the desktop window and the hosted interface."""
import json
import hashlib
import io
import logging
import wave
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import FileResponse,StreamingResponse,Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

import agent_store
import app_runtime
import mission_manager
import data_credentials
from data_tools import DATA,DataError

router=APIRouter(prefix='/api')

async def integration_input(request,limit=600000):
    try:
        body=bytearray()
        async for block in request.stream():
            body.extend(block)
            if len(body)>limit:raise ValueError()
        value=json.loads(body)
        if not isinstance(value,dict):raise ValueError()
        return value
    except (ValueError,TypeError):raise HTTPException(400,'La configuración debe ser un objeto JSON dentro del tamaño permitido.') from None

async def integration_action(method,*args):
    try:return await run_in_threadpool(method,*args)
    except ValueError as error:raise HTTPException(400,str(error)) from None
    except Exception:raise HTTPException(503,'No pude completar la solicitud de la integración. No la repitas automáticamente si pudo producir cambios.') from None

@router.get('/integrations')
async def integrations_list(query:str=''):
    from integrations import REGISTRY
    return await integration_action(REGISTRY.list,query)

@router.post('/integrations/preview')
async def integration_preview(request:Request):
    from integrations import REGISTRY
    return await integration_action(REGISTRY.preview,await integration_input(request))

@router.post('/integrations')
async def integration_save(request:Request):
    from integrations import REGISTRY
    body=await integration_input(request)
    return await integration_action(REGISTRY.save,body.get('draft'),body.get('api_key'))

@router.patch('/integrations/{identifier}')
async def integration_update(identifier:str,request:Request):
    from integrations import REGISTRY
    return await integration_action(REGISTRY.update,identifier,await integration_input(request))

@router.delete('/integrations/{identifier}')
async def integration_delete(identifier:str):
    from integrations import REGISTRY
    return await integration_action(REGISTRY.delete,identifier)

@router.post('/integrations/{identifier}/call')
async def integration_call(identifier:str,request:Request):
    from integrations import REGISTRY
    body=await integration_input(request,80000)
    return await integration_action(REGISTRY.call,identifier,body.get('operation_id'),body.get('arguments',{}))

@router.post('/integrations/approvals/{identifier}')
async def integration_decide(identifier:str,request:Request):
    from integrations import REGISTRY
    body=await integration_input(request,2000)
    if type(body.get('approve')) is not bool:raise HTTPException(400,'Falta indicar la decisión.')
    return await integration_action(REGISTRY.decide,identifier,body['approve'])

@router.post('/voice/diagnostics')
async def voice_diagnostics(request:Request):
    import voice_diagnostics as metrics
    try:
        raw=bytearray()
        async for block in request.stream():
            raw.extend(block)
            if len(raw)>8000:raise ValueError()
        value=json.loads(raw)
        if not isinstance(value,dict) or not isinstance(value.get('counts',{}),dict):raise ValueError()
        return metrics.record(value)
    except (ValueError,TypeError):raise HTTPException(400,'Métricas de voz no válidas.') from None

@router.get('/voice/diagnostics')
def read_voice_diagnostics():
    import voice_diagnostics as metrics
    return metrics.snapshots()

DATA_PROVIDERS = {
    'tomtom': dict(label='TomTom · lugares y tránsito', required=True, help_url='https://developer.tomtom.com/'),
    'finnhub': dict(label='Finnhub · acciones', required=True, help_url='https://finnhub.io/'),
    'coingecko': dict(label='CoinGecko · criptomonedas', required=True, help_url='https://www.coingecko.com/en/api'),
    'gnews': dict(label='GNews · respaldo de noticias', required=False, help_url='https://gnews.io/'),
    'nasa': dict(label='NASA · opcional; APOD funciona sin clave', required=False, help_url='https://api.nasa.gov/'),
}

@router.get('/data/providers')
def data_providers():
    try: states=data_credentials.status()
    except RuntimeError:raise HTTPException(503,'Windows no pudo leer las conexiones de datos.') from None
    return {'providers':{name:{**meta,**states[name]} for name,meta in DATA_PROVIDERS.items()}}

@router.post('/data/providers/{provider}')
async def save_data_key(provider:str,request:Request):
    # Parse explicitly: validation responses must never echo a rejected key.
    try:
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>6000:raise ValueError()
        body=json.loads(raw)
        if not isinstance(body,dict):raise ValueError()
        result=data_credentials.save_key(provider,body.get('api_key'))
        DATA.clear_cache()
        return result
    except ValueError:raise HTTPException(400,'Proveedor o clave no válidos.') from None
    except RuntimeError:raise HTTPException(503,'Windows no pudo proteger la clave. No se guardó.') from None

class DataQueryIn(BaseModel):
    name:str=Field(min_length=1,max_length=80)
    arguments:dict=Field(default_factory=dict)

@router.get('/data/astronomy/video')
def astronomy_video(date:str=Query(pattern=r'^\d{4}-\d{2}-\d{2}$')):
    try:
        content,media_type=DATA.astronomy_video(date)
        return Response(content,media_type=media_type,headers={'Cache-Control':'private, max-age=1800','X-Content-Type-Options':'nosniff'})
    except DataError as error:
        raise HTTPException(413 if error.code=='too_large' else 502,str(error)) from None

@router.post('/data/execute')
def execute_data(body:DataQueryIn):
    if len(json.dumps(body.arguments,ensure_ascii=False))>12000:
        raise HTTPException(400,'La consulta es demasiado extensa.')
    if body.name!='read_public_page':
        try:return DATA.execute(body.name,body.arguments)
        except RuntimeError:return {'status':'error','title':'Conexión no disponible','summary':'Windows no pudo leer las conexiones de datos.'}
    url=body.arguments.get('url')
    if not isinstance(url,str) or len(url)>3000:
        raise HTTPException(400,'Indicá una dirección pública válida.')
    env={key:value for key,value in app_runtime.environment().items()
         if not any(word in key.upper() for word in ('KEY','TOKEN','SECRET','PASSWORD'))}
    try:
        process=subprocess.run([str(app_runtime.agent_python()),str(app_runtime.ROOT/'public_reader.py')],
            input=json.dumps({'url':url}),capture_output=True,text=True,encoding='utf-8',errors='replace',
            env=env,cwd=app_runtime.ROOT,creationflags=subprocess.CREATE_NO_WINDOW,timeout=22)
        result=json.loads(process.stdout)
        if not isinstance(result,dict) or result.get('status') not in ('ok','error'):raise ValueError()
        result['kind']='page'
        # The full text is available to reasoning, with an excerpt for the screen.
        return result
    except (subprocess.TimeoutExpired,ValueError,OSError):
        return {'status':'error','title':'Página no disponible','summary':'No pude leer esa página pública dentro del plazo.'}

class MissionIn(BaseModel):
    prompt:str=Field(min_length=1,max_length=100000)
    title:str=Field(default='Misión de Jarvis',max_length=160)
    provider:str|None=None
    project:str=Field(default='aurelio',pattern=r'^[A-Za-z0-9_-]{1,60}$')

def claude_command():
    executable=Path.home()/'.local/bin/claude.exe'
    return shutil.which('claude') or (str(executable) if executable.exists() else None)

@router.get('/agent/status')
def agent_status():
    status=app_runtime.status();provider=status['provider']
    ready=status['openjarvis_installed'] and (status['openai_configured'] if provider=='openai' else status['local_ready'] if provider=='local' else bool(claude_command()))
    model=status['openai_model'] if provider=='openai' else status['local_model'] if provider=='local' else 'Claude Code'
    status.update(ready=ready,model=model,message=(f'{provider.upper()} configurado · {model}' if ready else 'Falta configurar el motor elegido o terminar la descarga del modelo.'))
    return status

class SettingsIn(BaseModel):
    provider:str
    conversation_provider:str|None=None
    openai_model:str=Field(default='gpt-5.4-mini',min_length=1,max_length=120)
    local_model:str=Field(default='qwen3:8b',min_length=1,max_length=120)
    voice:str='local'

@router.post('/agent/settings')
def update_settings(body:SettingsIn):
    try:app_runtime.save_settings(body.model_dump(exclude_none=True,exclude_unset=True))
    except ValueError as error:raise HTTPException(400,str(error)) from error
    if body.provider=='local':app_runtime.warm_local_model()
    return agent_status()

@router.get('/missions')
def missions(project:str|None=None,limit:int=Query(default=100,ge=1,le=200),before:float|None=None):
    try:return {'missions':agent_store.history(project,limit,before) if project else agent_store.recent(limit)}
    except ValueError as error:raise HTTPException(400,str(error)) from error

@router.post('/missions')
def create_mission(body:MissionIn):
    provider=body.provider or app_runtime.settings()['provider']
    if provider not in ('openai','claude','local'):raise HTTPException(400,'Motor no válido.')
    if provider=='openai' and not app_runtime.status()['openai_configured']:raise HTTPException(409,'Configurá una clave de OpenAI o elegí el motor local.')
    if provider=='claude' and not claude_command():raise HTTPException(409,'Falta instalar y conectar Claude Code en esta PC.')
    if provider=='local' and not app_runtime.status()['local_ready']:raise HTTPException(409,'Descargá el modelo local antes de iniciar la misión.')
    try:return mission_manager.create(body.title,body.prompt,provider,body.project,claude_command())
    except ValueError as error:raise HTTPException(400,str(error)) from error

@router.get('/missions/{identifier}')
def get_mission(identifier:str):
    item=agent_store.mission(identifier)
    if not item:raise HTTPException(404,'Misión no encontrada.')
    item['approvals']=agent_store.approvals(identifier)
    return item

@router.post('/missions/{identifier}/cancel')
def cancel_mission(identifier:str):return {'ok':mission_manager.cancel(identifier)}

@router.get('/missions/{identifier}/file/{filename:path}')
def mission_file(identifier:str,filename:str):
    task=get_mission(identifier)
    if not any(item['path']==filename for item in task['artifacts']):raise HTTPException(404,'Este archivo no pertenece a los resultados de la misión.')
    folder=(Path(app_runtime.settings()['storage_dir'])/'artifacts'/identifier).resolve()
    path=(folder/filename).resolve()
    if not path.is_relative_to(folder) or not path.is_file() or path.is_symlink() or any(part.startswith('.') for part in Path(filename).parts):raise HTTPException(404,'Archivo no disponible.')
    return FileResponse(path,filename=path.name)

class ApprovalIn(BaseModel):approve:bool

@router.post('/approvals/{identifier}/decision')
def approval_decision(identifier:str,body:ApprovalIn):
    record=agent_store.approval(identifier)
    if not record:raise HTTPException(404,'Propuesta no encontrada.')
    task=agent_store.mission(record['mission'])
    if not task or task['status']!='awaiting_approval':raise HTTPException(409,'Esta misión ya no espera esa aprobación.')
    from execution_review import snapshot
    if body.approve and snapshot(record['payload']['folder'])!=record['payload']['files']:
        agent_store.approval_transition(identifier,'pending','expired','Cambiaron los archivos.')
        mission_manager.cancel(record['mission'],'Los archivos cambiaron desde la revisión. Prepará una solicitud nueva.')
        raise HTTPException(409,'Los archivos cambiaron desde la propuesta. Jarvis debe preparar una nueva.')
    if not agent_store.approval_transition(identifier,'pending','approved' if body.approve else 'denied'):
        raise HTTPException(409,'Esta propuesta ya fue respondida.')
    if not body.approve:mission_manager.cancel(record['mission'],'Cancelada porque se rechazó la ejecución propuesta.')
    return {'ok':True,'approved':body.approve}

@router.get('/memory')
def memory(query:str=Query(default='',max_length=300)):return {'notes':agent_store.recall(query)}

@router.get('/projects')
def projects():return {'projects':agent_store.projects()}

class ProjectIn(BaseModel):
    id:str=Field(min_length=1,max_length=60)
    name:str=Field(min_length=1,max_length=100)

@router.post('/projects')
def save_project(body:ProjectIn):
    if not body.name.strip():raise HTTPException(400,'Escribí un nombre para el proyecto.')
    try:return agent_store.save_project(body.id,body.name)
    except ValueError as error:raise HTTPException(400,str(error)) from error

class NoteIn(BaseModel):content:str=Field(min_length=1,max_length=10000)

@router.post('/memory')
def add_note(body:NoteIn):
    try:return {'id':agent_store.note_add(body.content),'saved':True}
    except ValueError as error:raise HTTPException(400,str(error)) from None

@router.post('/memory/{identifier}/forget')
def forget_note(identifier:int):
    if not agent_store.note_delete(identifier):raise HTTPException(404,'Ese recuerdo ya no existe.')
    return {'ok':True}

@router.post('/memory/{identifier}/update')
def update_note(identifier:int,body:NoteIn):
    try:changed=agent_store.note_update(identifier,body.content)
    except ValueError as error:raise HTTPException(400,str(error)) from None
    if not changed:raise HTTPException(404,'Ese recuerdo ya no existe.')
    return {'id':identifier,'updated':True}

class WebSearchIn(BaseModel):query:str=Field(min_length=1,max_length=300)

@router.post('/web/search')
def search_web(body:WebSearchIn):
    env={key:value for key,value in app_runtime.environment().items()
         if not any(word in key.upper() for word in ('KEY','TOKEN','SECRET','PASSWORD'))}
    try:
        result=subprocess.run([str(app_runtime.agent_python()),str(app_runtime.ROOT/'web_search_worker.py')],
            input=json.dumps({'query':body.query}),capture_output=True,text=True,encoding='utf-8',errors='replace',
            env=env,cwd=app_runtime.ROOT,creationflags=subprocess.CREATE_NO_WINDOW,timeout=18)
        data=json.loads(result.stdout.strip())
        if result.returncode or not data.get('results'):raise ValueError('No results')
        return data
    except (subprocess.TimeoutExpired,ValueError,OSError):
        raise HTTPException(503,'La búsqueda web no devolvió resultados. Podés reintentar; no se inventó una dirección.') from None

@router.post('/projects/{project}/upload')
async def upload(project:str,request:Request,name:str):
    try:lock=mission_manager.project_mutex(project)
    except ValueError as error:raise HTTPException(400,str(error)) from error
    if not name or Path(name).name!=name or name.startswith('.') or Path(name).is_reserved() or any(ch in name for ch in '<>:"|?*') or name.endswith((' ','.')):
        raise HTTPException(400,'Nombre de archivo no válido.')
    if not lock.acquire(blocking=False):
        raise HTTPException(409,'El proyecto tiene una misión activa. Volvé a cargar el archivo cuando termine.')
    try:
        folder=mission_manager.workspace(project)
        target=folder/name
        if target.exists() or target.is_symlink():raise HTTPException(409,'Ya existe ese archivo.')
        import tempfile
        with tempfile.NamedTemporaryFile(dir=folder,delete=False) as temporary:
            stage=Path(temporary.name)
        try:
            size=0
            with stage.open('wb') as stream:
                async for chunk in request.stream():
                    size+=len(chunk)
                    if size>25_000_000:raise HTTPException(413,'El archivo supera los 25 MB.')
                    stream.write(chunk)
            try:stage.rename(target)  # Windows rename refuses to overwrite.
            except FileExistsError as error:raise HTTPException(409,'Ya existe ese archivo.') from error
        finally:stage.unlink(missing_ok=True)
        return {'name':name,'bytes':size}
    finally:lock.release()

def speech_folder():
    folder=Path(app_runtime.settings()['storage_dir'])/'tmp/speech'
    folder.mkdir(parents=True,exist_ok=True)
    # Only this app's old temporary recordings / synthesized files are removed.
    for path in folder.iterdir():
        if path.is_file() and time.time()-path.stat().st_mtime>86400:path.unlink(missing_ok=True)
    return folder

def speech_job(payload,timeout=180):
    config=app_runtime.settings();payload['storage_dir']=config['storage_dir']
    result=subprocess.run([str(app_runtime.agent_python()),str(app_runtime.ROOT/'speech_worker.py')],input=json.dumps(payload,ensure_ascii=False),
                          text=True,encoding='utf-8',errors='replace',capture_output=True,env=app_runtime.environment(),
                          creationflags=subprocess.CREATE_NO_WINDOW,timeout=timeout)
    if result.returncode:raise HTTPException(503,'No pude procesar el audio local. Verificá que los modelos estén preparados.')
    try:return json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError,IndexError) as error:raise HTTPException(503,'El motor de voz no devolvió un resultado.') from error

# Only one Whisper process may load its model at a time across desktop and web.
import threading
TRANSCRIPTION_SLOT = threading.BoundedSemaphore(1)
MAX_RECORDING_BYTES = 15_000_000

@router.post('/speech/transcribe')
async def transcribe(request:Request):
    import asyncio
    if not TRANSCRIPTION_SLOT.acquire(blocking=False):
        raise HTTPException(429,'Ya hay una transcripción en curso.',headers={'Retry-After':'2'})
    path=None
    worker=None
    try:
        length=request.headers.get('content-length')
        if length and length.isdecimal() and int(length)>MAX_RECORDING_BYTES:
            raise HTTPException(413,'El audio es demasiado grande para esta captura.')
        size=0
        path=speech_folder()/(uuid.uuid4().hex+'.webm')
        with path.open('xb') as stream:
            async for chunk in request.stream():
                size+=len(chunk)
                if size>MAX_RECORDING_BYTES:raise HTTPException(413,'El audio es demasiado grande para esta captura.')
                stream.write(chunk)
        if not size:raise HTTPException(400,'No llegó audio.')
        # The background thread may still be reading the recording after a disconnect.
        # Its completion callback owns the slot and file once processing starts.
        def finished(future):
            try:
                if not future.cancelled():future.exception()
                path.unlink(missing_ok=True)
            finally:
                TRANSCRIPTION_SLOT.release()
        worker=asyncio.create_task(asyncio.to_thread(speech_job,{'operation':'transcribe','path':str(path)}))
        worker.add_done_callback(finished)
        return await asyncio.shield(worker)
    finally:
        if worker is None:
            try:
                if path:path.unlink(missing_ok=True)
            finally:TRANSCRIPTION_SLOT.release()

class SpeakIn(BaseModel):
    model_config={'extra':'forbid'}
    text:str=Field(min_length=1,max_length=1000)

def valid_cached_wav(data):
    try:
        with wave.open(io.BytesIO(data),'rb') as audio:
            frames=audio.getnframes();channels=audio.getnchannels();width=audio.getsampwidth()
            return (frames>0 and 1<=channels<=2 and 1<=width<=4 and 8000<=audio.getframerate()<=192000
                    and audio.getcomptype()=='NONE' and len(audio.readframes(frames))==frames*channels*width)
    except (wave.Error,EOFError,ValueError,RuntimeError):return False

@router.get('/speech/fish/status')
def fish_status():
    import fish_voice
    return fish_voice.status()

@router.post('/speech/fish/key')
async def fish_key(request:Request):
    # Keys are entered only into the local window, never the hosted UI.
    origin=request.headers.get('origin')
    if origin and origin!=str(request.base_url).rstrip('/'):
        raise HTTPException(403,'Guardá la clave desde la ventana local de Jarvis en esta PC.')
    if request.headers.get('content-type','').split(';')[0]!='application/json':raise HTTPException(400,'Enviá la clave desde el formulario local.')
    content=bytearray()
    async for chunk in request.stream():
        if len(content)+len(chunk)>8192:raise HTTPException(413,'La configuración enviada es demasiado grande.')
        content.extend(chunk)
    try:
        body=json.loads(content)
        if not isinstance(body,dict) or set(body)!={'api_key'} or not isinstance(body['api_key'],str):raise ValueError()
    except (ValueError,TypeError):raise HTTPException(400,'La clave debe enviarse desde el formulario local.') from None
    import fish_voice
    try:fish_voice.save_key(body['api_key'])
    except fish_voice.FishVoiceError as error:raise HTTPException(error.status_code,str(error)) from None
    return {'ok':True,'key_configured':True}

@router.post('/speech/fish/test')
def fish_test():
    if app_runtime.voice_mode()!='fish':raise HTTPException(409,'Esta instalación no está usando Fish. La voz seleccionada se respeta también en las pruebas.')
    import fish_voice
    identifier=uuid.uuid4().hex
    try:
        data=fish_voice.synthesize(fish_voice.TEST_PHRASE)
        (speech_folder()/(identifier+'.wav')).write_bytes(data)
        fish_voice.record_test(True)
    except fish_voice.FishVoiceError as error:
        fish_voice.record_test(False)
        raise HTTPException(error.status_code,str(error)) from None
    app_runtime.save_settings({'voice':'fish'})
    return {'audio':identifier,'engine':'fish','model':fish_voice.MODEL,'voice_id':fish_voice.VOICE_ID,'text':fish_voice.TEST_PHRASE}

@router.get('/speech/owned/status')
def owned_status():
    import owned_voice
    return owned_voice.status()

@router.get('/speech/owned/sample')
def owned_sample():
    import owned_voice
    if not owned_voice.status()['sample_ready']:raise HTTPException(409,'La muestra local todavía se está preparando.')
    return FileResponse(owned_voice.folder()/'samples/demo.wav',media_type='audio/wav')

class VoiceApprovalIn(BaseModel):
    approve:bool
    profile_sha256:str|None=None
    sample_sha256:str|None=None

@router.post('/speech/owned/approve')
def owned_approval(body:VoiceApprovalIn):
    import owned_voice
    try:state=owned_voice.approve(body.approve,body.profile_sha256,body.sample_sha256)
    except RuntimeError as error:raise HTTPException(409,str(error)) from None
    if body.approve:app_runtime.save_settings({'voice':'owned'})
    return state

@router.post('/speech/speak')
def speak(body:SpeakIn):
    identifier=uuid.uuid4().hex
    path=speech_folder()/(identifier+'.wav')
    config=app_runtime.settings()
    if app_runtime.voice_mode()=='owned':
        import owned_voice
        try:
            current=owned_voice.status()
            if not current['approved']:raise RuntimeError('La voz elegida no está aprobada.')
            acknowledgement=body.text.strip()=='Sí, señor.'
            cache=None
            if acknowledgement:
                key=hashlib.sha256((current['engine']+current['profile_sha256']+body.text).encode()).hexdigest()
                cache=Path(config['storage_dir'])/'cache/voice-ack'/(key+'.wav')
            if cache and cache.is_file():
                data=cache.read_bytes()
                if not valid_cached_wav(data):data=owned_voice.synthesize(body.text)
            else:data=owned_voice.synthesize(body.text)
            path.write_bytes(data)
            if cache:
                cache.parent.mkdir(parents=True,exist_ok=True)
                temporary=cache.with_suffix('.'+identifier+'.tmp');temporary.write_bytes(data);temporary.replace(cache)
        except (RuntimeError,httpx.HTTPError):raise HTTPException(409,'La voz propia local todavía no está lista o no pudo generar esta frase. No se usó Fish ni otra voz. Podés seguir trabajando por texto.') from None
        return {'audio':identifier,'engine':'owned','model':owned_voice.status()['engine'],'profile':'jarvis-owned'}
    elif app_runtime.voice_mode()=='fish':
        import fish_voice
        try:path.write_bytes(fish_voice.synthesize(body.text))
        except fish_voice.FishVoiceError as error:raise HTTPException(error.status_code,str(error)) from None
        return {'audio':identifier,'engine':'fish','model':fish_voice.MODEL,'voice_id':fish_voice.VOICE_ID}
    elif config['tts_engine']=='jarvis_local':
        from local_voice_service import ensure_voice_service
        try:
            token=ensure_voice_service()
            response=httpx.post(config['tts_url']+'/synthesize',headers={'Authorization':'Bearer '+token},json={'text':body.text},timeout=900)
            response.raise_for_status();path.write_bytes(response.content)
        except (httpx.HTTPError,RuntimeError) as error:raise HTTPException(503,'La voz de Jarvis está preparándose o no pudo generar el audio. Podés seguir usando texto.') from error
    else:speech_job({'operation':'speak','text':body.text,'path':str(path)})
    return {'audio':identifier,'engine':config['tts_engine']}

@router.get('/speech/audio/{identifier}')
def speech_audio(identifier:str):
    if not re.fullmatch(r'[a-f0-9]{32}',identifier):raise HTTPException(404,'Audio no encontrado.')
    path=speech_folder()/(identifier+'.wav')
    if not path.exists():raise HTTPException(404,'Audio no encontrado.')
    return FileResponse(path,media_type='audio/wav')

@router.post('/speech/stream')
async def stream_speech(body:SpeakIn,request:Request):
    import asyncio
    import owned_voice
    if app_runtime.voice_mode()!='owned' or not owned_voice.status()['approved']:
        raise HTTPException(409,'La voz elegida no está disponible. No se usó otra voz.')
    cancelled=threading.Event()
    iterator=iter(owned_voice.synthesize_stream(body.text,cancel_event=cancelled))
    def close():
        try:
            if hasattr(iterator,'close'):iterator.close()
        except ValueError:
            # A pending synchronous read owns the generator until its next yield.
            # output() will close it when that read returns.
            pass
    def failed(status,code,message,retry_after=None):
        close()
        logging.getLogger(__name__).warning('voice_stream_start_failed category=%s',code)
        headers={'X-Jarvis-Voice-Error':code,'Access-Control-Expose-Headers':'X-Jarvis-Voice-Error, Retry-After'}
        if retry_after is not None:headers['Retry-After']=str(retry_after)
        return HTTPException(status,message,headers=headers)
    empty=object()
    first_task=asyncio.create_task(run_in_threadpool(next,iterator,empty))
    def finished(task):
        if not task.cancelled():task.exception()
        close()
    try:
        while not first_task.done():
            if await request.is_disconnected():
                cancelled.set()
                raise HTTPException(499,'La solicitud de voz fue cancelada.')
            await asyncio.wait({first_task},timeout=.02)
        first=await first_task
        if first is empty:raise RuntimeError('empty_audio')
    except owned_voice.VoiceBusyError as error:
        raise failed(429,'voice_busy','La voz de Jarvis sigue terminando la frase anterior. Repetí tu pedido en un momento.',error.retry_after) from None
    except owned_voice.VoiceStreamCancelled:
        close()
        raise HTTPException(499,'La solicitud de voz fue cancelada.') from None
    except httpx.TimeoutException:
        raise failed(503,'voice_timeout','El motor de voz de Jarvis tardó demasiado en generar el audio. Volvé a intentar.') from None
    except httpx.HTTPError:
        raise failed(503,'voice_connection','Se perdió la conexión con el motor local de la voz de Jarvis. Volvé a intentar.') from None
    except (RuntimeError,StopIteration):
        raise failed(503,'voice_generation','El motor local no pudo generar el audio con tu voz de Jarvis. Volvé a intentar.') from None
    except BaseException:
        cancelled.set()
        if not first_task.done():first_task.add_done_callback(finished)
        else:close()
        raise
    def output():
        try:
            yield first
            yield from iterator
        finally:
            close()
    class SpeechStreamResponse(StreamingResponse):
        async def __call__(self,scope,receive,send):
            try:await super().__call__(scope,receive,send)
            finally:
                cancelled.set()
                await run_in_threadpool(close)
    return SpeechStreamResponse(output(),media_type='application/octet-stream',headers={
        'X-Audio-Format':'pcm_s16le','X-Audio-Sample-Rate':'24000','Cache-Control':'no-store',
        'Access-Control-Expose-Headers':'X-Audio-Format, X-Audio-Sample-Rate'})

VOICE_PREPARE_LOCK=threading.Lock()
VOICE_PREPARED_PROFILE=None
VOICE_PREPARATION_STATE={'state':'idle','ready':False,'message':'La voz todavía no se preparó.'}
VOICE_PREPARATION_STATE_LOCK=threading.Lock()

@router.get('/speech/preparation')
def voice_preparation_status():
    with VOICE_PREPARATION_STATE_LOCK:return dict(VOICE_PREPARATION_STATE)

@router.post('/speech/preparation')
def start_voice_preparation():
    with VOICE_PREPARATION_STATE_LOCK:
        if VOICE_PREPARATION_STATE['state']=='preparing':return dict(VOICE_PREPARATION_STATE)
        if VOICE_PREPARED_PROFILE:
            try:
                import owned_voice
                health=httpx.get(owned_voice.URL+'/health',timeout=.7,trust_env=False).json()
                profile=owned_voice.status()
                if health.get('ready') and profile.get('approved') and health.get('engine')==profile.get('engine') and profile.get('profile_sha256')==VOICE_PREPARED_PROFILE:
                    VOICE_PREPARATION_STATE.update(state='ready',ready=True,message='Tu voz de Jarvis está lista.')
                    return dict(VOICE_PREPARATION_STATE)
            except (httpx.HTTPError,ValueError):pass
        VOICE_PREPARATION_STATE.update(state='preparing',ready=False,message='Cargando tu voz de Jarvis en esta PC. El primer inicio puede tardar; la aplicación ya está disponible.')
    def prepare():
        try:
            prepare_live_speech()
        except Exception:
            with VOICE_PREPARATION_STATE_LOCK:
                VOICE_PREPARATION_STATE.update(state='error',ready=False,message='No pude preparar tu voz de Jarvis. Tocá Iniciar voz para reintentarlo.')
    threading.Thread(target=prepare,daemon=True).start()
    return voice_preparation_status()

@router.post('/speech/prepare')
def prepare_live_speech():
    import owned_voice
    global VOICE_PREPARED_PROFILE
    current=owned_voice.status()
    if not current['approved']:raise HTTPException(409,'La voz elegida no está lista.')
    with VOICE_PREPARE_LOCK:
        health=None
        try:health=httpx.get(owned_voice.URL+'/health',timeout=1,trust_env=False).json()
        except (httpx.HTTPError,ValueError):pass
        if VOICE_PREPARED_PROFILE!=current['profile_sha256'] or not health or not health.get('ready'):
            try:
                for block in owned_voice.synthesize_stream('Sí, señor.'):pass
            except (RuntimeError,httpx.HTTPError):raise HTTPException(503,'No pude preparar la voz elegida. Reintentá.') from None
            VOICE_PREPARED_PROFILE=current['profile_sha256']
        with VOICE_PREPARATION_STATE_LOCK:
            VOICE_PREPARATION_STATE.update(state='ready',ready=True,message='Tu voz de Jarvis está lista.')
    return {'ready':True,'profile_sha256':VOICE_PREPARED_PROFILE}
