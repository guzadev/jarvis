/* One replaceable data result. No history, startup queries or automatic refresh. */
(() => {
  'use strict';
  if(window.JarvisData)return;
  const state={panel:null,body:null,title:null,notice:null,last:null,pending:null,version:0,settings:null,connector:null,line:null,lineGlow:null,point:null,layoutFrame:0,anchor:null,layoutObserver:null,animation:null};
  const el=(tag,cls,value)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(value!==undefined)node.textContent=asText(value);return node;};
  function asText(value){
    if(value===null||value===undefined)return '—';
    if(typeof value==='boolean')return value?'Sí':'No';
    if(Array.isArray(value))return value.map(asText).join(' · ');
    if(typeof value==='object')return Object.entries(value).map(([key,item])=>`${key}: ${asText(item)}`).join(' · ');
    return String(value);
  }
  function safeURL(value){
    if(typeof value!=='string'||/[\u0000-\u001f\u007f]/.test(value))return null;
    try{const url=new URL(value);return url.protocol==='https:'&&url.hostname&&!url.username&&!url.password?url.href:null;}catch{return null;}
  }
  function dateText(value){
    if(value===undefined||value===null||value==='')return '';
    if(typeof value==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(value)){
      const date=new Date(value+'T00:00:00Z');return Number.isNaN(date.getTime())?value:date.toLocaleDateString('es-AR',{dateStyle:'medium',timeZone:'UTC'});
    }
    const input=typeof value==='number'?(value<1e12?value*1000:value):value,date=new Date(input);
    return Number.isNaN(date.getTime())?asText(value):date.toLocaleString('es-AR',{dateStyle:'medium',timeStyle:'short'});
  }
  function normalize(result){
    if(!result||typeof result!=='object'||Array.isArray(result))return {status:'ok',title:'Resultado',summary:asText(result)};
    return {...result,status:['ok','needs_choice','error'].includes(result.status)?result.status:result.error?'error':'ok',title:result.title|| (result.status==='error'?'No pude completar la consulta':'Resultado')};
  }
  function cancelPending(){
    state.version++;
    const media=state.media;state.media=null;
    if(media){media.controller?.abort();media.node.pause();media.node.removeAttribute('src');media.node.load?.();if(media.url)URL.revokeObjectURL(media.url);}
    const request=state.pending;state.pending=null;
    if(request){clearTimeout(request.slowTimer);clearTimeout(request.timeout);request.controller.abort();}
    state.panel?.setAttribute('aria-busy','false');
  }
  function ensure(){
    if(state.panel)return state.panel;
    const panel=state.panel=el('section','jarvis-data-panel hud-data-board');panel.id='jarvisDataPanel';panel.hidden=true;panel.open=false;panel.tabIndex=-1;panel.setAttribute('role','region');panel.setAttribute('aria-labelledby','jarvisDataTitle');
    const header=el('header','data-board-header'),heading=el('div');heading.append(el('div','data-eyebrow','RESULTADO'));state.title=el('h2','data-board-title','Resultados');state.title.id='jarvisDataTitle';state.title.setAttribute('aria-live','polite');heading.append(state.title);
    const closeButton=el('button','data-close','×');closeButton.type='button';closeButton.setAttribute('aria-label','Cerrar resultado');closeButton.addEventListener('click',close);header.append(heading,closeButton);
    state.notice=el('p','data-notice');state.notice.hidden=true;state.notice.setAttribute('role','status');state.body=el('div','data-board-body');panel.append(header,state.notice,state.body);
    document.body.append(panel);
    if(document.createElementNS){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('class','data-hud-connector');svg.setAttribute('aria-hidden','true');svg.dataset.visible='false';
      state.lineGlow=document.createElementNS('http://www.w3.org/2000/svg','path');state.lineGlow.setAttribute('class','data-connector-glow');state.line=document.createElementNS('http://www.w3.org/2000/svg','path');state.line.setAttribute('class','data-connector-line');state.point=document.createElementNS('http://www.w3.org/2000/svg','circle');state.point.setAttribute('class','data-connector-point');state.point.setAttribute('r','3');svg.append(state.lineGlow,state.line,state.point);document.body.append(svg);state.connector=svg;}
    const schedule=()=>{if(!panel.open||state.layoutFrame)return;if(typeof requestAnimationFrame==='function')state.layoutFrame=requestAnimationFrame(()=>{state.layoutFrame=0;layout();});else layout();};
    window.addEventListener?.('resize',schedule,{passive:true});window.addEventListener?.('scroll',schedule,{passive:true});
    document.addEventListener?.('keydown',event=>{if(event.key!=='Escape'||!panel.open||event.defaultPrevented)return;const dialogs=document.querySelectorAll?.('dialog[open]');if(dialogs?.length)return;event.preventDefault();close();});
    if(typeof ResizeObserver==='function'){state.layoutObserver=new ResizeObserver(schedule);state.layoutObserver.observe(panel);const orb=document.getElementById?.('orb');if(orb)state.layoutObserver.observe(orb);}
    return panel;
  }
  function layout(){
    const panel=state.panel;if(!panel?.open)return;
    const width=window.innerWidth||1200,height=window.innerHeight||800,padding=width>1400?36:24,gap=width>1400?44:34;
    const orb=document.getElementById?.('orb'),rect=orb?.getBoundingClientRect?.();let side='right',space=rect?width-padding-rect.right-gap:Math.min(width*.36,500),flow=width<=1000;
    if(rect&&space<300){const leftSpace=rect.left-padding-gap;if(leftSpace>=300){side='left';space=leftSpace;}else flow=true;}
    const host=flow?(document.querySelector?.('.command-center')||document.body):document.body;if(panel.parentNode!==host)host.append(panel);
    panel.dataset.layout=flow?'flow':'floating';panel.dataset.side=side;document.body.dataset.hudResult='open';document.body.dataset.hudSide=flow?'flow':side;
    if(!flow&&panel.style?.setProperty){const cardWidth=Math.floor(Math.min(550,Math.max(300,space))),left=side==='right'?(rect?rect.right+gap:width-padding-cardWidth):(rect?rect.left-gap-cardWidth:padding),top=Math.max(100,Math.min(rect?rect.top+rect.height*.08:118,height*.24));
      const dock=document.querySelector?.('.command-dock')?.getBoundingClientRect?.(),bottom=dock&&dock.top>top+300?Math.min(height-30,dock.top-16):height-60;
      panel.style.setProperty('--hud-left',`${Math.round(left)}px`);panel.style.setProperty('--hud-top',`${Math.round(top)}px`);panel.style.setProperty('--hud-width',`${cardWidth}px`);panel.style.setProperty('--hud-max-height',`${Math.max(250,bottom-top)}px`);
    }
    if(state.connector){state.connector.setAttribute('viewBox',`0 0 ${width} ${height}`);const board=panel.getBoundingClientRect?.();const showLine=!flow&&rect&&board&&rect.bottom>90&&rect.top<height-60;state.connector.dataset.visible=String(Boolean(showLine));
      if(showLine){const radius=rect.width*.41,angle=side==='right'?-.42:Math.PI+.42,x=rect.left+rect.width/2+Math.cos(angle)*radius,y=rect.top+rect.height/2+Math.sin(angle)*radius,endX=side==='right'?board.left:board.right,endY=board.top+42,elbow=x+(side==='right'?25:-25),d=`M ${x} ${y} L ${elbow} ${y} L ${endX+(side==='right'?-14:14)} ${endY} L ${endX} ${endY}`;state.line.setAttribute('d',d);state.lineGlow.setAttribute('d',d);state.point.setAttribute('cx',String(x));state.point.setAttribute('cy',String(y));state.anchor={x,y,board};}
    }
  }
  function show(){const panel=ensure();state.animation?.cancel();state.animation=null;panel.hidden=false;panel.open=true;panel.dataset.open='true';layout();const reduced=typeof matchMedia==='function'&&matchMedia('(prefers-reduced-motion: reduce)').matches;
    if(!reduced&&typeof panel.animate==='function'){const origin=state.anchor,dx=panel.dataset.layout==='floating'&&origin?Math.max(-180,Math.min(180,origin.x-origin.board.left)):0,dy=panel.dataset.layout==='floating'&&origin?Math.max(-80,Math.min(80,origin.y-origin.board.top)):16;const animation=panel.animate([{opacity:0,transform:`translate(${dx}px,${dy}px) scale(.78)`},{opacity:1,transform:'translate(0,0) scale(1)'}],{duration:520,easing:'cubic-bezier(.16,1,.3,1)'});if(animation){state.animation=animation;animation.onfinish=()=>{if(state.animation===animation){state.animation=null;animation.cancel();if(panel.open)layout();}};}}
  }
  // A small DOM-only Markdown renderer: generated text never becomes HTML.
  function plainInline(value){return asText(value).replace(/\[([^\]]+)\]\([^)]+\)/g,'$1').replace(/\*\*([^*]+)\*\*|__([^_]+)__|`([^`]+)`/g,(_,bold,under,code)=>bold||under||code).replace(/^#{1,6}\s+/,'');}
  function inline(parent,value,depth=0){
    const source=asText(value);if(depth>4){parent.append(document.createTextNode(source));return;}
    const pattern=/`([^`\n]+)`|\*\*([^*\n]+)\*\*|__([^_\n]+)__|\[([^\]\n]+)\]\(([^\s)]+)\)|\*([^*\n]+)\*/g;let previous=0,match;
    while((match=pattern.exec(source))){if(match.index>previous)parent.append(document.createTextNode(source.slice(previous,match.index)));let node;
      if(match[1]!==undefined)node=el('code','',match[1]);else if(match[2]!==undefined||match[3]!==undefined){node=el('strong');inline(node,match[2]??match[3],depth+1);}else if(match[4]!==undefined){const url=safeURL(match[5]);node=el(url?'a':'span');if(url){node.href=url;node.target='_blank';node.rel='noopener noreferrer';}inline(node,match[4],depth+1);}else{node=el('em');inline(node,match[6],depth+1);}parent.append(node);previous=pattern.lastIndex;
    }if(previous<source.length)parent.append(document.createTextNode(source.slice(previous)));
  }
  function richText(value,cls='data-summary'){
    const container=el('div',`${cls} data-rich-text`),lines=asText(value).replace(/\r\n/g,'\n').split('\n');let paragraph=[],list=null,code=null;
    const flush=()=>{if(paragraph.length){const node=el('p');inline(node,paragraph.join('\n'));container.append(node);paragraph=[];}};
    for(const line of lines){if(/^\s*```/.test(line)){flush();list=null;if(code){container.append(el('pre','',code.join('\n')));code=null;}else code=[];continue;}if(code){code.push(line);continue;}if(!line.trim()){flush();list=null;continue;}
      const heading=line.match(/^\s*#{1,6}\s+(.+)$/),entry=line.match(/^\s*(?:[-*]\s+|\d+[.)]\s+)(.+)$/);
      if(heading){flush();list=null;const node=el('h3');inline(node,heading[1]);container.append(node);}else if(entry){flush();if(!list){list=el(/^\s*\d/.test(line)?'ol':'ul');container.append(list);}const node=el('li');inline(node,entry[1]);list.append(node);}else{list=null;paragraph.push(line);}
    }flush();if(code)container.append(el('pre','',code.join('\n')));return container;
  }
  function summaryMetrics(summary){
    const fields=[],remaining=[];for(const line of asText(summary).split(/\r?\n/)){const match=line.match(/^\s*(?:[-*]\s+)?(?:\*\*([^*]+)\*\*|__([^_]+)__|([^:\n]{2,50}))\s*[:：]\s*(.+?)\s*$/);if(match){const label=plainInline(match[1]||match[2]||match[3]).replace(/:$/,''),value=plainInline(match[4]);if(value.length<=130&&(match[1]||match[2]||/[\d$€%]/.test(value))){fields.push({label,value});continue;}}remaining.push(line);}return {fields,summary:remaining.join('\n').trim()};
  }
  function notice(message='',kind='info'){ensure();state.notice.textContent=message;state.notice.hidden=!message;state.notice.dataset.kind=kind;}
  function sourceLabel(source){if(!source)return '';if(typeof source==='string'){const url=safeURL(source);return url?new URL(url).hostname:source;}return asText(source.name||source.title||source.label||source.source||source.url||source);}
  function sourceNode(source){
    const label=sourceLabel(source),url=safeURL(typeof source==='string'?source:source?.url);
    if(!url)return el('span','',label);
    const link=el('a','',label);link.href=url;link.target='_blank';link.rel='noopener noreferrer';return link;
  }
  function metadata(result){
    const footer=el('footer','data-metadata'),source=el('div','data-source');source.append(el('span','data-meta-label','Fuente: '));
    if(Array.isArray(result.source)){result.source.forEach((item,index)=>{if(index)source.append(document.createTextNode(' · '));source.append(sourceNode(item));});}else source.append(result.source?sourceNode(result.source):el('span','','No informada'));
    footer.append(source,el('div','data-fetched',result.fetched_at?`Consultado: ${dateText(result.fetched_at)}`:'Fecha de consulta no informada'));
    if(result.attribution)footer.append(el('p','data-attribution',result.attribution));return footer;
  }
  function renderImage(image){
    const url=safeURL(image?.url);if(!url){state.body.append(el('p','data-inline-notice','La fuente no proporcionó una imagen HTTPS válida.'));return;}
    const figure=el('figure','data-image'),img=el('img');img.alt=asText(image.alt||'Imagen de la fuente consultada');img.src=url;img.referrerPolicy='no-referrer';img.decoding='async';
    img.addEventListener('error',()=>{img.hidden=true;figure.prepend(el('p','data-inline-notice','No pude cargar la imagen. Podés abrir el original desde su enlace.'));},{once:true});figure.append(img);
    const caption=el('figcaption');if(image.credit)caption.append(el('span','data-image-credit',image.credit));const original=el('a','','Abrir imagen original ↗');original.href=url;original.target='_blank';original.rel='noopener noreferrer';caption.append(original);figure.append(caption);state.body.append(figure);
  }
  function renderVideo(video,image){
    if(!/^\d{4}-\d{2}-\d{2}$/.test(String(video?.date||''))){if(image)renderImage(image);return;}
    const figure=el('figure','data-image data-video'),movie=el('video');movie.preload='none';movie.playsInline=true;
    const poster=safeURL(image?.url);if(poster)movie.poster=poster;
    movie.setAttribute('aria-label',image?.alt||'Video astronómico de NASA');
    const button=el('button','data-configure data-video-play','Reproducir video aquí'),message=el('p','data-inline-notice');button.type='button';message.hidden=true;
    const caption=el('figcaption');if(image?.credit)caption.append(el('span','data-image-credit',image.credit));
    const media=state.media={node:movie,url:null,controller:null},version=state.version;
    figure.append(movie,button,message,caption);state.body.append(figure);
    button.addEventListener('click',async()=>{
      if(state.media!==media||media.controller)return;
      const controller=media.controller=new AbortController();button.disabled=true;button.textContent='Cargando video de NASA…';message.hidden=true;
      try{
        // Load only after a click, through the paired companion. Blob playback
        // works with the installed desktop's existing media-src policy.
        const response=await localFetch('/api/data/astronomy/video?date='+encodeURIComponent(video.date),{signal:AbortSignal.any([controller.signal,AbortSignal.timeout(45000)])});
        if(!response.ok){let problem;try{problem=await response.json();}catch{}throw new Error(problem?.detail||'NASA no pudo entregar el video. La portada sigue disponible.');}
        if(!['video/mp4','video/webm'].includes((response.headers.get('Content-Type')||'').split(';')[0]))throw new Error('NASA no devolvió un video compatible. La portada sigue disponible.');
        const blob=await response.blob();
        if(controller.signal.aborted||version!==state.version||state.media!==media)return;
        media.url=URL.createObjectURL(blob);movie.src=media.url;movie.controls=true;button.hidden=true;
        await movie.play().catch(()=>{});
      }catch(error){
        if(controller.signal.aborted||version!==state.version||state.media!==media)return;
        message.textContent=error.message||'No pude cargar el video. Podés abrir la publicación original.';message.hidden=false;
      }finally{if(state.media===media){media.controller=null;button.disabled=false;button.textContent='Reintentar video aquí';}}
    });
  }
  function renderFields(fields){
    const values=Array.isArray(fields)?fields:fields&&typeof fields==='object'?Object.entries(fields).map(([label,value])=>({label,value})):[];
    if(!values.length)return;const list=el('dl','data-fields');for(const [index,field] of values.entries()){if(!field||typeof field!=='object')continue;const label=plainInline(field.label||field.name||''),row=el('div','data-field');if(index===0&&/precio|cotizaci[oó]n|temperatura|valor|price/i.test(label))row.className+=' data-field-primary';row.append(el('dt','',label),el('dd','',plainInline(field.value)));list.append(row);}state.body.append(list);
  }
  function renderTable(columns,rows){
    if(!Array.isArray(rows)||!rows.length)return;
    const input=Array.isArray(columns)&&columns.length?columns:Array.isArray(rows[0])?rows[0].map((value,index)=>({key:index,label:`Dato ${index+1}`})):Object.keys(rows[0]||{});
    const headers=input.map((column,index)=>typeof column==='object'&&column!==null?{key:column.key??column.field??column.name??index,label:column.label||column.title||column.name||String(column.key??index+1)}:{key:column,label:String(column)});
    const wrapper=el('div','data-table-wrap');wrapper.tabIndex=0;wrapper.setAttribute('role','region');wrapper.setAttribute('aria-label','Tabla de resultados');
    const table=el('table','data-table'),head=el('thead'),headRow=el('tr');for(const column of headers){const cell=el('th','',column.label);cell.scope='col';headRow.append(cell);}head.append(headRow);table.append(head);
    const body=el('tbody');for(const row of rows){const line=el('tr');headers.forEach((column,index)=>line.append(el('td','',Array.isArray(row)?row[index]:row?.[column.key])));body.append(line);}table.append(body);wrapper.append(table);state.body.append(wrapper);
  }
  function renderItems(result){
    if(!Array.isArray(result.items)||!result.items.length)return;
    const news=/news|noticia|headline|rss/i.test(String(result.kind||''))||result.items.some(item=>item?.url&&item?.published);
    const list=el('ol',news?'data-news':'data-items');
    for(const item of (news?result.items.slice(0,5):result.items)){
      if(!item||typeof item!=='object'){list.append(el('li','',item));continue;}
      const row=el('li'),url=safeURL(item.url),title=item.title||item.label||item.date||'Resultado';
      if(url){const link=el('a','data-item-title',title);link.href=url;link.target='_blank';link.rel='noopener noreferrer';row.append(link);}else row.append(el('span','data-item-title',title));
      const details=[sourceLabel(item.source),dateText(item.published)].filter(Boolean).join(' · ');if(details)row.append(el('div','data-item-meta',details));
      if(item.summary||item.description)row.append(el('p','data-item-summary',item.summary||item.description));if(item.value!==undefined)row.append(el('span','data-item-value',item.value));list.append(row);
    }state.body.append(list);
  }
  function renderChoices(result){
    if(!Array.isArray(result.choices)||!result.choices.length){state.body.append(el('p','data-inline-notice','No hay lugares para elegir. Probá con una ciudad y su provincia o país.'));return;}
    const list=el('div','data-choices');list.setAttribute('aria-label','Elegir lugar');
    for(const choice of result.choices){if(choice?.place_id===undefined||choice?.place_id===null)continue;const button=el('button','data-choice',choice.label||choice.place_id);button.type='button';button.addEventListener('click',async()=>{
      list.querySelectorAll('button').forEach(node=>node.disabled=true);
      const selected=await query('select_place',{place_id:choice.place_id});
      if(selected?.status==='ok')window.dispatchEvent(new CustomEvent('jarvis:data-choice',{detail:{place_id:choice.place_id,label:choice.label||String(choice.place_id),result:selected}}));
    });list.append(button);}state.body.append(list);
  }
  function present(input){
    ensure();const result=normalize(input);state.last=result;state.title.textContent=plainInline(result.title);state.panel.dataset.status=result.status;state.panel.dataset.kind=String(result.kind||'generic');state.panel.setAttribute('aria-busy','false');state.body.replaceChildren();notice();
    const missingKey=/missing.*key|key.*required|falta.*clave|clave.*requerida/i.test(String(result.code||''));
    let summary=result.summary|| (result.status==='error'?(typeof result.error==='string'?result.error:typeof result.detail==='string'?result.detail:missingKey?'Falta configurar la clave de este servicio en Jarvis. No se realizó la consulta.':'No pude completar esta consulta.'):result.status==='needs_choice'?'Elegí el lugar al que te referís.':'');
    const imageFirst=result.status==='ok'&&Boolean(result.image||result.video);state.panel.dataset.hasImage=String(imageFirst);
    let fields=result.fields;if(!imageFirst&&result.status==='ok'&&(!fields||Array.isArray(fields)&&!fields.length)&&summary){const extracted=summaryMetrics(summary);if(extracted.fields.length){fields=extracted.fields;summary=extracted.summary;}}
    state.panel.dataset.hasMetrics=String(Boolean(Array.isArray(fields)?fields.length:fields&&typeof fields==='object'&&Object.keys(fields).length));
    if(!imageFirst&&result.status==='ok')renderFields(fields);
    if(summary&&!imageFirst)state.body.append(richText(summary,result.status==='error'?'data-summary data-error':'data-summary'));
    if(result.status==='error'&&missingKey){const button=el('button','data-configure','Configurar servicio');button.type='button';button.addEventListener('click',()=>configure(result.provider||result.provider_alias));state.body.append(button);}
    if(imageFirst){if(result.video)renderVideo(result.video,result.image);else renderImage(result.image);}
    if(result.notice)notice(asText(result.notice));
    if(result.delayed===true)state.body.append(el('p','data-inline-notice','La fuente informó una demora en la actualización.'));
    if(result.stale===true)state.body.append(el('p','data-inline-notice','Este dato corresponde a una actualización anterior de la fuente.'));
    if(Array.isArray(result.warnings)&&result.warnings.length){const warnings=el('ul','data-warnings');result.warnings.forEach(value=>warnings.append(el('li','',value)));state.body.append(warnings);}
    if(result.status==='needs_choice')renderChoices(result);
    else if(result.status!=='error'){
      if(imageFirst&&summary){const explanation=el('details','data-image-explanation');explanation.append(el('summary','','Explicación de la fuente'),richText(summary));state.body.append(explanation);}
      if(imageFirst)renderFields(fields);renderTable(result.columns,result.rows);renderItems(result);
      if(result.content){const details=el('details','data-api-content');details.append(el('summary','','Ver datos completos'),el('pre','data-api-json',typeof result.content==='string'?result.content:JSON.stringify(result.content,null,2)));state.body.append(details);}
    }
    state.body.append(metadata(result));state.body.scrollTop=0;show();return result;
  }
  function render(result){cancelPending();return present(result);}
  async function localFetch(path,options){
    if(typeof window.JarvisPC?.fetch==='function')return window.JarvisPC.fetch(path,options);
    if(typeof apiFetch==='function')return apiFetch(path,options);
    return window.fetch(path,options);
  }
  async function query(name,args={},options={}){
    cancelPending();ensure();const version=state.version,controller=new AbortController();
    const request={controller,slowTimer:null,timeout:null,timedOut:false};state.pending=request;
    state.title.textContent='Consultando…';state.panel.dataset.status='loading';state.panel.setAttribute('aria-busy','true');state.body.replaceChildren(el('p','data-loading','Consultando la fuente solicitada…'));notice();show();
    request.slowTimer=setTimeout(()=>{if(state.pending===request)notice('La fuente está tardando más de lo habitual. La consulta sigue en curso.');},8000);
    request.timeout=setTimeout(()=>{request.timedOut=true;controller.abort();},45000);
    try{
      if(typeof name!=='string'||!name.trim())throw new Error('Falta indicar qué dato querés consultar.');
      if(!args||typeof args!=='object'||Array.isArray(args))throw new Error('Los datos de la consulta no son válidos.');
      const response=await localFetch('/api/data/execute',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,arguments:args}),signal:controller.signal});
      let result;try{result=await response.json();}catch{throw new Error('La fuente no devolvió un resultado que Jarvis pueda mostrar.');}
      if(version!==state.version)return null;
      if(typeof options.isCurrent==='function'&&!options.isCurrent()){close();return null;}
      if(!response.ok)result={...result,status:'error',title:result?.title||'No pude completar la consulta',summary:result?.summary|| (typeof result?.detail==='string'?result.detail:`El servicio respondió con un error (${response.status}).`)};
      return present(result);
    }catch(error){
      if(version!==state.version)return null;
      if(typeof options.isCurrent==='function'&&!options.isCurrent()){close();return null;}
      return present({status:'error',title:request.timedOut?'La consulta tardó demasiado':'No pude consultar el dato',summary:request.timedOut?'La fuente no respondió a tiempo. Podés volver a hacer la consulta.':error.message||'No pude conectar con el compañero de Jarvis. Abrí Jarvis en tu PC y reintentá.'});
    }finally{clearTimeout(request.slowTimer);clearTimeout(request.timeout);if(state.pending===request)state.pending=null;}
  }
  function close(){state.animation?.cancel();state.animation=null;cancelPending();if(state.panel){state.panel.open=false;state.panel.hidden=true;state.panel.dataset.open='false';}if(state.connector)state.connector.dataset.visible='false';delete document.body.dataset.hudResult;delete document.body.dataset.hudSide;}
  function clear(){close();state.last=null;if(state.body)state.body.replaceChildren();if(state.title)state.title.textContent='Resultados';notice();}
  function open(){ensure();if(state.last&&!state.pending){present(state.last);return;}if(!state.last&&!state.pending){state.title.textContent='Resultados';state.body.replaceChildren(el('p','data-empty','Todavía no hay un resultado para mostrar.'));}show();}
  function settingsNotice(message='',kind='info'){const settings=state.settings;settings.notice.textContent=message;settings.notice.hidden=!message;settings.notice.dataset.kind=kind;}
  function ensureSettings(){
    if(state.settings)return state.settings;
    const panel=el('dialog','jarvis-data-panel jarvis-data-settings');panel.id='jarvisDataSettings';panel.setAttribute('aria-labelledby','jarvisDataSettingsTitle');
    const header=el('header','data-board-header'),heading=el('div');heading.append(el('div','data-eyebrow','JARVIS / CONEXIONES'));const title=el('h2','data-board-title','Servicios de datos');title.id='jarvisDataSettingsTitle';heading.append(title);
    const closeButton=el('button','data-close','×');closeButton.type='button';closeButton.setAttribute('aria-label','Cerrar configuración de datos');closeButton.addEventListener('click',()=>panel.close());header.append(heading,closeButton);
    const body=el('div','data-board-body'),intro=el('p','data-settings-intro','Conectá cada servicio con tu propia clave. Jarvis la guarda cifrada en esta PC.'),list=el('div','data-provider-list');list.setAttribute('aria-label','Servicios disponibles');
    const form=el('form','data-key-form');form.hidden=true;const label=el('label');label.htmlFor='jarvisDataKey';const input=el('input');input.id='jarvisDataKey';input.type='password';input.autocomplete='off';input.spellcheck=false;input.required=true;input.placeholder='Pegá tu clave acá';
    const note=el('p','data-key-note'),help=el('a','data-provider-help','Obtener mi clave en el sitio oficial ↗');help.target='_blank';help.rel='noopener noreferrer';const save=el('button','data-configure','Guardar clave');save.type='submit';form.append(label,input,note,help,save);
    const message=el('p','data-settings-notice');message.hidden=true;message.setAttribute('role','status');body.append(intro,list,form,message);panel.append(header,body);document.body.append(panel);
    const settings=state.settings={panel,list,form,label,input,note,help,save,notice:message,providers:{},selected:null,busy:false,revision:0};
    form.addEventListener('submit',saveProvider);panel.addEventListener('close',()=>{input.value='';});return settings;
  }
  function providerId(requested){
    if(typeof requested!=='string')return null;const normalized=requested.toLowerCase().trim(),providers=state.settings.providers;
    if(Object.hasOwn(providers,normalized))return normalized;
    for(const [id,provider] of Object.entries(providers)){if(sourceLabel(provider.label).toLowerCase()===normalized||(Array.isArray(provider.aliases)&&provider.aliases.some(alias=>String(alias).toLowerCase()===normalized)))return id;}
    return null;
  }
  function renderProviders(){
    const settings=state.settings;settings.list.replaceChildren();
    for(const [id,provider] of Object.entries(settings.providers)){
      if(!provider||typeof provider!=='object')continue;
      const button=el('button','data-provider');button.type='button';button.disabled=settings.busy;button.setAttribute('aria-pressed',String(id===settings.selected));button.append(el('span','data-provider-label',provider.label||id),el('small','data-provider-state',provider.configured?'Conectado':provider.required?'Falta clave':'Opcional'));button.dataset.configured=String(Boolean(provider.configured));button.addEventListener('click',()=>selectProvider(id));settings.list.append(button);
    }
  }
  function selectProvider(id){
    const settings=state.settings;if(settings.busy||!Object.hasOwn(settings.providers,id))return;const provider=settings.providers[id];settings.selected=id;settings.form.hidden=false;settings.input.value='';settings.label.textContent=`Clave de ${asText(provider.label||id)}`;settings.note.textContent=provider.required?'La clave se usa únicamente desde el compañero de Jarvis.':'Esta clave es opcional. Las fuentes públicas que no la requieren siguen disponibles.';
    const help=safeURL(provider.help_url);settings.help.hidden=!help;if(help)settings.help.href=help;else settings.help.removeAttribute('href');renderProviders();settings.input.focus();
  }
  async function providerCall(path,body,sensitive=''){
    const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),20000);const redact=value=>sensitive?String(value).split(sensitive).join('…'):String(value);
    try{
      const response=await localFetch(path,{...(body!==undefined?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{}),signal:controller.signal});let value;try{value=await response.json();}catch{throw new Error('El compañero no devolvió una respuesta válida.');}
      if(!response.ok)throw new Error(typeof value?.detail==='string'?redact(value.detail):'No pude actualizar este servicio. Revisá la clave y reintentá.');return value;
    }catch(error){throw new Error(error.name==='AbortError'?'El compañero tardó demasiado en responder. Reintentá la conexión.':redact(error.message||'No pude conectar con el compañero de Jarvis.'));}
    finally{clearTimeout(timeout);}
  }
  async function configure(requested){
    const settings=ensureSettings();if(!settings.panel.open)settings.panel.showModal();settings.input.value='';
    if(settings.busy){settingsNotice('Hay una clave guardándose. Esperá un momento.');return null;}
    const revision=++settings.revision;settings.form.hidden=true;settingsNotice('Comprobando los servicios de datos…');
    try{const value=await providerCall('/api/data/providers');if(revision!==settings.revision)return null;if(!value.providers||typeof value.providers!=='object'||Array.isArray(value.providers))throw new Error('No pude leer los servicios disponibles.');
      // Keep only public metadata; never retain a response's unknown credential fields.
      settings.providers=Object.fromEntries(Object.entries(value.providers).filter(([,provider])=>provider&&typeof provider==='object').map(([id,provider])=>[id,{label:provider.label||id,configured:Boolean(provider.configured),required:Boolean(provider.required),help_url:provider.help_url,aliases:provider.aliases}]));
      settings.selected=null;renderProviders();settingsNotice();const id=providerId(requested);if(id)selectProvider(id);else if(!settings.list.children.length)settingsNotice('No hay servicios configurables disponibles.');return settings.providers;
    }catch(error){if(revision===settings.revision)settingsNotice(error.message,'error');return null;}
  }
  async function saveProvider(event){
    event.preventDefault();const settings=state.settings;if(settings.busy||!settings.selected)return;const id=settings.selected,key=settings.input.value.trim();settings.input.value='';
    if(!key){settingsNotice('Pegá la clave del servicio antes de guardar.','error');return;}
    settings.busy=true;settings.save.disabled=true;settings.input.disabled=true;renderProviders();settingsNotice('Guardando la clave cifrada en esta PC…');
    try{await providerCall(`/api/data/providers/${encodeURIComponent(id)}`,{api_key:key},key);settings.providers[id].configured=true;settingsNotice('Clave guardada. Ya podés volver a consultar este servicio.');}
    catch(error){settingsNotice(error.message,'error');}
    finally{settings.input.value='';settings.input.disabled=false;settings.busy=false;settings.save.disabled=false;renderProviders();}
  }
  window.JarvisData={query,render,close,clear,open,configure,openSettings:configure,get lastResult(){return state.last;}};
})();
