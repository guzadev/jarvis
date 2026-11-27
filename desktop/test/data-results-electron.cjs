'use strict';
// Test the real local UI with public data, without microphone or AI requests.
const {app,BrowserWindow,session}=require('electron');
const fs=require('node:fs/promises');
const path=require('node:path');
const destination=process.env.JARVIS_DATA_TEST_OUTPUT;
if(!destination)throw new Error('Set JARVIS_DATA_TEST_OUTPUT.');
app.whenReady().then(async()=>{
  try{
    session.defaultSession.setPermissionRequestHandler((_contents,_permission,callback)=>callback(false));
    const win=new BrowserWindow({show:false,width:1440,height:1000,webPreferences:{offscreen:true,nodeIntegration:false,contextIsolation:true,sandbox:true,backgroundThrottling:false}});
    await win.loadURL('http://127.0.0.1:8788/');
    const result=await win.webContents.executeJavaScript(`(async()=>{
      if(!window.JarvisData)throw new Error('Missing result module');
      if(document.getElementById('jarvisDataPanel'))throw new Error('Result panel created before query');
      const dollar=await JarvisData.query('get_dollar',{});
      const panel=document.getElementById('jarvisDataPanel');
      if(dollar.status!=='ok'||!panel.open||panel.querySelectorAll('tbody tr').length<1)throw new Error('Dollar result not displayed');
      const first={kind:panel.dataset.kind,rows:panel.querySelectorAll('tbody tr').length};
      const astronomy=await JarvisData.query('get_astronomy',{});
      if(astronomy.status!=='ok'||!panel.open)throw new Error('NASA result not displayed');
      if(document.querySelectorAll('#jarvisDataPanel').length!==1||panel.querySelector('table'))throw new Error('Old results retained');
      const image=panel.querySelector('img');
      if(image)await Promise.race([image.decode(),new Promise((_,reject)=>setTimeout(()=>reject(new Error('Image timeout')),20000))]);
      const second={kind:panel.dataset.kind,imageLoaded:!!image?.naturalWidth,title:panel.querySelector('h2').textContent};
      const rect=panel.getBoundingClientRect();
      if(rect.width>innerWidth||rect.height>innerHeight)throw new Error('Result exceeds viewport');
      const picture={width:rect.width,height:rect.height,scrollHeight:panel.querySelector('.data-board-body').scrollHeight};
      return {ok:true,first,second,picture,conversationHidden:document.getElementById('transcript').hidden,nodeUnavailable:typeof require==='undefined'};
    })()`);
    await fs.mkdir(path.dirname(destination),{recursive:true});
    await fs.writeFile(destination,JSON.stringify(result,null,2));
    await new Promise(resolve=>setTimeout(resolve,700));
    await fs.writeFile(destination.replace(/\.json$/,'.png'),(await win.webContents.capturePage()).toPNG());
    result.choiceSessionIsolation=await win.webContents.executeJavaScript(`(async()=>{
      const transport=apiFetch,owned=window.JarvisRealtimeOwned,originalChannel=dc;
      const outputA=[],outputB=[],channelA={readyState:'open',send:value=>outputA.push(JSON.parse(value))},channelB={readyState:'open',send:value=>outputB.push(JSON.parse(value))};
      let turn=1;
      window.JarvisRealtimeOwned={get turn(){return turn;},afterTurn:(_turn,callback)=>callback()};
      const place={place_id:'fixture-choice',label:'Lugar de prueba'};
      try{
        dc=channelA;
        apiFetch=async()=>new Response(JSON.stringify({status:'needs_choice',title:'Elegí el lugar',choices:[place]}),{headers:{'Content-Type':'application/json'}});
        await queryAndDisplayData('fixture-call','resolve_place',{query:'fixture'},channelA);
        const count=outputA.length;
        dc=channelB;turn++;
        window.dispatchEvent(new CustomEvent('jarvis:data-choice',{detail:{...place,result:{status:'ok',place}}}));
        if(outputA.length!==count||outputB.length)throw new Error('Selection leaked into another session');
        return true;
      }finally{dc=originalChannel;apiFetch=transport;window.JarvisRealtimeOwned=owned;JarvisData.close();}
    })()`);
    await fs.writeFile(destination,JSON.stringify(result,null,2));
    win.destroy();app.quit();
  }catch(error){await fs.writeFile(destination,JSON.stringify({ok:false,error:error.message},null,2));app.exit(1);}
});
