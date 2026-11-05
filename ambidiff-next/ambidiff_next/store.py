"""Estado incremental SQLite; ocorrências imutáveis, revisões em trilha separada."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import uuid
from .models import stable_id


def now():return datetime.now(timezone.utc).isoformat()
def dump(value):return json.dumps(value,ensure_ascii=False,allow_nan=False)
def load(value,default=None):return json.loads(value) if value is not None else default


class Store:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,config TEXT NOT NULL,status TEXT NOT NULL,
                metrics TEXT NOT NULL,current TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,error TEXT);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT,run_id TEXT,kind TEXT,payload TEXT,priority INTEGER,
                state TEXT,attempts INTEGER DEFAULT 0,reason TEXT,result TEXT,PRIMARY KEY(run_id,id));
            CREATE INDEX IF NOT EXISTS tasks_ready ON tasks(run_id,state,priority);
            CREATE TABLE IF NOT EXISTS pages(run_id TEXT,side INTEGER,url TEXT,data TEXT,PRIMARY KEY(run_id,side,url));
            CREATE TABLE IF NOT EXISTS groups(run_id TEXT,id TEXT,signature TEXT,PRIMARY KEY(run_id,id),UNIQUE(run_id,signature));
            CREATE TABLE IF NOT EXISTS occurrences(run_id TEXT,id TEXT,group_id TEXT,data TEXT,PRIMARY KEY(run_id,id));
            CREATE TABLE IF NOT EXISTS reviews(run_id TEXT,id TEXT,status TEXT DEFAULT 'pending',selected INTEGER DEFAULT 0,
                PRIMARY KEY(run_id,id));
            CREATE TABLE IF NOT EXISTS review_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT,id TEXT,action TEXT,time TEXT);
            CREATE TABLE IF NOT EXISTS logs(seq INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT,time TEXT,message TEXT);
            CREATE TABLE IF NOT EXISTS diagnostics(seq INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT,data TEXT);
            ''')
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=15);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()
    def create_run(self,config):
        rid=uuid.uuid4().hex;stamp=now()
        with self.connect() as db:db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)',(rid,dump(config),'pending','{}','null',stamp,stamp,None))
        return rid
    def get_run(self,rid):
        with self.connect() as db:row=db.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone()
        if row is None:raise KeyError('Comparação não encontrada')
        d=dict(row)
        for key in ('config','metrics','current'):d[key]=load(d[key])
        return d
    def list_runs(self):
        with self.connect() as db:ids=[r[0] for r in db.execute('SELECT id FROM runs ORDER BY created_at DESC')]
        return [self.get_run(rid) for rid in ids]
    def update_run(self,rid,**fields):
        allowed={'status','metrics','current','error'}
        if not set(fields)<=allowed:raise ValueError('Campo de execução inválido')
        values={k:dump(v) if k in ('metrics','current') else v for k,v in fields.items()}
        values['updated_at']=now()
        with self.connect() as db:db.execute('UPDATE runs SET '+','.join(k+'=?' for k in values)+' WHERE id=?',(*values.values(),rid))
    def interrupt(self,rid):
        # Pedido idempotente; estado final nunca regride por um clique atrasado.
        with self.connect() as db:db.execute("UPDATE runs SET status='stop_requested',updated_at=? WHERE id=? AND status IN ('pending','running','stop_requested')",(now(),rid))
    def log(self,rid,message):
        import re
        from .policy import redact_url
        safe=re.sub(r'https?://[^\s<>]+',lambda m:redact_url(m[0]),str(message))[:1500]
        with self.connect() as db:db.execute('INSERT INTO logs(run_id,time,message) VALUES(?,?,?)',(rid,now(),safe))
    def logs(self,rid,after=0):
        with self.connect() as db:
            rows=[dict(r) for r in db.execute('SELECT seq,time,message FROM logs WHERE run_id=? AND seq>? ORDER BY seq LIMIT 250',(rid,int(after)))]
        return {'entries':rows,'cursor':rows[-1]['seq'] if rows else int(after)}
    def diagnose(self,rid,item):
        with self.connect() as db:db.execute('INSERT INTO diagnostics(run_id,data) VALUES(?,?)',(rid,dump(item)))
    def enqueue(self,rid,kind,payload,priority=2,reason=''):
        tid=stable_id('task',kind,payload.get('urls',payload))
        with self.connect() as db:
            result=db.execute("INSERT OR IGNORE INTO tasks(id,run_id,kind,payload,priority,state,reason) VALUES(?,?,?,?,?,'pending',?)",(tid,rid,kind,dump(payload),priority,reason))
        return bool(result.rowcount)
    def tasks(self,rid):
        with self.connect() as db:rows=[dict(r) for r in db.execute('SELECT * FROM tasks WHERE run_id=? ORDER BY priority,rowid',(rid,))]
        for row in rows:
            row['payload']=load(row['payload']);row['result']=load(row['result'])
        return rows
    def claim(self,rid):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT id FROM tasks WHERE run_id=? AND state='pending' ORDER BY priority,rowid LIMIT 1",(rid,)).fetchone()
            if row is None:return None
            db.execute("UPDATE tasks SET state='running',attempts=attempts+1 WHERE run_id=? AND id=?",(rid,row['id']))
        return next(t for t in self.tasks(rid) if t['id']==row['id'])
    def finish(self,rid,tid,state='done',reason='',result=None):
        if state not in ('done','failed','pending','inconclusive','sampled','blocked'):raise ValueError('Estado de tarefa inválido')
        with self.connect() as db:db.execute('UPDATE tasks SET state=?,reason=?,result=? WHERE run_id=? AND id=?',(state,reason,dump(result),rid,tid))
    def recover(self,rid):
        with self.connect() as db:
            db.execute("UPDATE tasks SET state=CASE WHEN attempts<2 THEN 'pending' ELSE 'failed' END,reason='Operação interrompida; recuperação limitada' WHERE run_id=? AND state='running'",(rid,))
    def save_page(self,rid,side,page):
        with self.connect() as db:db.execute('INSERT OR REPLACE INTO pages VALUES(?,?,?,?)',(rid,side,page.url,dump(page.to_dict())))
    def get_page(self,rid,side,url):
        from .models import Page
        with self.connect() as db:row=db.execute('SELECT data FROM pages WHERE run_id=? AND side=? AND url=?',(rid,side,url)).fetchone()
        return Page.from_dict(load(row[0])) if row else None
    def add_finding(self,rid,item):
        # Não agrupa só por rótulo. Contexto e fatos distintos permanecem distintos.
        signature=stable_id('group',*(item.get(k) for k in ('code','nature','element','section','observed_a','observed_b')),
            None if item.get('shared_component') else (item.get('page_a'),item.get('page_b')))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT id FROM groups WHERE run_id=? AND signature=?',(rid,signature)).fetchone()
            if row:gid=row['id']
            else:
                number=db.execute('SELECT COUNT(*) FROM groups WHERE run_id=?',(rid,)).fetchone()[0]+1
                gid=f'DIV-{number:04d}';db.execute('INSERT INTO groups VALUES(?,?,?)',(rid,gid,signature))
            db.execute('INSERT OR IGNORE INTO occurrences VALUES(?,?,?,?)',(rid,item['id'],gid,dump(item)))
        return gid
    def review(self,rid,ids,action,selected=None):
        if action not in ('select','confirmed','false_positive','editorial','corrected','hidden','pending'):raise ValueError('Revisão inválida')
        with self.connect() as db:
            for gid in dict.fromkeys(ids):
                if not db.execute('SELECT 1 FROM groups WHERE run_id=? AND id=?',(rid,gid)).fetchone():raise ValueError('DIV não encontrada')
                db.execute('INSERT OR IGNORE INTO reviews(run_id,id) VALUES(?,?)',(rid,gid))
                if action=='select':db.execute('UPDATE reviews SET selected=? WHERE run_id=? AND id=?',(int(bool(selected)),rid,gid))
                else:db.execute('UPDATE reviews SET status=? WHERE run_id=? AND id=?',(action,rid,gid))
                db.execute('INSERT INTO review_events(run_id,id,action,time) VALUES(?,?,?,?)',(rid,gid,action+(':'+str(bool(selected)) if action=='select' else ''),now()))
    def report(self,rid,selected=None):
        run=self.get_run(rid)
        with self.connect() as db:
            raw=[(r['group_id'],load(r['data'])) for r in db.execute('SELECT * FROM occurrences WHERE run_id=? ORDER BY rowid',(rid,))]
            reviews={r['id']:{'status':r['status'],'selected':bool(r['selected'])} for r in db.execute('SELECT * FROM reviews WHERE run_id=?',(rid,))}
            diagnostics=[load(r[0]) for r in db.execute('SELECT data FROM diagnostics WHERE run_id=? ORDER BY seq',(rid,))]
            logs=[dict(r) for r in db.execute('SELECT seq,time,message FROM logs WHERE run_id=? ORDER BY seq',(rid,))]
            pages=[{'side':r['side'],'url':r['url'],'data':load(r['data'])} for r in db.execute('SELECT * FROM pages WHERE run_id=?',(rid,))]
        groups={}
        for gid,row in raw:
            if gid not in groups:groups[gid]={**row,'id':gid,'occurrence_ids':[],'count':0,**{'review_status':reviews.get(gid,{}).get('status','pending'),'selected':reviews.get(gid,{}).get('selected',False)}}
            groups[gid]['occurrence_ids'].append(row['id']);groups[gid]['count']+=1
        findings=list(groups.values())
        if selected is not None:
            ids={r['id'] for r in findings if r['selected']} if selected is True else set(selected)
            findings=[r for r in findings if r['id'] in ids and r['review_status']!='hidden']
            raw=[(g,r) for g,r in raw if g in {f['id'] for f in findings}]
        return {'run':run,'findings':findings,'occurrences':[r for _,r in raw],'reviews':reviews,
                'tasks':self.tasks(rid),'logs':logs,'diagnostics':diagnostics,'pages':pages,'scope':'selected' if selected is not None else 'all'}
