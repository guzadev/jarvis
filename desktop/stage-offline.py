"""Assemble an offline, relocatable Windows desktop distribution from installed assets."""
import argparse
import csv
import hashlib
import io
import json
import os
import re
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
import zipfile

PROFILE_SHA = "0a556d46be172f6cc06a61638b8a6a340f4667bec7337234647a496e390e01ed"
SAMPLE_SHA = "9ced57817f9cdadbd15597123f6fce3925cdb3ce74dc16138472e85de799f624"
SKIP = {"__pycache__", ".git", ".cache", ".pytest_cache", "tests", "test", "direct_url.json", "record", "origin.json"}
PRIVATE = {".env", ".npmrc", ".pypirc", "credentials.json", ".jarvis-app.json", ".jarvis-web.json"}
WHISPER = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")


def safe_relative(name):
    path = PurePosixPath(name)
    if not path.parts or path.is_absolute() or ".." in path.parts or ":" in name or "\\" in name:
        raise ValueError("Unexpected path in the distribution manifest.")
    return Path(*path.parts)


def regular(path):
    if path.is_symlink() or path.is_junction() or not path.is_file():
        raise ValueError(f"Not a regular input file: {path.name}")
    return path


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def skip(name):
    return name.casefold() in SKIP | PRIVATE or name.casefold().startswith((".env.", "__editable__")) or name.lower().endswith((".pyc", ".pyo", ".egg-link", ".pdb"))


class Stage:
    def __init__(self, directory):
        self.directory = directory
        self.hashes = {}
        self.packages = {}

    def copy(self, src, name, expected=None):
        dest = self.directory / safe_relative(name)
        if name in self.hashes:
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(regular(src), dest)
        digest = sha(dest)
        if expected and digest != expected:
            raise ValueError(f"Checksum mismatch: {name}")
        self.hashes[name] = digest

    def write(self, name, data):
        dest = self.directory / safe_relative(name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        self.hashes[name] = hashlib.sha256(data).hexdigest()

    def tree(self, source, prefix, exclude=()):
        if source.is_symlink() or source.is_junction() or not source.is_dir():
            raise ValueError(f"Unexpected source directory: {source.name}")
        for base, dirs, files in os.walk(source):
            parent = Path(base)
            dirs[:] = [d for d in dirs if not skip(d) and d not in exclude and not (parent/d).is_symlink() and not (parent/d).is_junction()]
            for file in files:
                if not skip(file) and file not in exclude:
                    path = parent / file
                    self.copy(path, (prefix + "/" if prefix else "") + path.relative_to(source).as_posix())

    def site(self, site, prefix):
        # Only installed distribution records. Stray downloads, user files and executables
        # emitted in Scripts/ by pip are not inputs to the desktop bundle.
        if site.resolve() != site.absolute():raise ValueError("Linked site-packages root")
        verified_dirs = {site}
        def verify_parents(directory):
            if directory not in verified_dirs:
                verify_parents(directory.parent)
                if directory.is_symlink() or directory.is_junction():raise ValueError("Linked package directory")
                verified_dirs.add(directory)
        packages = []
        for dist in sorted(site.glob("*.dist-info")):
            if dist.is_symlink() or dist.is_junction():
                raise ValueError("Linked package metadata")
            record = dist / "RECORD"
            metadata = (dist / "METADATA").read_text(encoding="utf-8")
            fields = metadata.split("\n\n", 1)[0].splitlines()
            name = next(line[6:] for line in fields if line.startswith("Name: "))
            version = next(line[9:] for line in fields if line.startswith("Version: "))
            packages.append({"name": name, "version": version})
            clean_record = io.StringIO(newline="")
            writer = csv.writer(clean_record)
            with regular(record).open(encoding="utf-8", newline="") as input_file:
                for row in csv.reader(input_file):
                    relative = PurePosixPath(row[0].replace("\\", "/"))
                    if ".." in relative.parts or relative.is_absolute() or relative.parts[0] == "bin":
                        continue
                    if any(skip(part) for part in relative.parts):continue
                    if relative.suffix.lower() == ".pth":
                        if len(relative.parts) == 1:continue
                        # Model weights are separately included from the model manifest.
                        continue
                    rel = relative.as_posix()
                    if rel.startswith('torch/lib/') and rel.endswith('.lib'):
                        continue  # Static C++ development libraries are not used by voice inference.
                    path = site / safe_relative(rel)
                    verify_parents(path.parent)
                    self.copy(path, prefix + "/" + rel)
                    writer.writerow([rel, "", ""])
            own_record = dist.name + "/RECORD"
            writer.writerow([own_record, "", ""])
            self.write(prefix + "/" + own_record, clean_record.getvalue().encode("utf-8"))
        if not packages:raise ValueError("Environment has no installed distributions")
        self.packages[prefix] = packages

    def venv(self, src, dest):
        cfg=(src/"pyvenv.cfg").read_text(encoding="utf-8")
        if "version = 3.13.3" not in cfg:raise ValueError("Expected Python 3.13.3 environments")
        for exe in ("python.exe", "pythonw.exe"):
            self.copy(src/"Scripts"/exe, dest+"/Scripts/"+exe)
        self.write(dest+"/pyvenv.cfg",b"home = __JARVIS_PYTHON_HOME__\ninclude-system-site-packages = false\nversion = 3.13.3\n")
        self.site(src/"Lib/site-packages", dest+"/Lib/site-packages")


def stage_ollama(st, storage):
    runtime = storage / "tools/ollama"
    st.copy(runtime/"ollama.exe", "data/tools/ollama/ollama.exe")
    st.tree(runtime/"lib", "data/tools/ollama/lib")
    base = storage / "models/ollama"
    tag = "manifests/registry.ollama.ai/library/qwen3/8b"
    tags = [tag]
    tag_v2 = "manifests-v2/ollama.com/library/qwen3/8b"
    if (base/tag_v2).is_file():tags.append(tag_v2)
    seen = set()
    def contents(manifest):
        if manifest.get("schemaVersion") != 2:raise ValueError("Unsupported Ollama manifest")
        for layer in [manifest["config"], *manifest["layers"]]:
            digest = layer["digest"]
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):raise ValueError("Invalid Ollama layer")
            relative = "blobs/" + digest.replace(":", "-")
            source = regular(base/relative)
            if source.stat().st_size != layer["size"]:raise ValueError("Incorrect Ollama layer size")
            if digest in seen:continue
            seen.add(digest)
            st.copy(source, "data/models/ollama/"+relative, digest[7:])
            if layer["mediaType"] == "application/vnd.docker.distribution.manifest.v2+json":
                contents(json.loads(source.read_bytes()))
    for name in tags:
        st.copy(base/name, "data/models/ollama/"+name)
        contents(json.loads((base/name).read_bytes()))


