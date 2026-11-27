'use strict';
const { app, BrowserWindow, Menu, Tray, nativeImage, session, ipcMain, safeStorage, shell, dialog, nativeTheme } = require('electron');
const path = require('node:path');
const fs = require('node:fs/promises');
const syncFS = require('node:fs');
const http = require('node:http');
const crypto = require('node:crypto');
const { pathToFileURL } = require('node:url');
const runtime = require('./runtime.cjs');
const { APP_ORIGIN, localURL, externalURL, audioPermission, ownedListener } = require('./policy.cjs');
const setupURL = pathToFileURL(path.join(__dirname, 'onboarding.html')).href;
const iconPath = path.join(__dirname, 'icon.png');
const pointerDir = path.join(app.getPath('appData'), 'JarvisDesktop');
const pointerFile = path.join(pointerDir, 'installation.json');
// Chromium initializes its cache at ready; choose the data drive before that.
let bootPointer = {};
try { bootPointer = JSON.parse(syncFS.readFileSync(pointerFile, 'utf8')); } catch {}
let bootStorage = bootPointer.storageRoot;
if (!bootStorage) {
  try { bootStorage = JSON.parse(syncFS.readFileSync(path.resolve(__dirname, '..', '.jarvis-app.json'), 'utf8')).storage_dir; } catch {}
}
if (!bootStorage && app.isPackaged) bootStorage = path.join(path.dirname(app.getPath('exe')), 'data');
const desktopData = process.env.JARVIS_DESKTOP_DATA || bootStorage || path.join(app.getPath('userData'), 'desktop');
syncFS.mkdirSync(path.join(desktopData, 'desktop-profile'), { recursive: true });
app.setPath('userData', path.join(desktopData, 'desktop-profile'));
app.setPath('sessionData', path.join(desktopData, 'desktop-profile'));
let window, tray, info, service, quitting = false, starting = false, bridge, bridgeTimer, reconnecting = false;
let state = { busy: true, message: 'Buscando tu instalación de Jarvis…', needsKey: false, error: '' };
const single = app.requestSingleInstanceLock();
if (!single) app.quit();
function update(values) { state = { ...state, ...values }; if (window && !window.isDestroyed() && window.webContents.getURL() === setupURL) window.webContents.send('setup:changed', state); }
function show() { if (window) { if (window.isMinimized()) window.restore(); window.show(); window.focus(); } }
app.on('second-instance', show);
function isSetup(event) { return window && event.sender === window.webContents && event.senderFrame === window.webContents.mainFrame && event.senderFrame.url === setupURL; }
async function findInstallation() {
  const base = app.isPackaged ? path.dirname(app.getPath('exe')) : __dirname;
  const registered = await runtime.readJSON(pointerFile).catch(() => ({}));
  const candidates = [process.env.JARVIS_BACKEND_ROOT, registered.backendRoot,
    path.join(base, 'backend'), path.resolve(__dirname, '..'),
    path.join(app.getPath('downloads'), 'jarvis-local-template', 'jarvis-local-template'),
    path.join(app.getPath('downloads'), 'jarvis-local-template')].filter(Boolean);
  const active = await runtime.listener();
  const available = [];
  for (const candidate of candidates) {
    const root = path.resolve(candidate);
    if (!await runtime.exists(path.join(root, 'server.py')) || !await runtime.exists(path.join(root, '.venv', 'Scripts', 'python.exe'))) continue;
    available.push(await runtime.inspect(root));
  }
  let found = active ? available.find(item => ownedListener(active, item.root, item.pythonHome)) : available[0];
  if (active && !found) throw new Error('Otra aplicación está usando la conexión local de Jarvis. Cerrala y tocá Reintentar. No se cerró ningún programa.');
  if (!found) throw new Error('No está el paquete completo de Jarvis. Ejecutá el instalador de Windows; no necesitás instalar componentes por separado.');
  if (found.root === path.join(base, 'backend')) {
    await runtime.prepareBundled(found.root, path.join(base, 'runtime', 'python'));
    found = await runtime.inspect(found.root);
  }
  await fs.mkdir(pointerDir, { recursive: true });
  await fs.writeFile(pointerFile, JSON.stringify({ backendRoot: found.root, storageRoot: found.storage }));
  return found;
}
async function storedKey() {
  const encrypted = await fs.readFile(path.join(info.root, '.jarvis-openai.dpapi')).catch(() => null);
  if (!encrypted) return null;
  if (!safeStorage.isEncryptionAvailable()) throw new Error('Windows no pudo abrir la clave guardada. Volvé a conectar tu cuenta.');
  try { return safeStorage.decryptString(encrypted); }
  catch { update({ needsKey: true }); return null; }
}
async function desktopBridge() {
  if (bridge) return;
  const token = crypto.randomBytes(32).toString('hex');
  bridge = http.createServer((request, response) => {
    const actual = request.headers.authorization || '';
    const expected = 'Bearer ' + token;
    if (request.method !== 'POST' || request.url !== '/show' || actual.length !== expected.length || !crypto.timingSafeEqual(Buffer.from(actual), Buffer.from(expected))) { response.writeHead(403); response.end(); return; }
    show(); response.writeHead(204); response.end();
  });
  await new Promise(resolve => bridge.listen(0, '127.0.0.1', resolve));
  const file = path.join(info.root, '.jarvis-desktop.json');
  const heartbeat = () => fs.writeFile(file, JSON.stringify({ port: bridge.address().port, token, updated: Date.now() / 1000 })).catch(() => {});
  await heartbeat(); bridgeTimer = setInterval(heartbeat, 5000); bridgeTimer.unref();
}
async function start() {
  if (starting) return; starting = true;
  update({ busy: true, needsKey: false, error: '', message: 'Comprobando los componentes de Jarvis…' });
  try {
    info = info || await findInstallation();
    update({ downloading: true, message: 'Preparando los modelos desde sus proveedores oficiales…' });
    try { await runtime.prepareModels(info, message => update({ message })); }
    finally { update({ downloading: false }); }
    // The backend validates and loads the selected voice in the background.
    // Importing Torch/CUDA here can freeze onboarding on a cold external disk.
    const key = await storedKey();
    if (!info.keyConfigured && !key) { update({ busy: false, needsKey: true, message: 'Conectá OpenAI una vez para empezar. Tu voz de Jarvis ya está incluida.' }); return; }
    update({ message: 'Iniciando Jarvis y preparando tu voz…' });
    service = await runtime.startBackend(info, key);
    // Cold model preparation belongs to the background service. A slow disk must
    // not keep the entire desktop window trapped in onboarding.
    void fetch(APP_ORIGIN + '/api/speech/preparation', { method: 'POST', signal: AbortSignal.timeout(8000) }).catch(() => {});
    await desktopBridge();
    await window.loadURL(APP_ORIGIN + '/');
    const choiceFile = path.join(info.root, '.jarvis-install-choice.json');
    const choice = await runtime.readJSON(choiceFile).catch(() => null);
    if (['qwen3:1.7b','qwen3:4b','qwen3:8b','qwen3:14b'].includes(choice?.model)) {
      const response = await fetch(APP_ORIGIN + '/api/agent/local/prepare', { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model: choice.model, activate: true }), signal: AbortSignal.timeout(10000) }).catch(() => null);
      if (response?.ok) {
        await fs.unlink(choiceFile).catch(() => {});
        window.webContents.send('jarvis:local-models-open');
      }
    }
    window.setTitle('Jarvis');
    if (!process.argv.includes('--background')) show();
    update({ busy: false, message: 'Jarvis está listo.' });
    // Windows startup is opt-in through the tray menu, never enabled at launch.
  } catch (error) {
    if (quitting || !window || window.isDestroyed()) return;
    if (window.webContents.getURL() !== setupURL) await window.loadURL(setupURL);
    const message = error.name === 'TimeoutError' || error.name === 'AbortError'
      ? 'La conexión local tardó en iniciar. Tocá Reintentar; tu instalación y tu voz se conservan.' : error.message;
    update({ busy: false, error: message, message: 'Jarvis necesita completar este paso.' }); show();
  } finally { starting = false; }
}
async function connectionSettings() {
  if (starting || !info) return;
  reconnecting = true;
  await window.loadURL(setupURL);
  update({ busy: false, needsKey: true, error: '', message: 'Conectá OpenAI. Al guardar, Jarvis reinicia su conexión; tu voz y tus datos se conservan.' });
  show();
}
function installPermissions() {
  const ownSession = session.defaultSession;
  ownSession.setPermissionRequestHandler((contents, permission, callback, details) => callback(audioPermission(contents, permission, details, window?.webContents)));
  ownSession.setPermissionCheckHandler((contents, permission, origin, details) => audioPermission(contents, permission, { ...details, requestingOrigin: origin }, window?.webContents));
  ownSession.setDisplayMediaRequestHandler((_request, callback) => callback({}));
  ownSession.webRequest.onHeadersReceived((details, callback) => {
    if (!localURL(details.url)) { callback({ responseHeaders: details.responseHeaders }); return; }
    callback({ responseHeaders: { ...details.responseHeaders, 'Content-Security-Policy': ["default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; media-src 'self' blob:; font-src 'self' data:; connect-src 'self' https://api.openai.com wss://api.openai.com; object-src 'none'; frame-src 'none'; base-uri 'self'; form-action 'self'"] } });
  });
}
async function init() {
  nativeTheme.themeSource = 'dark';
  window = new BrowserWindow({ width: 1440, height: 980, minWidth: 860, minHeight: 650, show: false, title: 'Jarvis', backgroundColor: '#030b10', icon: iconPath,
    autoHideMenuBar: true, webPreferences: { preload: path.join(__dirname, 'preload.cjs'), nodeIntegration: false, contextIsolation: true, sandbox: true,
      webSecurity: true, allowRunningInsecureContent: false, backgroundThrottling: false, spellcheck: false,
      autoplayPolicy: 'no-user-gesture-required' } });
  Menu.setApplicationMenu(null); installPermissions();
  window.webContents.setWindowOpenHandler(({ url }) => { if (externalURL(url)) shell.openExternal(url); return { action: 'deny' }; });
  window.webContents.on('will-navigate', event => { const url = event.url; if (!localURL(url) && url !== setupURL) { event.preventDefault(); if (externalURL(url)) shell.openExternal(url); } });
  window.webContents.on('will-frame-navigate', event => { if (!event.isMainFrame) event.preventDefault(); });
  window.webContents.on('will-redirect', event => { if (!localURL(event.url)) event.preventDefault(); });
  window.webContents.on('will-attach-webview', event => event.preventDefault());
  window.on('close', () => { if(!quitting){quitting = true; app.quit();} });
  for(const event of ['hide','minimize','blur'])window.on(event,()=>{
    if(!window.isDestroyed())window.webContents.send('jarvis:suspend');
  });
  window.webContents.on('page-title-updated', event => event.preventDefault());
  tray = new Tray(nativeImage.createFromPath(iconPath).resize({ width: 24, height: 24 })); tray.setToolTip('Jarvis');
  tray.setContextMenu(Menu.buildFromTemplate([{ label: 'Abrir Jarvis', click: show }, { label: 'Conexión con OpenAI…', click: () => void connectionSettings() },
    { label: 'Abrir interfaz web', click: () => shell.openExternal('https://jarvis-aurelio.vercel.app/') },
    { type: 'separator' }, { label: 'Iniciar con Windows', type: 'checkbox', checked: app.isPackaged && app.getLoginItemSettings().openAtLogin,
      click: item => { if (app.isPackaged) app.setLoginItemSettings({ openAtLogin: item.checked, args: ['--background'] }); } },
    { label: 'Salir de la aplicación', click: () => { quitting = true; app.quit(); } }]));
  tray.on('double-click', show);
  ipcMain.handle('setup:status', event => { if (!isSetup(event)) throw new Error('Origen no permitido.'); return state; });
  ipcMain.handle('setup:retry', event => { if (!isSetup(event)) return; void start(); });
  ipcMain.handle('setup:cancel-downloads', event => { if (isSetup(event)) runtime.cancelModelDownloads(); });
  ipcMain.handle('setup:connect', async (event, key) => {
    if (!isSetup(event) || !info) return;
    if (typeof key !== 'string' || !/^sk-[\w-]{20,500}$/.test(key.trim())) { update({ error: 'Pegá una clave de OpenAI válida para conectar Jarvis.' }); return; }
    if (!safeStorage.isEncryptionAvailable()) { update({ error: 'Windows no pudo activar el almacenamiento seguro de la clave. Reiniciá tu sesión y volvé a intentarlo.' }); return; }
    const pending = path.join(info.root, '.jarvis-openai.dpapi.pending');
    try {
      await fs.writeFile(pending, safeStorage.encryptString(key.trim()));
      key = '';
      if (reconnecting) await runtime.stopBackend(info);
      await fs.rename(pending, path.join(info.root, '.jarvis-openai.dpapi'));
      reconnecting = false; void start();
    } catch (error) { key = ''; await fs.unlink(pending).catch(() => {}); update({ busy: false, error: error.message }); }
  });
  ipcMain.handle('setup:diagnostics', async event => { if (!isSetup(event) || !info) return; const logs = path.join(info.storage, 'logs'); await fs.mkdir(logs, { recursive: true }); await shell.openPath(logs); });
  await window.loadURL(setupURL);
  if (!process.argv.includes('--background')) show();
  await start();
}
app.on('before-quit', () => { quitting = true; runtime.cancelModelDownloads(); clearInterval(bridgeTimer); bridge?.close(); if (info) fs.unlink(path.join(info.root, '.jarvis-desktop.json')).catch(() => {}); });
// A shared companion can serve an explicitly opened web UI; wake capture requires
// a live foreground client and cannot reopen a closed application.
app.on('window-all-closed', () => { if (quitting) app.quit(); });
if (single) app.whenReady().then(init).catch(error => { dialog.showErrorBox('Jarvis', error.message); quitting = true; app.quit(); });
