"""Repackage a verified clean offline payload without copying live user data.

The cache is read-only. Immutable runtimes/models are hard-linked where possible;
every changed file is atomically replaced, never written through a hard link.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import zipfile


def relative(name):
    parts=PurePosixPath(name).parts
    if not parts or name.startswith('/') or '..' in parts or ':' in name or '\\' in name:
        raise ValueError('Unsafe manifest path')
    forbidden={'.env','.jarvis-app.json','.jarvis-web.json','.jarvis-fish.json','.jarvis-desktop.json','.wake-config.json','.jarvis-state.db','.jarvis-openai.dpapi','.git'}
    if any(p.lower() in forbidden or p.lower().endswith(('.dpapi','.sqlite3','.db-wal','.db-shm')) for p in parts):
        raise ValueError('Private file in cache manifest')
    if name.startswith(('data/private/','data/projects/','data/artifacts/','data/logs/','data/desktop-profile/')):
        raise ValueError('User directory in cache manifest')
    return Path(*parts)


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def build(args):
    cache,source,core,out=(p.resolve() for p in (args.cache,args.source,args.electron,args.output))
    if out.exists() or any(out.is_relative_to(p) for p in (cache,source,core)):
        raise ValueError('Choose a new output outside the inputs')
    index=json.loads((cache/'offline-manifest.json').read_text(encoding='utf-8'))['files']
    out.mkdir(parents=True)
    hashes={}
    def replace(name,content=None,src=None):
        dest=out/relative(name);dest.parent.mkdir(parents=True,exist_ok=True)
        stage=dest.with_name(dest.name+'.release-staging')
        if src is not None:shutil.copyfile(src,stage)
        else:stage.write_bytes(content)
        os.replace(stage,dest);hashes[name]=digest(dest)
    for name,checksum in sorted(index.items()):
        if args.publisher_downloads and (name.startswith(('data/models/ollama/','data/tools/ollama/','data/models/qwen3-tts-1.7b-base/','data/models/whisper-small/')) or
                                        (name.startswith('data/.owned-voice-venv/Lib/site-packages/torch/lib/') and name.endswith('.lib'))):continue
        if name.startswith('backend/') and not name.startswith('backend/.venv/'):continue
        if not name.startswith(('backend/.venv/','data/','runtime/')):continue
        src=cache/relative(name)
        if not src.is_file() or src.is_symlink() or src.is_junction():raise ValueError('Non-regular cache input')
        dest=out/relative(name);dest.parent.mkdir(parents=True,exist_ok=True)
        try:os.link(src,dest)
        except OSError:shutil.copyfile(src,dest)
        hashes[name]=checksum
    for file in sorted(core.rglob('*')):
        if file.is_file():
            if file.is_symlink():raise ValueError('Linked core input')
            replace(file.relative_to(core).as_posix(),src=file)
    downloads=out.parent/'companion'
    subprocess.run(['node',str(source/'scripts/package-companion.mjs'),str(downloads)],check=True)
    with zipfile.ZipFile(downloads/'Jarvis-Codigo-Windows.zip') as archive:
        manifest=archive.read('companion-files.json');files=json.loads(manifest)['files']
        for name,checksum in files.items():
            contents=archive.read(name)
            if hashlib.sha256(contents).hexdigest()!=checksum:raise ValueError('Companion checksum mismatch')
            replace('backend/'+name,content=contents)
        replace('backend/companion-files.json',content=manifest)
    for prefix in ('backend/.venv','data/.agent-venv','data/.owned-voice-venv'):
        replace(prefix+'/pyvenv.cfg',content=b'home = __JARVIS_PYTHON_HOME__\ninclude-system-site-packages = false\nversion = 3.13.3\n')
    replace('LEEME-INSTALADOR.txt',src=source/'desktop/LEEME-INSTALADOR.txt')
    replace('README.md',src=source/'README.md')
    for file in sorted((source/'docs').rglob('*')):
        if file.is_file():replace('docs/'+file.relative_to(source/'docs').as_posix(),src=file)
    profile=json.loads((out/'data/models/jarvis-owned/profile.json').read_text())
    if set(profile)!={'approved','prepared','engine','model_revision','profile_sha256','sample_sha256'}:
        raise ValueError('Unexpected voice profile metadata')
    for file,checksum in [('voice.pth',profile['profile_sha256']),('samples/demo.wav',profile['sample_sha256'])]:
        if digest(out/'data/models/jarvis-owned'/file)!=checksum:raise ValueError('Voice profile changed')
    (out/'offline-manifest.json').write_text(json.dumps({'algorithm':'sha256','files':hashes},indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({'files':len(hashes),'bytes':sum((out/relative(name)).stat().st_size for name in hashes),'payload':str(out)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for option in ('cache','source','electron','output'):parser.add_argument('--'+option,type=Path,required=True)
    parser.add_argument('--publisher-downloads',action='store_true',default=True,help='Do not distribute model weights; fetch them from their publishers at setup.')
    build(parser.parse_args())
