import vm from 'node:vm';
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
test('Local models UI: exact deletion across polls, active protection, deferred activation and cancellation', async()=>{
const source=readFileSync(root+'/public/assets/local-models.js','utf8');
const ids=new Map(),calls=[],timers=new Map(),events=[];let nextTimer=0,refreshes=0;
class Element{
 constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.parentNode=null;this.listeners={};this.attributes={};this.dataset={};this._text='';this.hidden=false;this.open=false;this.disabled=false;this.value='';}
 set id(v){this._id=v;ids.set(v,this);}get id(){return this._id;}
 set textContent(v){this._text=String(v);this.replaceChildren();}get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
 set innerHTML(v){throw new Error('unsafe innerHTML');}
 get isConnected(){return this===body||!!this.parentNode?.isConnected;}
 append(...items){for(const item of items){item.remove();item.parentNode=this;this.children.push(item);}}
 replaceChildren(...items){this.children.forEach(c=>c.parentNode=null);this.children=[];this.append(...items);}
 remove(){if(this.parentNode){const p=this.parentNode;p.children.splice(p.children.indexOf(this),1);this.parentNode=null;}}
 matches(s){return s.startsWith('.')?(this.className||'').split(' ').includes(s.slice(1)):this.tagName.toLowerCase()===s;}
 querySelectorAll(s){return this.children.flatMap(c=>[...(c.matches(s)?[c]:[]),...c.querySelectorAll(s)]);}
 querySelector(s){return this.querySelectorAll(s)[0]||null;}
 setAttribute(k,v){this.attributes[k]=String(v);}removeAttribute(k){delete this.attributes[k];}
 addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);}dispatchEvent(e){for(const fn of this.listeners[e.type]||[])fn(e);}
 click(){if(!this.disabled)this.dispatchEvent({type:'click'});}focus(){document.activeElement=this;}
 showModal(){this.open=true;}close(){this.open=false;this.dispatchEvent({type:'close'});}
}
const body=new Element('body'),toolbar=new Element('div');toolbar.className='mission-toolbar';body.append(toolbar);
const document={body,readyState:'complete',activeElement:null,createElement:t=>new Element(t),getElementById:id=>ids.get(id)||null,querySelector:s=>body.querySelector(s)};
const data={installed:[{name:'qwen3:8b',bytes:5200000000,digest:'fixture'},{name:'tiny:1b',bytes:900000000,digest:'fixture2'}],available:[{id:'qwen3:8b',name:'Qwen3 8B',download_bytes:5200000000,description:'Razonamiento de prueba',memory_note:'Memoria orientativa, no garantía',source_url:'https://ollama.com/library/qwen3'},{id:'another:4b',name:'<img src=x onerror=alert(1)>',download_bytes:2700000000,description:'<script>untrusted</script>',memory_note:'Revisá la memoria de tu equipo',source_url:'javascript:alert(1)'},{id:'tiny:1b',name:'Tiny 1B',download_bytes:900000000,source_url:'https://user:pass@example.com/'}],online:true,active_model:'',provider:'openai',state:{state:'idle'}};
let nextFailure=null,pendingRead=false;
async function transport(path,options){calls.push({path,options});assert(options.signal instanceof AbortSignal);if(nextFailure){const fail=nextFailure;nextFailure=null;return {ok:false,json:async()=>fail};}if(pendingRead&&path.endsWith('/models')){pendingRead=false;return new Promise((_resolve,reject)=>options.signal.addEventListener('abort',()=>reject(Object.assign(new Error('aborted'),{name:'AbortError'})),{once:true}));}
 const payload=options.body?JSON.parse(options.body):{};
 if(path.endsWith('/prepare'))data.state={state:'pulling',model:payload.model,message:'Descarga de prueba',completed:0,total:2700000000,percent:0};
 if(path.endsWith('/select')){data.active_model=payload.model;data.provider='local';}
 if(path.endsWith('/remove')){assert.notEqual(payload.model,data.active_model);data.installed=data.installed.filter(i=>i.name!==payload.model);}
 if(path.endsWith('/cancel'))data.state={state:'cancelled',model:data.state.model,message:'Cancelado por el usuario'};
 return {ok:true,json:async()=>structuredClone(data)};
}
const windowListeners=new Map();
const window={addEventListener(type,fn){windowListeners.set(type,fn);},JarvisPC:{fetch:transport},JarvisMissions:{refreshStatus:async()=>{refreshes++;}},dispatchEvent:e=>events.push(e)};
const context={window,document,URL,AbortController,TypeError,CustomEvent:class{constructor(type,{detail}){this.type=type;this.detail=detail;}},setTimeout:(fn,ms)=>{timers.set(++nextTimer,{fn,ms});return nextTimer;},clearTimeout:id=>timers.delete(id)};
vm.createContext(context);vm.runInContext(source,context);
const api=window.JarvisLocalModels,flush=()=>new Promise(r=>setImmediate(r)),panel=()=>ids.get('jarvisLocalModelsPanel'),findButton=(container,text)=>container.querySelectorAll('button').find(b=>b.textContent===text),row=name=>panel().querySelectorAll('.local-model-installed').find(n=>n.querySelector('h4').textContent===name);
assert.equal(calls.length,0);assert(windowListeners.has('jarvis:local-models-open'));assert.equal(toolbar.children.length,1);api.init();assert.equal(toolbar.children.length,1);const launch=toolbar.children[0];launch.focus();
await api.open();assert(panel().open);assert.equal(calls.length,1);assert.equal(calls[0].path,'/api/agent/local/models');assert.equal(panel().querySelectorAll('script').length,0);assert.equal(panel().querySelectorAll('img').length,0);assert.equal(panel().querySelectorAll('a').length,1,'unsafe sources not rendered');assert.equal(panel().querySelectorAll('a')[0].rel,'noopener noreferrer');assert(panel().textContent.includes('<script>untrusted</script>'));assert(panel().textContent.includes('La voz y su perfil'));assert.equal(panel().querySelector('.local-model-current').querySelector('strong').textContent,'OpenAI');assert.equal([...timers.values()].filter(t=>t.ms===2000).length,1);
// Exact-name deletion survives background polling, and a partial name never posts.
findButton(row('tiny:1b'),'Eliminar').click();let form=panel().querySelector('form'),input=form.querySelector('input');input.value='tiny';input.dispatchEvent({type:'input'});assert(findButton(form,'Eliminar modelo').disabled);const before=calls.length;form.dispatchEvent({type:'submit',preventDefault(){}});await flush();assert.equal(calls.length,before);await api.refresh();assert.equal(panel().querySelector('input'),input);assert.equal(input.value,'tiny');input.value='tiny:1b';input.dispatchEvent({type:'input'});assert(!findButton(form,'Eliminar modelo').disabled);form.dispatchEvent({type:'submit',preventDefault(){}});await flush();assert(calls.some(c=>c.path.endsWith('/remove')&&JSON.parse(c.options.body).model==='tiny:1b'));assert(!row('tiny:1b'));
// Selection uses the backend and prevents removal of the active model.
findButton(row('qwen3:8b'),'Usar este modelo').click();await flush();assert.equal(data.active_model,'qwen3:8b');assert(findButton(row('qwen3:8b'),'Eliminar').disabled);assert(panel().querySelector('.local-model-current').textContent.includes('qwen3:8b'));
// Prepare payload has activate:true; the old active engine remains until backend ready.
const card=panel().querySelectorAll('.local-model-card').find(c=>c.querySelector('h4').textContent.startsWith('<img'));findButton(card,'Descargar y usar').click();await flush();const prepare=calls.find(c=>c.path.endsWith('/prepare'));assert.deepEqual(JSON.parse(prepare.options.body),{model:'another:4b',activate:true});assert.equal(data.active_model,'qwen3:8b');assert(panel().querySelector('.local-model-progress-detail').textContent.includes('0 B de 2,7 GB'));assert.equal(panel().querySelector('progress').value,0);
panel().close();assert.equal(document.activeElement,launch);assert.equal([...timers.values()].filter(t=>t.ms===2000).length,1,'download keeps polling after close');
data.active_model='another:4b';data.provider='local';data.installed.push({name:'another:4b',bytes:2700000000,digest:'done'});data.state={state:'ready',model:'another:4b',message:'Listo'};await api.refresh();assert.equal(timers.size,0,'closed and completed stops polling');
await api.open();assert(findButton(row('another:4b'),'Eliminar').disabled);data.state={state:'pulling',model:'x',completed:12,total:0};await api.refresh();assert.equal(panel().querySelector('progress').attributes.value,undefined);findButton(panel(),'Cancelar descarga').click();await flush();assert(calls.some(c=>c.path.endsWith('/cancel')));assert.equal(data.state.state,'cancelled');
panel().close();assert.equal(timers.size,0);assert(refreshes>=4);assert(events.every(e=>e.type==='jarvis:local-models-changed'));
// Authenticated global fallback; no raw fetch bypass, object errors remain generic.
delete window.JarvisPC.fetch;context.apiFetch=transport;await api.open();nextFailure={detail:{internal:'UNTRUSTED_OBJECT'}};await api.refresh().catch(()=>{});assert(!panel().textContent.includes('UNTRUSTED_OBJECT'));panel().close();
// Ten-second timeout aborts the request, leaves the dialog usable and cleans timers on close.
pendingRead=true;const opening=api.open();await flush();const timeout=[...timers].find(([,t])=>t.ms===10000);assert(timeout);timers.delete(timeout[0]);timeout[1].fn();await opening;assert(panel().textContent.includes('10 segundos'));panel().close();assert.equal(timers.size,0);
windowListeners.get('jarvis:local-models-open')();await flush();assert(panel().open);panel().close();assert.equal(timers.size,0);assert(calls.every(c=>c.path.startsWith('/api/agent/local/')));
console.log('PASS VM: lazy toolbar singleton; authenticated transports; safe DOM/HTTPS sources; exact-name delete survives polls; active model protected; select/prepare/cancel payloads; old model preserved until backend ready; truthful 0-byte/indeterminate progress; closed download polling and idle cleanup; focus restoration; object error safety; 10s abort; no voice/profile/cloud/mic requests.');

});
