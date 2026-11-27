import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import test from 'node:test';

const source=readFileSync(new URL('../public/assets/local-voice.js',import.meta.url),'utf8');
const config={provider:'openai',voice_mode:'owned',owned:{approved:true},realtime_owned_enabled:true};
const device={deviceId:'usb-device',groupId:'usb-group',kind:'audioinput',label:'Example USB'};
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};}
function stream(id,groupId){
  const track={stops:0,label:id,stop(){this.stops++;},getSettings(){return {deviceId:id,groupId};}};
  return {track,getTracks:()=>[track],getAudioTracks:()=>[track]};
}
function fixture(getMedia){
  const ready=deferred();let lists=0;
  const calls=[];
  const context={window:{JarvisRealtimeOwned:{async start({signal}){await ready.promise;if(signal.aborted)throw Object.assign(new Error(),{name:'AbortError'});}}},
    AbortController,AbortSignal,setTimeout:(fn,ms)=>{const t=setTimeout(fn,ms);t.unref();return t;},clearTimeout,clearInterval,
    navigator:{mediaDevices:{enumerateDevices:async()=>++lists===1?[]:[device],getUserMedia(opts){calls.push(opts.audio.deviceId);return getMedia(calls.length);}}},
    AudioContext:class{async resume(){}createAnalyser(){return {};}createMediaStreamSource(){return {connect(){}};}},
    audioContext:null,micStream:null,running:false,wakeStatus:{preferred_microphone:'auto',microphone:'Example USB'},sessionInfo:{},statusEl:{},
    syncHud(){},async holdWakeMicrophone(){}};
  vm.createContext(context);vm.runInContext(source,context);
  return {context,ready,calls,voice:context.window.JarvisLocalVoice};
}
test('exact reopen fails, default recovers once, running waits for realtime',async()=>{
  const first=stream('default','other'),last=stream('default','other');
  const f=fixture(async n=>{if(n===2)throw Object.assign(new Error(),{name:'NotReadableError'});return n===1?first:last;});
  const start=f.voice.start(config);await settle();assert.equal(f.calls.length,3);
  assert.equal(f.calls[1].exact,'usb-device');assert.equal(f.calls[2],undefined);
  assert.equal(first.track.stops,1);assert.equal(f.context.running,false);
  f.ready.resolve();await start;assert.equal(f.context.running,true);f.voice.stop();assert.equal(last.track.stops,1);
});
test('default alias of same group stays open and stopping cancels pending session',async()=>{
  const mic=stream('default','usb-group');const f=fixture(async()=>mic);
  const start=f.voice.start(config);await settle();assert.equal(f.calls.length,1);
  f.voice.stop();f.ready.resolve();await assert.rejects(start,{name:'AbortError'});
  assert.equal(mic.track.stops,1);assert.equal(f.context.running,false);
});
test('Claude jobs still use the OpenAI realtime conversation with the owned profile',async()=>{
  const mic=stream('default','usb-group'),f=fixture(async()=>mic);
  const start=f.voice.start({...config,provider:'claude',conversation_provider:'openai'});
  await settle();assert.equal(f.context.running,false);
  f.ready.resolve();await start;assert.equal(f.context.running,true);
  f.voice.stop();assert.equal(mic.track.stops,1);
});
test('cancel during exact acquisition releases late stream without fallback',async()=>{
  const first=stream('default','other'),late=stream('usb-device','usb-group'),waiting=deferred();
  const f=fixture(async n=>n===1?first:waiting.promise);const controller=new AbortController();
  const start=f.voice.start(config,{signal:controller.signal});await settle();
  controller.abort();f.voice.stop();await assert.rejects(start,{name:'AbortError'});
  waiting.resolve(late);await settle();assert.equal(first.track.stops,1);assert.equal(late.track.stops,1);
  assert.equal(f.calls.length,2);assert.equal(f.context.micStream,null);
});

