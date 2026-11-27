"""Prepare a local voice; downloads happen only during this explicit setup."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT=Path(__file__).resolve().parent
REVISION='6c2b0d75eae4b7047358e3b6bd9325f857d43f77'
FILES={
    'config.json':'ef262b1454dd2a77e1461b0b2cd53e19b8a7624cc131b837d36df67356bc75e8',
    'vocab.json':'928260878a59da8a72a2a5b7687fea29d5106137669d90945430fe17e415304a',
    'model.pth':'c7ea20001c6a0a841c77e252d8409f6a74fb423e79b3206a0771ba5989776187',
}

def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage',required=True)
    parser.add_argument('--reference',required=True,type=Path)
    parser.add_argument('--skip-install',action='store_true',help='Reuse an installed voice environment.')
    args=parser.parse_args()
    if not args.reference.is_file():parser.error('No existe la referencia de audio.')
    storage=Path(args.storage).resolve()
    for name in ('tmp','cache/pip','cache/huggingface','models/xtts-v2'):(storage/name).mkdir(parents=True,exist_ok=True)
    env={key:value for key,value in os.environ.items() if not any(word in key.upper() for word in ('KEY','TOKEN','SECRET','PASSWORD'))}
    env.update(TEMP=str(storage/'tmp'),TMP=str(storage/'tmp'),PIP_CACHE_DIR=str(storage/'cache/pip'),
               HF_HOME=str(storage/'cache/huggingface'),PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
    python=storage/'.owned-voice-venv/Scripts/python.exe'
    def run(command):subprocess.run(command,cwd=ROOT,env=env,check=True)
    if not args.skip_install:
        if not python.exists():run([sys.executable,'-m','venv',str(storage/'.owned-voice-venv')])
        run([str(python),'-m','pip','install','torch==2.6.0','torchaudio==2.6.0','--index-url','https://download.pytorch.org/whl/cu124'])
        run([str(python),'-m','pip','install','-r',str(ROOT/'requirements-owned-voice.txt')])
    if not python.exists():raise RuntimeError('Falta el entorno de voz local.')
    folder=storage/'models/xtts-v2'
    for name,expected in FILES.items():
        target=folder/name
        if target.is_file() and digest(target)==expected:continue
        print('Descargando XTTS-v2:',name,flush=True)
        temporary=target.with_suffix('.download')
        url=f'https://huggingface.co/coqui/XTTS-v2/resolve/{REVISION}/{name}'
        with urllib.request.urlopen(url,timeout=120) as response,temporary.open('wb') as stream:
            while chunk:=response.read(1024*1024):stream.write(chunk)
        if digest(temporary)!=expected:
            temporary.unlink()
            raise RuntimeError('El modelo no coincide con su SHA-256: '+name)
        temporary.replace(target)
    manifest=folder/'manifest.json'
    manifest.write_text(json.dumps(dict(repository='coqui/XTTS-v2',revision=REVISION,files=FILES),indent=2),encoding='utf-8')
    run([str(python),str(ROOT/'owned_voice_service.py'),'--prepare','--storage',str(storage),'--reference',str(args.reference.resolve())])
    print('Muestra preparada. Escuchala en Conexion > Perfil local de Jarvis antes de activarla.',flush=True)

if __name__=='__main__':main()
