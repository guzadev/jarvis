/* Jarvis actions: one current operation, isolated from voice and the reactor. */
(() => {
  'use strict';
  if (window.JarvisMissions) return;
  const ACTIVE = new Set(['queued', 'running', 'awaiting_approval']);
  const LABELS = {queued:'En cola',running:'Ejecutando',awaiting_approval:'Necesita tu aprobación',done:'Completada',error:'Error',cancelled:'Cancelada',interrupted:'Interrumpida'};
  const MODELS = ['gpt-5.4-mini','gpt-6.2-sol','gpt-6.2-astra'];
  const state = {initialized:false,projects:[],selected:'aurelio',currentId:null,agent:null,connected:false,items:new Map(),rendered:new Map(),decisions:new Set(),waiters:new Map(),loading:false,sending:false,saving:false,timer:null,statusTimer:null};
  const $ = id => document.getElementById(id);
  const el = (tag,cls,text) => {const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=String(text);return node;};
  const emit = (name,detail) => window.dispatchEvent(new CustomEvent(`jarvis:${name}`,{detail}));
  const errorText = error => error?.message || String(error);
  const bytes = value => Number(value)>=1000000 ? `${(Number(value)/1000000).toFixed(1)} MB` : `${Math.max(1,Math.round(Number(value||0)/1000))} KB`;
  const idPath = id => encodeURIComponent(String(id));
  function say(message='',kind='info') {const node=$('missionNotice');if(!node)return;node.textContent=message;node.dataset.kind=kind;node.hidden=!message;}
  async function request(path,options={}) {
    if(typeof apiFetch!=='function') throw new Error('La conexión con Jarvis todavía no está disponible.');
    const response=await apiFetch(path,{...options,signal:options.signal || AbortSignal.timeout(60000)});
    if(!response.ok){let message=`La PC respondió con un error (${response.status}).`;try{const data=await response.json();message=typeof data.detail==='string'?data.detail:Array.isArray(data.detail)?data.detail.map(item=>item.msg).join('; '):data.message||message;}catch{}throw new Error(message);}
    return response;
  }
  const json = async (path,options={}) => (await request(path,options)).json();
  const post = (path,body) => json(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  function rememberProjects(){try{localStorage.setItem('jarvis.projects',JSON.stringify({items:state.projects,selected:state.selected}));}catch{say('El navegador no pudo guardar la lista de proyectos. Las misiones siguen guardadas en tu PC.','error');}}
  function slug(value){return String(value).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9_-]+/g,'-').replace(/^-+|-+$/g,'').slice(0,60);}
  function projectValid(value){return /^[a-z0-9_-]{1,60}$/.test(value)&&! /^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i.test(value);}
  function restoreProjects(){
    let saved;try{saved=JSON.parse(localStorage.getItem('jarvis.projects')||'null');}catch{}
    const items=Array.isArray(saved)?saved:Array.isArray(saved?.items)?saved.items:[];
    const unique=new Map();
    for(const item of items){const id=typeof item==='string'?slug(item):slug(item?.id||'');if(projectValid(id))unique.set(id,{id,name:typeof item==='string'?item:String(item.name||id)});}
    if(!unique.has('aurelio'))unique.set('aurelio',{id:'aurelio',name:'General'});
    state.projects=[...unique.values()];state.selected=unique.has(saved?.selected)?saved.selected:'aurelio';
  }
  function renderProjects(){
    const select=$('missionProject');if(!select)return;select.replaceChildren();
    state.projects.forEach(project=>{const option=el('option','',project.name);option.value=project.id;select.append(option);});select.value=state.selected;
    const selected=state.projects.find(project=>project.id===state.selected);if($('missionProjectLabel'))$('missionProjectLabel').textContent=selected?.name||state.selected;
  }
  function currentItem(){return state.currentId?state.items.get(state.currentId)||null:null;}
  function currentActive(){return ACTIVE.has(currentItem()?.status);}
  function projectItems(){const item=currentItem();return item?[item]:[];}
  function rememberItem(item,detailed=false){
    if(!item?.id)return;const previous=state.items.get(item.id);state.items.set(item.id,{...previous,...item});
    const current=state.items.get(item.id);if(item.id===state.currentId&&(!previous||previous.status!==current.status||previous.output!==current.output))emit('mission',current);
  }
  function activate(item){
    if(!item?.id)return;
    if(item.project&&projectValid(item.project)){
      if(!state.projects.some(project=>project.id===item.project))state.projects.push({id:item.project,name:item.project});
      state.selected=item.project;rememberProjects();renderProjects();
    }
    state.currentId=item.id;rememberItem(item);render();$('missionMessages').scrollTop=0;emit('project-change',{project:state.selected});
  }
  function clearCurrent(){
    if(currentActive()){say('Esperá a que termine la operación o detenela antes de iniciar otra.');return;}
    state.currentId=null;render();say();emit('project-change',{project:state.selected});$('missionInput')?.focus();
  }
  function renderConnection(){
    const node=$('companionState');if(node){node.dataset.state=state.connected?'connected':'offline';node.replaceChildren(el('i','led'),document.createTextNode(state.connected?'COMPAÑERO CONECTADO':'COMPAÑERO SIN CONEXIÓN'));}
    if($('companionOffline'))$('companionOffline').hidden=state.connected;
    if($('missionAgentStatus')){
      const agent=state.agent||{},engine=agent.tts_engine==='jarvis_local'?'Chatterbox':agent.tts_engine==='piper'?'Piper':agent.tts_engine||'sin configurar';
      const voice=agent.voice_mode==='owned'?'Jarvis propio · voz local':agent.voice_mode==='fish'?'Jarvis latino · Fish gratis':agent.voice_mode==='openai'?'pendiente de actualización':`local · ${engine}`;
      $('missionAgentStatus').textContent=state.connected?`${agent.message||'Compañero disponible.'} · Voz efectiva: ${voice}${agent.voice_mode==='local'?` · Reconocimiento ${agent.speech_ready?'listo':'pendiente'} · Síntesis ${agent.tts_ready?'lista':'pendiente'}`:''}`:'Conectá el compañero para usar los motores de tu PC.';
    }
    if($('sendMission'))$('sendMission').disabled=state.sending||state.saving||!state.connected||currentActive();
    if($('missionInput'))$('missionInput').disabled=state.sending;
    if($('missionUpload'))$('missionUpload').disabled=!state.connected||currentActive();
    if($('newAction'))$('newAction').disabled=state.sending||currentActive();
    if($('missionProject'))$('missionProject').disabled=state.sending||currentActive();
    if($('newProject'))$('newProject').disabled=state.sending||currentActive();
    ['missionEngine','missionVoice','missionLocalModel'].forEach(id=>{if($(id))$(id).disabled=state.saving;});
    if($('missionModel'))$('missionModel').disabled=state.saving||$('missionEngine')?.value==='claude';
  }
  function renderSettings(){
    if(!state.agent||state.saving||document.activeElement?.closest('.mission-toolbar'))return;
    const agent=state.agent;if($('missionEngine'))$('missionEngine').value=agent.provider||'openai';
    const select=$('missionModel');if(select){select.replaceChildren();const values=agent.provider==='local'?[...new Set([agent.local_model,...(agent.local_models||[])].filter(Boolean))]:agent.provider==='claude'?['Claude Code']:[...new Set([...MODELS,agent.openai_model].filter(Boolean))];for(const model of values){const option=el('option','',model);option.value=model;select.append(option);}select.value=agent.provider==='local'?agent.local_model:agent.provider==='claude'?'Claude Code':agent.openai_model;select.disabled=agent.provider==='claude';}
    if($('missionLocalModel')){$('missionLocalModel').value=agent.local_model||'qwen3:8b';$('missionLocalModel').hidden=agent.provider!=='local';}
    if($('missionVoice'))$('missionVoice').value=agent.voice==='owned'?'owned':agent.voice==='fish'?'fish':agent.voice==='openai'?'openai':'local';
  }
  async function refreshStatus(){
    if(state.statusPromise)return state.statusPromise;
    state.statusPromise=(async()=>{
      try{const reconnecting=!state.connected;state.agent=await json('/api/agent/status',{signal:AbortSignal.timeout(10000)});state.connected=true;renderSettings();emit('agent-status',state.agent);if(reconnecting)await refreshProjects();return state.agent;}
      catch(error){state.connected=false;say(errorText(error),'error');emit('companion-offline',{message:errorText(error)});return null;}
      finally{state.statusPromise=null;renderConnection();}
    })();return state.statusPromise;
  }
  async function refreshProjects(){
    try{const response=await json('/api/projects'),known=new Map(state.projects.map(item=>[item.id,item]));for(const item of response.projects||[])if(projectValid(item.id))known.set(item.id,{id:item.id,name:String(item.name||item.id)});state.projects=[...known.values()];rememberProjects();renderProjects();}
    catch(error){say('No pude actualizar la lista de proyectos: '+errorText(error),'error');}
  }
  async function saveSettings(){
    if(state.saving)return;state.saving=true;renderConnection();const provider=$('missionEngine').value;
    const body={provider,openai_model:provider==='openai'?$('missionModel').value:state.agent?.openai_model||MODELS[0],local_model:provider==='local'?($('missionLocalModel').value.trim()||$('missionModel').value):state.agent?.local_model||'qwen3:8b',voice:$('missionVoice').value};
    try{state.agent=await post('/api/agent/settings',body);state.connected=true;say('Configuración guardada.');emit('agent-status',state.agent);}
    catch(error){say(errorText(error),'error');}
    finally{state.saving=false;renderSettings();renderConnection();}
  }
  function switchProvider(){
    if($('missionEngine').value==='local'&&window.JarvisLocalModels){renderSettings();window.JarvisLocalModels.open();return;}
    const provider=$('missionEngine').value,select=$('missionModel');select.replaceChildren();
    const values=provider==='openai'?MODELS:provider==='claude'?['Claude Code']:[...new Set([state.agent?.local_model||'qwen3:8b',...(state.agent?.local_models||[])])];
    values.forEach(model=>{const option=el('option','',model);option.value=model;select.append(option);});
    if(provider==='openai')select.value=MODELS.includes(state.agent?.openai_model)?state.agent.openai_model:MODELS[0];
    select.disabled=provider==='claude';$('missionLocalModel').hidden=provider!=='local';saveSettings();
  }
  function renderMarkdown(target,text){if(typeof mdRender==='function')target.innerHTML=mdRender(String(text||''));else target.textContent=String(text||'');target.querySelectorAll('a').forEach(link=>{link.target='_blank';link.rel='noopener noreferrer';});if(typeof renderJarvisMath==='function')renderJarvisMath(target);else if(typeof window.renderMathInElement==='function')window.renderMathInElement(target,{trust:false,throwOnError:false,maxExpand:500,maxSize:20});}
  async function downloadArtifact(mission,artifact,button){
    button.disabled=true;try{const path=String(artifact.path).split('/').map(encodeURIComponent).join('/');const response=await request(`/api/missions/${idPath(mission.id)}/file/${path}`);const blob=await response.blob();const url=URL.createObjectURL(blob),anchor=el('a');anchor.href=url;anchor.download=artifact.name||String(artifact.path).split('/').pop();document.body.append(anchor);anchor.click();anchor.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);say(`Descarga preparada: ${anchor.download}`);}
    catch(error){say(errorText(error),'error');}finally{button.disabled=false;}
  }
  function renderApproval(record,mission){
    const card=el('section','approval-card');card.setAttribute('aria-label','Revisar ejecución en tu PC');card.append(el('h3','',record.state==='pending'?'Revisá esta ejecución':'Ejecución revisada'));
    const payload=record.payload||{},details=el('dl');const pair=(key,value)=>{details.append(el('dt','',key),el('dd','',value));};pair('TIPO',payload.kind||'Ejecución');pair('CARPETA DE TRABAJO',payload.folder||'No informada');pair('IDENTIFICADOR DE LA PROPUESTA',record.id);card.append(details);
    const command=el('pre','approval-command',payload.content||'');command.tabIndex=0;command.setAttribute('aria-label','Comando o código completo');card.append(el('h4','','COMANDO / CÓDIGO COMPLETO'),command);
    const files=payload.files&&typeof payload.files==='object'?Object.entries(payload.files):[];
    const scope=el('details','approval-snapshot'),summary=el('summary','',`Archivos de la carpeta en la revisión (${files.length})`);scope.append(summary);
    const list=el('ul','approval-files');for(const [name,digest] of files){const li=el('li');li.append(el('span','',name),el('code','',String(digest)));list.append(li);}if(!files.length)list.append(el('li','','No hay archivos incluidos en esta revisión.'));scope.append(list);card.append(scope);
    card.append(el('p','approval-scope','La revisión compara los archivos de esta carpeta. Excluye archivos y carpetas ocultos, node_modules, .git, .venv, venv, .jarvis-runs, __pycache__, .next, dist y archivos de más de 50 MB. Esta lista es una instantánea de la carpeta; no limita los archivos a los que el comando puede acceder.'));
    card.append(el('p','','Se ejecutará con los permisos de tu usuario de Windows. Revisá el comando completo antes de aprobar.'));
    if(payload.sha256){const hash=el('details','approval-hash');hash.append(el('summary','','Huella SHA-256 del comando'),el('code','',payload.sha256));card.append(hash);}
    const pending=record.state==='pending'&&mission.status==='awaiting_approval';
    if(pending){const actions=el('div','approval-actions');for(const [approve,label] of [[true,'Aprobar una vez'],[false,'Rechazar']]){const button=el('button','',label);button.type='button';button.disabled=state.decisions.has(record.id);button.addEventListener('click',async()=>{if(state.decisions.has(record.id))return;state.decisions.add(record.id);actions.querySelectorAll('button').forEach(node=>node.disabled=true);try{await post(`/api/approvals/${idPath(record.id)}/decision`,{approve});say(approve?'Aprobación enviada para esta ejecución.':'Ejecución rechazada.');await fetchMission(mission.id);render();}catch(error){say(errorText(error),'error');try{const current=await fetchMission(mission.id);if(current.status==='awaiting_approval'&&current.approvals?.some(item=>item.id===record.id&&item.state==='pending'))state.decisions.delete(record.id);}catch{}state.rendered.get(mission.id)?.node.remove();state.rendered.delete(mission.id);render();}});actions.append(button);}card.append(actions);}
    else{const labels={approved:'Aprobada una vez',executing:'En ejecución',done:'Ejecutada',failed:'Falló',denied:'Rechazada',expired:'Vencida',pending:'Ya no está disponible'};let outcome=labels[record.state]||record.state||'No disponible';let result=record.result;
      if(typeof result==='string'&&result){try{result=JSON.parse(result);}catch{}}
      if(result&&typeof result==='object'&&Object.hasOwn(result,'exit_code'))outcome+=` · Código de salida: ${result.exit_code}`;
      card.append(el('p','approval-outcome',outcome));
      if(result!==undefined&&result!==null&&result!==''){
        const details=el('details','approval-result');details.append(el('summary','','Ver resultado'));
        const value=typeof result==='string'?result:typeof result.stdout==='string'||typeof result.stderr==='string'?[result.stdout?`Salida:\n${result.stdout}`:'',result.stderr?`Errores:\n${result.stderr}`:''].filter(Boolean).join('\n\n')||'La ejecución terminó sin texto de salida.':JSON.stringify(result,null,2),output=el('pre','',value);output.tabIndex=0;details.append(output);card.append(details);
      }
    }
    return card;
  }
  function missionNode(item){
    const operation=el('section','mission-record action-current');operation.id=`mission-${item.id}`;operation.dataset.mission=item.id;
    const header=el('header','action-heading'),status=el('span','mission-state',LABELS[item.status]||item.status);status.dataset.state=item.status;header.append(el('h3','','Pedido actual'),status);operation.append(header,el('p','action-request',item.prompt||item.title||''));
    if(ACTIVE.has(item.status)){
      const latest=[...(item.events||[])].reverse().find(event=>typeof event.message==='string'&&event.message.trim());
      const progress=item.status==='awaiting_approval'?'Revisá la ejecución para continuar.':item.status==='queued'?'La acción está en cola.':latest?.message||'Ejecutando tu pedido…';
      const node=el('p','mission-progress',progress);node.setAttribute('role','status');operation.append(node);
    }
    const reviewed=[];for(const approval of item.approvals||[]){if(approval.state==='pending'&&item.status==='awaiting_approval')operation.append(renderApproval(approval,item));else reviewed.push(approval);}
    if(item.output){const result=el('section','action-result'),body=el('div','message-body');result.append(el('h3','','Resultado'));renderMarkdown(body,item.output);result.append(body);operation.append(result);}
    if(item.artifacts?.length){const files=el('section','action-files'),artifacts=el('div','mission-artifacts');files.append(el('h3','',`Archivos (${item.artifacts.length})`));artifacts.setAttribute('aria-label','Archivos de esta operación');for(const artifact of item.artifacts){const button=el('button','artifact-chip');button.type='button';button.append(el('span','',artifact.path||artifact.name),el('small','',bytes(artifact.bytes)),el('span','artifact-download','Descargar ↓'));button.addEventListener('click',()=>downloadArtifact(item,artifact,button));artifacts.append(button);}files.append(artifacts);operation.append(files);}
    if(item.events?.length||reviewed.length){const events=el('details','mission-events');events.append(el('summary','','Detalles de esta operación'));if(item.events?.length){const list=el('ol');for(const event of item.events){const entry=el('li');entry.append(el('span','',event.name||event.type||'Actividad'));if(event.message)entry.append(el('pre','',typeof event.message==='string'?event.message:JSON.stringify(event.message,null,2)));list.append(entry);}events.append(list);}for(const approval of reviewed)events.append(renderApproval(approval,item));operation.append(events);}
    if(ACTIVE.has(item.status)){const cancel=el('button','mission-cancel','Detener acción');cancel.type='button';cancel.addEventListener('click',async()=>{cancel.disabled=true;try{await json(`/api/missions/${idPath(item.id)}/cancel`,{method:'POST'});await fetchMission(item.id);render();}catch(error){say(errorText(error),'error');cancel.disabled=false;}});operation.append(cancel);}
    return operation;
  }
  function render(){
    const holder=$('missionMessages');if(!holder)return;const item=currentItem();$('missionEmpty').hidden=Boolean(item);
    for(const [id,record] of state.rendered)if(id!==item?.id){record.node.remove();state.rendered.delete(id);}
    if(item){const signature=JSON.stringify([item.status,item.output,item.events,item.artifacts,item.approvals,item.prompt]);let record=state.rendered.get(item.id);if(!record||record.signature!==signature){const node=missionNode(item);if(record?.node.parentNode===holder){const open=[...record.node.querySelectorAll('details')].map(details=>details.open);record.node.replaceWith(node);node.querySelectorAll('details').forEach((details,i)=>details.open=Boolean(open[i]));}else holder.append(node);state.rendered.set(item.id,{node,signature});}}
    renderConnection();
  }
  async function fetchMission(id){const item=await json(`/api/missions/${idPath(id)}`);rememberItem(item,true);return item;}
  async function refreshCurrent(){
    const id=state.currentId;if(!id||state.loading)return;state.loading=true;
    try{await fetchMission(id);state.connected=true;if(state.currentId===id)render();}
    catch(error){if(state.currentId===id)say(errorText(error),'error');}
    finally{state.loading=false;renderConnection();}
  }
  async function selectProject(id){
    const project=String(id).toLowerCase();if(!state.projects.some(item=>item.id===project))throw new Error('El proyecto no existe en la lista.');
    if(currentActive()){renderProjects();throw new Error('Esperá a que termine la operación o detenela antes de cambiar de carpeta.');}
    state.selected=project;state.currentId=null;rememberProjects();renderProjects();render();say();emit('project-change',{project});
  }
  function projectNameDialog(){
    let dialog=$('missionProjectDialog');if(dialog?.open)return Promise.resolve(null);
    if(!dialog){
      dialog=el('dialog','project-create-dialog');dialog.id='missionProjectDialog';dialog.setAttribute('aria-labelledby','newProjectTitle');
      const title=el('h2','','Nueva carpeta de trabajo');title.id='newProjectTitle';const form=el('form');form.id='newProjectForm';
      const label=el('label','','Nombre de la carpeta');label.htmlFor='newProjectName';const input=el('input');input.id='newProjectName';input.name='name';input.maxLength=100;input.required=true;input.autocomplete='off';
      const preview=el('p','project-slug-preview');preview.id='newProjectSlug';preview.setAttribute('aria-live','polite');const notice=el('p','project-create-notice');notice.id='newProjectNotice';notice.setAttribute('role','status');
      const actions=el('div','approval-actions'),create=el('button','','Crear'),cancel=el('button','','Cancelar');create.type='submit';cancel.type='button';cancel.addEventListener('click',()=>dialog.close());actions.append(create,cancel);form.append(label,input,preview,notice,actions);dialog.append(title,form);document.body.append(dialog);
      input.addEventListener('input',()=>{const id=slug(input.value);preview.textContent=id?`Carpeta del proyecto: ${id}`:'';notice.textContent='';});
    }
    const form=$('newProjectForm'),input=$('newProjectName');input.value='';$('newProjectSlug').textContent='';$('newProjectNotice').textContent='';
    return new Promise(resolve=>{let result=null;const submit=event=>{event.preventDefault();const name=input.value.trim(),id=slug(name);if(!name||!projectValid(id)){$('newProjectNotice').textContent='Elegí un nombre que genere una carpeta válida con letras y números.';input.focus();return;}result=name;dialog.close();};form.addEventListener('submit',submit);dialog.addEventListener('close',()=>{form.removeEventListener('submit',submit);resolve(result);},{once:true});dialog.showModal();input.focus();});
  }
  async function createProject(){const name=await projectNameDialog();if(!name)return;const id=slug(name);try{const saved=await post('/api/projects',{id,name:name.slice(0,100)});if(!state.projects.some(item=>item.id===id))state.projects.push(saved);await selectProject(id);$('missionInput').focus();}catch(error){say(errorText(error),'error');}}
  function openPanel(){const panel=$('missionsPanel');if(panel&&!panel.open)panel.showModal();}
  async function submit(prompt,options={}){
    if(!state.initialized)init();const content=String(prompt||'').trim();if(!content)throw new Error('Indicá la acción que querés realizar.');if(content.length>100000)throw new Error('El pedido supera los 100.000 caracteres.');if(state.sending||state.saving)throw new Error('Esperá a que termine el envío o el cambio de motor.');if(currentActive()){const error=new Error('Hay una operación en curso. Esperá a que termine o detenela.');say(error.message);throw error;}
    if(options.open!==false)openPanel();state.sending=true;renderConnection();say();const project=options.project||state.selected;
    try{
      const provider=options.provider||$('missionEngine')?.value||state.agent?.provider||'openai';
      const mission=await post('/api/missions',{prompt:content,title:content.replace(/\s+/g,' ').slice(0,100),provider,project});state.connected=true;activate(mission);
      if($('missionInput')?.value.trim()===content)$('missionInput').value='';render();emit('mission-submitted',mission);return mission;
    }catch(error){say(errorText(error),'error');throw error;}finally{state.sending=false;renderConnection();$('missionInput')?.focus();}
  }
  function wait(id,options={}){
    const key=String(id);if(state.waiters.has(key))return state.waiters.get(key);
    const promise=(async()=>{const deadline=Date.now()+(options.timeoutMs||1800000);let failures=0;
      while(Date.now()<deadline){try{const item=await fetchMission(key);failures=0;render();if(!ACTIVE.has(item.status))return item;}catch(error){if(++failures>=5)throw error;}
        await new Promise(resolve=>setTimeout(resolve,1500));
      }throw new Error('La operación sigue guardada en tu PC, pero terminó el tiempo de espera.');
    })().finally(()=>state.waiters.delete(key));state.waiters.set(key,promise);return promise;
  }
  async function uploadFile(file){
    if(!file)return;if(file.size>25000000){say('El archivo supera los 25 MB.','error');return;}
    const button=$('missionUpload');button.disabled=true;const project=state.selected;
    try{const result=await json(`/api/projects/${idPath(project)}/upload?name=${encodeURIComponent(file.name)}`,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});say(`Archivo cargado en ${state.projects.find(item=>item.id===project)?.name||project}: ${result.name} (${bytes(result.bytes)}).`);emit('file-uploaded',{project,...result});}
    catch(error){say(errorText(error),'error');}finally{button.disabled=!state.connected;$('missionFile').value='';}
  }
  async function refreshMemory(){
    const holder=$('memoryNotes');holder.replaceChildren(el('p','memory-empty','Cargando memoria…'));
    try{const response=await json('/api/memory');holder.replaceChildren();for(const note of response.notes||[]){const row=el('article','memory-note');row.append(el('p','',note.content));const button=el('button','','Olvidar');button.type='button';button.addEventListener('click',async()=>{button.disabled=true;try{await json(`/api/memory/${idPath(note.id)}/forget`,{method:'POST'});row.remove();if(!holder.children.length)holder.append(el('p','memory-empty','Todavía no guardaste notas.'));}catch(error){$('memoryNotice').textContent=errorText(error);button.disabled=false;}});row.append(button);holder.append(row);}if(!holder.children.length)holder.append(el('p','memory-empty','Todavía no guardaste notas.'));}
    catch(error){holder.replaceChildren(el('p','memory-empty',errorText(error)));}
  }
  async function openMemory(){const panel=$('memoryPanel');if(!panel.open)panel.showModal();$('memoryNotice').textContent='';await refreshMemory();}
  async function addMemory(event){event.preventDefault();const input=$('memoryInput'),content=input.value.trim();if(!content)return;const button=$('saveMemory');button.disabled=true;$('memoryNotice').textContent='';try{await post('/api/memory',{content});input.value='';await refreshMemory();}catch(error){$('memoryNotice').textContent=errorText(error);}finally{button.disabled=false;}}
  async function tick(){if(document.hidden||!currentActive())return;await refreshCurrent();}
  function init(){
    if(state.initialized||!$('missionsPanel'))return;state.initialized=true;restoreProjects();renderProjects();render();
    $('missionForm').addEventListener('submit',event=>{event.preventDefault();submit($('missionInput').value).catch(()=>{});});
    $('missionInput').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();$('missionForm').requestSubmit();}});
    $('missionProject').addEventListener('change',event=>selectProject(event.target.value).catch(error=>say(errorText(error),'error')));
    $('newProject').addEventListener('click',createProject);$('newAction').addEventListener('click',clearCurrent);
    $('missionEngine').addEventListener('change',switchProvider);$('missionModel').addEventListener('change',()=>{if($('missionEngine').value==='local')$('missionLocalModel').value=$('missionModel').value;saveSettings();});$('missionLocalModel').addEventListener('change',saveSettings);$('missionVoice').addEventListener('change',saveSettings);
    $('reconnectCompanion').addEventListener('click',async()=>{say('Buscando el compañero…');const status=await refreshStatus();if(status){say();await refreshCurrent();}else{say('No pude conectar con el compañero. Abrí Jarvis en tu PC y reconectá.','error');if(typeof onlineInterface!=='undefined'&&onlineInterface)$('connectPc')?.click();}});
    $('missionUpload').addEventListener('click',()=>$('missionFile').click());$('missionFile').addEventListener('change',()=>uploadFile($('missionFile').files[0]));$('missionMemory').addEventListener('click',openMemory);$('memoryForm').addEventListener('submit',addMemory);
    document.querySelectorAll('[data-mission-close]').forEach(button=>button.addEventListener('click',()=>button.closest('dialog')?.close()));
    window.addEventListener('jarvis:mission-created',event=>{const item=event.detail?.task||event.detail;if(item?.id){activate(item);refreshCurrent();}});
    document.addEventListener('visibilitychange',()=>{if(!document.hidden){refreshStatus();tick();}});
    refreshStatus();state.timer=setInterval(tick,3500);state.statusTimer=setInterval(()=>{if(!document.hidden&&!state.saving)refreshStatus();},15000);
  }
  window.JarvisMissions={init,refreshStatus,submit,wait,selectProject,open:openPanel,refresh:refreshCurrent,clear:clearCurrent,get selectedProject(){return state.selected;},get currentMission(){return currentItem();},get agentState(){return state.agent;},get companionConnected(){return state.connected;},get missions(){return projectItems();}};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();

