'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../../public/assets/realtime-owned.js'),'utf8');
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(ended=false){
  const timers=new Map(),texts=[];let timerId=0,stops=0,speechRequests=0;
  const controller=new AbortController(),track=new EventTarget();
  Object.assign(track,{readyState:ended?'ended':'live',muted:false,enabled:true});
  const nodes={};
  class Peer extends EventTarget{
    constructor(){super();this.connectionState='new';}
    addTrack(){}
    createDataChannel(){this.channel=new EventTarget();Object.assign(this.channel,{readyState:'open',send(){}});return this.channel;}
    async createOffer(){return {sdp:'synthetic-offer'};}
    async setLocalDescription(){}
    async setRemoteDescription(){this.connectionState='connected';this.channel.onopen();}
    async getStats(){return new Map();}
    transition(value){this.connectionState=value;this.dispatchEvent(new Event('connectionstatechange'));}
  }
  const context={window:{addEventListener(){}},document:{getElementById:id=>nodes[id]??={}},
    crypto:{randomUUID:()=> 'test-voice-client'},Date,performance,AbortController,AbortSignal,DOMException,
    setTimeout(fn,ms){timers.set(++timerId,{fn,ms});return timerId;},clearTimeout(id){timers.delete(id);},
    setInterval(fn,ms){timers.set(++timerId,{fn,ms});return timerId;},clearInterval(id){timers.delete(id);},pc:null,dc:null,analyserIn:null,analyserOut:null,
    audioContext:{state:'running',createAnalyser(){return {connect(){},disconnect(){}};},destination:{}},
    statusEl:{},sessionInfo:{},responseInProgress:false,voiceActivityAt:0,voiceIssue:'',wakeConversation:false,
    handleEvent(){},RTCPeerConnection:Peer,
    fetch:async()=>({ok:true,text:async()=> 'synthetic-answer'}),
    apiFetch:async(url,options)=>{
      if(url==='/api/session')return {ok:true,json:async()=>({local_voice:true,client_secret:'synthetic',max_session_seconds:300})};
      if(url==='/api/speech/preparation')return {ok:true,json:async()=>({ready:true})};
      if(url==='/api/speech/stream'){speechRequests++;texts.push(JSON.parse(options.body).text);return {ok:true,headers:{get:key=>key==='X-Audio-Format'?'pcm_s16le':'24000'},body:{getReader:()=>({read:async()=>({done:true}),cancel:async()=>{}})}};}
      return {ok:true};
    },
    stop(){stops++;controller.abort();}
  };
  vm.createContext(context);vm.runInContext(source,context);
  return {context,track,controller,timers,nodes,texts,
    start:()=>context.window.JarvisRealtimeOwned.start({stream:{getTracks:()=>[track],getAudioTracks:()=>[track]},signal:controller.signal}),
    get stops(){return stops;},get speechRequests(){return speechRequests;},
    expire(ms){for(const [id,timer] of [...timers])if(timer.ms===ms&&timers.delete(id))timer.fn();}};
}
test('a brief RTC disconnect recovers without stopping and stale peers cannot stop a new session',async()=>{
  const f=fixture();await f.start();await settle();const old=f.context.pc;
  old.transition('disconnected');assert.equal(f.stops,0);
  old.transition('connected');f.expire(8000);assert.equal(f.stops,0);
  old.transition('disconnected');f.context.pc={connectionState:'connected'};f.expire(8000);
  assert.equal(f.stops,0);f.controller.abort();
});
test('persistent disconnect stops once with a visible reason',async()=>{
  const f=fixture();await f.start();f.context.pc.transition('disconnected');f.expire(8000);
  assert.equal(f.stops,1);assert.match(f.context.voiceIssue,/recuperar la conexión/);f.expire(8000);assert.equal(f.stops,1);
});
test('dead input prevents the greeting and ending a live input reports a microphone fault',async()=>{
  const dead=fixture(true);await dead.start();await settle();assert.equal(dead.speechRequests,0);assert.equal(dead.stops,1);
  const f=fixture();await f.start();f.track.readyState='ended';f.track.dispatchEvent(new Event('ended'));
  assert.equal(f.stops,1);assert.match(f.context.voiceIssue,/micrófono dejó de estar disponible/);
});
test('temporary mute recovers; persistent mute produces an explicit input failure',async()=>{
  const f=fixture();await f.start();f.track.muted=true;f.track.dispatchEvent(new Event('mute'));
  f.track.muted=false;f.track.dispatchEvent(new Event('unmute'));f.expire(12000);assert.equal(f.stops,0);
  f.track.muted=true;f.track.dispatchEvent(new Event('mute'));f.expire(12000);assert.equal(f.stops,1);
  assert.match(f.context.voiceIssue,/dejó de entregar audio/);
});
test('closing the events channel is detected even when the peer remains connected',async()=>{
  const f=fixture();await f.start();assert.equal(f.context.pc.connectionState,'connected');
  f.context.dc.dispatchEvent(new Event('close'));assert.equal(f.stops,1);
  assert.match(f.context.voiceIssue,/canal de conversación/);
});
test('SDP negotiation has its own deadline before the channel opening deadline begins',async()=>{
  const f=fixture();let release;
  f.context.fetch=()=>new Promise(resolve=>{release=()=>resolve({ok:true,text:async()=> 'synthetic-answer'});});
  const waiting=f.start();await settle();
  assert.equal([...f.timers.values()].some(timer=>timer.ms===15000),false);
  release();await waiting;assert.equal(f.stops,0);f.controller.abort();
});

