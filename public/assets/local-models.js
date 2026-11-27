/* Local reasoning models. All downloads and model changes run in the authenticated PC service. */
(() => {
  'use strict';
  if (window.JarvisLocalModels) return;
  const ACTIVE = new Set(['downloading', 'installing', 'pulling']);
  const TERMINAL = new Set(['idle', 'ready', 'error', 'cancelled']);
  const LABELS = {idle:'En espera',downloading:'Descargando',installing:'Instalando componentes',pulling:'Descargando modelo',ready:'Preparado',error:'Necesita atención',cancelled:'Descarga cancelada'};
  const state = {panel:null,notice:null,summary:null,progress:null,progressTitle:null,progressDetail:null,progressBar:null,cancel:null,lists:null,data:null,listKey:'',timer:null,loading:null,busy:false,tracking:false,readError:false,confirmation:null,returnFocus:null};
  const node = (tag,cls,text) => {const item=document.createElement(tag);if(cls)item.className=cls;if(text!==undefined)item.textContent=String(text);return item;};
  const button = (text,handler,cls='local-model-button') => {const item=node('button',cls,text);item.type='button';item.addEventListener('click',handler);return item;};
  const bytes = value => {const amount=Number(value);if(!Number.isFinite(amount)||amount<0)return 'Tamaño no informado';if(amount===0)return '0 B';if(amount>=1e9)return `${(amount/1e9).toLocaleString('es-AR',{maximumFractionDigits:2})} GB`;if(amount>=1e6)return `${(amount/1e6).toLocaleString('es-AR',{maximumFractionDigits:1})} MB`;return `${Math.ceil(amount/1e3)} KB`;};
  const modelName = item => typeof item?.name==='string'?item.name:'';
  function officialURL(value){try{if(typeof value!=='string'||/[\u0000-\u001f\u007f]/.test(value))return null;const url=new URL(value);return url.protocol==='https:'&&url.hostname&&!url.username&&!url.password?url.href:null;}catch{return null;}}
  function active(){return typeof state.data?.active_model==='string'?state.data.active_model:'';}
  function downloading(){return state.tracking||ACTIVE.has(state.data?.state?.state);}
  function notice(text='',kind='info'){ensure();state.notice.textContent=text;state.notice.dataset.kind=kind;state.notice.hidden=!text;}
  async function api(action='',body){
    const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),10000);
    try{
      const transport=typeof window.JarvisPC?.fetch==='function'?window.JarvisPC.fetch.bind(window.JarvisPC):typeof apiFetch==='function'?apiFetch:null;
      if(!transport)throw new Error('Conectá Jarvis con el compañero de esta PC para administrar los modelos.');
      const response=await transport('/api/agent/local/'+(action||'models'),{signal:controller.signal,...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
      let result;try{result=await response.json();}catch{throw new Error('El compañero no devolvió una respuesta válida.');}
      if(!response.ok)throw new Error(typeof result?.detail==='string'?result.detail:'No pude completar la operación en esta PC.');
      return result;
    }catch(error){if(error?.name==='AbortError'||controller.signal.aborted)throw new Error('La PC tardó más de 10 segundos en responder. Podés actualizar el estado; una descarga ya iniciada puede seguir trabajando.');if(error instanceof TypeError)throw new Error('No pude conectar con el compañero de esta PC. Revisá que Jarvis esté abierto y reintentá.');throw error;}
    finally{clearTimeout(timeout);}
  }
  function ensure(){
    if(state.panel)return;
    const panel=state.panel=node('dialog','jarvis-local-models');panel.id='jarvisLocalModelsPanel';panel.setAttribute('aria-labelledby','jarvisLocalModelsTitle');panel.setAttribute('aria-describedby','jarvisLocalModelsIntro');
    const header=node('header','local-model-header'),copy=node('div');copy.append(node('p','local-model-eyebrow','JARVIS / RAZONAMIENTO LOCAL'));const title=node('h2','','Modelos locales');title.id='jarvisLocalModelsTitle';copy.append(title);
    const close=button('×',()=>panel.close(),'local-model-close');close.setAttribute('aria-label','Cerrar modelos locales');header.append(copy,close);
    const intro=node('p','local-model-intro','Elegí qué modelo usar para razonar y ejecutar tareas en esta PC. La voz y su perfil se configuran por separado.');intro.id='jarvisLocalModelsIntro';
    state.summary=node('div','local-model-current');state.summary.setAttribute('aria-live','polite');
    state.notice=node('p','local-model-notice');state.notice.hidden=true;state.notice.setAttribute('role','status');
    const progress=state.progress=node('section','local-model-progress');progress.hidden=true;progress.setAttribute('aria-labelledby','localModelProgressTitle');const top=node('div','local-model-progress-top');state.progressTitle=node('h3');state.progressTitle.id='localModelProgressTitle';state.cancel=button('Cancelar descarga',()=>operate('cancel',{}),'local-model-button local-model-secondary');top.append(state.progressTitle,state.cancel);state.progressDetail=node('p','local-model-progress-detail');state.progressBar=node('progress');state.progressBar.max=100;state.progressBar.setAttribute('aria-label','Progreso de preparación del modelo');progress.append(top,state.progressDetail,state.progressBar);
    state.lists=node('div','local-model-sections');const footer=node('footer','local-model-footer');footer.append(node('p','','Las descargas y el almacenamiento se realizan en esta PC. Los tamaños son aproximados y la memoria indicada depende del uso y del equipo.'),button('Actualizar estado',()=>refresh().catch(()=>{}),'local-model-text-button'));
    panel.append(header,intro,state.summary,state.notice,progress,state.lists,footer);
    panel.addEventListener('close',()=>{state.confirmation=null;state.listKey='';if(!downloading()){clearTimeout(state.timer);state.timer=null;}if(state.returnFocus?.isConnected)state.returnFocus.focus();});
    document.body.append(panel);
  }
  function schedule(){clearTimeout(state.timer);state.timer=null;if(state.panel?.open||downloading())state.timer=setTimeout(()=>{state.timer=null;refresh().catch(()=>{});},2000);}
  async function refresh(){
    if(state.loading)return state.loading;
    state.loading=(async()=>{try{const data=await api();if(!data||!Array.isArray(data.installed)||!Array.isArray(data.available))throw new Error('La PC no devolvió un catálogo de modelos válido.');const wasPreparing=downloading();state.data=data;if(TERMINAL.has(data.state?.state))state.tracking=false;if(state.readError){state.readError=false;notice();}render();if(wasPreparing&&data.state?.state==='ready'){Promise.resolve(window.JarvisMissions?.refreshStatus?.()).catch(()=>{});window.dispatchEvent(new CustomEvent('jarvis:local-models-changed',{detail:{action:'ready',model:data.state.model||data.active_model||null}}));}return data;}catch(error){state.readError=true;notice(error.message,'error');throw error;}finally{state.loading=null;schedule();}})();
    return state.loading;
  }
  function render(){
    ensure();const data=state.data;if(!data)return;
    const provider={openai:'OpenAI',claude:'Claude Code',local:'Local'}[data.provider]||'Sin información';state.summary.replaceChildren(node('span','local-model-current-label','MOTOR DE TAREAS ACTUAL'),node('strong','',data.provider==='local'?(active()||'Local'):provider),node('span','local-model-connection',data.online?'Servicio local disponible':'Servicio local sin conexión'));
    const task=data.state||{},isActive=ACTIVE.has(task.state),hasProgress=isActive||['error','cancelled','ready'].includes(task.state);state.progress.hidden=!hasProgress;state.progress.dataset.state=task.state||'idle';
    state.progressTitle.textContent=`${LABELS[task.state]||'Estado'}${task.model?' · '+task.model:''}`;
    const completed=Number(task.completed),total=Number(task.total),percent=task.percent==null?NaN:Number(task.percent);const known=Number.isFinite(percent)?percent:Number.isFinite(total)&&total>0&&Number.isFinite(completed)?completed/total*100:NaN;
    const details=[typeof task.message==='string'?task.message:''];if(total>0&&completed>=0)details.push(`${bytes(completed)} de ${bytes(total)}`);if(Number.isFinite(known))details.push(`${Math.round(Math.max(0,Math.min(100,known)))} %`);state.progressDetail.textContent=details.filter(Boolean).join(' · ');
    if(Number.isFinite(known))state.progressBar.value=Math.max(0,Math.min(100,known));else state.progressBar.removeAttribute('value');state.progressBar.hidden=!isActive;state.cancel.hidden=!isActive;state.cancel.disabled=state.busy;
    const key=JSON.stringify([data.installed,data.available,data.active_model,data.provider,state.busy,isActive]);if(key!==state.listKey&&!state.confirmation){state.listKey=key;renderLists();}
  }
  function section(title,description){const item=node('section','local-model-section');item.append(node('h3','',title),node('p','local-model-section-intro',description));return item;}
  function renderLists(){
    state.lists.replaceChildren();const data=state.data,locked=state.busy||downloading(),installed=section('En esta PC','Podés cambiar de modelo o liberar el espacio de uno que ya no uses.');
    if(!data.installed.length)installed.append(node('p','local-model-empty','Todavía no hay modelos de razonamiento instalados. Elegí uno del catálogo para descargarlo.'));
    for(const item of data.installed){const name=modelName(item);if(!name)continue;const row=node('article','local-model-installed'),info=node('div','local-model-installed-info');info.append(node('h4','',name),node('p','local-model-size',bytes(item.bytes)));const actions=node('div','local-model-actions');if(name===active()){const chosen=node('span','local-model-selected','En uso');chosen.setAttribute('aria-label','Modelo de razonamiento activo');actions.append(chosen);}else{const select=button('Usar este modelo',()=>operate('select',{model:name}));select.disabled=locked;actions.append(select);}const remove=button('Eliminar',()=>confirmRemove(row,name,remove),'local-model-text-button local-model-danger');remove.disabled=locked||name===active();if(name===active())remove.title='Cambiá de modelo antes de eliminarlo.';actions.append(remove);row.append(info,actions);installed.append(row);}
    const catalog=section('Descargar otro modelo','Los archivos se obtienen desde la fuente indicada. El motor actual se conserva hasta completar la preparación.');const cards=node('div','local-model-catalog');
    for(const item of data.available){if(typeof item?.id!=='string'||!item.id)continue;const card=node('article','local-model-card'),heading=node('div','local-model-card-heading');heading.append(node('h4','',item.name||item.id),node('span','local-model-size',item.download_bytes?`≈ ${bytes(item.download_bytes)}`:'Tamaño no informado'));card.append(heading);if(item.description)card.append(node('p','local-model-description',item.description));if(item.memory_note)card.append(node('p','local-model-memory',item.memory_note));const link=officialURL(item.source_url);if(link){const source=node('a','local-model-source','Ver fuente de descarga ↗');source.href=link;source.target='_blank';source.rel='noopener noreferrer';card.append(source);}const exists=data.installed.some(inst=>modelName(inst)===item.id);const install=button(exists?(active()===item.id?'En uso':'Usar modelo instalado'):'Descargar y usar',()=>operate(exists?'select':'prepare',exists?{model:item.id}:{model:item.id,activate:true}));install.disabled=locked||active()===item.id;card.append(install);cards.append(card);}
    if(!cards.children.length)cards.append(node('p','local-model-empty','El catálogo no está disponible. Actualizá el estado para volver a consultar.'));catalog.append(cards);state.lists.append(installed,catalog);
  }
  function confirmRemove(row,name,trigger){
    if(state.busy||downloading())return;if(state.confirmation){state.confirmation.box.remove();state.confirmation=null;}
    const box=node('form','local-model-confirm'),title=node('h5','','Eliminar '+name);title.id='localModelDeleteTitle';box.setAttribute('aria-labelledby',title.id);const explanation=node('p','','Se eliminarán los archivos de este modelo de razonamiento en esta PC. Podrás descargarlo otra vez.');const label=node('label','','Para confirmar, escribí el nombre exacto: '+name),input=node('input');input.type='text';input.autocomplete='off';input.spellcheck=false;input.setAttribute('aria-label','Nombre exacto del modelo a eliminar');label.append(input);const actions=node('div','local-model-actions'),remove=node('button','local-model-button local-model-destructive','Eliminar modelo');remove.type='submit';remove.disabled=true;const cancel=button('Conservar',()=>{box.remove();state.confirmation=null;state.listKey='';render();trigger.isConnected&&trigger.focus();},'local-model-text-button');actions.append(cancel,remove);box.append(title,explanation,label,actions);row.append(box);state.confirmation={box,name};input.addEventListener('input',()=>remove.disabled=input.value!==name||state.busy);box.addEventListener('submit',event=>{event.preventDefault();if(input.value!==name||state.busy)return;if(active()===name){notice('Este modelo está en uso. Cambiá a otro antes de eliminarlo.','error');return;}state.confirmation=null;operate('remove',{model:name});});input.focus();
  }
  async function operate(action,payload){
    if(state.busy)return;if(action==='remove'&&active()===payload.model){notice('Cambiá de modelo antes de eliminar el que está en uso.','error');return;}
    state.busy=true;state.readError=false;state.listKey='';render();notice({prepare:'Solicitando la descarga. El motor actual se conserva hasta que el modelo esté preparado.',select:'Cambiando el motor de tareas…',remove:'Eliminando los archivos del modelo…',cancel:'Solicitando la cancelación…'}[action]||'Actualizando…');
    try{await api(action,payload);if(action==='prepare')state.tracking=true;notice({prepare:'Preparación solicitada. Podés cerrar esta ventana y volver a revisar el avance.',select:'Modelo de razonamiento seleccionado.',remove:'Modelo eliminado de esta PC.',cancel:'Cancelación solicitada.'}[action]);await refresh();await Promise.resolve(window.JarvisMissions?.refreshStatus?.()).catch(()=>{});window.dispatchEvent(new CustomEvent('jarvis:local-models-changed',{detail:{action,model:payload.model||null}}));}
    catch(error){notice(error.message,'error');if(action==='prepare')state.tracking=true;schedule();}
    finally{state.busy=false;state.listKey='';render();}
  }
  async function open(){ensure();init();if(!state.panel.open){state.returnFocus=document.activeElement;state.panel.showModal();}if(!state.data)notice('Consultando los modelos de esta PC…');try{await refresh();if(state.notice.textContent==='Consultando los modelos de esta PC…')notice();}catch{}return state.data;}
  function init(){const toolbar=document.querySelector('.mission-toolbar');if(toolbar&&!document.getElementById('manageLocalModels')){const launch=button('Modelos locales ↗',open,'quick-action local-models-launch');launch.id='manageLocalModels';toolbar.append(launch);}}
  window.JarvisLocalModels={open,refresh,init};
  window.addEventListener('jarvis:local-models-open',()=>{open().catch(()=>{});});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
