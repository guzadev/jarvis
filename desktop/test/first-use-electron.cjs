'use strict';
// Real onboarding/DPAPI; the backend is stubbed so no API request can be made.
const { app, BrowserWindow, safeStorage } = require('electron');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const output = process.env.JARVIS_FIRST_USE_OUTPUT;
if (!output) throw new Error('Set JARVIS_FIRST_USE_OUTPUT.');
const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'jarvis-first-use-'));
const root = path.join(fixture, 'backend');
fs.mkdirSync(path.join(root, '.venv', 'Scripts'), { recursive: true });
fs.mkdirSync(path.join(fixture, 'registration'), { recursive: true });
fs.writeFileSync(path.join(root, 'server.py'), '# fixture');
fs.writeFileSync(path.join(root, '.venv', 'Scripts', 'python.exe'), 'fixture');
fs.writeFileSync(path.join(root, '.venv', 'pyvenv.cfg'), 'home = ' + fixture + '\n');
app.setPath('appData', path.join(fixture, 'registration'));
process.env.JARVIS_BACKEND_ROOT = root;
process.env.JARVIS_DESKTOP_DATA = path.join(fixture, 'data');
const runtime = require('../runtime.cjs');
runtime.listener = async () => null;
runtime.checkVoice = async () => ({ compatible: true });
let backendCalls = 0, passedKey;
runtime.startBackend = async (_info, key) => { backendCalls++; passedKey = key; throw new Error('Prueba de conexión completa.'); };
require('../main.cjs');
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
app.whenReady().then(async () => {
  try {
    let win, page;
    for (let i = 0; i < 60; i++) {
      win = BrowserWindow.getAllWindows()[0];
      if (win) page = await win.webContents.executeJavaScript('({needsKey:Boolean(document.getElementById("connect")&&!document.getElementById("connect").hidden),message:document.getElementById("message")?.textContent})').catch(() => null);
      if (page?.needsKey) break;
      await wait(250);
    }
    if (!page?.needsKey) throw new Error('The first-use form was not displayed.');
    const form = await win.webContents.executeJavaScript('({password:document.getElementById("key").type==="password",noNode:typeof window.require==="undefined",empty:document.getElementById("key").value==="",keyHelp:document.querySelector("a")?.href==="https://platform.openai.com/api-keys"})');
    const initialBackendCalls = backendCalls;
    await win.webContents.executeJavaScript('document.getElementById("key").value="invalid";document.getElementById("connect").requestSubmit()');
    await wait(400);
    const invalid = await win.webContents.executeJavaScript('({cleared:document.getElementById("key").value==="",error:document.getElementById("error").textContent.includes("válida")})');
    const dummy = 'sk-local-test-' + 'x'.repeat(30);
    await win.webContents.executeJavaScript(`document.getElementById('key').value=${JSON.stringify(dummy)};document.getElementById('connect').requestSubmit()`);
    for (let i = 0; i < 40 && !backendCalls; i++) await wait(100);
    const encrypted = fs.readFileSync(path.join(root, '.jarvis-openai.dpapi'));
    const result = { ok: true, ...form, initialBackendCalls, invalidRejected: invalid.error && invalid.cleared,
      dpapiAvailable: safeStorage.isEncryptionAvailable(), storedEncrypted: !encrypted.includes(Buffer.from(dummy)),
      decryptedForOwnBackend: safeStorage.decryptString(encrypted) === dummy && passedKey === dummy,
      backendStubbed: true, cloudRequests: 0 };
    if (!result.password || !result.noNode || !result.keyHelp || initialBackendCalls !== 0 || !result.invalidRejected || !result.storedEncrypted || !result.decryptedForOwnBackend) throw new Error('First-use verification failed.');
    fs.writeFileSync(output, JSON.stringify(result, null, 2));
    app.quit();
  } catch (error) { fs.writeFileSync(output, JSON.stringify({ ok: false, error: error.message }, null, 2)); app.exit(1); }
});
app.on('quit', () => {
  if (path.dirname(fixture) !== path.resolve(os.tmpdir()) || !path.basename(fixture).startsWith('jarvis-first-use-')) return;
  try { fs.rmSync(fixture, { recursive: true, force: true }); } catch {}
});
