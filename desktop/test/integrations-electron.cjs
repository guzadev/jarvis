'use strict';
// Local UI only: no microphone, OpenAI requests or external integration calls.
const {app,BrowserWindow,session}=require('electron');
const fs=require('node:fs/promises');
const destination=process.env.JARVIS_INTEGRATIONS_UI_OUTPUT;
if(!destination)throw new Error('Set JARVIS_INTEGRATIONS_UI_OUTPUT.');
app.whenReady().then(async()=>{
  let win;
  try{
    session.defaultSession.setPermissionRequestHandler((_contents,_permission,callback)=>callback(false));
    win=new BrowserWindow({show:false,width:1440,height:1000,webPreferences:{offscreen:true,nodeIntegration:false,contextIsolation:true,sandbox:true,backgroundThrottling:false}});
    await win.loadURL('http://127.0.0.1:8788/');
    const result=await win.webContents.executeJavaScript(`(async()=>{
      if(typeof start!=='function'||typeof handleEvent!=='function')throw new Error('Main voice interface script did not load');
      if(document.querySelector('#jarvisIntegrationsPanel'))throw new Error('Integration UI eagerly opened');
      await JarvisIntegrations.open();
      const panel=document.querySelector('#jarvisIntegrationsPanel');
      if(!panel?.open)throw new Error('No integration panel');
      const text=panel.innerText;
      const rect=panel.getBoundingClientRect();
      return {ok:true,title:panel.querySelector('h2')?.textContent,withinViewport:rect.width<=innerWidth&&rect.height<=innerHeight,
        addAvailable:/Añadir|Agregar|Nueva/.test(text),credentialInputsEmpty:[...panel.querySelectorAll('input[type=password]')].every(input=>!input.value),
        physicalMicrophoneUsed:false,externalIntegrationInvoked:false};
    })()`);
    await new Promise(resolve=>setTimeout(resolve,350));
    await fs.writeFile(destination,JSON.stringify(result,null,2));
    await fs.writeFile(destination.replace(/\.json$/,'.png'),(await win.webContents.capturePage()).toPNG());
    win.destroy();app.exit(result.withinViewport&&result.addAvailable?0:1);
  }catch(error){await fs.writeFile(destination,JSON.stringify({ok:false,error:error.message}));win?.destroy();app.exit(1);}
});
