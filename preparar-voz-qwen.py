"""Install and prepare the optional CUDA Qwen speaker profile using local input."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request

ROOT=Path(__file__).resolve().parent


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def download_weights(storage):
    manifest=json.loads((ROOT/'qwen-voice-weights.json').read_text(encoding='utf-8-sig'))
    folder=storage/'models/qwen3-tts-1.7b-base'
    base=f"https://huggingface.co/{manifest['repository']}/resolve/{manifest['revision']}/"
    for name, expected in manifest['files'].items():
        target=folder/name
        if target.is_file() and digest(target)==expected:continue
        target.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as temp:
            partial=Path(temp.name)
        try:
            print('Descargando',name,flush=True)
            with urllib.request.urlopen(base+name,timeout=120) as response, partial.open('wb') as out:
                while block:=response.read(1024*1024):out.write(block)
            if digest(partial)!=expected:raise ValueError('Falló la verificación de '+name)
            partial.replace(target)
        finally:partial.unlink(missing_ok=True)
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--storage',required=True,type=Path)
    p.add_argument('--reference',required=True,type=Path)
    p.add_argument('--transcript',required=True,type=Path,help='Archivo UTF-8 con la transcripción literal del audio.')
    args=p.parse_args()
    reference=args.reference.resolve();transcript=args.transcript.resolve()
    if not reference.is_file() or not transcript.is_file() or not transcript.read_text(encoding='utf-8-sig').strip():
        p.error('Se requiere audio local y un archivo UTF-8 con su transcripción.')
    storage=args.storage.resolve()
    env={k:v for k,v in os.environ.items() if not any(w in k.upper() for w in ('KEY','TOKEN','SECRET','PASSWORD'))}
    for path in ('tmp','cache/pip','cache/huggingface','tools/qwen-voice-packages'):
        (storage/path).mkdir(parents=True,exist_ok=True)
    env.update(TEMP=str(storage/'tmp'),TMP=str(storage/'tmp'),PIP_CACHE_DIR=str(storage/'cache/pip'),HF_HOME=str(storage/'cache/huggingface'),PYTHONUTF8='1')
    python=storage/'.owned-voice-venv/Scripts/python.exe'
    def run(args):subprocess.run(args,env=env,cwd=ROOT,check=True)
    if not python.exists():run([sys.executable,'-m','venv',str(storage/'.owned-voice-venv')])
    run([str(python),'-m','pip','install','torch==2.6.0','torchaudio==2.6.0','--index-url','https://download.pytorch.org/whl/cu124'])
    run([str(python),'-m','pip','install','-r',str(ROOT/'requirements-owned-voice.txt')])
    run([str(python),'-m','pip','install','--upgrade','--target',str(storage/'tools/qwen-voice-packages'),'--no-deps','-r',str(ROOT/'requirements-qwen.txt')])
    run([str(python),'-m','pip','install','--upgrade','--target',str(storage/'tools/qwen-voice-packages'),'--no-deps','--require-hashes','-r',str(ROOT/'requirements-qwen-fast.txt')])
    download_weights(storage)
    run([str(python),str(ROOT/'qwen_voice_service.py'),'--storage',str(storage),'--reference',str(reference),'--transcript',str(transcript)])
    print('Perfil Qwen preparado. Escuchá la muestra y elegí si querés usarla.')


if __name__=='__main__':main()
