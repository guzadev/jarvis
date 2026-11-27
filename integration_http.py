"""One HTTPS request to a public pinned destination. The parent supplies its single key via stdin."""
import http.client
import json
import socket
import ssl
import sys
from urllib.parse import quote, quote_plus, urlencode

from public_reader import destination

MAX_BYTES = 2 * 1024 * 1024


def perform(job):
    url = job["url"]
    parsed, host, port, addresses = destination(url)
    if parsed.scheme != "https" or port != 443 or parsed.fragment or parsed.query:
        raise ValueError()
    family, kind, protocol, _, addr = addresses[0]
    sock = socket.socket(family, kind, protocol)
    conn = http.client.HTTPConnection(host, port, timeout=12)
    try:
        sock.settimeout(12)
        sock.connect(addr)
        conn.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
        headers = dict(job.get("headers", {}))
        query = dict(job.get("query", {}))
        key = job.get("key", "")
        auth = job.get("auth", {})
        if key:
            if auth["type"] == "bearer":
                headers["Authorization"] = "Bearer " + key
            elif auth["in"] == "query":
                query[auth["name"]] = key
            else:
                headers[auth["name"]] = key
        path = parsed.path or "/"
        if query:
            path += "?" + urlencode(query)
        headers.update({"Accept": "application/json", "Accept-Encoding": "identity"})
        body = None
        if "body" in job:
            headers["Content-Type"] = "application/json"
            body = json.dumps(job["body"], ensure_ascii=False, allow_nan=False).encode()
        conn.request(job["method"], path, body=body, headers=headers)
        response = conn.getresponse()
        if not 200 <= response.status < 300:
            message = "El proveedor no confirmó el resultado. La operación puede haberse procesado." if response.status >= 500 else "El proveedor rechazó la solicitud o redirigió la conexión."
            return {"status":"error","http_status":response.status,"summary":message}
        limit = min(MAX_BYTES, job.get("limit", MAX_BYTES))
        if response.headers.get("Content-Encoding","identity").lower() != "identity" or (response.length or 0) > limit:
            raise ValueError()
        raw = response.read(limit + 1)
        if len(raw) > limit:
            raise ValueError()
        value = json.loads(raw) if raw.strip() else None
        if key:
            from base64 import b64encode
            variants = {key, quote(key,safe=""), quote_plus(key), b64encode(key.encode()).decode()}
            def scrub(item):
                if isinstance(item, str):
                    for secret in variants:
                        item = item.replace(secret, "[privado]")
                elif isinstance(item, list):
                    return [scrub(v) for v in item]
                elif isinstance(item, dict):
                    return {scrub(k):scrub(v) for k,v in item.items()}
                elif str(item) in variants:
                    return "[privado]"
                return item
            value = scrub(value)
        return {"status":"ok", "http_status":response.status, "data":value}
    finally:
        conn.close()
        sock.close()


if __name__ == "__main__":
    try:
        incoming = sys.stdin.buffer.read(524289)
        if len(incoming) > 524288:
            raise ValueError()
        result = perform(json.loads(incoming))
        output = json.dumps(result, ensure_ascii=True, allow_nan=False)
    except Exception:
        output = '{"status":"error","summary":"La solicitud no pudo verificarse o el proveedor no devolvió JSON válido. El resultado de la operación es incierto."}'
    sys.stdout.buffer.write(output.encode("utf-8"))