def visual_cpp_runtime():
    # PE normal+delay imports in the four packaged environments. Keep the set
    # narrow, and authenticate each redistributable before bundling it app-local.
    names = ("msvcp140.dll", "msvcp140_1.dll", "vcomp140.dll", "vcruntime140.dll", "vcruntime140_1.dll")
    system = Path(os.environ["SystemRoot"]) / "System32"
    powershell = system / "WindowsPowerShell/v1.0/powershell.exe"
    script = """
$ErrorActionPreference='Stop'
foreach ($name in @('msvcp140.dll','msvcp140_1.dll','vcomp140.dll','vcruntime140.dll','vcruntime140_1.dll')) {
  $path=Join-Path ([Environment]::SystemDirectory) $name
  $sig=Get-AuthenticodeSignature -LiteralPath $path
  if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch '(?:^|, )O=Microsoft Corporation(?:,|$)') {throw "Invalid runtime signature: $name"}
  Write-Output "$name $((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash)"
}
"""
    result = subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-Command", script], check=True,
                            capture_output=True, text=True, timeout=120, env={**os.environ, 'PSModulePath': str(powershell.parent/'Modules')})
    hashes = dict(line.split() for line in result.stdout.splitlines() if line.strip())
    if hashes.keys() != set(names):raise ValueError("Missing authenticated Visual C++ runtime")
    return [(system / name, hashes[name].lower()) for name in names]