test('credit exhaustion during SDP negotiation explains billing and never plays the greeting',async()=>{
  const f=fixture();
  f.context.fetch=async()=>({ok:false,status:429,text:async()=>JSON.stringify({error:{type:'insufficient_quota',code:'credit_balance_exhausted',message:'private provider detail'}})});
  await assert.rejects(f.start(),error=>error.quotaBlocked&&error.code==='credit_balance_exhausted'&&/sin crédito/.test(error.message)&&!error.message.includes('private'));
  assert.equal(f.speechRequests,0);
  assert.equal(f.context.window.JarvisOpenAIError.canAutoStart(),false);
  f.controller.abort();
});

test('billing failures returned by the companion use the same safe message',async()=>{
  const f=fixture(),original=f.context.apiFetch;
  f.context.apiFetch=async(url,options)=>url==='/api/session'?{ok:false,status:429,json:async()=>({detail:'OpenAI: '+JSON.stringify({error:{code:'credit_balance_exhausted',type:'insufficient_quota'}})})}:original(url,options);
  await assert.rejects(f.start(),error=>error.quotaBlocked&&/Recargá/.test(error.message));
  assert.equal(f.speechRequests,0);f.controller.abort();
});

test('temporary throttling respects Retry-After and does not claim credit exhaustion',()=>{
  const f=fixture(),helper=f.context.window.JarvisOpenAIError;let now=1000;
  f.context.Date={now:()=>now};
  const error=helper.fromResponse(429,{error:{code:'rate_limit_exceeded'}},{get:name=>name==='Retry-After'?'90':null});
  assert.equal(error.quotaBlocked,false);assert.match(error.message,/90 segundos/);assert.doesNotMatch(error.message,/sin crédito/);
  assert.equal(helper.canAutoStart(),false);now+=90001;assert.equal(helper.canAutoStart(),true);
});

test('spend limits and ambiguous 429 responses are not misreported as empty balance',()=>{
  const f=fixture(),helper=f.context.window.JarvisOpenAIError;
  const spend=helper.fromResponse(429,{error:{type:'insufficient_quota',code:'project_spend_limit_exceeded'}});
  assert.equal(spend.quotaBlocked,true);assert.match(spend.message,/límite de gasto/);
  helper.reset();assert.equal(helper.canAutoStart(),true);
  const unknown=helper.fromResponse(429,'upstream returned non-JSON');
  assert.equal(unknown.quotaBlocked,false);assert.doesNotMatch(unknown.message,/sin crédito/);
});

test('HTTP-date Retry-After is respected and an OpenAI quota does not block local conversation',()=>{
  const f=fixture(),helper=f.context.window.JarvisOpenAIError;
  const now=Date.parse('2026-11-25T15:00:00Z');
  f.context.Date={now:()=>now,parse:Date.parse};
  assert.match(helper.fromResponse(429,{}, {get:()=> 'Wed, 25 Nov 2026 15:02:00 GMT'}).message,/120 segundos/);
  helper.fromResponse(429,{error:{code:'credit_balance_exhausted'}});
  helper.setConfig({voice_mode:'owned',conversation_provider:'local',realtime_owned_enabled:true});
  assert.equal(helper.canAutoStart(),true);
  helper.setConfig({voice_mode:'owned',conversation_provider:'openai',realtime_owned_enabled:true});
  assert.equal(helper.canAutoStart(),false);
});

