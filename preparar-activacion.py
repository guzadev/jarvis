"""Prepare local Spanish wake recognition using the installed Whisper model."""
from pathlib import Path
import json
import subprocess
import app_runtime


def main():
    python=app_runtime.agent_python()
    if not python.is_file():raise RuntimeError('Primero completa la instalacion del companero de Jarvis.')
    folder=Path(app_runtime.settings()['storage_dir'])/'models/whisper-small'
    environment={key:value for key,value in app_runtime.environment().items() if not any(part in key.upper() for part in ('KEY','TOKEN','SECRET','PASSWORD'))}
    if not all((folder/name).is_file() for name in ('model.bin','config.json','tokenizer.json')):
        subprocess.run([str(python),str(app_runtime.ROOT/'preparar-modelos.py'),'--transcription-only'],env=environment,check=True)
    environment.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    subprocess.run([str(python),'-c','from faster_whisper import WhisperModel; import sys; WhisperModel(sys.argv[1],device="cpu",compute_type="int8",local_files_only=True)',str(folder)],env=environment,check=True)
    wake_config=app_runtime.ROOT/'.wake-config.json'
    if not wake_config.exists():wake_config.write_text(json.dumps({'enabled':False,'microphone':'auto'}),encoding='utf-8')
    print('Activacion local en espanol preparada con Whisper Small. Audio procesado en esta PC, sin API.')


if __name__=='__main__':main()
