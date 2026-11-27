"""Install an optional local reasoning model directly from its providers."""
import hashlib
import ipaddress
import json
from pathlib import Path, PureWindowsPath
import shutil
import socket
import stat
import tempfile
import threading
import time
from urllib.parse import urljoin, urlsplit
import zipfile

import httpx

import app_runtime
import agent_store


_RUNTIME_URL = "https://github.com/ollama/ollama/releases/download/v0.40.16/ollama-windows-amd64.zip"
_RUNTIME_SHA = "50fcf5ad54277f2fa5d173ebfc93bcb017adbc0c9ef2314daabc96ca9e6aa64e"
_HOSTS = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com", "github-releases.githubusercontent.com"}
_MODELS = {
    "qwen3:1.7b": (1_400_000_000, "El modelo más pequeño del catálogo para tareas breves."),
    "qwen3:4b": (2_500_000_000, "Tamaño intermedio para consultas y tareas cotidianas."),
    "qwen3:8b": (5_200_000_000, "Mayor capacidad para tareas con varios pasos."),
    "qwen3:14b": (9_300_000_000, "El modelo más grande del catálogo para tareas complejas."),
}
_LOCK = threading.RLock()
_worker = None
_stop = None
_pending_activation = None
_sockets = set()
_status = dict(state="idle", model=None, message="", completed=0, total=0, percent=0)


def catalog():
    return [dict(id=model, name="Qwen3 "+model.split(":")[1].upper(), download_bytes=size,
                 description=description, memory_note="La RAM o VRAM necesaria supera el tamaño de descarga y varía según el contexto y el equipo.",
                 source_url="https://ollama.com/library/"+model) for model,(size,description) in _MODELS.items()]


def state():
    with _LOCK:
        return _status.copy()


class _Cancelled(Exception):
    pass


def _check(stop):
    if stop.is_set():
        raise _Cancelled()


def _progress(stop, phase, message, completed=0, total=0):
    with _LOCK:
        _check(stop)
        _status.update(state=phase, message=message, completed=completed, total=total,
                       percent=min(100, int(100*completed/total)) if total else 0)


def _loopback(raw):
    parsed=urlsplit(raw)
    if parsed.scheme!="http" or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment or parsed.path not in ("","/"):
        raise ValueError("La dirección de Ollama debe ser local.")
    if parsed.hostname!="localhost" and not ipaddress.ip_address(parsed.hostname or "").is_loopback:
        raise ValueError("La dirección de Ollama debe ser local.")
    return raw.rstrip("/")


def _download(client, archive, stop):
    url=_RUNTIME_URL
    for _ in range(6):
        _check(stop)
        parsed=urlsplit(url)
        if parsed.scheme!="https" or parsed.hostname not in _HOSTS or parsed.port not in (443,None) or parsed.username is not None or parsed.password is not None:
            raise ValueError("Destino de descarga de Ollama no autorizado.")
        client.cookies.clear()
        with client.stream("GET",url) as response:
            if response.is_redirect:
                if not response.headers.get("location"):break
                url=urljoin(url,response.headers["location"])
                continue
            response.raise_for_status()
            expected=int(response.headers.get("Content-Length",0))
            hasher=hashlib.sha256()
            count=0
            with archive.open("xb") as output:
                for block in response.iter_bytes(1024*1024):
                    _check(stop)
                    count+=len(block)
                    if count>6*1024**3:raise ValueError("El archivo de Ollama supera el tamaño admitido.")
                    output.write(block)
                    hasher.update(block)
                    _progress(stop,"downloading","Descargando el motor oficial de Ollama.",count,expected)
            if hasher.hexdigest()!=_RUNTIME_SHA:
                raise ValueError("El motor descargado no coincide con la huella oficial esperada.")
            client.cookies.clear()
            return
    raise ValueError("No se pudo resolver el enlace oficial de Ollama.")


def _extract(archive, folder, stop):
    with zipfile.ZipFile(archive) as package:
        members=package.infolist()
        if sum(m.file_size for m in members)>12*1024**3:
            raise ValueError("Archivo de instalación de Ollama no válido.")
        for member in members:
            _check(stop)
            part=PureWindowsPath(member.filename)
            if (part.anchor or not part.parts or ".." in part.parts or
                any(":" in p or p.endswith((" ",".")) or PureWindowsPath(p).is_reserved() for p in part.parts) or
                stat.S_ISLNK(member.external_attr>>16)):
                raise ValueError("Ruta inesperada dentro del archivo de Ollama.")
            target=folder.joinpath(*part.parts)
            if member.is_dir():
                target.mkdir(parents=True,exist_ok=True)
                continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with package.open(member) as source, target.open("xb") as dest:
                while block:=source.read(1024*1024):
                    _check(stop)
                    dest.write(block)


