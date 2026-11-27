'use strict';
if(location.origin==='http://127.0.0.1:8788'){
  const {ipcRenderer}=require('electron');
  ipcRenderer.on('jarvis:suspend',()=>window.dispatchEvent(new Event('jarvis:suspend')));
}
if (location.protocol === 'file:' && location.pathname.endsWith('/onboarding.html')) {
  const { contextBridge, ipcRenderer } = require('electron');
  contextBridge.exposeInMainWorld('jarvisSetup', Object.freeze({
    status: () => ipcRenderer.invoke('setup:status'),
    connect: key => ipcRenderer.invoke('setup:connect', key),
    retry: () => ipcRenderer.invoke('setup:retry'),
    diagnostics: () => ipcRenderer.invoke('setup:diagnostics'),
    onStatus: callback => { ipcRenderer.on('setup:changed', (_event, value) => callback(value)); }
  }));
}
