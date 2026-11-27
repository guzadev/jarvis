'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm');
const fs=require('node:fs'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../../index.html'),'utf8');

test('hiding or closing an armed UI stops conversation and releases wake permission',()=>{
  const callbacks={},calls=[];let stops=0;
  const context={listeningEnabled:true,listeningRevision:0,pairingOnly:false,running:true,starting:false,wakeClient:'fixture',
    document:{hidden:false,addEventListener:(name,fn)=>callbacks[name]=fn},window:{addEventListener:(name,fn)=>callbacks[name]=fn},
    stop(){stops++;context.running=false;context.starting=false;},
    wakeJson:(url,body,options)=>{calls.push({url,body,options});return Promise.resolve({});}};
  vm.createContext(context);
  vm.runInContext(html.slice(html.indexOf('function suspendListening(){'),html.indexOf('setInterval(pollWake,1000)')),context);
  callbacks.visibilitychange();assert.equal(stops,0);
  context.document.hidden=true;callbacks.visibilitychange();
  assert.equal(stops,1);assert.equal(context.listeningEnabled,false);
  assert.equal(calls[0].url,'/api/wake/config');assert.equal(calls[0].body.enabled,false);
  assert.equal(calls[1].body.foreground,false);assert.equal(calls[1].body.active,false);
  assert.ok(calls.every(call=>call.options.keepalive));
  callbacks.pagehide();assert.equal(stops,1,'already disabled windows do not change another active UI');
  context.listeningEnabled=true;context.starting=true;callbacks['jarvis:suspend']();
  assert.equal(stops,2);assert.equal(context.listeningEnabled,false);
});

test('the Off button stops a live session before waiting for any network response',async()=>{
  const events=[],nodes={};let release;
  const context={listeningEnabled:true,listeningRevision:0,running:true,starting:false,document:{hidden:false,getElementById:id=>nodes[id]??={}},
    stop(){events.push('stop');context.running=false;},
    wakeJson:()=>new Promise(resolve=>{events.push('request');release=resolve;}),renderWakeStatus(){},addCard(){}};
  vm.createContext(context);
  vm.runInContext(html.slice(html.indexOf('async function configureWake('),html.indexOf('document.getElementById("wakeToggle").addEventListener')),context);
  const result=context.configureWake(false);
  assert.equal(context.listeningEnabled,false);assert.deepEqual(events,['stop','request']);
  release({enabled:false});await result;
});

test('an old enable response cannot undo a later suspension or Off click',async()=>{
  const nodes={},pending=[];
  const context={listeningEnabled:false,listeningRevision:0,pairingOnly:false,running:false,starting:false,wakeClient:'fixture',
    document:{hidden:false,hasFocus:()=>true,getElementById:id=>nodes[id]??={},addEventListener(){}},window:{addEventListener(){}},
    stop(){},wakeJson:(url,body)=>url==='/api/wake/config'&&body.enabled?new Promise(resolve=>pending.push(resolve)):Promise.resolve({enabled:false}),renderWakeStatus(){},addCard(){}};
  vm.createContext(context);
  vm.runInContext(html.slice(html.indexOf('async function configureWake('),html.indexOf('document.getElementById("wakeToggle").addEventListener')),context);
  vm.runInContext(html.slice(html.indexOf('function suspendListening(){'),html.indexOf('setInterval(pollWake,1000)')),context);
  const enable=context.configureWake(true);
  context.suspendListening();context.document.hidden=false;
  pending[0]({enabled:true});assert.equal(await enable,false);assert.equal(context.listeningEnabled,false);
});

test('a microphone granted after cancelling startup is stopped before any cloud session',async()=>{
  const nodes={},requests=[];let grant,stopped=0;
  const context={AbortController,AbortSignal,voiceAttempt:0,voiceStartup:null,voiceIssue:'',listeningEnabled:true,
    running:false,starting:false,onlineInterface:false,audioContext:null,wakeStatus:null,
    document:{hidden:false,getElementById:id=>nodes[id]??={}},window:{},statusEl:{},sessionInfo:{},
    navigator:{mediaDevices:{enumerateDevices:async()=>[],getUserMedia:()=>new Promise(resolve=>{grant=resolve;})}},
    syncHud(){},holdWakeMicrophone:async()=>{},
    apiFetch:async url=>{requests.push(url);return {ok:true,json:async()=>({voice_mode:'openai',ready:true})};},
    stop(){context.voiceAttempt++;context.voiceStartup?.abort();context.starting=false;context.running=false;}};
  vm.createContext(context);vm.runInContext(html.slice(html.indexOf('async function start() {'),html.indexOf('\nfunction stop() {')),context);
  const startup=context.start();await new Promise(resolve=>setImmediate(resolve));assert.equal(typeof grant,'function');
  context.stop();grant({getTracks:()=>[{stop(){stopped++;}}]});await startup;
  assert.equal(stopped,1);assert.deepEqual(requests,['/api/agent/status']);assert.equal(context.running,false);
});

test('a pairing popup can finish without starting voice while the page lacks focus',async()=>{
  const nodes={},callbacks={};let finishPairing,requests=0;
  const context={AbortController,AbortSignal,voiceAttempt:0,voiceStartup:null,voiceIssue:'',listeningEnabled:false,listeningRevision:0,pairingOnly:false,
    running:false,starting:false,onlineInterface:true,audioContext:null,pcPairingToken:'',
    document:{hidden:false,hasFocus:()=>false,getElementById:id=>nodes[id]??={},addEventListener(){}},
    window:{JarvisPC:{connect:()=>new Promise(resolve=>{finishPairing=resolve;})},addEventListener:(event,fn)=>callbacks[event]=fn},
    navigator:{},statusEl:{},sessionInfo:{},syncHud(){},rememberPcPairing(){},
    apiFetch:async()=>{requests++;throw new Error('Voice must stay off');},stop(){throw new Error('Pairing was cancelled by blur');}};
  vm.createContext(context);
  vm.runInContext(html.slice(html.indexOf('async function start() {'),html.indexOf('\nfunction stop() {')),context);
  vm.runInContext(html.slice(html.indexOf('function suspendListening(){'),html.indexOf('setInterval(pollWake,1000)')),context);
  const start=context.start();callbacks.blur();finishPairing('paired-fixture');await start;
  assert.equal(requests,0);assert.equal(context.listeningEnabled,false);assert.equal(context.starting,false);
  assert.match(context.statusEl.textContent,/PC conectada/);
});
