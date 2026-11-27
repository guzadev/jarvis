"""Build the public-only UI and configure a private pairing with this PC."""
import argparse
import json
import secrets
from pathlib import Path
from urllib.parse import urlsplit

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--origin")
args = parser.parse_args()
web = root / "vercel-web"
web.mkdir(exist_ok=True)
(web / "index.html").write_bytes((root / "index.html").read_bytes())
(web / "LICENSE").write_bytes((root / "LICENSE").read_bytes())
(web / "vercel.json").write_text(json.dumps({
    "$schema": "https://openapi.vercel.sh/vercel.json",
    "framework": None,
    "buildCommand": "",
    "installCommand": "",
    "outputDirectory": ".",
    "headers": [{"source": "/(.*)", "headers": [
        {"key": "X-Content-Type-Options", "value": "nosniff"},
        {"key": "Referrer-Policy", "value": "no-referrer"},
        {"key": "Permissions-Policy", "value": "microphone=(self)"},
    ]}],
}, indent=2), encoding="utf-8")
(web / ".vercelignore").write_text(".vercel\n.env*\n*.log\n", encoding="utf-8")
if args.origin:
    parsed = urlsplit(args.origin)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise SystemExit("La web debe ser un origen HTTPS valido, sin rutas ni tokens.")
    config_path = root / ".jarvis-web.json"
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    config.update(origin=f"https://{parsed.netloc}", token=config.get("token") or secrets.token_urlsafe(32))
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print("Web vinculada:", config["origin"], "; credencial local omitida.")
print("Publicacion preparada con HTML, licencia y configuracion Vercel. Sin credenciales ni archivos de trabajo.")