def _install(client,storage,stop):
    runtime=storage/"tools/ollama"
    if (runtime/"ollama.exe").is_file():return
    if runtime.exists():
        raise ValueError("Ya existe una carpeta de Ollama incompleta. Se conservó su contenido.")
    runtime.parent.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(runtime.parent).free < 15*1024**3:
        raise ValueError("Falta espacio para descargar y descomprimir Ollama. Liberá 15 GiB en la unidad de Jarvis.")
    with tempfile.TemporaryDirectory(dir=runtime.parent,prefix=".ollama-") as tmp:
        stage=Path(tmp)
        _download(client,stage/"runtime.zip",stop)
        _progress(stop,"installing","Instalando el motor local verificado.")
        folder=stage/"runtime"
        folder.mkdir()
        _extract(stage/"runtime.zip",folder,stop)
        if not (folder/"ollama.exe").is_file():
            raise ValueError("Falta el ejecutable en el archivo de Ollama.")
        with _LOCK:
            _check(stop)
            if runtime.exists():
                if (runtime/"ollama.exe").is_file():return
                raise ValueError("La carpeta de Ollama cambió durante la instalación.")
            folder.rename(runtime)


def _tags(client,base):
    res=client.get(base+"/api/tags",timeout=2)
    res.raise_for_status()
    return {entry["name"] for entry in res.json()["models"]}


def _pull(client,base,model,stop):
    layers={}
    _progress(stop,"pulling","Descargando el modelo desde el registro oficial de Ollama.")
    with client.stream("POST",base+"/api/pull",json={"model":model,"stream":True}) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            _check(stop)
            if not line:continue
            event=json.loads(line)
            if event.get("error"):raise ValueError("Ollama informó un error al descargar el modelo.")
            digest=event.get("digest")
            if digest and isinstance(event.get("total"),int):
                size=max(0,event["total"])
                amount=min(size,max(0,event.get("completed",0)))
                layers[digest]=(amount,size)
                _progress(stop,"pulling","Descargando y verificando las capas del modelo.",
                          sum(x for x,_ in layers.values()),sum(y for _,y in layers.values()))
            if event.get("status")=="success":return
    raise ValueError("Ollama no confirmó que terminó la descarga.")


def _provision(model,stop):
    config=app_runtime.settings()
    base=_loopback(config["ollama_url"])
    def trace(event,info):
        if event in ("connection.connect_tcp.complete","connection.start_tls.complete"):
            sock=info["return_value"].get_extra_info("socket")
            if sock is not None:
                with _LOCK:
                    _check(stop)
                    _sockets.add(sock)
    def mark(request):
        request.extensions["trace"]=trace
    with httpx.Client(trust_env=False,follow_redirects=False,timeout=httpx.Timeout(30,connect=6),
                      event_hooks={"request":[mark]}) as client:
        try:present=_tags(client,base)
        except httpx.TransportError:
            _install(client,Path(config["storage_dir"]),stop)
            _check(stop)
            if not app_runtime.ensure_ollama():raise ValueError("No pude iniciar el motor local.")
            deadline=time.monotonic()+20
            while True:
                _check(stop)
                try:
                    present=_tags(client,base)
                    break
                except httpx.TransportError:
                    if time.monotonic()>=deadline:raise ValueError("Ollama no respondió en esta PC.") from None
                    stop.wait(.25)
        if model not in present:
            storage=Path(config["storage_dir"])
            required=_MODELS[model][0]+1024**3
            if shutil.disk_usage(storage).free < required:
                raise ValueError("Falta espacio para el modelo elegido y los archivos temporales de Ollama.")
            _pull(client,base,model,stop)
            _check(stop)
            if model not in _tags(client,base):
                raise ValueError("El modelo no figura entre los instalados en Ollama.")


def _run(model,stop):
    global _worker, _pending_activation
    try:
        _provision(model,stop)
        with _LOCK:
            _check(stop)
            activation=_pending_activation
            if activation is not None:app_runtime.save_settings(_activation(activation))
            _status.update(state="ready",message="El modelo está listo en esta PC.",percent=100)
        if activation is not None:app_runtime.warm_local_model()
    except _Cancelled:
        pass
    except Exception as error:
        with _LOCK:
            if not stop.is_set():
                # Provider errors can contain signed URLs or local path details.
                _status.update(state="error",message=str(error) if type(error) is ValueError and str(error).startswith(("El motor descargado","Ya existe una carpeta","El modelo no figura","Falta el ejecutable","Falta espacio","Ollama no respondió","No pude iniciar","Ollama informó","La carpeta de Ollama")) else "No pude preparar el modelo local. Verificá la conexión y el espacio disponible.")
    finally:
        with _LOCK:
            _sockets.clear()
            _pending_activation=None
            _worker=None


