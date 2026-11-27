"""Private persistent Chatterbox server; the public app streams its audio."""
import io
import json
import os
import secrets
import subprocess
import sys
import threading
from pathlib import Path

LOCK=threading.RLock()

def ensure_voice_service():
    import app_runtime
    import httpx
    config=app_runtime.settings();storage=Path(config['storage_dir'])
    state=storage/'.voice-service.json'
    with LOCK:
        previous=json.loads(state.read_text()) if state.exists() else {}
        try:
            response=httpx.get(config['tts_url']+'/health',timeout=2)
            if response.is_success and previous.get('token'):return previous['token']
        except httpx.HTTPError:pass
        python=storage/'.voice-venv/Scripts/python.exe'
        if not python.exists():raise RuntimeError('Falta instalar Chatterbox local.')
        token=secrets.token_urlsafe(40)
        env=app_runtime.environment();env['JARVIS_VOICE_TOKEN']=token;env['JARVIS_VOICE_STORAGE']=str(storage)
        (storage/'logs').mkdir(exist_ok=True)
        from urllib.parse import urlsplit
        port=urlsplit(config['tts_url']).port or 8799
        with (storage/'logs/local-voice.log').open('ab') as log:
            process=subprocess.Popen([str(python),str(Path(__file__).resolve()),'--serve',str(port)],env=env,
                                     stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        state.write_text(json.dumps({'pid':process.pid,'token':token}),encoding='utf-8')
        # Server startup does not load the model; first synthesis does.
        import time
        for _ in range(60):
            try:
                if httpx.get(config['tts_url']+'/health',timeout=1).is_success:return token
            except httpx.HTTPError:pass
            if process.poll() is not None:raise RuntimeError('El servicio de voz no pudo iniciar. Revisá local-voice.log.')
            time.sleep(.3)
        raise RuntimeError('La voz todavía está iniciándose.')

def serve(port):
    import hmac
    import torch
    import soundfile as sf
    import uvicorn
    from fastapi import FastAPI,Request,HTTPException,Response
    from pydantic import BaseModel,Field
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    storage=Path(os.environ['JARVIS_VOICE_STORAGE'])
    token=os.environ['JARVIS_VOICE_TOKEN'];model=None
    api=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    class Speech(BaseModel):text:str=Field(min_length=1,max_length=1000)
    @api.get('/health')
    def health():return {'ready':model is not None,'engine':'Chatterbox Multilingual v3'}
    @api.post('/synthesize')
    def synthesize(body:Speech,request:Request):
        nonlocal model
        if not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+token):raise HTTPException(401)
        with LOCK:
            if model is None:
                model=ChatterboxMultilingualTTS.from_pretrained(device='cuda' if torch.cuda.is_available() else 'cpu',t3_model='v3')
            reference=storage/'models/voice-reference/jarvis-latino.mp3'
            if not reference.exists():raise HTTPException(409,'Falta seleccionar una referencia de voz local.')
            with torch.inference_mode():
                audio=model.generate(body.text,language_id='es',audio_prompt_path=str(reference),exaggeration=.35,cfg_weight=.4,temperature=.7)
            data=io.BytesIO();sf.write(data,audio.detach().cpu().numpy().squeeze(),model.sr,format='WAV',subtype='PCM_16')
            (storage/'models/jarvis-voice-ready.json').write_text(json.dumps({'engine':'Chatterbox Multilingual v3','reference':'Jarvis latino · muestra 1','synthesis_passed':True}),encoding='utf-8')
            return Response(data.getvalue(),media_type='audio/wav')
    uvicorn.run(api,host='127.0.0.1',port=port,log_level='warning')

if __name__=='__main__':serve(int(sys.argv[2]))
