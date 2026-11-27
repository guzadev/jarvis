"""Short-lived local voice metrics. Never accepts text, audio or credentials."""
from collections import OrderedDict
import math
import re
import threading
import time

LOCK=threading.Lock()
RECENT=OrderedDict()
COUNTERS={'speech_started','speech_stopped','responses','text_events','response_done','errors','tools','pcm_bytes','outbound_bytes','outbound_packets'}
STATES={'connecting','listening','speaking','waiting','stopped','error','new','checking','connected','completed','disconnected','failed','closed','open','closing','live','ended','suspended','running','interrupted'}

def record(value):
    identifier=value.get('client_id')
    if not isinstance(identifier,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}',identifier):raise ValueError('Identificador no válido.')
    result={'client_id':identifier,'at':time.time()}
    for name in ('phase','peer','channel','microphone','audio_context'):
        if value.get(name) in STATES:result[name]=value[name]
    for name in ('mic_enabled','mic_muted'):
        if isinstance(value.get(name),bool):result[name]=value[name]
    for name in ('input_level','input_peak'):
        level=value.get(name)
        if isinstance(level,(float,int)) and math.isfinite(level):result[name]=round(max(0,min(1,level)),4)
    result['counts']={name:min(max(int(count),0),10**12) for name,count in value.get('counts',{}).items()
                      if name in COUNTERS and isinstance(count,(int,float)) and math.isfinite(count)}
    code=value.get('error_code')
    if isinstance(code,str) and re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}',code):result['error_code']=code
    with LOCK:
        RECENT[identifier]=result;RECENT.move_to_end(identifier)
        while len(RECENT)>6:RECENT.popitem(last=False)
    return {'ok':True}

def snapshots():
    with LOCK:return {'clients':[dict(value) for value in RECENT.values() if time.time()-value['at']<180]}
