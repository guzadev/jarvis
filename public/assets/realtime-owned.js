/* OpenAI handles live microphone audio; only the owner's approved profile speaks. */
(() => {
  // Billing failures and transient rate limits both use HTTP 429.
  // Preserve the provider's category without exposing its raw response or credentials.
  let quotaBlocked=false,retryAfter=0,needsOpenAI=true;
  function openAIError(status,body,headers){
    let data=body;
    if(typeof data==='string'){
      try{data=JSON.parse(data.replace(/^OpenAI:\s*/,''));}catch{data={};}
    }
    if(typeof data?.detail==='string'){
      try{data=JSON.parse(data.detail.replace(/^OpenAI:\s*/,''));}catch{}
    }
    const failure=data?.error||data||{};
    const code=failure.code||failure.type||headers?.get?.('X-Jarvis-OpenAI-Error')||'';
    const quota=['credit_balance_exhausted','insufficient_quota','billing_hard_limit_reached','organization_spend_limit_exceeded','project_spend_limit_exceeded','organization_usage_limit_exceeded'];
    const blocked=quota.includes(code)||failure.type==='insufficient_quota';
    let message;
    if(code==='credit_balance_exhausted')message='OpenAI se quedó sin crédito. Recargá el saldo de la API y después tocá Iniciar voz. Tu voz de Jarvis se conserva.';
    else if(code==='project_spend_limit_exceeded'||code==='organization_spend_limit_exceeded'||code==='billing_hard_limit_reached')message='Se alcanzó el límite de gasto de OpenAI. Revisá los límites de la API y después tocá Iniciar voz.';
    else if(code==='organization_usage_limit_exceeded')message='Se alcanzó el límite de uso de la organización en OpenAI. Revisá ese límite antes de iniciar voz.';
    else if(blocked)message='OpenAI bloqueó la conversación por saldo o cupo de la API. Revisá Facturación y Límites antes de iniciar voz.';
    else if(status===401||code==='invalid_api_key')message='OpenAI no aceptó la clave de la API. Revisá la conexión de OpenAI.';
    else if(status===403||code==='model_not_found')message='La cuenta de OpenAI no tiene acceso al modelo de conversación configurado.';
    else if(status===429||code==='rate_limit_exceeded'||code==='slow_down'){
      const hint=headers?.get?.('Retry-After');
      const seconds=hint?.trim()?Number(hint):NaN;
      const date=hint&&!Number.isFinite(seconds)?Date.parse(hint):NaN;
      const delay=Math.max(1000,Number.isFinite(seconds)&&seconds>=0?seconds*1000:Number.isFinite(date)?date-Date.now():30000);
      retryAfter=Date.now()+delay;
      message='OpenAI alcanzó un límite temporal de conexiones o solicitudes. Esperá '+Math.ceil(delay/1000)+' segundos antes de iniciar voz.';
    }else message='OpenAI no pudo conectar la conversación'+(status?' ('+status+')':'')+'. Volvé a intentar.';
    if(blocked)quotaBlocked=true;
    const error=new Error(message);
    error.code=/^[a-zA-Z0-9_.-]{1,80}$/.test(code)?code:'openai_connection';
    error.quotaBlocked=blocked;
    return error;
  }
  window.JarvisOpenAIError={fromResponse:openAIError,canAutoStart:()=>!needsOpenAI||(!quotaBlocked&&Date.now()>=retryAfter),
    setConfig(config){needsOpenAI=config.voice_mode==='openai'||(config.voice_mode==='owned'&&(config.conversation_provider||config.provider)==='openai'&&config.realtime_owned_enabled===true);},
    get quotaBlocked(){return quotaBlocked;},reset(){quotaBlocked=false;retryAfter=0;}};
  let live=false, epoch=0, responseId='', pending='', queue=[], draining=false, modelBusy=false;
  let speechRequest=null, nextAt=0, output=null, stats={};
  let deferredReply=null,pendingNotice=null;
  const metrics={};let metricsTimer=null,metricsStream=null,metricsPhase='stopped',metricsError='',inputPeak=0,metricsSession=0,metricsReport=0;
  const metricsId=globalThis.crypto?.randomUUID?.()||'voice_'+Date.now().toString(36)+Math.random().toString(36).slice(2);
  async function reportMetrics(){
    try{
      const session=metricsSession,report=++metricsReport,connection=pc,channel=dc,phase=metricsPhase,errorCode=metricsError,counts={...metrics};
      const track=metricsStream?.getAudioTracks()[0];
      const capture={microphone:track?.readyState,mic_enabled:track?.enabled,mic_muted:track?.muted,audio_context:audioContext?.state};
      let level=0;
      if(analyserIn){const values=new Float32Array(analyserIn.fftSize);analyserIn.getFloatTimeDomainData(values);level=Math.sqrt(values.reduce((sum,value)=>sum+value*value,0)/values.length);}
      inputPeak=Math.max(inputPeak,level);
      const snapshot={client_id:metricsId,phase,peer:connection?.connectionState,channel:channel?.readyState,...capture,input_level:level,input_peak:inputPeak,error_code:errorCode,counts};
      if(connection){const info=await connection.getStats();if(session!==metricsSession||report!==metricsReport)return;info.forEach(item=>{if(item.type==='outbound-rtp'&&item.kind==='audio'){counts.outbound_bytes=item.bytesSent||0;counts.outbound_packets=item.packetsSent||0;}});}
      if(session!==metricsSession||report!==metricsReport)return;
      Object.assign(metrics,{outbound_bytes:counts.outbound_bytes||0,outbound_packets:counts.outbound_packets||0});
      await apiFetch('/api/voice/diagnostics',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(snapshot),signal:AbortSignal.timeout(2000)});
    }catch{}
  }
  const count=name=>{metrics[name]=(metrics[name]||0)+1;};
  const sources=new Set(),ignored=new Set();
  const issue=message=>{const node=document.getElementById('voiceProblem');node.textContent=message;node.hidden=!message;};
  function watchCapture(connection,stream,signal,channel){
    let reconnectTimer=null,muteTimer=null;
    const track=stream.getAudioTracks()[0];
    const current=()=>live&&!signal.aborted&&pc===connection;
    const fail=(code,message)=>{
      if(!current())return;
      metricsError=code;void reportMetrics();
      stop();voiceIssue=message;issue(message);statusEl.textContent='La conversación se interrumpió';
    };
    const changed=()=>{
      if(!current())return;
      clearTimeout(reconnectTimer);reconnectTimer=null;
      if(connection.connectionState==='failed')fail('peer_failed','Se perdió la conexión de voz. Tocá Iniciar voz para reconectar.');
      else if(connection.connectionState==='disconnected'){
        statusEl.textContent='Recuperando la conexión de voz…';
        reconnectTimer=setTimeout(()=>{
          if(current()&&connection.connectionState==='disconnected')fail('peer_disconnected','No pude recuperar la conexión de voz. Tocá Iniciar voz para reconectar.');
        },8000);
      }else if(connection.connectionState==='connected')state();
    };
    const ended=()=>fail('microphone_ended','El micrófono dejó de estar disponible. Reconectalo y tocá Iniciar voz.');
    const channelClosed=()=>fail('events_closed','Se cerró el canal de conversación. Tocá Iniciar voz para reconectar.');
    const channelError=()=>fail('events_error','Falló el canal de conversación. Tocá Iniciar voz para reconectar.');
    const muted=()=>{
      clearTimeout(muteTimer);
      muteTimer=setTimeout(()=>{
        if(current()&&track.muted)fail('microphone_muted','El micrófono dejó de entregar audio. Revisá su conexión y tocá Iniciar voz.');
      },12000);
    };
    const unmuted=()=>{clearTimeout(muteTimer);muteTimer=null;};
    connection.addEventListener('connectionstatechange',changed);
    channel.addEventListener('close',channelClosed);channel.addEventListener('error',channelError);
    track?.addEventListener('ended',ended);track?.addEventListener('mute',muted);track?.addEventListener('unmute',unmuted);
    signal.addEventListener('abort',()=>{
      clearTimeout(reconnectTimer);clearTimeout(muteTimer);
      connection.removeEventListener('connectionstatechange',changed);
      channel.removeEventListener('close',channelClosed);channel.removeEventListener('error',channelError);
      track?.removeEventListener('ended',ended);track?.removeEventListener('mute',muted);track?.removeEventListener('unmute',unmuted);
    },{once:true});
    if(!track||track.readyState==='ended')ended();else if(track.muted)muted();
    return current();
  }
  function state(){
    responseInProgress=modelBusy||draining||sources.size>0;
    voiceActivityAt=Date.now();
    if(live)statusEl.textContent=sources.size?'Jarvis está hablando':modelBusy||draining?'Preparando la respuesta…':'Te escucho';
    metricsPhase=!live?'stopped':sources.size?'speaking':modelBusy||draining?'waiting':'listening';
  }
  function interrupt(){
    deferredReply=null;pendingNotice=null;epoch++;pending='';queue=[];speechRequest?.abort();speechRequest=null;
    for(const source of sources){try{source.stop();}catch{}source.disconnect();}sources.clear();
    draining=false;modelBusy=false;nextAt=0;
    if(responseId)ignored.add(responseId);
    state();
  }
  function pcm(bytes){
    const samples=new Float32Array(bytes.length/2),view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
    for(let i=0;i<samples.length;i++)samples[i]=view.getInt16(i*2,true)/32768;
    return samples;
  }
  function play(samples,turn){
    if(!live||turn!==epoch||!samples.length)return;
    const buffer=audioContext.createBuffer(1,samples.length,24000);buffer.copyToChannel(samples,0);
    const source=audioContext.createBufferSource();source.buffer=buffer;source.connect(output);
    const at=Math.max(audioContext.currentTime+.06,nextAt);nextAt=at+buffer.duration;
    sources.add(source);source.onended=()=>{sources.delete(source);source.disconnect();if(turn===epoch)state();};
    source.start(at);
    if(!stats.firstAudioMs&&stats.turnStarted)stats.firstAudioMs=Math.round(performance.now()-stats.turnStarted+(at-audioContext.currentTime)*1000);
    state();
  }
  async function drain(){
    if(draining||!live)return;
    const turn=epoch;draining=true;state();
    try{
      while(live&&turn===epoch&&queue.length){
        const text=queue.shift();speechRequest=new AbortController();
        const response=await apiFetch('/api/speech/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text}),signal:AbortSignal.any([speechRequest.signal,AbortSignal.timeout(120000)])});
        if(!response.ok){metricsError=response.headers.get('X-Jarvis-Voice-Error')||(response.status===429?'voice_busy':'voice_generation');let message='No pude generar tu voz de Jarvis.';try{message=(await response.json()).detail||message;}catch{}throw new Error(message);}
        if(response.headers.get('X-Audio-Format')!=='pcm_s16le'||response.headers.get('X-Audio-Sample-Rate')!=='24000')throw new Error('El motor no devolvió el formato de tu voz.');
        const reader=response.body.getReader();let carry=new Uint8Array();
        try{
          while(live&&turn===epoch){
            const {done,value}=await reader.read();if(done)break;
            metrics.pcm_bytes=(metrics.pcm_bytes||0)+value.length;
            const joined=new Uint8Array(carry.length+value.length);joined.set(carry);joined.set(value,carry.length);
            const size=joined.length-joined.length%2;carry=joined.slice(size);play(pcm(joined.subarray(0,size)),turn);
          }
        }finally{await reader.cancel().catch(()=>{});}
        if(carry.length)throw new Error('Llegó un bloque de audio incompleto.');
      }
    }catch(error){if(live&&turn===epoch&&error.name!=='AbortError')issue(error.name==='TypeError'?'Se perdió la conexión con la voz de Jarvis.':error.message);}
    finally{if(turn===epoch){draining=false;speechRequest=null;state();}}
  }
  function enqueue(text){
    const plain=text.replace(/[#*_`>|]/g,'').trim();if(!plain)return;
    queue.push(plain);drain();
  }
  function flush(final=false){
    while(pending){
      const match=pending.match(/^([\s\S]*?[.!?])(?:\s|$)/);
      let length=match?match[1].length:0;
      if(!length&&pending.length>=180){
        // Keep clauses together so the voice retains the context of the sentence.
        const clause=pending.slice(0,320).match(/^([\s\S]{60,}[,;:—])\s/);
        if(clause)length=clause[1].length;
      }
      if(!length&&pending.length>=320){
        const space=pending.lastIndexOf(' ',300);
        length=space>0?space:300;
      }
      if(!length&&final)length=pending.length;
      if(length<=0)break;
      enqueue(pending.slice(0,length));pending=pending.slice(length).trimStart();
    }
  }
  function afterTool(origin, respond){
    if(!live){respond();return;}
    if(!origin||ignored.has(origin)||origin!==responseId)return;
    if(modelBusy){deferredReply={origin,respond};return;}
    respond();
  }
  function afterTurn(turn,notify){
    if(!live){notify();return;}
    if(turn!==epoch)return;
    if(modelBusy){pendingNotice=notify;return;}
    notify();
  }
  function event(ev){
    if(!live)return;
    if(ev.type==='input_audio_buffer.speech_started'){
      count('speech_started');
      interrupt();stats={turnStarted:performance.now(),firstAudioMs:0};issue('');return;
    }
    if(ev.type==='input_audio_buffer.speech_stopped'){count('speech_stopped');stats.turnStarted=performance.now();return;}
    if(ev.type==='response.created'){
      count('responses');
      responseId=ev.response.id;pending='';modelBusy=true;if(!stats.turnStarted)stats.turnStarted=performance.now();state();return;
    }
    if(ignored.has(ev.response_id||ev.response?.id))return true;
    if(ev.type==='response.output_text.delta'){
      count('text_events');
      if(!stats.firstTextMs)stats.firstTextMs=Math.round(performance.now()-stats.turnStarted);
      pending+=ev.delta;flush();return;
    }
    if(ev.type==='response.done'){
      count('response_done');
      if(ev.response.status==='completed')flush(true);else pending='';
      modelBusy=false;state();
      const waiting=deferredReply;deferredReply=null;
      if(waiting&&ev.response.status==='completed'&&waiting.origin===ev.response.id)waiting.respond();
      else if(pendingNotice){const notify=pendingNotice;pendingNotice=null;notify();}
      if(ev.response.status==='failed'){
        const problem=openAIError(0,{error:ev.response.status_details?.error});
        metricsError=problem.code;
        if(problem.quotaBlocked){stop();voiceIssue=problem.message;}
        issue(problem.message);
      }
      if(ev.response.status==='incomplete'){
        const reason=ev.response.status_details?.reason||'unknown';
        metricsError=reason==='max_output_tokens'?'incomplete_max_output_tokens':'incomplete_response';
        issue('OpenAI cortó la respuesta antes de completarla. Revisá si hay una acción en curso antes de repetir el pedido.');
      }
    }
    if(ev.type==='response.function_call_arguments.done')count('tools');
    if(ev.type==='error'){
      count('errors');const problem=openAIError(0,ev);metricsError=problem.code;
      if(problem.quotaBlocked){stop();voiceIssue=problem.message;}
      issue(problem.message);
    }
  }
  async function prepareVoice(signal){
    const request=(path,method='GET')=>apiFetch(path,{method,signal:signal?AbortSignal.any([signal,AbortSignal.timeout(8000)]):AbortSignal.timeout(8000)});
    const first=await request('/api/speech/preparation','POST');
    if(!first.ok)throw new Error('No pude iniciar la preparación de tu voz de Jarvis.');
    let preparation=await first.json();
    const deadline=performance.now()+360000;
    while(!preparation.ready){
      if(signal?.aborted)throw new DOMException('Cancelado','AbortError');
      if(preparation.state==='error')throw new Error(preparation.message||'No pude preparar tu voz de Jarvis.');
      if(performance.now()>deadline)throw new Error('Tu voz sigue cargándose en esta PC. Podés seguir usando las acciones y volver a iniciar voz cuando termine.');
      responseInProgress=true;voiceActivityAt=Date.now();
      statusEl.textContent='Preparando tu voz de Jarvis…';
      sessionInfo.textContent=preparation.message||'Cargando el modelo local de tu voz; la aplicación sigue disponible.';
      await new Promise((resolve,reject)=>{
        const aborted=()=>{clearTimeout(timer);reject(new DOMException('Cancelado','AbortError'));};
        const timer=setTimeout(()=>{signal?.removeEventListener('abort',aborted);resolve();},1000);
        signal?.addEventListener('abort',aborted,{once:true});
        if(signal?.aborted)aborted();
      });
      const response=await request('/api/speech/preparation');
      if(!response.ok)throw new Error('Se perdió la conexión con la voz local. Volvé a intentar.');
      preparation=await response.json();
    }
  }
  let monitoringPreparation=false;
  async function monitorPreparation(){
    if(monitoringPreparation)return;monitoringPreparation=true;
    try{
      for(let attempt=0;attempt<180;attempt++){
        const response=await apiFetch('/api/speech/preparation',{signal:AbortSignal.timeout(4000)});
        if(!response.ok)return;
        const preparation=await response.json();
        if(preparation.ready){if(!running&&!starting)sessionInfo.textContent='Tu voz de Jarvis está lista. Decí Jarvis o tocá Iniciar voz.';return;}
        if(!running&&!starting){
          sessionInfo.textContent=preparation.message||'Cargando tu voz de Jarvis…';
          if(preparation.state==='error'){issue(preparation.message);return;}
          statusEl.textContent='Preparando tu voz de Jarvis…';
        }
        await new Promise(resolve=>setTimeout(resolve,2000));
      }
    }catch{}finally{monitoringPreparation=false;}
  }
  window.addEventListener('jarvis:agent-status',event=>{window.JarvisOpenAIError.setConfig(event.detail);if(event.detail?.voice_mode==='owned'&&event.detail?.realtime_owned_enabled)void monitorPreparation();});
  async function start({stream,signal}){
    metricsSession++;
    interrupt();ignored.clear();live=true;responseId='';stats={};issue('');
    for(const key of Object.keys(metrics))delete metrics[key];metricsError='';inputPeak=0;metricsStream=stream;metricsPhase='connecting';
    clearInterval(metricsTimer);metricsTimer=setInterval(reportMetrics,1500);
    signal.addEventListener('abort',()=>{clearInterval(metricsTimer);metricsTimer=null;metricsPhase='stopped';void reportMetrics();metricsStream=null;},{once:true});
    signal.addEventListener('abort',()=>{live=false;interrupt();output?.disconnect();output=null;},{once:true});
    output=analyserOut=audioContext.createAnalyser();output.fftSize=256;output.connect(audioContext.destination);
    statusEl.textContent='Conectando la conversación en vivo…';
    await prepareVoice(signal);
    if(signal.aborted)return;
    const response=await apiFetch('/api/session',{method:'POST',signal:AbortSignal.any([signal,AbortSignal.timeout(30000)])});
    const session=await response.json();if(!response.ok){const error=openAIError(response.status,session,response.headers);metricsError=error.code;throw error;}
    if(!session.local_voice)throw new Error('La sesión no conserva la voz de Jarvis elegida.');
    if(signal.aborted)return;
    const connection=pc=new RTCPeerConnection();stream.getTracks().forEach(track=>connection.addTrack(track,stream));
    // No remote audio is ever played: output is exclusively the approved local profile.
    const channel=dc=connection.createDataChannel('oai-events');channel.onmessage=message=>handleEvent(JSON.parse(message.data),channel);
    if(!watchCapture(connection,stream,signal,channel))return;
    let waitTimer=null,finishOpen;
    const opened=new Promise((resolve,reject)=>{
      let finished=false;
      const aborted=()=>finishOpen(Object.assign(new Error('Cancelado'),{name:'AbortError'}));
      finishOpen=error=>{if(finished)return;finished=true;clearTimeout(waitTimer);signal.removeEventListener('abort',aborted);error?reject(error):resolve();};
      channel.onopen=()=>finishOpen();
      signal.addEventListener('abort',aborted,{once:true});
    });
    opened.catch(()=>{});
    const offer=await connection.createOffer();await connection.setLocalDescription(offer);
    const answer=await fetch('https://api.openai.com/v1/realtime/calls',{method:'POST',headers:{Authorization:'Bearer '+session.client_secret,'Content-Type':'application/sdp'},body:offer.sdp,signal:AbortSignal.any([signal,AbortSignal.timeout(30000)])});
    const sdp=await answer.text();if(!answer.ok){const error=openAIError(answer.status,sdp,answer.headers);metricsError=error.code;throw error;}
    if(signal.aborted)return;
    await connection.setRemoteDescription({type:'answer',sdp});
    if(channel.readyState==='open')finishOpen();
    else waitTimer=setTimeout(()=>finishOpen(new Error('OpenAI no abrió el canal de voz. Reintentá.')),15000);
    await opened;
    if(signal.aborted||pc!==connection)return;
    window.JarvisOpenAIError.reset();
    sessionInfo.textContent='Voz de Jarvis · conversación en vivo';wakeConversation=false;
    enqueue('Sí, señor.');
    sessionTimer=setTimeout(()=>{stop();statusEl.textContent='Sesión finalizada. Tocá Iniciar voz para volver a conversar.';},(session.max_session_seconds||300)*1000);
    state();
  }
  window.JarvisRealtimeOwned={start,event,afterTool,afterTurn,prepareVoice,ignoresEvent:ev=>live&&ignored.has(ev.response_id||ev.response?.id),get turn(){return live?epoch:null;},get stats(){return {...stats};}};
})();
