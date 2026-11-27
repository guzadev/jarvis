"""Current-user Windows credential storage for public data providers."""
import ctypes
import json
import os
from pathlib import Path
import tempfile
import threading

import app_runtime

PROVIDERS = {"tomtom": "TOMTOM_API_KEY", "finnhub": "FINNHUB_API_KEY",
             "coingecko": "COINGECKO_API_KEY", "gnews": "GNEWS_API_KEY", "nasa": "NASA_API_KEY"}
_LOCK = threading.Lock()
_STORAGE_ERROR = "Windows no pudo leer o proteger las claves de datos de esta PC."


def _provider(name):
    if not isinstance(name, str) or name not in PROVIDERS:
        raise ValueError("Proveedor de datos desconocido.")
    return PROVIDERS[name]


def _file():
    return Path(app_runtime.settings()["storage_dir"]) / "private" / "data-api-keys.dpapi"


def _crypt(data, decrypt=False):
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    pointer = ctypes.POINTER(Blob)
    buffer = ctypes.create_string_buffer(data)
    src = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    out = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [pointer, ctypes.c_void_p, pointer, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, pointer]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(out)):
        raise RuntimeError(_STORAGE_ERROR)
    try:
        return ctypes.string_at(out.data, out.size)
    finally:
        kernel.LocalFree(ctypes.cast(out.data, ctypes.c_void_p))


def _read(path):
    try:
        with path.open("rb") as file:
            data = file.read(65537)
        if len(data) > 65536:
            raise ValueError()
        keys = json.loads(_crypt(data, decrypt=True))
        if not isinstance(keys, dict) or any(k not in PROVIDERS or not isinstance(v, str) for k, v in keys.items()):
            raise ValueError()
        return keys
    except FileNotFoundError:
        return {}
    except Exception:
        raise RuntimeError(_STORAGE_ERROR) from None


def get_key(provider):
    env = _provider(provider)
    return os.environ.get(env, "").strip() or _read(_file()).get(provider)


def status():
    stored = _read(_file())
    return {p: {"configured": bool(os.environ.get(env, "").strip() or stored.get(p))}
            for p, env in PROVIDERS.items()}


def save_key(provider, key):
    _provider(provider)
    if not isinstance(key, str):
        raise ValueError("Ingresá una clave API válida.")
    key = key.strip()
    if not 4 <= len(key) <= 4096 or any(not 33 <= ord(c) <= 126 for c in key):
        raise ValueError("Ingresá una clave API válida.")
    path = _file()
    try:
        import msvcrt
        path.parent.mkdir(exist_ok=True, parents=True)
        with _LOCK, path.with_suffix(".lock").open("a+b") as lock:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            try:
                keys = _read(path)
                keys[provider] = key
                cipher = _crypt(json.dumps(keys).encode())
                fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".pending")
                try:
                    with os.fdopen(fd, "wb") as file:
                        file.write(cipher)
                        file.flush()
                        os.fsync(file.fileno())
                    os.replace(tmp, path)
                finally:
                    Path(tmp).unlink(missing_ok=True)
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    except Exception:
        raise RuntimeError(_STORAGE_ERROR) from None
    return {"provider": provider, "configured": True}
