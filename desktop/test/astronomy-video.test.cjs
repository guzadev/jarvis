'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm');
const fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../../public/assets/data-results.js'),'utf8');
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(){
  const calls=[],revoked=[];let created=0;
  class Element{
    constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.attributes={};this.listeners={};this._text='';}
    append(...nodes){for(const node of nodes){node.parentNode=this;this.children.push(node);}}
    replaceChildren(...nodes){this.children=[];this.append(...nodes);}
    set textContent(value){this._text=String(value);this.children=[];}
    get textContent(){return this._text+this.children.map(child=>child.textContent).join('');}
    setAttribute(name,value){this.attributes[name]=value;}
    removeAttribute(name){delete this.attributes[name];if(name==='src')this.src='';}
    addEventListener(name,fn){this.listeners[name]=fn;}
    pause(){this.paused=true;}
    async play(){this.played=true;}
    click(){return this.listeners.click?.();}
  }
  const body=new Element('body');
  const document={body,createElement:tag=>new Element(tag),createTextNode:value=>Object.assign(new Element('text'),{textContent:value})};
  class MediaURL extends URL{
    static createObjectURL(){return 'blob:fixture-'+(++created);}
    static revokeObjectURL(value){revoked.push(value);}
  }
  const window={addEventListener(){},JarvisPC:{fetch:async(url,options)=>{calls.push({url,options});return window.response;}}};
  const context={window,document,URL:MediaURL,Date,AbortController,AbortSignal,setTimeout,clearTimeout};
  vm.createContext(context);vm.runInContext(source,context);
  const all=(tag,node=body)=>[...(node.tag===tag?[node]:[]),...node.children.flatMap(child=>all(tag,child))];
  return {data:window.JarvisData,window,calls,revoked,all,get created(){return created;}};
}
const apod={status:'ok',kind:'astronomy',title:'NASA video',source:'NASA APOD',
  image:{url:'https://assets.science.nasa.gov/poster.png',credit:'NASA fixture',role:'poster'},
  video:{url:'https://assets.science.nasa.gov/movie.mp4',date:'2026-11-25'}};

test('NASA video keeps its poster and does not download until explicitly played',async()=>{
  const f=fixture();f.data.render(apod);
  const movie=f.all('video')[0];assert.equal(movie.poster,apod.image.url);assert.equal(f.calls.length,0);
  f.window.response={ok:true,headers:{get:()=> 'video/mp4'},blob:async()=>({})};
  await f.all('button').find(node=>node.textContent==='Reproducir video aquí').click();
  assert.equal(f.calls[0].url,'/api/data/astronomy/video?date=2026-11-25');
  assert.equal(movie.src,'blob:fixture-1');assert.equal(movie.controls,true);assert.equal(movie.played,true);
  f.data.close();assert.equal(movie.paused,true);assert.deepEqual(f.revoked,['blob:fixture-1']);
});

test('closing or replacing APOD cancels a pending video and discards its late response',async()=>{
  for(const close of [true,false]){
    const f=fixture();let finish;
    f.window.response={ok:true,headers:{get:()=> 'video/mp4'},blob:()=>new Promise(resolve=>{finish=resolve;})};
    f.data.render(apod);
    const clicked=f.all('button').find(node=>node.textContent==='Reproducir video aquí').click();await settle();
    if(close)f.data.close();else f.data.render({status:'ok',title:'Another date',image:{url:'https://assets.science.nasa.gov/photo.jpg'}});
    assert.equal(f.calls[0].options.signal.aborted,true);finish({});await clicked;
    assert.equal(f.created,0);
    if(!close)assert.equal(f.data.lastResult.title,'Another date');
  }
});

test('an unavailable movie leaves the poster and a retry action on the existing card',async()=>{
  const f=fixture();f.data.render(apod);
  f.window.response={ok:false,json:async()=>({detail:'NASA no devolvió el video.'})};
  const button=f.all('button').find(node=>node.textContent==='Reproducir video aquí');await button.click();
  assert.equal(f.all('video')[0].poster,apod.image.url);assert.equal(button.disabled,false);
  assert.equal(button.textContent,'Reintentar video aquí');assert.equal(f.created,0);
});
