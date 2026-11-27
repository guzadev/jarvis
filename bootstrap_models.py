"""Fetch pinned voice and wake weights from their publishers; no API key or audio."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import urllib.request
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parent


def checksum(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def publisher_url(url):
    parsed = urlsplit(url)
    host = parsed.hostname or ''
    if (parsed.scheme != 'https' or parsed.port not in (None, 443) or
        parsed.username is not None or parsed.password is not None or
        not any(host == suffix or host.endswith('.' + suffix) for suffix in ('huggingface.co', 'hf.co'))):
        raise ValueError('El enlace no pertenece al proveedor autorizado del modelo.')
    return url


class PublisherRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        publisher_url(newurl)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def weights():
    qwen = json.loads((ROOT / 'qwen-voice-weights.json').read_text(encoding='utf-8-sig'))
    whisper = json.loads((ROOT / 'whisper-weights.json').read_text(encoding='utf-8'))
    result = []
    for config, folder, label in ((qwen, 'qwen3-tts-1.7b-base', 'Voz de Jarvis'),
                                   (whisper, 'whisper-small', 'Activación por voz')):
        for name, value in config['files'].items():
            pure = PurePosixPath(name)
            if pure.is_absolute() or '..' in pure.parts or ':' in name or '\\' in name:
                raise ValueError('Ruta de modelo no válida.')
            digest = value if isinstance(value, str) else value['sha256']
            size = config['sizes'][name] if isinstance(value, str) else value['bytes']
            result.append(dict(path='models/' + folder + '/' + name, sha256=digest,
                               bytes=size, label=label,
                               url=publisher_url('https://huggingface.co/' + config['repository'] +
                                                 '/resolve/' + config['revision'] + '/' + quote(name, safe='/'))))
    return result


def destination(storage, relative):
    target = storage / relative
    for current in (target, *target.parents):
        if current == storage:
            break
        if current.is_symlink() or current.is_junction():
            raise ValueError('La carpeta de descarga no puede ser un enlace externo.')
    return target


def download(item, target, opener, report):
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = destination(target.parent, target.name + '.partial')
    offset = partial.stat().st_size if partial.is_file() else 0
    if offset > item['bytes']:
        partial.unlink()
        offset = 0
    if offset == item['bytes'] and checksum(partial) == item['sha256']:
        os.replace(partial, target)
        report(item['bytes'])
        return
    if offset == item['bytes']:
        partial.unlink()
        offset = 0
    headers = {'User-Agent': 'Jarvis-Setup/0.1.4'}
    if offset:
        headers['Range'] = f'bytes={offset}-'
    request = urllib.request.Request(item['url'], headers=headers)
    with opener.open(request, timeout=60) as response:
        if offset and response.status != 206:
            offset = 0
        if offset and not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
            raise ValueError('El proveedor no confirmó el punto de reanudación.')
        received = offset
        with partial.open('ab' if offset else 'wb') as output:
            while block := response.read(1024 * 1024):
                received += len(block)
                if received > item['bytes']:
                    raise ValueError('El modelo supera el tamaño esperado.')
                output.write(block)
                report(received)
    if received != item['bytes'] or checksum(partial) != item['sha256']:
        partial.unlink(missing_ok=True)
        raise ValueError('La descarga no coincide con el modelo verificado. Volvé a intentar.')
    os.replace(partial, target)


def prepare(storage, report=print, opener=None):
    storage = storage.resolve()
    storage.mkdir(parents=True, exist_ok=True)
    items = weights()
    identity = hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()
    stamp = storage / '.publisher-models-ready.json'
    try:
        previous = json.loads(stamp.read_text()) if stamp.is_file() else {}
    except (OSError, ValueError):
        previous = {}
    total = sum(item['bytes'] for item in items)
    trusted = previous.get('files', {}) if isinstance(previous,dict) and previous.get('manifest') == identity else {}
    if not isinstance(trusted,dict):
        trusted = {}
    def fingerprint(path):
        stat = path.stat()
        return [stat.st_size, stat.st_mtime_ns]
    verified = {}
    need = 0
    for item in items:
        name = item['path']
        target = destination(storage, name)
        if target.is_file():
            current = fingerprint(target)
            if current[0] == item['bytes'] and (trusted.get(name) == current or checksum(target) == item['sha256']):
                verified[name] = current
                continue
        partial = destination(target.parent, target.name + '.partial')
        retained = partial.stat().st_size if partial.is_file() else 0
        need += max(0, item['bytes'] - retained)
    if len(verified) == len(items) and trusted == verified:
        return
    if len(verified) < len(items) and shutil.disk_usage(storage).free < need + 1024**3:
        raise ValueError('Falta espacio libre para descargar los modelos de voz.')
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), PublisherRedirects())
    completed = 0
    for item in items:
        target = destination(storage, item['path'])
        def progress(received):
            report(json.dumps({'message': item['label'] + ' · ' +
                               f'{(completed + received) / 1e9:.2f} / {total / 1e9:.2f} GB',
                               'completed': completed + received, 'total': total}, ensure_ascii=False))
        if item['path'] in verified:
            progress(item['bytes'])
        else:
            progress(0)
            download(item, target, opener, progress)
            verified[item['path']] = fingerprint(target)
        completed += item['bytes']
    pending = stamp.with_suffix('.pending')
    pending.write_text(json.dumps({'manifest': identity, 'files':verified}), encoding='utf-8')
    os.replace(pending, stamp)
    report(json.dumps({'message': 'Modelos de voz verificados. La voz de Jarvis se conserva.', 'completed': total, 'total': total}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage', required=True, type=Path)
    args = parser.parse_args()
    try:
        prepare(args.storage, report=lambda message: print(message, flush=True))
    except (OSError, ValueError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), flush=True)
        raise SystemExit(1)
