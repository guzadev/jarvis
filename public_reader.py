"""Read public HTML over a DNS-pinned connection, without a browser or credentials."""
from datetime import datetime, timezone
import http.client
import ipaddress
import json
import re
import socket
import ssl
import sys
import time
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

AGENT = "JarvisPublicReader"
MAX_BYTES = 2 * 1024 * 1024
REDIRECTS = {301, 302, 303, 307, 308}


class ReaderError(ValueError):
    pass


def address_allowed(address):
    ip = ipaddress.ip_address(address)
    if not ip.is_global or ip.is_multicast or ip.is_reserved or ip.is_loopback or ip.is_link_local:
        return False
    if ip.version == 6:
        return (ip in ipaddress.ip_network("2000::/3") and ip.sixtofour is None
                and ip.teredo is None and ip.ipv4_mapped is None)
    return True


def destination(url):
    if not isinstance(url, str) or not 1 <= len(url) <= 2000 or any(c.isspace() or ord(c) < 32 or c == "\\" for c in url):
        raise ReaderError("Dirección web no válida.")
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ReaderError("Se requiere una dirección web pública.")
    host = parsed.hostname.encode("idna").decode("ascii").rstrip(".")
    port = parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)
    if port != (443 if parsed.scheme == "https" else 80) or "%" in host or host.endswith((".local", ".localhost", ".internal")) or host == "localhost":
        raise ReaderError("Sólo se permiten sitios web públicos con su puerto habitual.")
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    if not addresses or any(not address_allowed(row[4][0]) for row in addresses):
        raise ReaderError("La dirección no corresponde a un sitio público.")
    return parsed, host, port, addresses


def remaining(deadline):
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise ReaderError("La página tardó demasiado en responder.")
    return min(5, seconds)


def fetch(url, deadline, limit, resolved=None):
    parsed, host, port, addresses = resolved or destination(url)
    context = ssl.create_default_context() if parsed.scheme == "https" else None
    for family, socktype, proto, _, sockaddr in addresses:
        sock = socket.socket(family, socktype, proto)
        try:
            sock.settimeout(remaining(deadline))
            sock.connect(sockaddr)
            if context:
                sock = context.wrap_socket(sock, server_hostname=host)
        except ssl.SSLError:
            sock.close()
            raise
        except OSError:
            sock.close()
            continue
        break
    else:
        raise ReaderError("No pude conectar con la fuente pública.")
    connection = http.client.HTTPConnection(host, port, timeout=5)
    connection.sock = sock
    try:
        sock.settimeout(remaining(deadline))
        path = quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
        query = quote(parsed.query, safe="/%?:@!$&'()*+,;=-._~")
        authority = "[" + host + "]" if ":" in host else host
        connection.request("GET", path + ("?" + query if query else ""), headers={
            "Host": authority, "User-Agent": AGENT+"/1.0", "Accept-Encoding": "identity",
            "Accept": "text/html,application/xhtml+xml,text/plain"})
        response = connection.getresponse()
        if response.status in REDIRECTS or response.status != 200:
            return response.status, response.headers, b""
        if response.headers.get("Content-Encoding", "identity").lower() != "identity":
            raise ReaderError("La fuente devolvió un formato no compatible.")
        if response.length is not None and response.length > limit:
            raise ReaderError("La página supera el tamaño permitido.")
        content = bytearray()
        while len(content) <= limit:
            sock.settimeout(remaining(deadline))
            block = response.read1(min(65536, limit + 1 - len(content)))
            if not block:
                break
            content.extend(block)
        if len(content) > limit:
            raise ReaderError("La página supera el tamaño permitido.")
        return response.status, response.headers, bytes(content)
    finally:
        connection.close()


def robots_allowed(url, cache, deadline):
    parsed = urlsplit(url)
    origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    if origin not in cache:
        status, _, body = fetch(origin+"/robots.txt", deadline, 256 * 1024)
        if status in (404, 410):
            cache[origin] = None
        elif status == 200:
            rule = RobotFileParser()
            rule.parse(body.decode("utf-8-sig", errors="replace").splitlines())
            cache[origin] = rule
        else:
            raise ReaderError("No pude comprobar que la fuente permita esta lectura.")
    if cache[origin] and not cache[origin].can_fetch(AGENT, url):
        raise ReaderError("La fuente restringe la lectura automatizada.")


def clean(text):
    return " ".join(text.split())


def extract(data, headers):
    charset = headers.get_content_charset() or "utf-8"
    text = data.decode(charset, errors="replace")
    content_type = headers.get_content_type()
    if content_type == "text/plain":
        return "", clean(text)
    if content_type not in ("text/html", "application/xhtml+xml"):
        raise ReaderError("El enlace no contiene una página de texto.")
    if re.search(r"<!\s*ENTITY\b|<!DOCTYPE[^>]*(?:\[|SYSTEM\b|PUBLIC\s+['\"]https?://)",text,re.I):
        raise ReaderError("La página contiene declaraciones XML no admitidas.")
    from scrapling import Selector
    doc = Selector(text)
    title = clean(doc.css("title::text").get() or "")
    roots = doc.css("article") or doc.css("main") or doc.css("body")
    if not roots:return title, ""
    root = roots[0]
    blocks = root.css("h1,h2,h3,p,li,blockquote")
    def collect(node):
        nodes=node.xpath(".//text()[not(ancestor::script or ancestor::style or ancestor::nav or ancestor::header or ancestor::footer or ancestor::noscript or ancestor::form or ancestor::aside or ancestor::template or ancestor::svg)]").getall()
        return clean(" ".join(nodes))
    paragraphs = list(dict.fromkeys(line for node in blocks if (line:=collect(node))))
    return title, "\n".join(paragraphs) or collect(root)


def read_url(url):
    deadline = time.monotonic() + 16
    robots = {}
    for redirect in range(4):
        # Validate before inspecting robots so credentials from the input are never sent.
        resolved = destination(url)
        parsed = resolved[0]
        robots_allowed(url, robots, deadline)
        status, headers, data = fetch(url, deadline, MAX_BYTES, resolved)
        if status in REDIRECTS:
            loc = headers.get("Location")
            if not loc or redirect == 3:raise ReaderError("La fuente redirigió demasiadas veces.")
            url = urljoin(url, loc)
            continue
        if status != 200:raise ReaderError("La fuente no permitió obtener la página.")
        title, text = extract(data, headers)
        if not text:raise ReaderError("No encontré texto legible en la página pública.")
        return {"status":"ok","source":urlunsplit((parsed.scheme,parsed.netloc,parsed.path,"","")),
                "title":title[:300],"summary":text[:650],"content":text[:16000],"truncated":len(text)>16000}


def main():
    try:
        raw = sys.stdin.buffer.readline(16385)
        if len(raw)>16384:raise ReaderError("Solicitud demasiado grande.")
        result = read_url(json.loads(raw)["url"])
    except ReaderError as exc:
        result = {"status":"error","error":str(exc)}
    except Exception:
        result = {"status":"error","error":"No pude leer la página pública."}
    if result["status"]=="error":
        result.update(title="",summary="",source="",content="",truncated=False)
    result["fetched_at"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(result,ensure_ascii=True),flush=True)
    return 0 if result["status"]=="ok" else 1


if __name__=="__main__":
    sys.exit(main())