/* Fish credentials are submitted only to the local companion and never stored in the browser. */
(() => {
  const $=id=>document.getElementById(id);let busy=false;
  async function request(path,body){
    const response=await apiFetch(path,{...(body!==undefined?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(145000)});
    const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'No pude conectar la voz de Jarvis.');return data;
  }
  async function refresh(){
    const local=!onlineInterface;$('fishKeyForm').hidden=!local;$('fishOnlineOnly').hidden=local;
    try{const state=await request('/api/speech/fish/status');$('fishStatus').textContent=state.key_configured?(state.test_passed?'Fish conectado · última generación de prueba correcta':'Clave guardada · falta generar la frase de prueba'):'Falta conectar la clave gratuita de Fish Audio.';$('fishTestAgain').hidden=!state.key_configured;if(!state.free_available)$('fishStatus').textContent='La gratuidad necesita revalidación. No se activó ninguna opción de pago.';return state;}
    catch(error){$('fishStatus').textContent=error.message;}
  }
  async function test(){
    $('fishNotice').textContent='Generando una frase nueva con Jarvis de Fish…';
    const result=await request('/api/speech/fish/test',{});
    const response=await apiFetch('/api/speech/audio/'+result.audio,{signal:AbortSignal.timeout(15000)});if(!response.ok)throw new Error('La prueba se generó, pero no pude descargar su audio.');
    const blob=await response.blob(),audio=$('fishTestAudio');if(audio.dataset.url)URL.revokeObjectURL(audio.dataset.url);audio.src=audio.dataset.url=URL.createObjectURL(blob);audio.hidden=false;$('fishPhrase').textContent=result.text;
    $('fishNotice').textContent='Frase generada por Fish con la voz seleccionada. Escuchala con el reproductor.';
    await refresh();window.JarvisMissions?.refreshStatus();audio.play().catch(()=>{});
  }
  async function run(save){
    if(busy)return;busy=true;$('fishSaveAndTest').disabled=$('fishTestAgain').disabled=true;$('fishNotice').textContent='';
    try{
      if(save){const input=$('fishApiKey');const api_key=input.value.trim();if(!api_key)throw new Error('Pegá tu clave de Fish en el campo.');try{await request('/api/speech/fish/key',{api_key});}finally{input.value='';}}
      await test();
    }catch(error){$('fishNotice').textContent=error.message;}
    finally{busy=false;$('fishSaveAndTest').disabled=$('fishTestAgain').disabled=false;}
  }
  function open(){const panel=$('fishPanel');if(!panel.open)panel.showModal();refresh();}
  function init(){if(!$('fishPanel'))return;$('fishKeyForm').addEventListener('submit',event=>{event.preventDefault();run(true);});$('fishTestAgain').addEventListener('click',()=>run(false));$('configureFishVoice')?.addEventListener('click',open);document.querySelectorAll('[data-panel="fishPanel"]').forEach(button=>button.addEventListener('click',refresh));if(location.hash==='#fish'){history.replaceState(null,'',location.pathname+location.search);open();}}
  window.JarvisFish={open,refresh};if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();

(() => {
  const $=id=>document.getElementById(id);let busy=false,heardProfile=null;
  async function call(path,body){const response=await apiFetch(path,{...(body!==undefined?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(15000)});const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'No pude actualizar el perfil local.');return data;}
  async function refresh(){try{const state=await call('/api/speech/owned/status');$('ownedStatus').textContent=state.approved?'Perfil local aceptado y listo para usar.':state.message;$('ownedListen').hidden=!state.sample_ready;$('ownedDecision').hidden=!state.prepared;return state;}catch(error){$('ownedStatus').textContent=error.message;}}
  async function listen(){if(busy)return;busy=true;$('ownedListen').disabled=true;try{const before=await call('/api/speech/owned/status');const response=await apiFetch('/api/speech/owned/sample');if(!response.ok)throw new Error('La muestra todavía no está disponible.');const audio=$('ownedAudio');if(audio.dataset.url)URL.revokeObjectURL(audio.dataset.url);audio.src=audio.dataset.url=URL.createObjectURL(await response.blob());const after=await call('/api/speech/owned/status');if(before.profile_sha256!==after.profile_sha256||before.sample_sha256!==after.sample_sha256)throw new Error('La muestra cambió; escuchá la nueva.');heardProfile=after;audio.hidden=false;audio.play().catch(()=>{});}catch(error){$('ownedNotice').textContent=error.message;}finally{busy=false;$('ownedListen').disabled=false;}}
  async function decide(approve){if(busy)return;busy=true;try{if(approve&&!heardProfile)throw new Error('Escuchá la muestra local antes de elegirla.');await call('/api/speech/owned/approve',{approve,profile_sha256:heardProfile?.profile_sha256,sample_sha256:heardProfile?.sample_sha256});$('ownedNotice').textContent=approve?'Perfil local elegido para Jarvis.':'El perfil queda pendiente de ajuste. Jarvis sigue disponible por texto.';await refresh();window.JarvisMissions?.refreshStatus();}catch(error){$('ownedNotice').textContent=error.message;}finally{busy=false;}}
  function open(){if(!$('ownedPanel').open)$('ownedPanel').showModal();refresh();}
  function init(){$('configureOwnedVoice')?.addEventListener('click',open);document.querySelectorAll('[data-panel="ownedPanel"]').forEach(button=>button.addEventListener('click',refresh));$('ownedListen').addEventListener('click',listen);$('ownedAccept').addEventListener('click',()=>decide(true));$('ownedReject').addEventListener('click',()=>decide(false));if(location.hash==='#owned'){history.replaceState(null,'',location.pathname+location.search);open();}}
  window.JarvisOwned={open,refresh};if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
