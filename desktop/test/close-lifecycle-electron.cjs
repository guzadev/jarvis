'use strict';
// Isolated lifecycle check: no real backend, cloud API, capture or microphone.
const {app,BrowserWindow}=require('electron');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const output=process.env.JARVIS_CLOSE_TEST_OUTPUT;
if(!output)throw new Error('Set JARVIS_CLOSE_TEST_OUTPUT.');
const fixture=fs.mkdtempSync(path.join(os.tmpdir(),'jarvis-close-test-')),root=path.join(fixture,'backend');
fs.mkdirSync(path.join(root,'.venv','Scripts'),{recursive:true});
fs.writeFileSync(path.join(root,'server.py'),'# fixture');fs.writeFileSync(path.join(root,'.venv','Scripts','python.exe'),'fixture');
fs.writeFileSync(path.join(root,'.venv','pyvenv.cfg'),'home = '+fixture+'\n');
app.setPath('appData',path.join(fixture,'registration'));process.env.JARVIS_BACKEND_ROOT=root;process.env.JARVIS_DESKTOP_DATA=path.join(fixture,'data');
process.argv.push('--background');
const runtime=require('../runtime.cjs');runtime.listener=async()=>null;
let backendCalls=0,loginChanges=0,closeRequested=false;
runtime.startBackend=async()=>{backendCalls++;throw new Error('Backend must stay off');};
app.setLoginItemSettings=()=>{loginChanges++;};
app.once('will-quit',()=>fs.writeFileSync(output,JSON.stringify({ok:closeRequested&&BrowserWindow.getAllWindows().length===0&&backendCalls===0&&loginChanges===0,closeRequested,windowsRemaining:BrowserWindow.getAllWindows().length,backendCalls,loginChanges},null,2)));
require('../main.cjs');
app.whenReady().then(async()=>{
  for(let attempt=0;attempt<60;attempt++){
    const win=BrowserWindow.getAllWindows()[0];
    if(win&&win.webContents.getURL().includes('onboarding.html')){closeRequested=true;win.close();return;}
    await new Promise(resolve=>setTimeout(resolve,100));
  }
  fs.writeFileSync(output,JSON.stringify({ok:false,error:'No isolated window'}));app.exit(1);
});
