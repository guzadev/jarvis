'use strict';
if(location.origin==='http://127.0.0.1:8788'){
  const {ipcRenderer}=require('electron');
  ipcRenderer.on('jarvis:suspend',()=>window.dispatchEvent(new Event('jarvis:suspend')));
  ipcRenderer.on('jarvis:local-models-open',()=>window.dispatchEvent(new Event('jarvis:local-models-open')));
}
if (location.protocol === 'file:' && location.pathname.endsWith('/onboarding.html')) {
  const { contextBridge, ipcRenderer } = require('electron');
  contextBridge.exposeInMainWorld('jarvisSetup', Object.freeze({
    status: () => ipcRenderer.invoke('setup:status'),
    connect: key => ipcRenderer.invoke('setup:connect', key),
    retry: () => ipcRenderer.invoke('setup:retry'),
    cancelDownloads: () => ipcRenderer.invoke('setup:cancel-downloads'),
    diagnostics: () => ipcRenderer.invoke('setup:diagnostics'),
    onStatus: callback => { ipcRenderer.on('setup:changed', (_event, value) => callback(value)); }
  }));
}
