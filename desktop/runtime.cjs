'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const { execFile, spawn } = require('node:child_process');
const { promisify } = require('node:util');
const crypto = require('node:crypto');
const { ownedListener, APP_ORIGIN } = require('./policy.cjs');
const execute = promisify(execFile);
let modelDownloads;
function cancelModelDownloads() { modelDownloads?.kill(); }
async function prepareModels(info, progress) {
  if (modelDownloads) throw new Error('La preparación de los modelos ya está en curso.');
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => !/KEY|TOKEN|SECRET|PASSWORD/i.test(key)));
  env.PYTHONUTF8 = '1'; env.PYTHONIOENCODING = 'utf-8';
  await new Promise((resolve, reject) => {
    const child = spawn(info.python, ['-u', path.join(info.root, 'bootstrap_models.py'), '--storage', info.storage],
      { cwd: info.root, env, windowsHide: true, stdio: ['ignore', 'pipe', 'ignore'] });
    modelDownloads = child;
    let buffered = '', failure;
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', text => {
      buffered += text;
      if (buffered.length > 100000) { child.kill(); return; }
      const lines = buffered.split(/\r?\n/); buffered = lines.pop();
      for (const line of lines) {
        try { const item = JSON.parse(line); if (item.error) failure = String(item.error).slice(0,500); else if(item.message) progress(String(item.message).slice(0,500)); } catch {}
      }
    });
    child.on('error', error => { if (modelDownloads === child) modelDownloads = null; reject(error); });
    child.on('close', code => {
      if (modelDownloads === child) modelDownloads = null;
      if (code === 0) resolve(); else reject(new Error(failure || 'La descarga de los modelos se interrumpió. Tocá Reintentar para continuar.'));
    });
  });
}
async function exists(file) { try { await fs.access(file); return true; } catch { return false; } }
async function readJSON(file) { return JSON.parse(await fs.readFile(file, 'utf8')); }
function runPowerShell(source) {
  return execute(path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe'),
    ['-NoProfile', '-NonInteractive', '-EncodedCommand', Buffer.from(source, 'utf16le').toString('base64')],
    { windowsHide: true, encoding: 'utf8', timeout: 12000, maxBuffer: 1024 * 1024 });
}
async function listener() {
  const { stdout } = await runPowerShell("$ErrorActionPreference='Stop'; $p=Get-NetTCPConnection -LocalPort 8788 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if($p){Get-CimInstance Win32_Process -Filter ('ProcessId='+$p.OwningProcess) | Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress}else{'null'}");
  return JSON.parse(stdout.trim().replace(/^\uFEFF/, '') || 'null');
}
async function inspect(root) {
  const settingsPath = path.join(root, '.jarvis-app.json');
  const settings = await exists(settingsPath) ? await readJSON(settingsPath) : {};
  const storage = settings.storage_dir || path.resolve(root, '..', 'data');
  const env = await fs.readFile(path.join(root, '.env'), 'utf8').catch(() => '');
  const cfg = await fs.readFile(path.join(root, '.venv', 'pyvenv.cfg'), 'utf8');
  const pythonHome = cfg.match(/^home\s*=\s*(.+)$/m)?.[1].trim();
  return { root, storage, settings, keyConfigured: /^\s*OPENAI_API_KEY\s*=\s*["']?sk-[^\s"']+/m.test(env),
    pythonHome, python: path.join(root, '.venv', 'Scripts', 'python.exe') };
}
async function prepareBundled(root, pythonHome) {
  if (!await exists(path.join(pythonHome, 'python.exe'))) throw new Error('El paquete no contiene el motor de ejecuciÃ³n. ReinstalÃ¡ Jarvis con el paquete completo.');
  const storage = path.resolve(root, '..', 'data');
  for (const directory of [path.join(root, '.venv'), path.join(storage, '.agent-venv'), path.join(storage, '.owned-voice-venv')]) {
    if (!await exists(path.join(directory, 'Scripts', 'python.exe'))) throw new Error('Falta una parte del paquete. VolvÃ© a ejecutar el instalador completo.');
    await fs.writeFile(path.join(directory, 'pyvenv.cfg'), `home = ${pythonHome}\r\ninclude-system-site-packages = false\r\nversion = 3.13.3\r\nexecutable = ${path.join(pythonHome, 'python.exe')}\r\n`, 'utf8');
  }
  const settingsPath = path.join(root, '.jarvis-app.json');
  if (!await exists(settingsPath)) await fs.writeFile(settingsPath, JSON.stringify({ provider: 'openai', conversation_provider: 'openai', openai_model: 'gpt-5.4-mini',
    storage_dir: storage, voice: 'owned', realtime_owned_enabled: true }, null, 2));
  const wakePath = path.join(root, '.wake-config.json');
  if (!await exists(wakePath)) await fs.writeFile(wakePath, JSON.stringify({ enabled: false, microphone: 'auto' }));
  const pairPath = path.join(root, '.jarvis-web.json');
  if (!await exists(pairPath)) await fs.writeFile(pairPath, JSON.stringify({ origin: 'https://jarvis-aurelio.vercel.app', token: crypto.randomBytes(40).toString('base64url') }));
}
async function checkVoice(info) {
  const profilePath = path.join(info.storage, 'models', 'jarvis-owned', 'profile.json');
  const profile = await readJSON(profilePath).catch(() => null);
  if (!profile?.approved || profile.engine !== 'Qwen3-TTS-12Hz-1.7B-Base') throw new Error('El paquete de la voz elegida estÃ¡ incompleto. ReinstalÃ¡ el paquete completo de Jarvis.');
  for (const [file, expected] of [['voice.pth', profile.profile_sha256], ['samples/demo.wav', profile.sample_sha256]]) {
    const bytes = await fs.readFile(path.join(info.storage, 'models', 'jarvis-owned', file));
    if (crypto.createHash('sha256').update(bytes).digest('hex') !== expected) throw new Error('La voz elegida no pasÃ³ su comprobaciÃ³n de integridad. ReinstalÃ¡ el paquete completo.');
  }
  const manifest = await readJSON(path.join(info.root, 'qwen-voice-weights.json'));
  for (const name of Object.keys(manifest.files)) if (!await exists(path.join(info.storage, 'models', 'qwen3-tts-1.7b-base', name))) throw new Error('Faltan archivos del modelo de voz. ReinstalÃ¡ el paquete completo.');
  if (!await exists(path.join(info.storage, 'models', 'whisper-small', 'model.bin'))) throw new Error('Falta el modelo de escucha. ReinstalÃ¡ el paquete completo.');
  const probe = await execute(path.join(info.storage, '.owned-voice-venv', 'Scripts', 'python.exe'),
    ['-c', 'import json,torch; print(json.dumps({"available":torch.cuda.is_available()}))'],
    { windowsHide: true, timeout: 45000 }).catch(() => null);
  const gpu = probe ? JSON.parse(probe.stdout.trim().split(/\r?\n/).at(-1)) : null;
  return { compatible: gpu?.available === true };
}
async function stopBackend(info) {
  const current = await listener();
  if (!current) return;
  if (!ownedListener(current, info.root, info.pythonHome)) throw new Error('La conexiÃ³n pertenece a otra aplicaciÃ³n. No se cerrÃ³ ningÃºn programa.');
  // Read every task, including older approvals; diagnostics must fail closed.
  const query = 'import pathlib,sqlite3,sys; p=pathlib.Path(sys.argv[1]).resolve(); c=sqlite3.connect(p.as_uri()+"?mode=ro",uri=True); print(c.execute("SELECT COUNT(*) FROM missions WHERE status IN (?,?,?)",("queued","running","awaiting_approval")).fetchone()[0]); c.close()';
  const { stdout } = await execute(info.python, ['-c', query, path.join(info.storage, '.jarvis-state.db')], { windowsHide: true, timeout: 8000 });
  if (!/^\d+$/.test(stdout.trim())) throw new Error('No se pudo comprobar si hay trabajos activos. La conexiÃ³n se conservÃ³.');
  if (Number(stdout.trim()) > 0) throw new Error('Hay un trabajo en curso. EsperÃ¡ a que termine antes de cambiar la conexiÃ³n.');
  process.kill(current.ProcessId);
  for (let attempt = 0; attempt < 30; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 300));
    const status = await fetch(APP_ORIGIN + '/api/config', { signal: AbortSignal.timeout(500) }).catch(() => null);
    if (!status) return;
  }
  throw new Error('La conexiÃ³n anterior todavÃ­a estÃ¡ cerrÃ¡ndose. TocÃ¡ Reintentar.');
}
async function startBackend(info, apiKey) {
  const current = await listener();
  if (current) {
    if (!ownedListener(current, info.root, info.pythonHome)) throw new Error('Otra aplicaciÃ³n estÃ¡ usando la conexiÃ³n local de Jarvis. Cerrala y tocÃ¡ Reintentar. No se cerrÃ³ ningÃºn programa.');
    const status = await fetch(APP_ORIGIN + '/api/config', { signal: AbortSignal.timeout(4000) }).then(r => r.ok ? r.json() : null).catch(() => null);
    if (!status || typeof status.key_configured !== 'boolean') throw new Error('La instalaciÃ³n de Jarvis no estÃ¡ respondiendo. CerrÃ¡ Jarvis y volvÃ© a abrirlo.');
    return { shared: true, process: null };
  }
  const logs = path.join(info.storage, 'logs');
  const temp = path.join(info.storage, 'tmp');
  await fs.mkdir(logs, { recursive: true }); await fs.mkdir(temp, { recursive: true });
  const out = await fs.open(path.join(logs, 'desktop-server.out.log'), 'a');
  const err = await fs.open(path.join(logs, 'desktop-server.err.log'), 'a');
  const env = { ...process.env, TEMP: temp, TMP: temp, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' };
  if (apiKey) env.OPENAI_API_KEY = apiKey;
  const child = spawn(info.python, ['-u', path.join(info.root, 'server.py')], { cwd: info.root, env, windowsHide: true,
    detached: false, stdio: ['ignore', out.fd, err.fd] });
  await out.close(); await err.close();
  let failure; child.on('error', error => { failure = error; });
  await fs.writeFile(path.join(info.root, '.jarvis.pid'), String(child.pid || ''));
  for (let attempt = 0; attempt < 60; attempt++) {
    if (failure || child.exitCode !== null) throw new Error('Jarvis no pudo iniciar. TocÃ¡ Abrir diagnÃ³stico para consultar el registro.');
    try {
      const response = await fetch(APP_ORIGIN + '/api/config', { signal: AbortSignal.timeout(1000) });
      if (response.ok) {
        if (!ownedListener(await listener(), info.root, info.pythonHome)) throw new Error('La conexiÃ³n pertenece a otra aplicaciÃ³n.');
        return { shared: false, process: child };
      }
    } catch (error) { if (error.message.includes('otra aplicaciÃ³n')) throw error; }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error('Jarvis estÃ¡ tardando en iniciar. TocÃ¡ Reintentar; no hace falta reinstalar los modelos.');
}
module.exports = { exists, readJSON, inspect, prepareBundled, prepareModels, cancelModelDownloads, checkVoice, startBackend, stopBackend, listener };
