"""Read active Windows recording endpoints and match their labels to PortAudio."""
import os
import re
import unicodedata


def capture_inventory():
    """Return None on inventory failure, or a snapshot of DEVICE_STATE_ACTIVE capture endpoints."""
    if os.name != 'nt':
        return None
    import ctypes as c
    import uuid
    import winreg
    ole = c.WinDLL("ole32")
    ole.CoInitializeEx.argtypes = [c.c_void_p, c.c_uint]
    ole.CoInitializeEx.restype = c.c_long
    ole.CoCreateInstance.argtypes = [c.c_void_p, c.c_void_p, c.c_uint, c.c_void_p, c.c_void_p]
    ole.CoCreateInstance.restype = c.c_long
    ole.CoTaskMemFree.argtypes = [c.c_void_p]
    ptr = c.c_void_p
    initialized = ole.CoInitializeEx(None, 0)
    enumerator, collection = ptr(), ptr()

    def method(pointer, index, *args):
        table = c.cast(pointer, c.POINTER(c.POINTER(ptr))).contents
        return c.WINFUNCTYPE(c.c_long, ptr, *args)(table[index])

    def describe(endpoint):
        identifier = ptr()
        if method(endpoint, 5, c.POINTER(ptr))(endpoint, c.byref(identifier)) < 0:
            return None
        try:
            eid = c.wstring_at(identifier)
        finally:
            ole.CoTaskMemFree(identifier)
        location = r'SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Capture' + chr(92) + eid.rsplit('.',1)[-1] + r'\Properties'
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, location) as key:
                for name in ('{a45c254e-df1c-4efd-8020-67d146a850e0},14','{b3f8fa53-0004-438e-9003-51a46e139bfc},6'):
                    try:return {'id':eid,'name':winreg.QueryValueEx(key,name)[0]}
                    except FileNotFoundError:continue
        except OSError:pass
        return None

    try:
        clsid=(c.c_ubyte*16).from_buffer_copy(uuid.UUID('BCDE0395-E52F-467C-8E3D-C4579291692E').bytes_le)
        iid=(c.c_ubyte*16).from_buffer_copy(uuid.UUID('A95664D2-9614-4F35-A746-DE8DB63617E6').bytes_le)
        if ole.CoCreateInstance(c.byref(clsid),None,23,c.byref(iid),c.byref(enumerator))<0:return None
        if method(enumerator,3,c.c_int,c.c_uint,c.POINTER(ptr))(enumerator,1,1,c.byref(collection))<0:return None
        count=c.c_uint()
        if method(collection,3,c.POINTER(c.c_uint))(collection,c.byref(count))<0:return None
        endpoints=[]
        for index in range(count.value):
            endpoint=ptr()
            if method(collection,4,c.c_uint,c.POINTER(ptr))(collection,index,c.byref(endpoint))>=0:
                try:
                    item=describe(endpoint)
                    if item:endpoints.append(item)
                finally:method(endpoint,2)(endpoint)
        if count.value and not endpoints:return None
        roles={}
        for role in (2,0,1):
            endpoint=ptr()
            if method(enumerator,4,c.c_int,c.c_int,c.POINTER(ptr))(enumerator,1,role,c.byref(endpoint))>=0:
                try:roles[role]=describe(endpoint)
                finally:method(endpoint,2)(endpoint)
        return {'active':sorted(endpoints,key=lambda e:e['id']),'roles':roles}
    except (OSError,ValueError):
        return None
    finally:
        if collection.value:method(collection,2)(collection)
        if enumerator.value:method(enumerator,2)(enumerator)
        if initialized in (0,1):ole.CoUninitialize()


def default_microphone(role=None):
    snapshot=capture_inventory()
    if not snapshot:return None
    roles=snapshot['roles']
    return (roles.get(2) or roles.get(0)) if role is None else roles.get(role)


def words(name):
    plain=''.join(c for c in unicodedata.normalize('NFKD',name.casefold()) if not unicodedata.combining(c))
    return re.findall(r'[^\W_]+',plain)


GENERIC=set('mic mics micro microfono microphone microphones headset headphones auricular auriculares hands free ag audio bluetooth usb wireless stereo communications comunicacion comunicaciones dispositivo device de del da do the recording capture entrada input default predeterminado'.split())


def label_score(a,b):
    left,right=words(a),words(b)
    if left==right and left:return 3
    x,y=set(left)-GENERIC,set(right)-GENERIC
    if x and x==y:return 2
    common = x & y
    if (x<=y or y<=x) and (len(common)>=2 or any(len(t)>=3 and any(c.isdigit() for c in t) for t in common)):
        return 1
    return 0


def is_monitor(name):
    label=' '+' '.join(words(name))+' '
    return any(term in label for term in (' loopback ',' stereo mix ',' mezcla estereo ',' what u hear ',' wave out mix ',' monitor of '))


def ranked_inputs(devices,snapshot,default_index,hint='auto'):
    priority={'Windows WASAPI':0,'MME':1,'Windows DirectSound':2,'Windows WDM-KS':3}
    available=[d for d in devices if not is_monitor(d['name'])]
    if snapshot is not None:
        available=[d for d in available if any(label_score(d['name'],e['name']) for e in snapshot['active'])]
    if hint!='auto':
        available=[d for d in available if label_score(d['name'],hint)]
    roles=snapshot['roles'] if snapshot else {}
    def key(d):
        def score(h):return label_score(d['name'],h['name']) if h else 0
        comms,console=score(roles.get(2)),score(roles.get(0))
        host_rank=priority.get(d['hostapi'],9)
        # Exact and category-normalized matches identify the same endpoint.
        # Prefer its WASAPI representation over a legacy host's display alias.
        return (-label_score(d['name'],hint) if hint!='auto' else 0,
                -min(comms,2),-min(console,2),host_rank if snapshot else 0,
                d['id']!=default_index,host_rank,-comms,-console,d['id'])
    return sorted(available,key=key)
