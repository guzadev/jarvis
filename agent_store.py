"""Persistent missions, notes and conversation history on the owner's PC."""
from contextlib import closing, contextmanager
import json
import re
import sqlite3
import time
import threading
from pathlib import Path
import app_runtime

ROOT = Path(__file__).resolve().parent
DATABASE = None
INITIALIZE_LOCK=threading.RLock()

@contextmanager
def connect():
    path=Path(DATABASE) if DATABASE is not None else Path(app_runtime.settings()['storage_dir'])/'.jarvis-state.db'
    path.parent.mkdir(parents=True,exist_ok=True)
    with INITIALIZE_LOCK:
        legacy=ROOT/'.jarvis-state.db'
        if DATABASE is None and not path.exists() and legacy.exists() and path!=legacy:
            with closing(sqlite3.connect(legacy)) as source, closing(sqlite3.connect(path)) as target:source.backup(target)
    database = sqlite3.connect(path, timeout=20)
    database.row_factory = sqlite3.Row
    database.execute('PRAGMA journal_mode=WAL')
    database.executescript('''
      CREATE TABLE IF NOT EXISTS missions(
        id TEXT PRIMARY KEY,title TEXT,prompt TEXT,provider TEXT,model TEXT,
        status TEXT,output TEXT DEFAULT '',started REAL,ended REAL,
        events TEXT DEFAULT '[]',artifacts TEXT DEFAULT '[]',usage TEXT DEFAULT '{}',project TEXT DEFAULT 'aurelio');
      CREATE TABLE IF NOT EXISTS notes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,content TEXT,created REAL);
      CREATE TABLE IF NOT EXISTS approvals(
        id TEXT PRIMARY KEY,mission TEXT,project TEXT,payload TEXT,state TEXT,
        created REAL,result TEXT DEFAULT '');
      CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT,created REAL);
    ''')
    try:
        with database:yield database
    finally:database.close()

def canonical_project(name):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,60}', name) or Path(name).is_reserved():
        raise ValueError('Nombre de proyecto no válido.')
    return name.lower()

def create_mission(identifier,title,prompt,provider,model,project='aurelio'):
    with connect() as database:
        database.execute('INSERT INTO missions(id,title,prompt,provider,model,status,started,project) VALUES(?,?,?,?,?,?,?,?)',
                         (identifier,title,prompt,provider,model,'queued',time.time(),canonical_project(project)))

def mission(identifier):
    with connect() as database:
        row=database.execute('SELECT * FROM missions WHERE id=?',(identifier,)).fetchone()
    if not row:return None
    item=dict(row)
    item['project']=canonical_project(item['project'])
    for key in ('events','artifacts','usage'):item[key]=json.loads(item[key])
    return item

def recent(limit=30):
    with connect() as database:
        rows=database.execute('SELECT id,title,prompt,provider,model,status,output,started,ended,project FROM missions ORDER BY started DESC LIMIT ?', (limit,)).fetchall()
    return [{**dict(row), 'project':canonical_project(row['project'])} for row in rows]

def history(project,limit=100,before=None):
    project=canonical_project(project)
    with connect() as database:
        rows=database.execute('SELECT id,title,prompt,provider,model,status,output,started,ended,project FROM missions WHERE lower(project)=? AND started<? ORDER BY started DESC LIMIT ?',
                              (project,before if before is not None else time.time()+1,limit)).fetchall()
    return [{**dict(row),'project':project} for row in rows]

def projects():
    with connect() as database:
        saved={row['id']:dict(row) for row in database.execute('SELECT id,name FROM projects ORDER BY created')}
        for row in database.execute('SELECT DISTINCT lower(project) AS id FROM missions'):
            saved.setdefault(row['id'],{'id':row['id'],'name':'General' if row['id']=='aurelio' else row['id'].replace('-',' ').capitalize()})
    saved.setdefault('aurelio',{'id':'aurelio','name':'General'})
    return list(saved.values())

def save_project(identifier,name):
    identifier=canonical_project(identifier)
    with connect() as database:
        database.execute('INSERT INTO projects(id,name,created) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name',(identifier,name.strip(),time.time()))
    return {'id':identifier,'name':name.strip()}

def update(identifier,**values):
    allowed={'status','output','ended','events','artifacts','usage'}
    if not values or not set(values).issubset(allowed):raise ValueError('Invalid mission fields')
    values={key:json.dumps(value,ensure_ascii=False) if key in ('events','artifacts','usage') else value for key,value in values.items()}
    with connect() as database:
        database.execute('UPDATE missions SET '+','.join(key+'=?' for key in values)+' WHERE id=?',[*values.values(),identifier])

