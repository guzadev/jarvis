$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
Set-Location -LiteralPath $PSScriptRoot
$python=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {throw 'Primero ejecuta INSTALAR_JARVIS.cmd.'}
if (Get-NetTCPConnection -LocalPort 8788 -State Listen -ErrorAction SilentlyContinue) {throw 'Detene el companero con DETENER_JARVIS.cmd antes de actualizar.'}
@'
import hashlib,json,os,shutil,tempfile,urllib.request,zipfile
from pathlib import Path
root=Path.cwd()
base='https://github.com/guzadev/jarvis/releases/latest/download/'
def digest(data):return hashlib.sha256(data).hexdigest()
with urllib.request.urlopen(base+'version.json',timeout=30) as response:release=json.load(response)
old=json.loads((root/'companion-files.json').read_text(encoding='utf8'))
if old['version']==release['version']:
    print('Ya tenes la version actual.');raise SystemExit(0)
with tempfile.TemporaryDirectory(dir=root,prefix='.update-') as folder:
    stage=Path(folder);archive=stage/'release.zip'
    with urllib.request.urlopen(base+'Jarvis-Codigo-Windows.zip',timeout=120) as response, archive.open('wb') as out:
        shutil.copyfileobj(response,out)
    if digest(archive.read_bytes())!=release['sha256']:raise ValueError('La descarga no coincide con el SHA-256 publicado.')
    with zipfile.ZipFile(archive) as z:
        manifest=z.read('companion-files.json')
        new=json.loads(manifest);allowed=set(old['files']);names=list(z.namelist())
        if new['version']!=release['version'] or set(new['files'])!=allowed:raise ValueError('Cambio el formato del instalador. Extrae el nuevo ZIP en otra carpeta.')
        if len(names)!=len(set(names)) or set(names)!=allowed|{'companion-files.json'}:raise ValueError('Contenido de ZIP inesperado.')
        for name in names:
            relative=Path(name)
            if relative.is_absolute() or any(p.startswith('.') for p in relative.parts) or ':' in name:raise ValueError('Ruta no valida.')
            target=root/relative
            if not target.resolve().is_relative_to(root) or target.is_symlink():raise ValueError('Destino no valido.')
            contents=z.read(name)
            if name in allowed and digest(contents)!=new['files'][name]:raise ValueError('Archivo corrupto: '+name)
            dest=stage/'ready'/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(contents)
    applied=[]
    try:
        for name in sorted(allowed)+['companion-files.json']:
            target=root/name;backup=stage/'backup'/name
            if target.exists():
                backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,backup)
            target.parent.mkdir(parents=True,exist_ok=True);os.replace(stage/'ready'/name,target);applied.append(name)
    except BaseException:
        for name in reversed(applied):
            backup=stage/'backup'/name
            if backup.exists():os.replace(backup,root/name)
            else:(root/name).unlink(missing_ok=True)
        raise
    print('Companero actualizado:',new['version'])
    if any(new['files'][n]!=old['files'][n] for n in ('requirements.txt','requirements-agent.txt')):
        print('Las dependencias cambiaron. Ejecuta INSTALAR_JARVIS.cmd para actualizarlas.')
'@ | & $python -
if ($LASTEXITCODE -ne 0) {throw 'No se completo la actualizacion.'}
