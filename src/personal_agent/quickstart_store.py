"""Private, single-owner persistence for the quickstart."""
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import uuid


class QuickStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.private = self.root/'private'
        self.private.mkdir(exist_ok=True, mode=0o700)
        self.private.chmod(0o700)
        self.path = self.private/'quickstart.db'
        self.bootstrap = self.private/'bootstrap'
        self.secret_path = self.private/'connections.json'
        self.secret_lock = threading.RLock()
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS auth(id INTEGER PRIMARY KEY CHECK(id=1), salt TEXT, password TEXT);
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, expires REAL);
            CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, content TEXT, channel TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, request_key TEXT UNIQUE, message TEXT, channel TEXT, chat_id INTEGER, status TEXT, response TEXT, error TEXT, delivery TEXT, provider TEXT, model TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS tool_events(id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, tool TEXT, status TEXT, detail TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY, content TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY, memory_key TEXT NOT NULL, content TEXT NOT NULL, created REAL NOT NULL, supersedes TEXT, state TEXT NOT NULL DEFAULT 'current');
            CREATE INDEX IF NOT EXISTS memories_key_state ON memories(memory_key, state, created DESC);
            CREATE TABLE IF NOT EXISTS memory_candidates(id TEXT PRIMARY KEY, job_id TEXT, memory_key TEXT NOT NULL, content TEXT NOT NULL, created REAL NOT NULL, state TEXT NOT NULL DEFAULT 'pending');
            CREATE TABLE IF NOT EXISTS telegram_task_cards(job_id TEXT PRIMARY KEY, chat_id INTEGER NOT NULL, message_id INTEGER NOT NULL, state TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS telegram_notifications(id TEXT PRIMARY KEY, job_id TEXT NOT NULL, chat_id INTEGER NOT NULL, generation TEXT NOT NULL, kind TEXT NOT NULL, fingerprint TEXT, state TEXT NOT NULL, message_id INTEGER, created REAL NOT NULL, UNIQUE(job_id, kind));
            CREATE TABLE IF NOT EXISTS context_events(id TEXT PRIMARY KEY, captured_at REAL NOT NULL, source_kind TEXT NOT NULL, content TEXT NOT NULL, content_hash TEXT NOT NULL, expires_at REAL NOT NULL, sharing_state TEXT NOT NULL, source_app TEXT NOT NULL, source_domain TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS context_events_expiry ON context_events(expires_at);
            CREATE TABLE IF NOT EXISTS context_sharing_policies(assistant_id TEXT PRIMARY KEY, approved INTEGER NOT NULL, approved_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS context_job_attachments(job_id TEXT PRIMARY KEY, event_ids TEXT NOT NULL, assistant_id TEXT NOT NULL, approved INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS telegram_context_choices(token TEXT PRIMARY KEY, job_id TEXT NOT NULL, event_id TEXT NOT NULL, chat_id INTEGER NOT NULL, generation TEXT NOT NULL, message_id INTEGER, state TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY, title TEXT NOT NULL, purpose TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'active', created REAL NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS workspace_results(id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, job_id TEXT NOT NULL, content TEXT NOT NULL, evidence TEXT NOT NULL DEFAULT '', created REAL NOT NULL, UNIQUE(workspace_id, job_id));
            CREATE INDEX IF NOT EXISTS workspace_results_workspace ON workspace_results(workspace_id, created DESC);
            ''')
            columns={row['name'] for row in db.execute('PRAGMA table_info(messages)')}
            if 'workspace_id' not in columns: db.execute('ALTER TABLE messages ADD COLUMN workspace_id TEXT')
            if 'job_id' not in columns: db.execute('ALTER TABLE messages ADD COLUMN job_id TEXT')
            columns={row['name'] for row in db.execute('PRAGMA table_info(jobs)')}
            if 'workspace_id' not in columns: db.execute('ALTER TABLE jobs ADD COLUMN workspace_id TEXT')
        self.path.chmod(0o600)
        if not self.claimed() and not self.bootstrap.exists():
            self.write_private(self.bootstrap, secrets.token_urlsafe(32))

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def write_private(path, content):
        tmp = path.with_name(path.name+'.tmp-'+secrets.token_hex(6))
        fd = os.open(tmp, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, path)
        finally:
            if tmp.exists(): tmp.unlink()

    def claimed(self):
        with self.db() as db:
            return db.execute('SELECT 1 FROM auth').fetchone() is not None

    def claim(self, code, password, local_access=False):
        if not isinstance(password, str) or not 12 <= len(password) <= 256:
            raise ValueError('사용할 비밀번호를 12~256자로 입력하세요.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM auth').fetchone():
                raise ValueError('이미 초기 설정이 완료되었습니다. 로그인하세요.')
            if not self.bootstrap.exists() or not hmac.compare_digest(str(code), self.bootstrap.read_text()):
                raise ValueError('초기 설정 링크가 올바르지 않습니다. 실행한 터미널에서 다시 여세요.')
            salt = secrets.token_hex(16)
            digest = hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
            db.execute('INSERT INTO auth VALUES (1,?,?)',(salt,digest))
            db.execute('INSERT INTO config VALUES (?,?)',('local_access',json.dumps(local_access)))
        self.bootstrap.unlink(missing_ok=True)

    def login(self, password):
        if not isinstance(password,str) or len(password)>256: return None
        with self.db() as db:
            row = db.execute('SELECT * FROM auth').fetchone()
            if not row: return None
            digest = hashlib.scrypt(password.encode(),salt=bytes.fromhex(row['salt']),n=16384,r=8,p=1).hex()
            if not hmac.compare_digest(digest,row['password']): return None
            token = secrets.token_urlsafe(32)
            db.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
            db.execute('INSERT INTO sessions VALUES (?,?)',(hashlib.sha256(token.encode()).hexdigest(),time.time()+86400))
            return token

    def local_session(self):
        token=secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
            db.execute('INSERT INTO sessions VALUES (?,?)',(hashlib.sha256(token.encode()).hexdigest(),time.time()+86400))
        return token

    def session(self, token):
        with self.db() as db:
            return db.execute('SELECT 1 FROM sessions WHERE token=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone() is not None

    def logout(self, token):
        with self.db() as db:
            db.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(token.encode()).hexdigest(),))

    def config(self, key, default=None):
        with self.db() as db:
            row = db.execute('SELECT value FROM config WHERE key=?',(key,)).fetchone()
            return json.loads(row['value']) if row else default

    def put(self, key, value):
        with self.db() as db:
            db.execute('INSERT INTO config VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value)))

    def secret(self, key, value=None):
        with self.secret_lock:
            values = json.loads(self.secret_path.read_text()) if self.secret_path.exists() else {}
            if value is not None:
                values[key] = value
                self.write_private(self.secret_path, json.dumps(values))
            return values.get(key,'')

    def enqueue(self, message, request_key, channel='web', chat_id=None, workspace_id=None, db=None):
        if not isinstance(message,str) or not message.strip() or len(message)>12000:
            raise ValueError('메시지는 1~12,000자로 입력하세요.')
        if not isinstance(request_key,str) or not 1<=len(request_key)<=160:
            raise ValueError('요청 식별자가 필요합니다.')
        if db is None:
            with self.db() as conn:
                conn.execute('BEGIN IMMEDIATE')
                return self.enqueue(message,request_key,channel,chat_id,workspace_id,conn)
        if workspace_id is not None and not self.workspace(workspace_id, db=db):
            raise ValueError('작업공간을 찾을 수 없습니다.')
        old=db.execute('SELECT * FROM jobs WHERE request_key=?',(request_key,)).fetchone()
        if old:
            if old['message']!=message or old['channel']!=channel or old['chat_id']!=chat_id or old['workspace_id']!=workspace_id:
                raise ValueError('같은 요청 식별자를 다른 메시지에 사용할 수 없습니다.')
            return old['id']
        if db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]>=100:
            raise ValueError('대기 중인 작업이 많습니다. 잠시 후 다시 시도하세요.')
        task_id=str(uuid.uuid4())
        db.execute('INSERT INTO jobs(id,request_key,message,channel,chat_id,status,response,error,delivery,provider,model,created,workspace_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',(task_id,request_key,message,channel,chat_id,'queued',None,None,'none',None,None,time.time(),workspace_id))
        return task_id

    def history(self):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM (SELECT * FROM messages ORDER BY id DESC LIMIT 100) ORDER BY id')]

    def jobs(self):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 40')]

    def job(self, job_id):
        with self.db() as db:
            row=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            return dict(row) if row else None

    def notes(self):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM notes ORDER BY created DESC LIMIT 50')]

    def save_memory(self, memory_key, content):
        if not isinstance(memory_key,str) or not 2<=len(memory_key.strip())<=160: raise ValueError('기억 항목의 이름을 확인하세요.')
        if not isinstance(content,str) or not content.strip() or len(content)>4000: raise ValueError('기억할 내용을 확인하세요.')
        memory_id=str(uuid.uuid4())
        with self.db() as db:
            previous=db.execute("SELECT id FROM memories WHERE memory_key=? AND state='current' ORDER BY created DESC LIMIT 1",(memory_key.strip(),)).fetchone()
            if previous: db.execute("UPDATE memories SET state='superseded' WHERE id=?",(previous['id'],))
            db.execute('INSERT INTO memories(id,memory_key,content,created,supersedes,state) VALUES (?,?,?,?,?,?)',(memory_id,memory_key.strip(),content.strip(),time.time(),previous['id'] if previous else None,'current'))
        return {'id':memory_id,'memory_key':memory_key.strip(),'content':content.strip(),'supersedes':previous['id'] if previous else None,'state':'current'}

    def save_memory_candidate(self, job_id, memory_key, content):
        if not isinstance(memory_key,str) or not 2<=len(memory_key.strip())<=160: raise ValueError('기억 항목의 이름을 확인하세요.')
        if not isinstance(content,str) or not content.strip() or len(content)>4000: raise ValueError('기억할 내용을 확인하세요.')
        candidate_id=str(uuid.uuid4())
        with self.db() as db:
            db.execute('INSERT INTO memory_candidates(id,job_id,memory_key,content,created,state) VALUES (?,?,?,?,?,?)',(candidate_id,job_id,memory_key.strip(),content.strip(),time.time(),'pending'))
        return {'id':candidate_id,'memory_key':memory_key.strip(),'content':content.strip(),'state':'pending','saved':False}

    def issue_memory_approval(self, job_id, owner_message, ttl=600):
        """Issue a short-lived token bound to the authenticated owner job."""
        job=self.job(job_id)
        if not job or job.get('message')!=owner_message: raise ValueError('소유자 요청을 확인할 수 없습니다.')
        expires_at=int(time.time()+ttl)
        message_hash=hashlib.sha256(owner_message.encode()).hexdigest()
        secret=self.secret('memory_approval_secret')
        if not secret:
            secret=secrets.token_hex(32); self.secret('memory_approval_secret',secret)
        payload=f'{job_id}|{message_hash}|{expires_at}'
        token=hmac.new(secret.encode(),payload.encode(),hashlib.sha256).hexdigest()
        return {'job_id':job_id,'message_hash':message_hash,'expires_at':expires_at,'token':token}

    def verify_memory_approval(self, approval, job_id):
        if not isinstance(approval,dict) or approval.get('job_id')!=job_id or approval.get('expires_at',0)<time.time(): return False
        job=self.job(job_id)
        if not job: return False
        message_hash=hashlib.sha256(str(job.get('message','')).encode()).hexdigest()
        if not hmac.compare_digest(str(approval.get('message_hash','')),message_hash): return False
        secret=self.secret('memory_approval_secret')
        payload=f'{job_id}|{message_hash}|{approval.get("expires_at")}'
        expected=hmac.new(secret.encode(),payload.encode(),hashlib.sha256).hexdigest()
        return hmac.compare_digest(str(approval.get('token','')),expected)

    def memory_candidates(self):
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT id,job_id,memory_key,content,created,state FROM memory_candidates WHERE state='pending' ORDER BY created DESC LIMIT 50")]

    def memories(self):
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT id,memory_key,content,created,supersedes,state FROM memories WHERE state='current' ORDER BY created DESC LIMIT 50")]

    def personal_space(self):
        now=time.time()
        with self.db() as db:
            db.execute('DELETE FROM context_events WHERE expires_at<=?',(now,))
            memories=[dict(r) for r in db.execute('SELECT id,content,created FROM notes ORDER BY created DESC LIMIT 50')]
            memories.extend(dict(r) for r in db.execute("SELECT id,content,created FROM memories WHERE state='current' ORDER BY created DESC LIMIT 50"))
            memories=sorted(memories,key=lambda row:row.get('created',0),reverse=True)[:50]
            results=[dict(r) for r in db.execute('SELECT id,workspace_id,job_id,content,created FROM workspace_results ORDER BY created DESC LIMIT 50')]
            context=[dict(r) for r in db.execute('SELECT id,captured_at,source_kind,expires_at,sharing_state,source_app,source_domain FROM context_events ORDER BY captured_at DESC LIMIT 100')]
            evidence=[dict(r) for r in db.execute("SELECT tool,status,COUNT(*) AS count FROM tool_events WHERE tool!='model' GROUP BY tool,status ORDER BY tool,status")]
            candidates=[dict(r) for r in db.execute("SELECT id,job_id,memory_key,content,created,state FROM memory_candidates WHERE state='pending' ORDER BY created DESC LIMIT 50")]
        return {'memories':memories,'memory_count':len(memories),'memory_candidates':candidates,'memory_candidate_count':len(candidates),'results':results,'result_count':len(results),'context':context,'context_count':len(context),'evidence':evidence}

    def delete_personal_space_item(self, kind, item_id):
        if kind not in ('memories','memory_candidates','results') or not isinstance(item_id,str) or not item_id:
            raise ValueError('삭제할 Personal Space 항목을 확인하세요.')
        with self.db() as db:
            if kind=='results': deleted=db.execute('DELETE FROM workspace_results WHERE id=?',(item_id,)).rowcount
            elif kind=='memory_candidates': deleted=db.execute("DELETE FROM memory_candidates WHERE id=? AND state='pending'",(item_id,)).rowcount
            else:
                deleted=db.execute('DELETE FROM memories WHERE id=?',(item_id,)).rowcount
                if not deleted: deleted=db.execute('DELETE FROM notes WHERE id=?',(item_id,)).rowcount
        return {'deleted':bool(deleted),'id':item_id,'kind':kind}

    def workspaces(self, include_archived=False):
        query='SELECT * FROM workspaces'+('' if include_archived else " WHERE status='active'")+' ORDER BY updated DESC LIMIT 100'
        with self.db() as db:return [dict(row) for row in db.execute(query)]

    def workspace(self, workspace_id, db=None):
        if not isinstance(workspace_id,str) or not workspace_id:return None
        if db is None:
            with self.db() as conn:return self.workspace(workspace_id, conn)
        row=db.execute('SELECT * FROM workspaces WHERE id=?',(workspace_id,)).fetchone()
        return dict(row) if row else None

    def create_workspace(self, title, purpose=''):
        if not isinstance(title,str) or not 1<=len(title.strip())<=120:raise ValueError('작업공간 이름은 1~120자로 입력하세요.')
        if not isinstance(purpose,str) or len(purpose)>1000:raise ValueError('작업공간 설명을 확인하세요.')
        now=time.time();workspace_id=str(uuid.uuid4())
        with self.db() as db:
            db.execute('INSERT INTO workspaces VALUES (?,?,?,?,?,?)',(workspace_id,title.strip(),purpose.strip(),'active',now,now))
        return self.workspace(workspace_id)

    def update_workspace(self, workspace_id, title=None, purpose=None, archive=None):
        current=self.workspace(workspace_id)
        if not current:raise ValueError('작업공간을 찾을 수 없습니다.')
        next_title=current['title'] if title is None else title
        next_purpose=current['purpose'] if purpose is None else purpose
        next_status=current['status'] if archive is None else ('archived' if archive else 'active')
        if not isinstance(next_title,str) or not 1<=len(next_title.strip())<=120:raise ValueError('작업공간 이름은 1~120자로 입력하세요.')
        if not isinstance(next_purpose,str) or len(next_purpose)>1000:raise ValueError('작업공간 설명을 확인하세요.')
        with self.db() as db:db.execute('UPDATE workspaces SET title=?,purpose=?,status=?,updated=? WHERE id=?',(next_title.strip(),next_purpose.strip(),next_status,time.time(),workspace_id))
        return self.workspace(workspace_id)

    def save_workspace_result(self, workspace_id, job_id):
        workspace=self.workspace(workspace_id)
        if not workspace:raise ValueError('작업공간을 찾을 수 없습니다.')
        with self.db() as db:
            job=db.execute("SELECT * FROM jobs WHERE id=? AND status IN ('succeeded','partial')",(job_id,)).fetchone()
            if not job:raise ValueError('저장할 완료 결과를 찾을 수 없습니다.')
            detail=db.execute("SELECT detail FROM tool_events WHERE job_id=? AND tool!='model' AND status='succeeded' ORDER BY id DESC LIMIT 8",(job_id,)).fetchall()
            evidence=json.dumps([row['detail'][:500] for row in detail],ensure_ascii=False)
            db.execute('INSERT INTO workspace_results VALUES (?,?,?,?,?,?) ON CONFLICT(workspace_id,job_id) DO NOTHING',(str(uuid.uuid4()),workspace_id,job_id,job['response'] or '',evidence,time.time()))
            db.execute('UPDATE workspaces SET updated=? WHERE id=?',(time.time(),workspace_id))
        return self.workspace_detail(workspace_id)

    def workspace_detail(self, workspace_id):
        workspace=self.workspace(workspace_id)
        if not workspace:return None
        with self.db() as db:
            workspace['results']=[dict(row) for row in db.execute('SELECT id,job_id,content,created FROM workspace_results WHERE workspace_id=? ORDER BY created DESC LIMIT 30',(workspace_id,))]
            workspace['messages']=[dict(row) for row in db.execute('SELECT id,role,content,channel,created,workspace_id,job_id FROM messages WHERE workspace_id=? ORDER BY id DESC LIMIT 100',(workspace_id,))][::-1]
        return workspace

    def attach_context(self, job_id, event_ids, assistant_id, db=None):
        if (not isinstance(job_id,str) or not isinstance(event_ids,list) or not event_ids
                or len(event_ids)>20 or any(not isinstance(item,str) or not item for item in event_ids)
                or not isinstance(assistant_id,str) or not assistant_id):
            raise ValueError('연결할 컨텍스트를 확인하세요.')
        encoded=json.dumps(event_ids)
        if db is None:
            with self.db() as conn:
                conn.execute('BEGIN IMMEDIATE')
                return self.attach_context(job_id,event_ids,assistant_id,conn)
        db.execute('INSERT INTO context_job_attachments VALUES (?,?,?,?,?) ON CONFLICT(job_id) DO NOTHING',
                   (job_id,encoded,assistant_id,0,time.time()))

    def create_telegram_context_choice(self, job_id, event_id, chat_id, generation):
        token=secrets.token_urlsafe(9)
        with self.db() as db:
            db.execute('INSERT INTO telegram_context_choices VALUES (?,?,?,?,?,?,?,?)',(token,job_id,event_id,chat_id,generation,None,'offered',time.time()))
        return token

    def save_telegram_context_choice_message(self, tokens, message_id):
        if not isinstance(message_id,int):return
        with self.db() as db:
            marks=','.join('?' for _ in tokens)
            if marks:db.execute(f"UPDATE telegram_context_choices SET message_id=? WHERE token IN ({marks})",(message_id,*tokens))

    def telegram_context_choice(self, token):
        with self.db() as db:
            row=db.execute('SELECT * FROM telegram_context_choices WHERE token=?',(token,)).fetchone()
        return dict(row) if row else None

    def telegram_context_choice_for_job(self, job_id):
        with self.db() as db:
            row=db.execute("SELECT * FROM telegram_context_choices WHERE job_id=? AND state='offered' ORDER BY created LIMIT 1",(job_id,)).fetchone()
        return dict(row) if row else None

    def select_telegram_context_choice(self, token):
        with self.db() as db:
            db.execute("UPDATE telegram_context_choices SET state='selected' WHERE token=? AND state='offered'",(token,))
            row=db.execute('SELECT * FROM telegram_context_choices WHERE token=?',(token,)).fetchone()
        return dict(row) if row else None

    def context_attachment(self, job_id):
        with self.db() as db:
            row=db.execute('SELECT * FROM context_job_attachments WHERE job_id=?',(job_id,)).fetchone()
        if not row:return None
        item=dict(row)
        try:item['event_ids']=json.loads(item['event_ids'])
        except (TypeError,ValueError):return None
        return item

    def approve_context_attachment(self, job_id):
        with self.db() as db:
            db.execute('UPDATE context_job_attachments SET approved=1 WHERE job_id=?',(job_id,))

    def recent_tool_events(self):
        with self.db() as db:
            rows=[dict(r) for r in db.execute("SELECT id,job_id,tool,status,detail,created FROM tool_events WHERE tool!='model' ORDER BY id DESC LIMIT 30")]
        events=[]
        for row in rows:
            try:trace=json.loads(row.pop('detail'))
            except (TypeError,ValueError):trace={'error':'실행 근거를 읽을 수 없습니다.'}
            events.append({**row,'trace':trace if isinstance(trace,dict) else {'error':'실행 근거 형식이 올바르지 않습니다.'}})
        return events

    def task_events(self, job_id):
        with self.db() as db:
            rows=[dict(r) for r in db.execute("SELECT id,job_id,tool,status,detail,created FROM tool_events WHERE job_id=? AND tool!='model' ORDER BY id",(job_id,))]
        events=[]
        for row in rows:
            try:trace=json.loads(row.pop('detail'))
            except (TypeError,ValueError):trace={'error':'실행 근거를 읽을 수 없습니다.'}
            events.append({**row,'trace':trace if isinstance(trace,dict) else {'error':'실행 근거 형식이 올바르지 않습니다.'}})
        return events

    def task_artifacts(self, job_id):
        with self.db() as db:
            artifacts=[dict(row) for row in db.execute('SELECT id,workspace_id,job_id,created FROM workspace_results WHERE job_id=? ORDER BY created DESC',(job_id,))]
            tables={row['name'] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'file_workspace_results' in tables:
                artifacts.extend(dict(row) for row in db.execute('SELECT id,workspace_id,request_id AS job_id,path,created,state FROM file_workspace_results WHERE request_id=? ORDER BY created DESC',(job_id,)))
        return artifacts

    def task_notifications(self, job_id):
        with self.db() as db:
            return [dict(row) for row in db.execute('SELECT kind,state,created FROM telegram_notifications WHERE job_id=? ORDER BY created',(job_id,))]

    def evidence_summary(self, job_id):
        """Return categories and counts only; never expose tool payloads."""
        with self.db() as db:
            rows=db.execute("SELECT tool FROM tool_events WHERE job_id=? AND status='succeeded'",(job_id,)).fetchall()
        counts={}
        for row in rows:counts[row['tool']]=counts.get(row['tool'],0)+1
        labels=[]
        if counts.get('web_search'):labels.append(f"공개 웹 {counts['web_search']}곳 참고")
        documents=counts.get('read_file',0)
        if documents:labels.append(f'내 컴퓨터의 문서 {documents}개 사용')
        elif counts.get('find_files'):labels.append('내 컴퓨터의 자료 확인')
        notes=counts.get('list_notes',0)+counts.get('save_note',0)
        if notes:labels.append(f'내 기록 {notes}개 사용')
        return labels

    def task_card(self, job_id):
        with self.db() as db:
            row=db.execute('SELECT * FROM telegram_task_cards WHERE job_id=?',(job_id,)).fetchone()
            return dict(row) if row else None

    def save_task_card(self, job_id, chat_id, message_id, state):
        with self.db() as db:
            db.execute('INSERT INTO telegram_task_cards VALUES (?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET state=excluded.state',
                       (job_id,chat_id,message_id,state,time.time()))

    def notification(self, notification_id):
        with self.db() as db:
            row=db.execute('SELECT * FROM telegram_notifications WHERE id=?',(notification_id,)).fetchone()
            return dict(row) if row else None

    def queue_notification(self, job_id, chat_id, generation, kind, fingerprint=None):
        notification_id=str(uuid.uuid4())
        with self.db() as db:
            db.execute('INSERT OR IGNORE INTO telegram_notifications VALUES (?,?,?,?,?,?,?,?,?)',
                       (notification_id,job_id,chat_id,generation,kind,fingerprint,'queued',None,time.time()))
            row=db.execute('SELECT * FROM telegram_notifications WHERE job_id=? AND kind=?',(job_id,kind)).fetchone()
            return dict(row)

    def next_notification(self):
        with self.db() as db:
            row=db.execute("SELECT * FROM telegram_notifications WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            return dict(row) if row else None

    def update_notification(self, notification_id, state, message_id=None):
        with self.db() as db:
            if message_id is None:
                db.execute('UPDATE telegram_notifications SET state=? WHERE id=?',(state,notification_id))
            else:
                db.execute('UPDATE telegram_notifications SET state=?,message_id=? WHERE id=?',(state,message_id,notification_id))

    def recover(self):
        with self.db() as db:
            db.execute("UPDATE jobs SET status='interrupted',error='실행 중 재시작되었습니다. 자동으로 재호출하지 않습니다.' WHERE status='running'")
            db.execute("UPDATE jobs SET delivery='unknown' WHERE delivery='sending'")
            db.execute("UPDATE telegram_notifications SET state='unknown' WHERE state='sending'")

    def recovery_summary(self):
        """Return counts only; recovery guidance must never reveal task content."""
        with self.db() as db:
            interrupted=db.execute("SELECT count(*) FROM jobs WHERE status='interrupted'").fetchone()[0]
            uncertain=db.execute("SELECT count(*) FROM jobs WHERE delivery='unknown'").fetchone()[0]
            notifications=db.execute("SELECT count(*) FROM telegram_notifications WHERE state='unknown'").fetchone()[0]
        return {'interrupted_jobs':interrupted, 'uncertain_deliveries':uncertain,
                'uncertain_notifications':notifications}