def transition(identifier,expected,**values):
    if not set(values).issubset({'status','output','ended','events','artifacts','usage'}):raise ValueError('Invalid fields')
    values={key:json.dumps(value,ensure_ascii=False) if key in ('events','artifacts','usage') else value for key,value in values.items()}
    with connect() as database:
        result=database.execute('UPDATE missions SET '+','.join(key+'=?' for key in values)+' WHERE id=? AND status IN ('+','.join('?' for _ in expected)+')',[*values.values(),identifier,*expected])
        if result.rowcount and values.get('status') in ('cancelled','interrupted','error','done'):
            database.execute("UPDATE approvals SET state='expired' WHERE mission=? AND state IN ('pending','approved','executing')",(identifier,))
    return result.rowcount==1

def approval_create(identifier,mission,project,payload):
    with connect() as database:
        inserted=database.execute("""INSERT INTO approvals(id,mission,project,payload,state,created)
            SELECT ?,id,project,?,'pending',? FROM missions WHERE id=? AND status='running'""",
            (identifier,json.dumps(payload,ensure_ascii=False),time.time(),mission))
        if not inserted.rowcount:raise RuntimeError('La misión ya no está activa.')

def claim_execution(mission, approval):
    with connect() as database:
        database.execute('BEGIN IMMEDIATE')
        row=database.execute("""SELECT 1 FROM approvals a JOIN missions m ON m.id=a.mission
            WHERE m.id=? AND m.status='queued' AND a.id=? AND a.state='approved'""",(mission,approval)).fetchone()
        if not row:return False
        database.execute("UPDATE approvals SET state='executing' WHERE id=?",(approval,))
        database.execute("UPDATE missions SET status='running' WHERE id=?",(mission,))
        return True

def approval(identifier):
    with connect() as database:row=database.execute('SELECT * FROM approvals WHERE id=?',(identifier,)).fetchone()
    if not row:return None
    value=dict(row);value['payload']=json.loads(value['payload']);return value

def approvals(mission_id=None):
    with connect() as database:
        rows=database.execute('SELECT id FROM approvals WHERE mission=? ORDER BY created',(mission_id,)).fetchall() if mission_id else database.execute("SELECT id FROM approvals WHERE state IN ('pending','approved','executing') ORDER BY created").fetchall()
    return [approval(row['id']) for row in rows]

def approval_transition(identifier,expected,state,result=''):
    with connect() as database:
        value=database.execute('UPDATE approvals SET state=?,result=? WHERE id=? AND state=?',(state,result,identifier,expected))
    return value.rowcount==1

def note_add(content):
    content=' '.join(content.split()).strip()
    if not content:raise ValueError('La memoria no puede estar vacía.')
    if re.search(r'\b(?:sk-(?:proj-|fish-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,})',content):
        raise ValueError('Las claves de acceso no se guardan en la memoria de conversación.')
    with connect() as database:
        existing=database.execute('SELECT id FROM notes WHERE content=? COLLATE NOCASE',(content,)).fetchone()
        if existing:return existing['id']
        result=database.execute('INSERT INTO notes(content,created) VALUES(?,?)',(content,time.time()))
    return result.lastrowid

def notes():
    with connect() as database:
        return [dict(row) for row in database.execute('SELECT * FROM notes ORDER BY created DESC,id DESC LIMIT 100')]

def note_delete(identifier):
    with connect() as database:
        removed=database.execute('DELETE FROM notes WHERE id=?',(identifier,))
    return removed.rowcount==1

def note_update(identifier,content):
    content=' '.join(content.split()).strip()
    if not content:raise ValueError('La memoria no puede estar vacía.')
    if re.search(r'\b(?:sk-(?:proj-|fish-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,})',content):
        raise ValueError('Las claves de acceso no se guardan en la memoria de conversación.')
    with connect() as database:
        updated=database.execute('UPDATE notes SET content=?,created=? WHERE id=?',(content,time.time(),identifier))
    return updated.rowcount==1

def recall(query=''):
    import unicodedata
    def words(value):
        plain=unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().lower()
        return set(re.findall(r'[a-z0-9]+',plain))
    wanted=words(query)
    if not wanted:return notes()
    with connect() as database:
        candidates=[dict(row) for row in database.execute('SELECT * FROM notes ORDER BY created DESC,id DESC')]
    ranked=[(len(wanted&words(note['content'])),note) for note in candidates]
    return [note for score,note in sorted(ranked,key=lambda row:row[0],reverse=True) if score>0][:100]

def interrupted():
    with connect() as database:
        database.execute("UPDATE missions SET status='interrupted',ended=?,output=output||'\nEl servicio se reinició durante esta tarea.' WHERE status IN ('running','queued','awaiting_approval')",(time.time(),))
        database.execute("UPDATE approvals SET state='expired' WHERE state IN ('pending','approved','executing')")
