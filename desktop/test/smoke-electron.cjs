'use strict';
// Integration test of our own Electron application; no cloud model requests.
const { app, BrowserWindow } = require('electron');
const fs = require('node:fs/promises');
const syncFS=require('node:fs');
const path = require('node:path');
require('../main.cjs');
const destination = process.env.JARVIS_SMOKE_OUTPUT;
if (!destination) throw new Error('Set JARVIS_SMOKE_OUTPUT for the integration result.');
app.whenReady().then(async () => {
  try {
    let window;
    for (let attempt = 0; attempt < 90; attempt++) {
      window = BrowserWindow.getAllWindows()[0];
      if (window?.webContents.getURL().startsWith('http://127.0.0.1:8788/')) break;
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    if (!window?.webContents.getURL().startsWith('http://127.0.0.1:8788/')) {
      const message = await window?.webContents.executeJavaScript('document.getElementById("error")?.textContent');
      throw new Error(message || 'The desktop did not load the verified local application.');
    }
    await new Promise(resolve => setTimeout(resolve, 1800));
    const preferences = window.webContents.getLastWebPreferences();
    const result = await window.webContents.executeJavaScript(`(async () => {
      const result = { origin: location.origin, title: document.title,
        nodeUnavailable: typeof window.require === 'undefined', setupBridgeUnavailable: typeof window.jarvisSetup === 'undefined',
        canvasCount: document.querySelectorAll('canvas').length, webRtcAvailable: typeof RTCPeerConnection === 'function' };
      const status = await fetch('/api/agent/status').then(r => r.json());
      result.provider = status.provider; result.voice = status.voice_mode; result.ready = status.ready;
      const stream = await navigator.mediaDevices.getUserMedia({audio:true,video:false});
      result.microphoneOpened = stream.getAudioTracks().length === 1;
      result.videoTracks = stream.getVideoTracks().length;
      stream.getTracks().forEach(track => track.stop());
      const sample = await fetch('/api/speech/owned/sample');
      const audio = new AudioContext();
      const decoded = await audio.decodeAudioData(await sample.arrayBuffer());
      result.approvedVoiceSampleSeconds = decoded.duration; await audio.close();
      return result;
    })()`);
    result.sandbox = preferences.sandbox; result.contextIsolation = preferences.contextIsolation;
    result.nodeIntegration = preferences.nodeIntegration;
    await fs.mkdir(path.dirname(destination), { recursive: true });
    app.once('will-quit',()=>syncFS.writeFileSync(destination,JSON.stringify({ok:BrowserWindow.getAllWindows().length===0,...result,closeQuitsApplication:BrowserWindow.getAllWindows().length===0},null,2)));
    window.close();
  } catch (error) {
    await fs.writeFile(destination, JSON.stringify({ ok: false, error: error.message }, null, 2));
    app.exit(1);
  }
});
