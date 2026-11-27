/* Jarvis molecular hologram. Canvas only: no network, voice activation or dependencies. */
(() => {
  'use strict';
  const mounted=new WeakMap(),TAU=Math.PI*2,clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
  function geometry(){
    const nodes=[],edges=[],pairs=new Set(),golden=Math.PI*(3-Math.sqrt(5));
    for(let i=0;i<184;i++){
      const y=1-2*(i+.5)/184,r=Math.sqrt(1-y*y),angle=i*golden;
      const shell=1+.025*Math.sin(i*2.17);
      nodes.push({x:Math.cos(angle)*r*shell,y:y*shell,z:Math.sin(angle)*r*shell,shell:true,bright:i%13===0});
    }
    // Fixed inner clusters: stable topology, never randomized during animation.
    for(let i=0;i<46;i++){
      const y=1-2*(i+.5)/46,r=Math.sqrt(1-y*y),angle=i*golden+.8,depth=.28+.48*((i*17%43)/43);
      nodes.push({x:Math.cos(angle)*r*depth,y:y*depth,z:Math.sin(angle)*r*depth,shell:false,bright:i%9===0});
    }
    nodes.forEach((node,index)=>{
      const nearby=nodes.map((other,j)=>({j,d:(node.x-other.x)**2+(node.y-other.y)**2+(node.z-other.z)**2}))
        .filter(other=>other.j!==index&&(node.shell?nodes[other.j].shell:true))
        .sort((a,b)=>a.d-b.d).slice(0,node.shell?4:3);
      for(const other of nearby){if(other.d>(node.shell?.125:.42))continue;const a=Math.min(index,other.j),b=Math.max(index,other.j),key=`${a}:${b}`;if(pairs.has(key))continue;pairs.add(key);edges.push({a,b,shell:node.shell&&nodes[other.j].shell});}
    });
    return {nodes,edges};
  }
  function mount(canvas,options={}){
    if(!canvas||mounted.has(canvas))return mounted.get(canvas);
    const ctx=canvas.getContext('2d');if(!ctx)return null;
    const graph=geometry(),motion=matchMedia('(prefers-reduced-motion: reduce)'),buffers=new WeakMap();
    const projected=graph.nodes.map(()=>({x:0,y:0,z:0,depth:0}));
    const drawOrder=[...graph.edges.map((edge,index)=>({kind:'bond',index,depth:0})),...graph.nodes.map((node,index)=>({kind:'atom',index,depth:0}))];
    const colors=Array.from({length:16},(_,i)=>`rgba(59,209,243,${(.035+i*.033).toFixed(3)})`);
    const glow=document.createElement('canvas');glow.width=glow.height=64;const glowCtx=glow.getContext('2d');
    const light=glowCtx.createRadialGradient(32,32,0,32,32,32);light.addColorStop(0,'rgba(180,250,255,.65)');light.addColorStop(.18,'rgba(65,226,249,.28)');light.addColorStop(.5,'rgba(17,179,220,.07)');light.addColorStop(1,'rgba(0,130,180,0)');glowCtx.fillStyle=light;glowCtx.fillRect(0,0,64,64);
    const meter=options.spectrum,bars=meter?Array.from({length:28},()=>document.createElement('i')):[];if(meter)meter.replaceChildren(...bars);
    let yaw=-.35,pitch=.22,targetYaw=yaw,targetPitch=pitch,velocityX=0,velocityY=0;
    let hoverX=0,hoverY=0,parallaxX=0,parallaxY=0,energy=0,pointer=null;
    let inputEnergy=0,outputEnergy=0,speechPhase=0,speechYaw=0,speechPitch=0;
    let breathPhase=0,breathScale=1,renderRadius=192;
    let raf=0,lastFrame=0,lastMeter=0,lastInteraction=0,frames=0,dpr=1,visible=true,destroyed=false;
    const abort=new AbortController(),listen=(node,type,handler,config={})=>node.addEventListener(type,handler,{...config,signal:abort.signal});
    function schedule(){if(!raf&&!destroyed&&!document.hidden&&visible)raf=requestAnimationFrame(frame);}
    function resize(){const rect=canvas.getBoundingClientRect();dpr=Math.min(window.devicePixelRatio||1,2);const width=Math.max(1,Math.round(rect.width*dpr)),height=Math.max(1,Math.round(rect.height*dpr));if(canvas.width!==width||canvas.height!==height){canvas.width=width;canvas.height=height;}schedule();}
    function readAnalyser(analyser){
      if(!analyser||typeof analyser.getByteFrequencyData!=='function')return null;
      let data=buffers.get(analyser);if(!data||data.length!==analyser.frequencyBinCount){data=new Uint8Array(analyser.frequencyBinCount);buffers.set(analyser,data);}
      try{analyser.getByteFrequencyData(data);return data;}catch{return null;}
    }
    function mean(data){if(!data?.length)return 0;let sum=0;for(const value of data)sum+=value;return sum/data.length/255;}
    function project(x,y,z,radius){
      const cy=Math.cos(yaw+parallaxX+speechYaw),sy=Math.sin(yaw+parallaxX+speechYaw),cp=Math.cos(pitch+parallaxY+speechPitch),sp=Math.sin(pitch+parallaxY+speechPitch);
      const xx=x*cy+z*sy,zz=z*cy-x*sy,yy=y*cp-zz*sp,depth=y*sp+zz*cp;
      const perspective=760/(760-depth*radius);return {x:xx*radius*perspective,y:yy*radius*perspective,z:depth,depth:clamp((depth+1)/2,0,1)};
    }
    function frame(now){
      raf=0;if(destroyed||document.hidden||!visible)return;
      if(now-lastFrame<1000/30){schedule();return;}
      const dt=lastFrame?Math.min((now-lastFrame)/1000,.06):1/30;lastFrame=now;frames++;
      let signal={};try{signal=options.getSignal?.()||{};}catch{}
      const input=readAnalyser(signal.input),output=readAnalyser(signal.output),amplitude=clamp(Math.max(mean(input),mean(output))*2.8,0,1);
      energy+=(amplitude-energy)*(motion.matches?1:1-Math.exp(-dt*12));
      inputEnergy+=(clamp(mean(input)*2.8,0,1)-inputEnergy)*(motion.matches?1:1-Math.exp(-dt*12));
      outputEnergy+=(clamp(mean(output)*4.2,0,1)-outputEnergy)*(motion.matches?1:1-Math.exp(-dt*15));
      // Speech has its own source: microphone activity never triggers the speaking torsion.
      if(!motion.matches&&outputEnergy>.002)speechPhase+=dt*(2.3+outputEnergy*3.2);
      speechYaw=motion.matches?0:Math.sin(speechPhase*.85)*outputEnergy*.17;
      speechPitch=motion.matches?0:Math.cos(speechPhase*.63)*outputEnergy*.11;
      canvas.dataset.signal=outputEnergy>.012?'speaking':inputEnergy>.012?'listening':'idle';
      // One coherent 5.8-second breath in real 3D; phase pauses with rendering.
      // Base radius +/-2.4%, node drift +/-0.45%: combined idle change stays below 3%.
      if(!motion.matches)breathPhase=(breathPhase+dt*TAU/5.8)%TAU;
      breathScale=motion.matches?1:1+.024*Math.sin(breathPhase);
      if(!pointer?.dragging){
        if(!motion.matches){targetYaw+=velocityX*dt;targetPitch=clamp(targetPitch+velocityY*dt,-1.35,1.35);const decay=Math.exp(-dt*5.5);velocityX*=decay;velocityY*=decay;if(now-lastInteraction>1800)targetYaw+=dt*.048;}
        else velocityX=velocityY=0;
      }
      const ease=motion.matches?1:1-Math.exp(-dt*19);yaw+=(targetYaw-yaw)*ease;pitch+=(targetPitch-pitch)*ease;
      parallaxX+=((motion.matches?0:hoverX)-parallaxX)*ease;parallaxY+=((motion.matches?0:hoverY)-parallaxY)*ease;
      const w=canvas.width,h=canvas.height,scale=Math.min(w,h)/600;
      ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,w,h);ctx.setTransform(scale,0,0,scale,w/2,h/2);
      const radius=renderRadius=192*breathScale+inputEnergy*10+outputEnergy*25;
      const field=ctx.createRadialGradient(0,0,10,0,0,265);field.addColorStop(0,`rgba(7,137,171,${.055+(breathScale-1)*.35+inputEnergy*.035+outputEnergy*.14})`);field.addColorStop(.65,`rgba(5,112,145,${.025+outputEnergy*.035})`);field.addColorStop(1,'rgba(0,50,90,0)');ctx.fillStyle=field;ctx.fillRect(-290,-290,580,580);
      // Quiet optical frame: two interrupted hairlines, no panels, sectors or text.
      ctx.strokeStyle='rgba(61,181,219,.22)';ctx.lineWidth=.9;
      for(const [r,a,b] of [[264,-2.88,-.78],[264,-.48,.72],[264,1.04,2.88],[256,-2.36,.26],[256,.98,2.04]]){ctx.beginPath();ctx.arc(0,0,r,a,b);ctx.stroke();}
      ctx.strokeStyle='rgba(143,227,242,.32)';ctx.lineWidth=1.15;for(let i=0;i<4;i++){const a=i*TAU/4+.22;ctx.beginPath();ctx.moveTo(Math.cos(a)*260,Math.sin(a)*260);ctx.lineTo(Math.cos(a)*266,Math.sin(a)*266);ctx.stroke();}
      for(let i=0;i<graph.nodes.length;i++){const node=graph.nodes[i],twist=motion.matches?0:outputEnergy*.12*Math.sin(speechPhase+node.y*2.4),drift=motion.matches?1:1+.0045*Math.sin(breathPhase+node.x*.9+node.y*.7+node.z*.8)+outputEnergy*.018*Math.sin(speechPhase*1.7+node.y*3+node.x*2),x=node.x*Math.cos(twist)-node.z*Math.sin(twist),z=node.x*Math.sin(twist)+node.z*Math.cos(twist),p=project(x*drift,node.y*drift,z*drift,radius);Object.assign(projected[i],p);}
      for(const item of drawOrder){if(item.kind==='atom')item.depth=projected[item.index].z;else{const edge=graph.edges[item.index];item.depth=(projected[edge.a].z+projected[edge.b].z)/2;}}
      drawOrder.sort((a,b)=>a.depth-b.depth);
      // A few curved orbital filaments keep the hologram's laboratory character.
      for(let orbit=0;orbit<2;orbit++){const filamentScale=motion.matches?1:1+.004*Math.sin(breathPhase+orbit*1.3),tilt=.64+orbit*.98+(motion.matches?0:Math.sin(speechPhase*(.6+orbit*.12))*outputEnergy*.2);ctx.beginPath();for(let i=0;i<=96;i++){const a=i/96*TAU;const x=Math.cos(a)*1.12,y=Math.sin(a)*Math.cos(tilt)*1.12,z=Math.sin(a)*Math.sin(tilt)*1.12,p=project(x,y,z,radius*filamentScale);i?ctx.lineTo(p.x,p.y):ctx.moveTo(p.x,p.y);}ctx.strokeStyle=orbit?'rgba(78,207,235,.16)':'rgba(117,232,245,.21)';ctx.lineWidth=.75+outputEnergy*.6;ctx.stroke();}
      // Atoms and bonds share one depth order: foreground geometry occludes the back.
      for(const ordered of drawOrder){
        if(ordered.kind==='bond'){const edge=graph.edges[ordered.index],a=projected[edge.a],b=projected[edge.b],depth=(a.depth+b.depth)/2;
          const shade=Math.round(clamp((depth*.88+(edge.shell ? .08 : 0)+energy*.1+outputEnergy*.12)*15,0,15));ctx.strokeStyle=colors[shade];ctx.lineWidth=(edge.shell ? .56 : .42)+depth*.56+outputEnergy*.15;ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();continue;}
        const point=projected[ordered.index],node=graph.nodes[ordered.index],near=point.depth;
        if(node.bright&&near>.34){const diameter=13+near*13+inputEnergy*4+outputEnergy*20;ctx.globalAlpha=.23+near*.44;ctx.drawImage(glow,point.x-diameter/2,point.y-diameter/2,diameter,diameter);ctx.globalAlpha=1;}
        const atom=(node.shell?.7:.95)+near*(node.bright?1.65:.9)+energy*.3;
        ctx.fillStyle=node.bright?`rgba(185,248,255,${.18+near*.75})`:`rgba(64,212,239,${.12+near*.61})`;ctx.beginPath();ctx.arc(point.x,point.y,atom,0,TAU);ctx.fill();
        if(node.bright&&near>.65){ctx.strokeStyle='rgba(124,231,244,.18)';ctx.lineWidth=.6;ctx.beginPath();ctx.arc(point.x,point.y,atom+3.5,0,TAU);ctx.stroke();}
      }
      if(now-lastMeter>90){lastMeter=now;bars.forEach((bar,index)=>{const value=input?.length?input[Math.floor(index*input.length/bars.length)]/255:0;bar.style.height=`${2+value*35}px`;});}
      if(!motion.matches||pointer?.dragging||signal.active||energy>.002||Math.abs(targetYaw-yaw)>.001||Math.abs(targetPitch-pitch)>.001)schedule();
    }
    function endPointer(event){
      if(!pointer||event.pointerId!==pointer.id)return;
      const id=pointer.id;pointer=null;canvas.dataset.dragging='false';lastInteraction=performance.now();
      if(event.type==='pointercancel'||motion.matches){velocityX=velocityY=0;}
      try{if(canvas.hasPointerCapture(id))canvas.releasePointerCapture(id);}catch{}
      schedule();
    }
    listen(canvas,'pointerdown',event=>{
      if(pointer||!event.isPrimary||event.button!==0)return;
      const rect=canvas.getBoundingClientRect(),x=(event.clientX-rect.left)/rect.width-.5,y=(event.clientY-rect.top)/rect.height-.5;
      if(x*x+y*y>.245)return;
      pointer={id:event.pointerId,touch:event.pointerType==='touch',x:event.clientX,y:event.clientY,startX:event.clientX,startY:event.clientY,last:performance.now(),dragging:false};
      velocityX=velocityY=0;lastInteraction=performance.now();
      if(!pointer.touch){canvas.focus({preventScroll:true});canvas.setPointerCapture(event.pointerId);event.preventDefault();}
      schedule();
    });
    listen(canvas,'pointermove',event=>{
      const rect=canvas.getBoundingClientRect();
      if(!pointer){if(event.pointerType==='mouse'&&!motion.matches){hoverX=clamp((event.clientX-rect.left)/rect.width-.5,-.5,.5)*.13;hoverY=clamp((event.clientY-rect.top)/rect.height-.5,-.5,.5)*-.1;schedule();}return;}
      if(event.pointerId!==pointer.id)return;
      const totalX=event.clientX-pointer.startX,totalY=event.clientY-pointer.startY;
      if(!pointer.dragging){
        if(Math.hypot(totalX,totalY)<6)return;
        // On touch, vertical gestures belong to page scrolling, horizontal gestures rotate.
        if(pointer.touch&&Math.abs(totalX)<Math.abs(totalY)*1.15)return;
        pointer.dragging=true;canvas.dataset.dragging='true';try{canvas.setPointerCapture(event.pointerId);}catch{}
      }
      const now=performance.now(),dt=clamp((now-pointer.last)/1000,.008,.08),speed=3.9/Math.max(240,rect.width);
      const dx=(event.clientX-pointer.x)*speed,dy=(event.clientY-pointer.y)*speed;
      targetYaw+=dx;targetPitch=clamp(targetPitch+dy,-1.35,1.35);velocityX=clamp(dx/dt,-3.5,3.5);velocityY=clamp(dy/dt,-2.5,2.5);
      pointer.x=event.clientX;pointer.y=event.clientY;pointer.last=now;lastInteraction=now;hoverX=hoverY=0;
      if(event.cancelable)event.preventDefault();schedule();
    });
    listen(canvas,'pointerup',endPointer);listen(canvas,'pointercancel',endPointer);listen(canvas,'lostpointercapture',event=>{if(pointer?.id===event.pointerId){pointer=null;velocityX=velocityY=0;canvas.dataset.dragging='false';schedule();}});
    listen(canvas,'pointerleave',()=>{hoverX=hoverY=0;schedule();});
    listen(canvas,'keydown',event=>{
      const step=event.shiftKey?.3:.15;
      if(event.key==='ArrowLeft')targetYaw-=step;else if(event.key==='ArrowRight')targetYaw+=step;else if(event.key==='ArrowUp')targetPitch=clamp(targetPitch-step,-1.35,1.35);else if(event.key==='ArrowDown')targetPitch=clamp(targetPitch+step,-1.35,1.35);else if(event.key==='Home'){targetYaw=-.35;targetPitch=.22;}else return;
      event.preventDefault();velocityX=velocityY=0;lastInteraction=performance.now();schedule();
    });
    listen(document,'visibilitychange',()=>{lastFrame=0;if(document.hidden){cancelAnimationFrame(raf);raf=0;pointer=null;velocityX=velocityY=0;canvas.dataset.dragging='false';}else schedule();});
    listen(motion,'change',()=>{velocityX=velocityY=0;hoverX=hoverY=0;schedule();});listen(window,'resize',resize);
    const resizeObserver=new ResizeObserver(resize);resizeObserver.observe(canvas);
    const intersection=new IntersectionObserver(entries=>{visible=entries[0]?.isIntersecting!==false;if(visible){lastFrame=0;schedule();}else{cancelAnimationFrame(raf);raf=0;}},{rootMargin:'80px'});intersection.observe(canvas);
    const voiceObserver=new MutationObserver(schedule);voiceObserver.observe(document.body,{attributes:true,attributeFilter:['data-voice']});
    const instance={reset(){targetYaw=-.35;targetPitch=.22;velocityX=velocityY=0;lastInteraction=performance.now();schedule();},destroy(){destroyed=true;cancelAnimationFrame(raf);abort.abort();resizeObserver.disconnect();intersection.disconnect();voiceObserver.disconnect();mounted.delete(canvas);},get diagnostics(){return {nodes:graph.nodes.length,bonds:graph.edges.length,yaw,pitch,targetYaw,targetPitch,dragging:Boolean(pointer?.dragging),energy,inputEnergy,outputEnergy,speechYaw,speechPitch,frames,dpr,reducedMotion:motion.matches,breathPhase,breathScale,renderRadius};}};
    mounted.set(canvas,instance);resize();return instance;
  }
  window.JarvisMolecularOrb={mount};
})();
