"""Exact, one-use execution proposals. Model tools cannot approve proposals."""
import hashlib
import json
import os
import time
import uuid
from pathlib import Path

import agent_store

EXCLUDED={'node_modules','.git','.venv','venv','.jarvis-runs','__pycache__','.next','dist'}

def snapshot(folder):
    folder=Path(folder).resolve();result={}
    for current,dirs,files in os.walk(folder):
        dirs[:]=[name for name in dirs if name not in EXCLUDED and not name.startswith('.') and not (Path(current)/name).is_symlink() and not (Path(current)/name).is_junction()]
        for name in files:
            path=Path(current)/name
            if name.startswith('.') or path.is_symlink():continue
            if path.stat().st_size>50_000_000:continue
            result[path.relative_to(folder).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
            if len(result)>5000:raise ValueError('El proyecto es demasiado grande para esta revisión de ejecución.')
    return result

def propose(job,kind,content,emit):
    folder=Path(job['workspace']).resolve()
    identifier=uuid.uuid4().hex
    payload={'kind':kind,'content':content,'folder':str(folder),'files':snapshot(folder),
             'sha256':hashlib.sha256(content.encode('utf-8')).hexdigest()}
    agent_store.approval_create(identifier,job['id'],job.get('project','aurelio'),payload)
    emit('approval',id=identifier,name=kind,message='Hay una ejecución lista para revisar.')
    announced=False
    while True:
        record=agent_store.approval(identifier)
        state=record['state']
        task=agent_store.mission(job['id'])
        if not task or task['status'] in ('cancelled','interrupted','error'):raise SystemExit('La misión ya no está activa.')
        if state in ('denied','expired'):
            emit('error',message='La ejecución fue rechazada o venció. La misión se detuvo.')
            raise SystemExit('La ejecución no fue autorizada.')
        if state=='approved' and not announced:
            emit('execution_ready',id=identifier);announced=True
        if state=='executing':
            if snapshot(folder)!=payload['files']:
                agent_store.approval_transition(identifier,'executing','expired','Cambiaron los archivos del proyecto.')
                emit('error',message='Los archivos cambiaron desde la revisión. La misión se detuvo; prepará una solicitud nueva.')
                raise SystemExit('Los archivos cambiaron desde la revisión.')
            return identifier,payload
        time.sleep(.3)