test('billing errors on an established session release capture and block automatic activation',async()=>{
  const f=fixture();await f.start();
  f.context.window.JarvisRealtimeOwned.event({type:'error',error:{code:'credit_balance_exhausted',type:'insufficient_quota'}});
  assert.equal(f.stops,1);assert.match(f.context.voiceIssue,/sin crédito/);
  assert.equal(f.context.window.JarvisOpenAIError.canAutoStart(),false);
});

test('wake detection releases its microphone lease without retrying a billing-blocked connection',async()=>{
  const html=fs.readFileSync(path.join(__dirname,'../../index.html'),'utf8');
  const code=html.slice(html.indexOf('async function pollWake(){'),html.indexOf('function recordVoiceActivity(ev)'));
  let started=0,released=0;
  const context={wakePolling:false,onlineInterface:false,pcPairingToken:'',wakeClient:'test',running:false,starting:false,wakeHeld:false,listeningEnabled:true,
    document:{hidden:false,hasFocus:()=>true},wakeJson:async()=>({activate:true}),renderWakeStatus(){},
    window:{JarvisOpenAIError:{canAutoStart:()=>false}},releaseWakeMicrophone:async()=>{released++;},start:()=>{started++;}};
  vm.createContext(context);vm.runInContext(code,context);await context.pollWake();
  assert.equal(started,0);assert.equal(released,1);assert.equal(context.wakePolling,false);
});
test('late RTP statistics from a replaced session are discarded',async()=>{
  const f=fixture(),reports=[];const transport=f.context.apiFetch;
  f.context.apiFetch=async(url,options)=>{if(url==='/api/voice/diagnostics')reports.push(JSON.parse(options.body));return transport(url,options);};
  await f.start();let release;
  f.context.pc.getStats=()=>new Promise(resolve=>{release=()=>resolve(new Map([['old',{type:'outbound-rtp',kind:'audio',bytesSent:999999,packetsSent:999}]]));});
  f.expire(1500);await settle();await f.start();
  release();await settle();assert.equal(reports.length,0);
  f.expire(1500);await settle();assert.equal(reports.length,1);
  assert.equal(reports[0].counts.outbound_bytes,undefined);f.controller.abort();
});
test('a cancelled response cannot update activity or clear the next response state',async()=>{
  const f=fixture();await f.start();const owned=f.context.window.JarvisRealtimeOwned;
  owned.event({type:'response.created',response:{id:'old-response'}});
  owned.event({type:'input_audio_buffer.speech_started'});
  owned.event({type:'response.created',response:{id:'new-response'}});
  const html=fs.readFileSync(path.join(__dirname,'../../index.html'),'utf8');
  const start=html.indexOf('function handleEvent(ev,channel=dc)');
  const prefix=html.slice(start,html.indexOf('  // GA renamed',start))+'}';
  let recorded=0;f.context.recordVoiceActivity=()=>recorded++;
  vm.runInContext(prefix,f.context);
  f.context.handleEvent({type:'response.done',response:{id:'old-response',status:'cancelled'}});
  assert.equal(recorded,0);assert.equal(f.context.responseInProgress,true);f.controller.abort();
});
test('idle timeout does not cut startup or a long user utterance',()=>{
  const html=fs.readFileSync(path.join(__dirname,'../../index.html'),'utf8');
  const activity=html.slice(html.indexOf('function recordVoiceActivity(ev)'),html.indexOf("window.addEventListener('jarvis:agent-status',event=>{",html.indexOf('function recordVoiceActivity(ev)')));
  let idle,stops=0,now=0;
  const c={Date:{now:()=>now},tasksEl:{querySelector:()=>null},running:true,starting:true,userSpeaking:false,responseInProgress:false,voiceActivityAt:0,transcriptEl:{},setInterval(fn){idle=fn;},stop(){stops++;}};
  vm.createContext(c);vm.runInContext(activity,c);
  now=30000;idle();assert.equal(stops,0);
  c.starting=false;c.recordVoiceActivity({type:'input_audio_buffer.speech_started'});
  now=70000;idle();assert.equal(stops,0);
  c.recordVoiceActivity({type:'input_audio_buffer.speech_stopped'});now=94000;idle();assert.equal(stops,0);
  now=96000;idle();assert.equal(stops,1);
});
