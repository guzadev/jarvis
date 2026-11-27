"""Local XTTS-v2 synthesis and a persistent Jarvis speaker profile."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import threading

LOCK=threading.Lock()
MODEL=None


def forward_pcm(generator, stop, send):
    # send() may block on a full queue until the client disconnects. Check
    # the cancellation event before advancing the GPU generator again.
    while not stop.is_set():
        try:
            chunk = next(generator)
        except StopIteration:
            return
        if not stop.is_set():
            send(chunk)

def block_external_network():
    original_connect=socket.socket.connect;original_lookup=socket.getaddrinfo
    def local(host):
        if isinstance(host,bytes):host=host.decode('ascii',errors='replace')
        return host in ('127.0.0.1','::1','localhost')
    def connect(connection,address):
        if isinstance(address,tuple) and not local(address[0]):raise OSError('La voz de Jarvis funciona sin conexiones externas.')
        return original_connect(connection,address)
    def lookup(host,*args,**kwargs):
        if not local(host):raise OSError('No se permiten consultas de red externas en la voz local.')
        return original_lookup(host,*args,**kwargs)
    socket.socket.connect=connect;socket.getaddrinfo=lookup

def load_model(storage):
    global MODEL
    if MODEL is not None:return MODEL
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    import torch
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts
    torch.set_num_threads(6)
    checkpoint=storage/'models/xtts-v2'
    config=XttsConfig();config.load_json(str(checkpoint/'config.json'))
    model=Xtts.init_from_config(config)
    model.load_checkpoint(config,checkpoint_dir=str(checkpoint),vocab_path=str(checkpoint/'vocab.json'),eval=True,use_deepspeed=False)
    model.to('cuda' if torch.cuda.is_available() else 'cpu').eval()
    MODEL=model
    return model

def generate(storage,text,profile_path=None):
    import torch
    import soundfile as sf
    model=load_model(storage)
    state=torch.load(profile_path or storage/'models/jarvis-owned/voice.pth',map_location='cpu',weights_only=True)
    with torch.inference_mode():
        result=model.inference(text,'es',state['gpt_cond_latent'].to(model.device),state['speaker_embedding'].to(model.device),
                               temperature=.65,length_penalty=1.0,repetition_penalty=10.0,top_k=50,top_p=.85,
                               speed=.97,enable_text_splitting=True)
    data=io.BytesIO();sf.write(data,result['wav'],24000,format='WAV',subtype='PCM_16')
    return data.getvalue()

def prepare(storage,reference):
    import torch
    import soundfile as sf
    import numpy as np
    target=storage/'models/jarvis-owned';(target/'samples').mkdir(parents=True,exist_ok=True)
    audio,sr=sf.read(reference,dtype='float32');audio=audio.mean(axis=1) if audio.ndim>1 else audio
    if len(audio)/sr<6:raise RuntimeError('La referencia necesita al menos seis segundos de voz clara.')
    if not np.isfinite(audio).all():raise RuntimeError('La referencia contiene muestras de audio no válidas.')
    model=load_model(storage)
    phrase='Buenos días, señor. Soy Jarvis. Estoy listo para ayudarlo. ¿Por dónde comenzamos?'
    source=json.loads((storage/'models/xtts-v2/manifest.json').read_text(encoding='utf-8'))
    # Keep the previous profile intact if model conditioning or synthesis fails.
    with tempfile.TemporaryDirectory(prefix='preparing-',dir=target) as directory:
        stage=Path(directory);reference_wav=stage/'reference.wav';sf.write(reference_wav,audio,sr,subtype='PCM_16')
        latent,embedding=model.get_conditioning_latents(audio_path=[str(reference_wav)],gpt_cond_len=30,gpt_cond_chunk_len=6,max_ref_length=30)
        profile=stage/'voice.pth'
        torch.save({'gpt_cond_latent':latent.cpu(),'speaker_embedding':embedding.cpu()},profile)
        demo=stage/'demo.wav';demo.write_bytes(generate(storage,phrase,profile_path=profile))
        manifest={'engine':'XTTS-v2','prepared':True,'approved':False,'name':'Jarvis · perfil propio local','language':'es',
                  'model_revision':source['revision'],'profile_sha256':hashlib.sha256(profile.read_bytes()).hexdigest(),
                  'sample_sha256':hashlib.sha256(demo.read_bytes()).hexdigest(),
                  'reference_sha256':hashlib.sha256(reference.read_bytes()).hexdigest(),'reference_seconds':round(len(audio)/sr,2),
                  'sample_phrase':phrase,'runtime_requires_reference':False,'runtime_requires_internet':False}
        manifest_path=stage/'profile.json';manifest_path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
        profile.replace(target/'voice.pth');demo.replace(target/'samples/demo.wav');reference_wav.replace(target/'reference.wav')
        manifest_path.replace(target/'profile.json')
    print('OWNED_PROFILE_PREPARED',json.dumps(manifest,ensure_ascii=False),flush=True)

def serve(storage,engine='XTTS-v2',synthesize=generate,is_loaded=lambda:MODEL is not None,streamer=None):
    import hmac
    from fastapi import FastAPI,Request,HTTPException,Response
    from pydantic import BaseModel,Field
    import uvicorn
    api=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    token=os.environ['JARVIS_OWNED_TOKEN']
    class Speech(BaseModel):text:str=Field(min_length=1,max_length=1000)
    @api.get('/health')
    def health():return {'ready':is_loaded(),'engine':engine,'network':'loopback-only','streaming':streamer is not None}
    @api.post('/synthesize')
    def speak(body:Speech,request:Request):
        if not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+token):raise HTTPException(401)
        with LOCK:
            try:data=synthesize(storage,body.text)
            except Exception:raise HTTPException(503,'No pude generar la frase con el perfil local. No se usó otro motor.') from None
        return Response(data,media_type='audio/wav')
    @api.post('/synthesize-stream')
    async def stream(body:Speech, request:Request):
        import asyncio
        import queue
        from fastapi.responses import StreamingResponse
        if not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+token):
            raise HTTPException(401)
        if streamer is None:
            raise HTTPException(409, 'Este perfil no ofrece audio incremental.')
        if not LOCK.acquire(blocking=False):
            raise HTTPException(429, 'La voz local está ocupada.')
        stop = threading.Event()
        blocks = queue.Queue(maxsize=4)
        done = object()
        error = object()

        def send(item):
            while not stop.is_set():
                try:
                    blocks.put(item, timeout=.05)
                    return
                except queue.Full:
                    continue

        def produce():
            generator = None
            try:
                generator = streamer(storage, body.text)
                forward_pcm(generator, stop, send)
                send(done)
            except Exception:
                send(error)
            finally:
                try:
                    if generator is not None:generator.close()
                finally:
                    LOCK.release()

        async def read_block():
            while True:
                try:return blocks.get_nowait()
                except queue.Empty:await asyncio.sleep(.01)

        threading.Thread(target=produce,daemon=True).start()
        try:
            while blocks.empty():
                if await request.is_disconnected():raise HTTPException(499)
                await asyncio.sleep(.02)
            first = await read_block()
            if first is done or first is error:raise HTTPException(503, 'La voz local no produjo audio.')
        except BaseException:
            stop.set()
            raise

        async def content():
            try:
                yield first
                while True:
                    chunk = await read_block()
                    if chunk is done:return
                    if chunk is error:raise RuntimeError('Se interrumpió la síntesis local.')
                    yield chunk
            finally:
                stop.set()

        class AudioResponse(StreamingResponse):
            async def __call__(self, scope, receive, send):
                try:await super().__call__(scope, receive, send)
                finally:stop.set()

        return AudioResponse(content(),media_type='application/octet-stream',
            headers={'X-Audio-Sample-Rate':'24000','X-Audio-Format':'pcm_s16le','Cache-Control':'no-store'})

    uvicorn.run(api,host='127.0.0.1',port=8797,log_level='warning')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');parser.add_argument('--serve',action='store_true')
    parser.add_argument('--storage');parser.add_argument('--reference');args=parser.parse_args()
    storage=Path(args.storage or os.environ['JARVIS_OWNED_STORAGE'])
    block_external_network()
    if args.prepare:prepare(storage,Path(args.reference))
    else:serve(storage)
