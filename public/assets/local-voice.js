/* Offline voice uses the exact same missions API as the text console. */
(() => {
  let active=false, recorder=null, vadTimer=null, generation=0, busy=false, controller=null, voiceMode='local';
  let capturedStream=null;
  function releaseCapture(){
    if(!capturedStream)return;
    capturedStream.getTracks?.().forEach(track=>track.stop());
    if(micStream===capturedStream)micStream=null;
    capturedStream=null;
  }
  const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  function selectMicrophone(devices,name){
    const generic=new Set(['microphone','microfono','mic','input','entrada','auricular','auriculares','headset','hands','free','audio','bluetooth','ag','default','predeterminado','communications','comunicaciones','dispositivo','de','la','del','the','array','matriz']);
    const tokens=value=>String(value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().split(/[^a-z0-9]+/).filter(word=>word&&!generic.has(word));
    const wanted=tokens(name);if(!wanted.length)return null;
    const candidates=devices.filter(device=>device.kind==='audioinput').map(device=>{const found=tokens(device.label);const hits=wanted.filter(word=>found.includes(word)).length;return {device,score:hits/Math.sqrt(wanted.length*Math.max(found.length,1))-(['default','communications'].includes(device.deviceId) ? .001 : 0)};});
    candidates.sort((a,b)=>b.score-a.score);
    if(!(candidates[0]?.score>0)||candidates[1]?.score===candidates[0].score)return null;
    return candidates[0].device;
  }
  async function request(path,options={},timeout=20000,kind='json'){
    const parent=controller?.signal,deadline=new AbortController();
    const cancel=()=>deadline.abort();parent?.addEventListener('abort',cancel,{once:true});
    if(parent?.aborted)deadline.abort();
    const timer=setTimeout(()=>deadline.abort(),timeout);
    try{
      const response=await apiFetch(path,{...options,signal:deadline.signal});
      const body=await response[kind]();
      return {ok:response.ok,status:response.status,[kind]:async()=>body};
    }
    catch(error){
      if(deadline.signal.aborted&&!parent?.aborted)throw new Error('La PC tardó demasiado en responder. Volvé a intentar.');
      if(error.name==='TypeError')throw new Error('Se perdió la conexión con Jarvis en esta PC. Volvé a tocar Iniciar voz.');
      throw error;
    }
    finally{clearTimeout(timer);parent?.removeEventListener('abort',cancel);}
  }
  function notice(message=''){
    const node=typeof document!=='undefined'?document.getElementById('voiceProblem'):null;
    if(node){node.textContent=message;node.hidden=!message;}
  }
  const json=async(path,body)=>{
    const response=await request(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)},path==='/api/speech/speak'?180000:20000);
    const data=await response.json();if(!response.ok)throw new Error(data.detail||'No pude procesar la voz.');return data;
  };
  function setState(text){statusEl.textContent=text;voiceActivityAt=Date.now();}
  const cancelled=()=>Object.assign(new Error('Conexión cancelada.'),{name:'AbortError'});
  function microphone(constraints,signal){
    if(signal?.aborted)return Promise.reject(cancelled());
    return new Promise((resolve,reject)=>{
      let finished=false;
      const finish=(error,stream)=>{if(finished){stream?.getTracks().forEach(track=>track.stop());return;}finished=true;clearTimeout(timer);signal?.removeEventListener('abort',abort);error?reject(error):resolve(stream);};
      const abort=()=>finish(cancelled());
      const timer=setTimeout(()=>finish(new Error('El permiso del micrófono sigue pendiente. Elegí Permitir en el aviso del navegador y tocá Iniciar voz para reintentar.')),30000);
      signal?.addEventListener('abort',abort,{once:true});
      try{navigator.mediaDevices.getUserMedia(constraints).then(stream=>finish(null,stream),finish);}catch(error){finish(error);}
    });
  }
  async function speak(text,turn){
    // Split all prose into short model inputs; there is no overall character quota.
    const plain=text.replace(/```[\s\S]*?```/g,' El código está en pantalla. ').replace(/!\[[^\]]*\]\([^)]*\)/g,'').replace(/\[([^\]]+)\]\([^)]*\)/g,'$1').replace(/[#*_`>|]/g,'');
    const sentences=plain.match(/[^.!?]+[.!?]+|[^.!?]+$/g)||[plain];const chunks=[];
    for(const sentence of sentences){let rest=sentence.trim();while(rest.length>420){let cut=rest.lastIndexOf(' ',420);if(cut<1)cut=420;chunks.push(rest.slice(0,cut));rest=rest.slice(cut).trim();}if(rest){if(chunks.length&&(chunks.at(-1).length+rest.length<420))chunks[chunks.length-1]+=' '+rest;else chunks.push(rest);}}
    for(const chunk of chunks){
      if(!active||turn!==generation)return;
      setState('Jarvis está preparando la voz…');
      const result=await json('/api/speech/speak',{text:chunk});
      if(!active||turn!==generation)return;
      const response=await request('/api/speech/audio/'+result.audio,{},20000,'blob');if(!response.ok)throw new Error('No pude reproducir la voz de Jarvis.');
      const url=URL.createObjectURL(await response.blob());
      try{
        if(!active||turn!==generation)return;
        const audio=speechAudio=new Audio(url);
        analyserOut=audioContext.createAnalyser();analyserOut.fftSize=256;
        const source=audioContext.createMediaElementSource(audio);source.connect(analyserOut);analyserOut.connect(audioContext.destination);
        setState('Jarvis está hablando');
        await new Promise((resolve,reject)=>{audio.onended=resolve;audio.onerror=()=>reject(new Error('No pude reproducir la voz.'));audio.onpause=resolve;audio.play().catch(()=>reject(new Error('Pulsá Iniciar voz una vez para permitir el audio del navegador.')));});
      }finally{URL.revokeObjectURL(url);analyserOut=null;}
    }
  }
  async function mission(text,turn){
    const project=typeof window.JarvisMissions?.selectedProject==='function'?window.JarvisMissions.selectedProject():window.JarvisMissions?.selectedProject||'aurelio';
    const task=await json('/api/missions',{title:text.slice(0,90),prompt:text,project});
    window.dispatchEvent(new CustomEvent('jarvis:mission-created',{detail:task}));
    let reviewShown=false;
    while(active&&turn===generation){
      const response=await request('/api/missions/'+task.id);const item=await response.json();if(!response.ok)throw new Error(item.detail||'No pude seguir la misión.');
      if(!active||turn!==generation)return;
      voiceActivityAt=Date.now();
      if(item.status==='awaiting_approval'){
        setState('Hay una ejecución para revisar en Misiones');
        if(!reviewShown){reviewShown=true;const panel=document.getElementById('missionsPanel');if(panel&&!panel.open)panel.showModal();window.JarvisMissions?.refresh?.();}
      } else {
        const elapsed=Math.max(0,Math.floor((Date.now()/1000)-(item.started||Date.now()/1000)));
        const message=item.status==='queued'?'Tu pedido está en la cola de esta PC.':item.events?.at(-1)?.message||'Preparando el motor de Jarvis…';
        setState(message+(elapsed>=5?' · '+elapsed+' s':''));
      }
      if(!['queued','running','awaiting_approval'].includes(item.status)){
        transcriptEl.textContent=item.output||item.status;
        window.JarvisMissions?.refresh?.();
        if(item.status==='done')await speak(item.output,turn);
        else if(item.status==='error'||item.status==='interrupted')throw new Error(item.output||'No pude completar el pedido. Podés volver a intentarlo.');
        return;
      }
      await delay(1200);
    }
  }
  async function consume(blob,turn){
    if(!active||turn!==generation)return;
    busy=true;responseInProgress=true;
    micStream?.getAudioTracks().forEach(track=>track.enabled=false);
    try{
      notice();
      setState('Transcribiendo en tu PC…');
      const response=await request('/api/speech/transcribe',{method:'POST',headers:{'Content-Type':blob.type||'audio/webm'},body:blob},120000);
      const data=await response.json();if(!response.ok)throw new Error(data.detail||'No pude transcribir.');
      if(!active||turn!==generation)return;
      const text=(data.text||'').trim();
      if(!text||/^[¡¿\s]*(gracias por ver|suscr[ií]bete|subt[ií]tulos)[.!¡?¿\s]*$/i.test(text))return;
      transcriptEl.textContent=text;
      if(data.uncertain){
        notice('No entendí con claridad: «'+text+'». Repetí tu pedido, por favor.');
        await speak('No entendí bien. ¿Podés repetir tu pedido?',turn);return;
      }
      if(/^(volv[eé] a esperar|terminamos|finaliz[aá] la voz|dej[aá] de escuchar)[.!?]*$/i.test(text)){stop();return;}
      await mission(text,turn);
    }catch(error){if(active&&turn===generation&&error.name!=='AbortError'){notice(error.message);setState('Error · '+error.message);addCard('Voz de Jarvis',error.message,'warning');}}
    finally{
      if(turn!==generation)return;
      busy=false;responseInProgress=false;voiceActivityAt=Date.now();
      if(active&&turn===generation){micStream?.getAudioTracks().forEach(track=>track.enabled=true);setState(voiceMode==='fish'?'Te escucho · Jarvis de Fish':'Te escucho · voz local');capture(turn);}
    }
  }
  function capture(turn){
    if(!active||turn!==generation)return;
    const parts=[];let voiced=0,lastSpeech=0;const begin=performance.now();
    const preferred=MediaRecorder.isTypeSupported('audio/webm;codecs=opus')?'audio/webm;codecs=opus':'';
    const current=recorder=new MediaRecorder(micStream,{...(preferred?{mimeType:preferred}:{}),audioBitsPerSecond:32000});
    current.ondataavailable=event=>{if(event.data.size)parts.push(event.data);};
    current.onstop=()=>{clearInterval(timer);if(vadTimer===timer)vadTimer=null;if(active&&turn===generation&&voiced>=200)consume(new Blob(parts,{type:current.mimeType}),turn);else if(active&&turn===generation)capture(turn);};
    current.start(250);const samples=new Float32Array(analyserIn.fftSize);
    const timer=setInterval(()=>{
      if(!active||turn!==generation){clearInterval(timer);return;}
      analyserIn.getFloatTimeDomainData(samples);let sum=0;for(const value of samples)sum+=value*value;
      const rms=Math.sqrt(sum/samples.length),now=performance.now();
      if(rms>.016){lastSpeech=now;voiced+=60;voiceActivityAt=Date.now();}
      // A long sentence stays one mission. Recycle only a completely silent capture.
      if((voiced>=200&&now-lastSpeech>1100)||(!voiced&&now-begin>24000)){if(current.state==='recording')current.stop();}
    },60);
    vadTimer=timer;
  }
  async function startLocal(config,options={}){
    const turn=++generation;
    controller=new AbortController();
    const signal=options.signal?AbortSignal.any([options.signal,controller.signal]):controller.signal;
    try{await setupLocal(config,{signal},turn);}
    catch(error){if(turn===generation)stopLocal();throw error;}
  }
  async function setupLocal(config,options,turn){
    const valid=()=>turn===generation&&!options.signal.aborted;
    voiceMode=config.voice_mode==='owned'?'owned':config.voice_mode==='fish'?'fish':'local';
    if(voiceMode==='owned'&&!config.owned?.approved){window.JarvisOwned?.open();throw new Error('El perfil local de Jarvis está en preparación o pendiente de tu escucha. El texto sigue disponible.');}
    if(voiceMode==='fish'&&!config.fish?.key_configured){window.JarvisFish?.open();throw new Error('Conectá la clave de Fish en Voz de Jarvis para usar la voz que elegiste.');}
    if(voiceMode==='fish'&&!config.fish?.free_available)throw new Error('La modalidad gratuita de Fish necesita revalidación. No se activó una voz alternativa.');
    await holdWakeMicrophone();
    if(!valid())throw cancelled();
    const name=(wakeStatus?.preferred_microphone==='auto'?wakeStatus?.microphone:wakeStatus?.preferred_microphone)||'';
    const devices=await navigator.mediaDevices.enumerateDevices();const match=selectMicrophone(devices,name);
    statusEl.textContent='Abriendo el micrófono… Elegí Permitir si el navegador lo pregunta.';
    const processing={echoCancellation:true,noiseSuppression:true,autoGainControl:true};
    async function acquire(deviceId){
      if(!valid())throw cancelled();
      const stream=await microphone({audio:{...processing,...(deviceId?{deviceId}:{})}},options.signal);
      if(!valid()){stream.getTracks().forEach(track=>track.stop());throw cancelled();}
      capturedStream=micStream=stream;
      return stream;
    }
    let stream=await acquire(match?{ideal:match.deviceId}:null);
    // Labels become available after the first permission. Resolve Windows' input then.
    if(!match&&name){
      const resolved=selectMicrophone(await navigator.mediaDevices.enumerateDevices(),name);
      if(!valid())throw cancelled();
      const currentTrack=stream.getAudioTracks()[0],settings=currentTrack?.getSettings?.()||{};
      const sameInput=resolved&&(settings.deviceId===resolved.deviceId||
        (settings.groupId&&settings.groupId===resolved.groupId)||currentTrack?.label===resolved.label);
      if(resolved&&!sameInput){
        releaseCapture();
        try{stream=await acquire({exact:resolved.deviceId});}
        catch(error){
          if(!valid()||!['NotReadableError','NotFoundError','OverconstrainedError','AbortError'].includes(error.name))throw error;
          stream=await acquire(null);
        }
      }
    }
    audioContext=audioContext||new AudioContext();await Promise.race([audioContext.resume(),new Promise((_,reject)=>setTimeout(()=>reject(new Error('Pulsá Iniciar voz una vez para habilitar el audio.')),2000))]);
    if(!valid())throw cancelled();
    analyserIn=audioContext.createAnalyser();analyserIn.fftSize=1024;audioContext.createMediaStreamSource(micStream).connect(analyserIn);
    active=true;
    syncHud();sessionInfo.textContent=voiceMode==='owned'?'Jarvis propio · voz local · sin API de voz':voiceMode==='fish'?'Voz de Jarvis · Fish gratis · requiere Internet · reposo tras 25 s de silencio':'Voz local · sin cupo de minutos · vuelve a espera tras 25 s de silencio';
    if((config.conversation_provider||config.provider)==='openai'&&voiceMode==='owned'&&config.realtime_owned_enabled){
      if(!window.JarvisRealtimeOwned)throw new Error('La conexión de voz está cargando. Recargá Jarvis.');
      await window.JarvisRealtimeOwned.start({stream:micStream,signal:options.signal});
      if(!valid())throw cancelled();
      running=true;syncHud();return;
    }
    running=true;syncHud();
    if(wakeConversation||voiceMode==='owned'){wakeConversation=false;busy=true;responseInProgress=true;micStream.getAudioTracks().forEach(track=>track.enabled=false);try{await speak('Sí, señor.',turn);}finally{if(turn===generation){busy=false;responseInProgress=false;micStream?.getAudioTracks().forEach(track=>track.enabled=true);}}}
    if(!valid()||!active)return;
    setState(voiceMode==='fish'?'Te escucho · Jarvis de Fish':'Te escucho · voz local');capture(turn);
  }
  function stopLocal(){active=false;generation++;controller?.abort();controller=null;clearInterval(vadTimer);vadTimer=null;const old=recorder;recorder=null;if(old?.state==='recording')old.stop();releaseCapture();busy=false;}
  window.JarvisLocalVoice={start:startLocal,stop:stopLocal,selectMicrophone,get active(){return active;},get busy(){return busy;}};
})();
