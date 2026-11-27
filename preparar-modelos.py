"""Prepare the optional offline models explicitly selected by the user."""
import argparse
import json
import tarfile
import time
import urllib.request
from pathlib import Path

import httpx
import app_runtime

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--storage')
    parser.add_argument('--voice-only',action='store_true')
    parser.add_argument('--llm-only',action='store_true')
    parser.add_argument('--transcription-only',action='store_true')
    args=parser.parse_args()
    if args.storage:app_runtime.save_settings({'storage_dir':str(Path(args.storage).resolve())})
    config=app_runtime.settings();storage=Path(config['storage_dir'])
    for folder in ('models','tmp','cache'):(storage/folder).mkdir(parents=True,exist_ok=True)
    if not args.voice_only and not args.transcription_only:
        print('Modelo local de razonamiento: '+config['local_model'],flush=True)
        app_runtime.ensure_ollama()
        for _ in range(60):
            try:
                if httpx.get(config['ollama_url']+'/api/tags',timeout=1).is_success:break
            except httpx.HTTPError:time.sleep(.5)
        last=0
        with httpx.stream('POST',config['ollama_url']+'/api/pull',json={'name':config['local_model'],'stream':True},timeout=None) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:continue
                event=json.loads(line)
                if event.get('error'):raise RuntimeError(event['error'])
                if time.monotonic()-last>3 or event.get('status')=='success':
                    print(event.get('status',''),round(event.get('completed',0)/max(event.get('total',1),1)*100,1),flush=True);last=time.monotonic()
    if not args.llm_only:
        model=storage/'models/vits-piper-es_MX-ald-medium'
        if not args.transcription_only and not model.exists():
            print('Descargando voz latina local: Piper es-MX ald medium (no es la voz de la pelicula).',flush=True)
            archive=storage/'tmp/voz-local.tar.bz2'
            urllib.request.urlretrieve('https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-es_MX-ald-medium.tar.bz2',archive)
            with tarfile.open(archive) as source:source.extractall(storage/'models',filter='data')
        print('Descargando reconocimiento local: Whisper Small multilingue.',flush=True)
        from faster_whisper.utils import download_model
        download_model('small',output_dir=str(storage/'models/whisper-small'))
    print('Modelos solicitados preparados en '+str(storage/'models'),flush=True)

if __name__=='__main__':main()