def build(args):
    src, storage, home, electron, output = (p.resolve() for p in (args.source,args.storage,args.python_home,args.electron_dir,args.output))
    for name in ("Jarvis.exe", "resources/app.asar"):regular(electron/name)
    if output.exists():raise ValueError("Choose a new output directory; existing files are preserved.")
    if output.is_relative_to(electron) or output.is_relative_to(home) or output.is_relative_to(src):
        raise ValueError("Output must be separate from program inputs")
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".jarvis-stage-",dir=output.parent) as temporary:
        work=Path(temporary)
        target=work/"payload"
        target.mkdir()
        st=Stage(target)
        st.tree(electron,"")
        st.copy(src/"desktop/LEEME-INSTALADOR.txt","LEEME-INSTALADOR.txt")
        st.copy(src/"README.md","README.md")
        st.tree(src/"docs","docs")
        # Use the same source and browser-asset whitelist as the public companion ZIP.
        subprocess.run(["node",str(src/"scripts/package-companion.mjs"),str(work/"zip")],check=True,stdout=subprocess.DEVNULL)
        with zipfile.ZipFile(work/"zip/Jarvis-Codigo-Windows.zip") as bundle:
            index=json.loads(bundle.read("companion-files.json"))["files"]
            for name,digest in index.items():
                st.copy(src/safe_relative(name),"backend/"+name,digest)
            st.write("backend/companion-files.json",bundle.read("companion-files.json"))
        for name in ("python.exe","pythonw.exe","python3.dll","python313.dll","LICENSE.txt"):
            st.copy(home/name,"runtime/python/"+name)
        for library, digest in visual_cpp_runtime():
            st.copy(library, "runtime/python/"+library.name, digest)
        for sub in ("DLLs","Lib","tcl"):
            st.tree(home/sub,"runtime/python/"+sub,exclude=("site-packages","ensurepip"))
        st.venv(src/".venv","backend/.venv")
        st.venv(storage/".agent-venv","data/.agent-venv")
        st.venv(storage/".owned-voice-venv","data/.owned-voice-venv")
        st.site(storage/"tools/qwen-voice-packages","data/tools/qwen-voice-packages")
        weights=json.loads((src/"qwen-voice-weights.json").read_text(encoding="utf-8-sig"))
        if args.include_models:
            for name,digest in weights["files"].items():
                st.copy(storage/"models/qwen3-tts-1.7b-base"/safe_relative(name),"data/models/qwen3-tts-1.7b-base/"+name,digest)
            stage_ollama(st, storage)
            for name in WHISPER:
                st.copy(storage/"models/whisper-small"/name,"data/models/whisper-small/"+name)
        profile=storage/"models/jarvis-owned"
        state=json.loads((profile/"profile.json").read_text(encoding="utf-8-sig"))
        if not (state.get("approved") is True and state.get("prepared") is True and state.get("engine")=="Qwen3-TTS-12Hz-1.7B-Base" and state.get("model_revision")==weights["revision"] and state.get("profile_sha256")==PROFILE_SHA and state.get("sample_sha256")==SAMPLE_SHA):
            raise ValueError("Approved voice profile does not match the release")
        prefix="data/models/jarvis-owned/"
        st.copy(profile/"voice.pth",prefix+"voice.pth",PROFILE_SHA)
        st.copy(profile/"samples/demo.wav",prefix+"samples/demo.wav",SAMPLE_SHA)
        sanitized={key:state[key] for key in ("approved","prepared","engine","model_revision","profile_sha256","sample_sha256")}
        st.write(prefix+"profile.json",json.dumps(sanitized,indent=2).encode("utf-8"))
        st.write("dependencies.json",json.dumps(st.packages,sort_keys=True).encode("utf-8"))
        (target/"offline-manifest.json").write_text(json.dumps({"algorithm":"sha256","files":st.hashes},sort_keys=True,indent=2),encoding="utf-8")
        target.rename(output)
        print(f"Staged {len(st.hashes)} verified files into {output}")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    for option in ("source","storage","python-home","electron-dir","output"):
        parser.add_argument("--"+option,type=Path,required=True)
    parser.add_argument('--include-models',action='store_true',help='Private offline build only. Public releases fetch models from their publishers.')
    build(parser.parse_args())
