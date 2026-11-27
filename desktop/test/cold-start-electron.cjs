'use strict';
// Own app test: a voice request never finishes, but the main interface must open.
const {app,BrowserWindow}=require('electron');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const http=require('node:http');
const output=process.env.JARVIS_COLD_START_OUTPUT;
if(!output)throw new Error('Set JARVIS_COLD_START_OUTPUT.');
const fixture=fs.mkdtempSync(path.join(os.tmpdir(),'jarvis-cold-start-'));
const backend=path.join(fixture,'backend');fs.mkdirSync(backend,{recursive:true});
const sockets=new Set();
let voiceRequests=0,oldBlockingRequests=0;
const server=http.createServer((request,response)=>{
  if(request.url==='/api/speech/preparation'){voiceRequests++;return;}
  if(request.url==='/api/speech/prepare'){oldBlockingRequests++;return;}
  response.setHeader('Content-Type','text/html');response.end('<title>Jarvis cold start fixture</title><main>Interfaz disponible</main>');
});
server.on('connection',socket=>{sockets.add(socket);socket.on('close',()=>sockets.delete(socket));});
server.listen(0,'127.0.0.1',()=>{
  const origin='http://127.0.0.1:'+server.address().port;
  const policy=require('../policy.cjs');
  policy.APP_ORIGIN=origin;policy.localURL=value=>{try{return new URL(value).origin===origin;}catch{return false;}};
  process.env.JARVIS_BACKEND_ROOT=backend;process.env.JARVIS_DESKTOP_DATA=path.join(fixture,'data');
  app.setPath('appData',path.join(fixture,'registration'));
  const runtime=require('../runtime.cjs');
  runtime.exists=async()=>true;runtime.listener=async()=>null;
  runtime.inspect=async()=>({root:backend,storage:path.join(fixture,'storage'),keyConfigured:true});
  runtime.checkVoice=async()=>{throw new Error('GPU probe blocked the interface');};runtime.startBackend=async()=>({shared:true,process:null});
  require('../main.cjs');
  app.whenReady().then(async()=>{
    try{
      const before=Date.now();let win;
      for(let index=0;index<240;index++){
        win=BrowserWindow.getAllWindows()[0];
        if(win?.webContents.getURL()===origin+'/')break;
        await new Promise(resolve=>setTimeout(resolve,50));
      }
      if(win?.webContents.getURL()!==origin+'/'){
        const message=await win?.webContents.executeJavaScript('document.getElementById("error")?.textContent').catch(()=>null);
        throw new Error('Cold voice blocked the interface: '+(message||win?.webContents.getURL()||'no window'));
      }
      const elapsed=Date.now()-before;
      if(oldBlockingRequests)throw new Error('Desktop used the old blocking warmup');
      await fs.promises.writeFile(output,JSON.stringify({ok:true,interfaceOpenedMs:elapsed,voiceRequests,oldBlockingRequests,voiceStillPreparing:true,realProvidersCalled:false},null,2));
      app.quit();
    }catch(error){fs.writeFileSync(output,JSON.stringify({ok:false,error:error.message}));app.exit(1);}
  });
});
app.on('quit',()=>{
  for(const socket of sockets)socket.destroy();server.close();
  if(path.dirname(fixture)===path.resolve(os.tmpdir())&&path.basename(fixture).startsWith('jarvis-cold-start-')){
    try{fs.rmSync(fixture,{recursive:true,force:true});}catch{}
  }
});
