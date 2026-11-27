'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
function client(transport){
  const context={window:{addEventListener(){}},document:{getElementById(){return {}; }},apiFetch:transport,
    statusEl:{textContent:''},sessionInfo:{textContent:''},responseInProgress:false,voiceActivityAt:0,
    running:false,starting:true,performance,Date,AbortSignal,DOMException,setTimeout,clearTimeout};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../public/assets/realtime-owned.js'),'utf8'),context);
  return context;
}
test('cold voice polls readiness before creating any cloud session',async()=>{
  const calls=[];
  const context=client(async(url,options)=>{
    calls.push([url,options.method]);
    return {ok:true,json:async()=>calls.length===1?{state:'preparing',ready:false,message:'Cargando perfil elegido'}:{state:'ready',ready:true}};
  });
  await context.window.JarvisRealtimeOwned.prepareVoice(new AbortController().signal);
  assert.deepEqual(calls,[['/api/speech/preparation','POST'],['/api/speech/preparation','GET']]);
  assert.equal(context.responseInProgress,true);
  assert.match(context.sessionInfo.textContent,/perfil elegido/);
});
test('cancelling a cold startup releases its wait and performs no further calls',async()=>{
  const controller=new AbortController();let calls=0;
  const context=client(async()=>{calls++;return {ok:true,json:async()=>({state:'preparing',ready:false})};});
  const waiting=context.window.JarvisRealtimeOwned.prepareVoice(controller.signal);
  setTimeout(()=>controller.abort(),20);
  await assert.rejects(waiting,error=>error.name==='AbortError');
  assert.equal(calls,1);
});