def prepare(model,activate_settings=None):
    global _worker,_stop,_pending_activation
    if model not in _MODELS:raise ValueError("Modelo fuera del catálogo local.")
    activation=None if activate_settings is None else dict(activate_settings)
    if activation is not None:
        if activation.get("provider","local")!="local" or activation.get("local_model",model)!=model:
            raise ValueError("La configuración no coincide con el modelo elegido.")
        activation.update(provider="local",local_model=model)
    with _LOCK:
        if _worker is not None:
            if _status["model"]==model and not _stop.is_set() and _status["state"] not in ("ready","error"):
                if activation is not None:_pending_activation=activation
                return state()
            raise ValueError("Hay otra preparación de modelo local en curso.")
        _stop=threading.Event()
        _pending_activation=activation
        _status.update(state="installing",model=model,message="Comprobando el modelo en esta PC.",completed=0,total=0,percent=0)
        _worker=threading.Thread(target=_run,args=(model,_stop),name="jarvis-local-model-install",daemon=True)
        _worker.start()
        return state()


def cancel():
    with _LOCK:
        if _worker is not None and _status["state"] not in ("ready","error"):
            _stop.set()
            for sock in _sockets:
                try:sock.shutdown(socket.SHUT_RDWR)
                except OSError:pass
            _status.update(state="cancelled",message="Se canceló la preparación del modelo.")
        return state()


def _installed_rows(client,base):
    reply=client.get(base+"/api/tags",timeout=2)
    reply.raise_for_status()
    return [dict(name=item["name"],bytes=item.get("size",0),digest=item.get("digest",""))
            for item in reply.json()["models"] if isinstance(item.get("name"),str)]


def installed():
    config=app_runtime.settings()
    base=_loopback(config["ollama_url"])
    with httpx.Client(trust_env=False,follow_redirects=False,timeout=3) as client:
        try:rows=_installed_rows(client,base)
        except httpx.TransportError:
            if not (Path(config["storage_dir"])/"tools/ollama/ollama.exe").is_file():
                return {"installed":[],"available":catalog(),"online":False}
            # Discover already installed models even if the daemon was stopped.
            if not app_runtime.ensure_ollama():
                return {"installed":[],"available":catalog(),"online":False}
            for _ in range(8):
                try:
                    rows=_installed_rows(client,base)
                    break
                except httpx.TransportError:time.sleep(.25)
            else:return {"installed":[],"available":catalog(),"online":False}
    return {"installed":rows,"available":catalog(),"online":True}


def _activation(settings):
    values=dict(settings)
    config=app_runtime.settings()
    if "conversation_provider" not in values and config.get("conversation_provider","auto")=="auto":
        values["conversation_provider"]=app_runtime.conversation_provider(config)
    return values


def _require_installed(model):
    if not isinstance(model,str) or not model or len(model)>200:
        raise ValueError("Nombre de modelo no válido.")
    inventory=installed()
    if not inventory["online"] or model not in {row["name"] for row in inventory["installed"]}:
        raise ValueError("El modelo no figura entre los instalados en Ollama.")


def select(model):
    with _LOCK:
        if _worker is not None:raise ValueError("Hay una preparación de modelo local en curso.")
        _require_installed(model)
        app_runtime.save_settings(_activation({"provider":"local","local_model":model}))
        app_runtime.warm_local_model()
    return {"status":"ok","model":model}


def remove(model):
    with _LOCK:
        if _worker is not None:raise ValueError("Hay una preparación de modelo local en curso.")
        config=app_runtime.settings()
        if config["provider"]=="local" and config["local_model"]==model:
            raise ValueError("Elegí otro modelo antes de quitar el que está activo.")
        _require_installed(model)
        base=_loopback(config["ollama_url"])
        with agent_store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            busy=db.execute("""SELECT 1 FROM missions WHERE provider='local' AND model=?
                AND status IN ('queued','running','awaiting_approval') LIMIT 1""",(model,)).fetchone()
            if busy:raise ValueError("Una misión pendiente o en ejecución usa este modelo. Esperá a que termine.")
            with httpx.Client(trust_env=False,follow_redirects=False,timeout=15) as client:
                response=client.request("DELETE",base+"/api/delete",json={"model":model})
                response.raise_for_status()
    return {"status":"ok","model":model}

