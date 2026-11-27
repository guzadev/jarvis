/* User-initiated, origin-bound connection to the local Jarvis companion. */
(() => {
  'use strict';
  if (window.JarvisPC) return;
  const LOCAL_ORIGIN='http://127.0.0.1:8788',TIMEOUT_MS=12000;
  let active=null;
  function connectionError(code,message){const error=new Error(message);error.name='JarvisPCError';error.code=code;return error;}
  function settle(record,error,token){
    if(record.settled)return;
    record.settled=true;
    window.removeEventListener('message',record.onMessage);
    if(record.timeout!==null)clearTimeout(record.timeout);
    if(record.closedTimer!==null)clearInterval(record.closedTimer);
    if(active===record)active=null;
    try{record.popup?.close();}catch{}
    if(error)record.reject(error);else record.resolve(token);
  }
  function connect(){
    if(active)return active.promise;
    let resolve,reject;
    const promise=new Promise((accept,decline)=>{resolve=accept;reject=decline;});
    const record={promise,resolve,reject,popup:null,nonce:'',requested:false,settled:false,timeout:null,closedTimer:null,onMessage:null};
    active=record;
    try{
      const random=new Uint8Array(32);window.crypto.getRandomValues(random);
      record.nonce=Array.from(random,value=>value.toString(16).padStart(2,'0')).join('');
    }catch{
      active=null;
      reject(connectionError('PC_NOT_AVAILABLE','El navegador no pudo iniciar la conexión segura. Actualizá esta página y volvé a pulsar Iniciar voz.'));
      return promise;
    }
    record.onMessage=event=>{
      if(record.settled||event.source!==record.popup||event.origin!==LOCAL_ORIGIN)return;
      const data=event.data;
      if(!data||typeof data!=='object'||Array.isArray(data)||data.nonce!==record.nonce)return;
      if(data.type==='jarvis-pc-ready'){
        if(record.requested)return;
        record.requested=true;
        try{record.popup.postMessage({type:'jarvis-pc-link-request',nonce:record.nonce},LOCAL_ORIGIN);}
        catch{settle(record,connectionError('PC_NOT_AVAILABLE','No pude completar la conexión con Jarvis. Abrí Jarvis Aurelio en tu PC y volvé a pulsar Iniciar voz.'));}
      }else if(data.type==='jarvis-pc-paired'&&record.requested){
        if(typeof data.token!=='string'||data.token.length<32||data.token.length>256||/[^A-Za-z0-9_-]/.test(data.token))return;
        settle(record,null,data.token);
      }
    };
    // Install before opening. No await or network request may precede window.open:
    // the browser's original click gesture authorizes this one fixed local popup.
    window.addEventListener('message',record.onMessage);
    try{
      record.popup=window.open(`${LOCAL_ORIGIN}/connect?nonce=${encodeURIComponent(record.nonce)}`,'jarvis-pc-connect','popup=yes,width=440,height=320,resizable=yes,scrollbars=yes');
    }catch{}
    if(!record.popup){
      settle(record,connectionError('POPUP_BLOCKED','El navegador bloqueó la ventana de conexión. Permití esa ventana y volvé a pulsar Iniciar voz.'));
      return promise;
    }
    record.timeout=setTimeout(()=>settle(record,connectionError('PC_NOT_AVAILABLE','No pude encontrar Jarvis en esta PC. Abrí Jarvis Aurelio desde Windows y volvé a pulsar Iniciar voz.')),TIMEOUT_MS);
    record.closedTimer=setInterval(()=>{
      try{if(record.popup.closed)settle(record,connectionError('CANCELLED','Se cerró la conexión. Volvé a pulsar Iniciar voz para conectar.'));}
      catch{} // A browser isolation policy can hide closed; the bounded timeout remains.
    },250);
    return promise;
  }
  function cancel(){
    if(!active)return false;
    settle(active,connectionError('CANCELLED','Conexión cancelada.'));
    return true;
  }
  window.JarvisPC={connect,cancel};
})();
