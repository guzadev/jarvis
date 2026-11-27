'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

test('a generated summary keeps the API card and its attribution; new turns can show new cards',()=>{
  const html=fs.readFileSync(path.join(__dirname,'../../index.html'),'utf8');
  const rendered=[],outputs=[],channel={readyState:'open',jarvisDataTurn:7};
  const owned={turn:7,event(){return false;},ignoresEvent(){return false;}};
  const c={dc:channel,recordVoiceActivity(){},toolOutput(_id,value){outputs.push(value);},
    window:{JarvisRealtimeOwned:owned,JarvisData:{render(value){rendered.push(value);}}}};
  vm.createContext(c);
  vm.runInContext(html.slice(html.indexOf('function handleEvent(ev,channel=dc)'),html.indexOf('let dataChoiceContext=null;')),c);
  const show=kind=>c.handleEvent({type:'response.function_call_arguments.done',name:'display_card',call_id:'fixture',arguments:JSON.stringify({title:'Acciones',content:'Resumen generado',kind})},channel);
  show('info');assert.equal(rendered.length,0);assert.equal(outputs[0].status,'displayed');
  show('warning');assert.equal(rendered.length,1);
  owned.turn=8;show('info');assert.equal(rendered.length,2);
});

test('an APOD open_url defaults to the internal NASA API panel; external navigation must be explicit',()=>{
  const html=fs.readFileSync(path.join(__dirname,'../../index.html'),'utf8'),queries=[],opened=[];
  const channel={readyState:'open'},context={URL,dc:channel,recordVoiceActivity(){},
    window:{},queryAndDisplayData:(...args)=>queries.push(args),openTarget:(...args)=>opened.push(args)};
  vm.createContext(context);vm.runInContext(html.slice(html.indexOf('function handleEvent(ev,channel=dc)'),html.indexOf('let dataChoiceContext=null;')),context);
  const invoke=args=>context.handleEvent({type:'response.function_call_arguments.done',name:'open_url',call_id:'fixture',arguments:JSON.stringify(args)},channel);
  const url='https://science.nasa.gov/image-article/apod-2026-november-25-spherex-seeing-through-dust/';
  invoke({url});assert.equal(queries[0][1],'get_astronomy');assert.equal(queries[0][2].date,'2026-11-25');assert.equal(opened.length,0);
  invoke({url,external:true});assert.equal(opened.length,1);
  invoke({url:'https://www.nasa.gov/'});assert.equal(opened.length,2);
  assert.equal(context.astronomyRequestFromURL('https://science.nasa.gov.attacker.example/apod/'),null);
  assert.equal(context.astronomyRequestFromURL('https://apod.nasa.gov/apod/ap951201.html').date,'1995-12-01');
});
