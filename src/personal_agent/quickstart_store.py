"""Private, single-owner persistence for the quickstart."""
from contextlib import contextmanager
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import unicodedata
import uuid


_SECRET_STATE_LOCK = threading.RLock()


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
        self.secret_lock_path = self.private/'connections.lock'
        self.secret_lock = _SECRET_STATE_LOCK
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
            CREATE TABLE IF NOT EXISTS memory_approvals(token_hash TEXT PRIMARY KEY, owner_key TEXT NOT NULL, work_key TEXT NOT NULL, action TEXT NOT NULL, subject_id TEXT NOT NULL, memory_key TEXT NOT NULL, source_digest TEXT NOT NULL, content_digest TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, state TEXT NOT NULL DEFAULT 'issued', result_id TEXT, expected_memory_id TEXT, expected_memory_digest TEXT);
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
            if 'delivery_projection' not in columns: db.execute('ALTER TABLE messages ADD COLUMN delivery_projection TEXT')
            columns={row['name'] for row in db.execute('PRAGMA table_info(jobs)')}
            if 'workspace_id' not in columns: db.execute('ALTER TABLE jobs ADD COLUMN workspace_id TEXT')
            memory_columns={row['name'] for row in db.execute('PRAGMA table_info(memories)')}
            for name,kind in (('owner_key','TEXT'),('work_key','TEXT'),('content_digest','TEXT'),('candidate_id','TEXT')):
                if name not in memory_columns: db.execute(f'ALTER TABLE memories ADD COLUMN {name} {kind}')
            candidate_columns={row['name'] for row in db.execute('PRAGMA table_info(memory_candidates)')}
            for name,kind in (('owner_key','TEXT'),('work_key','TEXT'),('content_digest','TEXT'),('decided','REAL'),('resulting_memory_id','TEXT')):
                if name not in candidate_columns: db.execute(f'ALTER TABLE memory_candidates ADD COLUMN {name} {kind}')
            approval_columns={row['name'] for row in db.execute('PRAGMA table_info(memory_approvals)')}
            for name in ('expected_memory_id','expected_memory_digest'):
                if name not in approval_columns: db.execute(f'ALTER TABLE memory_approvals ADD COLUMN {name} TEXT')
            default_owner=self._memory_binding('local-owner')
            for row in db.execute('SELECT id,memory_key,content,owner_key,content_digest FROM memories'):
                db.execute('UPDATE memories SET owner_key=?,content_digest=? WHERE id=?',
                           (row['owner_key'] or default_owner,row['content_digest'] or self.memory_digest(row['memory_key'],row['content']),row['id']))
            for row in db.execute('SELECT id,job_id,memory_key,content,owner_key,work_key,content_digest FROM memory_candidates'):
                db.execute('UPDATE memory_candidates SET job_id=NULL,owner_key=?,work_key=?,content_digest=? WHERE id=?',
                           (row['owner_key'] or default_owner,row['work_key'] or self._memory_binding(row['job_id'] or 'legacy-work'),
                            row['content_digest'] or self.memory_digest(row['memory_key'],row['content']),row['id']))
        self.path.chmod(0o600)
        if not self.claimed() and not self.bootstrap.exists():
            self.write_private(self.bootstrap, secrets.token_urlsafe(32))

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.create_function(
            'unicode_search_key', 1,
            lambda value: unicodedata.normalize('NFKC', str(value or '')).casefold(),
            deterministic=True,
        )
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

    def secret(self, key, value=None, create=None):
        if value is not None and create is not None:raise ValueError('secret value and factory are mutually exclusive')
        with self.secret_lock:
            lock_fd=os.open(self.secret_lock_path,os.O_RDWR|os.O_CREAT,0o600)
            try:
                fcntl.flock(lock_fd,fcntl.LOCK_EX)
                values=json.loads(self.secret_path.read_text()) if self.secret_path.exists() else {}
                if value is not None:
                    values[key]=value
                    self.write_private(self.secret_path,json.dumps(values))
                elif create is not None and not values.get(key):
                    values[key]=create()
                    self.write_private(self.secret_path,json.dumps(values))
                return values.get(key,'')
            finally:
                fcntl.flock(lock_fd,fcntl.LOCK_UN)
                os.close(lock_fd)

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
            return [dict(r) for r in db.execute(
                'SELECT id,role,content,channel,created,workspace_id,job_id '
                'FROM (SELECT * FROM messages ORDER BY id DESC LIMIT 100) ORDER BY id')]

    def blocked_delivery_reply(self, job_id):
        """Recover the owner-facing blocked-turn projection from its transcript row."""
        with self.db() as db:
            row=db.execute("SELECT content FROM messages WHERE job_id=? AND role='assistant' AND delivery_projection='blocked-turn' ORDER BY id DESC LIMIT 1",(job_id,)).fetchone()
            return row['content'] if row else None

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

    @staticmethod
    def _memory_binding(value):
        if not isinstance(value,str) or not value.strip() or len(value)>200: raise ValueError('소유자 또는 작업 식별을 확인하세요.')
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _work_binding(value):
        if isinstance(value,str) and value.startswith('workref:') and len(value)==72:
            digest=value[8:]
            if all(character in '0123456789abcdef' for character in digest):return digest
        return QuickStore._memory_binding(value)

    @staticmethod
    def _memory_value(memory_key, content):
        if not isinstance(memory_key,str) or not 2<=len(memory_key.strip())<=160: raise ValueError('기억 항목의 이름을 확인하세요.')
        if not isinstance(content,str) or not content.strip() or len(content)>4000: raise ValueError('기억할 내용을 확인하세요.')
        return memory_key.strip(),content.strip()

    @staticmethod
    def memory_digest(memory_key, content):
        memory_key,content=QuickStore._memory_value(memory_key,content)
        return hashlib.sha256(json.dumps({'memory_key':memory_key,'content':content},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

    @staticmethod
    def _memory_row(row):
        if not row:return None
        value=dict(row)
        return {key:value[key] for key in ('id','memory_key','content','created','supersedes','state','content_digest','candidate_id') if key in value}

    def _save_memory(self, db, memory_key, content, owner_key, work_key=None, candidate_id=None,
                     preserve_correction_token=None):
        memory_id=str(uuid.uuid4());digest=self.memory_digest(memory_key,content)
        previous=db.execute("SELECT id FROM memories WHERE owner_key=? AND memory_key=? AND state='current' ORDER BY created DESC LIMIT 1",(owner_key,memory_key)).fetchone()
        if previous:
            db.execute("UPDATE memories SET state='superseded' WHERE id=? AND owner_key=?",(previous['id'],owner_key))
            if preserve_correction_token is None:
                db.execute("""UPDATE memory_approvals SET state='revoked',memory_key=''
                              WHERE owner_key=? AND action='correct-memory'
                                AND subject_id=? AND state='issued'""",
                           (owner_key,previous['id']))
            else:
                db.execute("""UPDATE memory_approvals SET state='revoked',memory_key=''
                              WHERE owner_key=? AND action='correct-memory'
                                AND subject_id=? AND token_hash<>? AND state='issued'""",
                           (owner_key,previous['id'],preserve_correction_token))
        # Comparing the expected and current row cannot see an absent -> present
        # -> absent sequence, so a stale token could still overwrite a later
        # owner choice. Every canonical write invalidates the other approvals
        # issued against this key.
        db.execute("""UPDATE memory_approvals SET state='revoked',memory_key=''
                      WHERE owner_key=? AND memory_key=? AND state='issued'
                        AND (? IS NULL OR token_hash<>?)""",
                   (owner_key,memory_key,preserve_correction_token,preserve_correction_token))
        db.execute('INSERT INTO memories(id,memory_key,content,created,supersedes,state,owner_key,work_key,content_digest,candidate_id) VALUES (?,?,?,?,?,?,?,?,?,?)',
                   (memory_id,memory_key,content,time.time(),previous['id'] if previous else None,'current',owner_key,work_key,digest,candidate_id))
        return self._memory_row(db.execute('SELECT * FROM memories WHERE id=?',(memory_id,)).fetchone())

    def save_memory(self, memory_key, content, owner_id='local-owner', work_id=None):
        memory_key,content=self._memory_value(memory_key,content);owner_key=self._memory_binding(owner_id)
        work_key=self._work_binding(work_id) if work_id is not None else None
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            return self._save_memory(db,memory_key,content,owner_key,work_key)

    def save_memory_candidate(self, job_id, memory_key, content, owner_id='local-owner', work_id=None):
        memory_key,content=self._memory_value(memory_key,content)
        work_id=job_id if work_id is None else work_id
        owner_key,work_key=self._memory_binding(owner_id),self._work_binding(work_id)
        candidate_id=str(uuid.uuid4());digest=self.memory_digest(memory_key,content)
        with self.db() as db:
            db.execute('INSERT INTO memory_candidates(id,job_id,memory_key,content,created,state,owner_key,work_key,content_digest) VALUES (?,?,?,?,?,?,?,?,?)',
                       (candidate_id,None,memory_key,content,time.time(),'pending',owner_key,work_key,digest))
        return {'id':candidate_id,'memory_key':memory_key,'content':content,'content_digest':digest,'state':'pending','saved':False}

    def issue_memory_approval(self, job_id, owner_message, ttl=600):
        """Issue a short-lived token bound to the authenticated owner job."""
        job=self.job(job_id)
        if not job or job.get('message')!=owner_message: raise ValueError('소유자 요청을 확인할 수 없습니다.')
        expires_at=int(time.time()+ttl)
        message_hash=hashlib.sha256(owner_message.encode()).hexdigest()
        secret=self.secret('memory_approval_secret',create=lambda:secrets.token_hex(32))
        payload=f'{job_id}|{message_hash}|{expires_at}'
        token=hmac.new(secret.encode(),payload.encode(),hashlib.sha256).hexdigest()
        return {'job_id':job_id,'message_hash':message_hash,'expires_at':expires_at,'token':token}

    def verify_memory_approval(self, approval, job_id):
        if not isinstance(approval,dict) or approval.get('job_id')!=job_id or approval.get('expires_at',0)<=time.time(): return False
        job=self.job(job_id)
        if not job: return False
        message_hash=hashlib.sha256(str(job.get('message','')).encode()).hexdigest()
        if not hmac.compare_digest(str(approval.get('message_hash','')),message_hash): return False
        secret=self.secret('memory_approval_secret')
        payload=f'{job_id}|{message_hash}|{approval.get("expires_at")}'
        expected=hmac.new(secret.encode(),payload.encode(),hashlib.sha256).hexdigest()
        return hmac.compare_digest(str(approval.get('token','')),expected)

    def memory_candidate(self, candidate_id, owner_id='local-owner', work_id=None):
        if not isinstance(candidate_id,str) or not candidate_id:return None
        owner_key=self._memory_binding(owner_id)
        with self.db() as db:
            if work_id is None:
                row=db.execute('SELECT * FROM memory_candidates WHERE id=? AND owner_key=?',(candidate_id,owner_key)).fetchone()
            else:
                row=db.execute('SELECT * FROM memory_candidates WHERE id=? AND owner_key=? AND work_key=?',
                               (candidate_id,owner_key,self._work_binding(work_id))).fetchone()
        if not row:return None
        value=dict(row)
        result={key:value[key] for key in ('id','memory_key','content','created','state','content_digest','decided','resulting_memory_id')}
        result['work_ref']='workref:'+value['work_key']
        return result

    def memory_candidates(self, owner_id=None, work_id=None, include_decided=False, limit=50, offset=0):
        if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=101:raise ValueError('기억 후보 조회 범위를 확인하세요.')
        if isinstance(offset,bool) or not isinstance(offset,int) or offset<0:raise ValueError('기억 후보 조회 위치를 확인하세요.')
        clauses=[];parameters=[]
        if owner_id is not None:clauses.append('owner_key=?');parameters.append(self._memory_binding(owner_id))
        if work_id is not None:clauses.append('work_key=?');parameters.append(self._work_binding(work_id))
        if not include_decided:clauses.append("state='pending'")
        where=(' WHERE '+' AND '.join(clauses)) if clauses else ''
        with self.db() as db:
            rows=db.execute('SELECT id,job_id,memory_key,content,created,state,content_digest,decided,resulting_memory_id,work_key FROM memory_candidates'+where+' ORDER BY created DESC,id DESC LIMIT ? OFFSET ?',(*parameters,limit,offset))
            results=[]
            for row in rows:
                value=dict(row);value['work_ref']='workref:'+value.pop('work_key');results.append(value)
            return results

    def memory(self, memory_id, owner_id='local-owner', current_only=True):
        if not isinstance(memory_id,str) or not memory_id:return None
        query='SELECT * FROM memories WHERE id=? AND owner_key=?'+(" AND state='current'" if current_only else '')
        with self.db() as db:
            return self._memory_row(db.execute(query,(memory_id,self._memory_binding(owner_id))).fetchone())

    def memories(self, owner_id=None, limit=50, offset=0):
        if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=101:raise ValueError('기억 조회 범위를 확인하세요.')
        if isinstance(offset,bool) or not isinstance(offset,int) or offset<0:raise ValueError('기억 조회 위치를 확인하세요.')
        where="state='current'";parameters=[]
        if owner_id is not None:where+=" AND owner_key=?";parameters.append(self._memory_binding(owner_id))
        with self.db() as db:
            return [self._memory_row(r) for r in db.execute('SELECT * FROM memories WHERE '+where+' ORDER BY created DESC,id DESC LIMIT ? OFFSET ?',(*parameters,limit,offset))]

    def memory_status_counts(self, owner_id):
        """Return authoritative aggregate counts, independent of list pagination."""
        owner_key=self._memory_binding(owner_id)
        with self.db() as db:
            current=db.execute("SELECT COUNT(*) FROM memories WHERE owner_key=? AND state='current'",(owner_key,)).fetchone()[0]
            candidate_rows=db.execute('SELECT state,COUNT(*) AS count FROM memory_candidates WHERE owner_key=? GROUP BY state',(owner_key,))
            candidates={state:0 for state in ('pending','accepted','rejected')}
            for row in candidate_rows:
                if row['state'] in candidates:candidates[row['state']]=row['count']
        return {'current_memory_count':current,'candidate_counts':candidates}

    def issue_candidate_memory_approval(self, owner_id, work_id, candidate_id, content_digest,
                                        ttl=600, now=None):
        """Validate a pending candidate and insert its approval in one transaction."""
        if not isinstance(candidate_id,str) or not candidate_id:raise ValueError('승인 대상을 확인하세요.')
        if not isinstance(content_digest,str) or len(content_digest)!=64:raise ValueError('승인 내용을 확인하세요.')
        if isinstance(ttl,bool) or not isinstance(ttl,(int,float)) or not 1<=ttl<=900:raise ValueError('승인 유효 시간을 확인하세요.')
        created=time.time() if now is None else float(now);token=secrets.token_urlsafe(32)
        owner_key=self._memory_binding(owner_id);work_key=self._work_binding(work_id)
        token_hash=self._exact_memory_token_hash(token)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            candidate=db.execute(
                "SELECT memory_key,content_digest,state FROM memory_candidates WHERE id=? AND owner_key=? AND work_key=?",
                (candidate_id,owner_key,work_key),
            ).fetchone()
            if not candidate or candidate['state']!='pending' or not hmac.compare_digest(str(candidate['content_digest']),content_digest):
                raise ValueError('기억 후보를 다시 확인하세요.')
            current=db.execute(
                "SELECT id,content_digest FROM memories WHERE owner_key=? AND memory_key=? AND state='current' ORDER BY created DESC LIMIT 1",
                (owner_key,candidate['memory_key']),
            ).fetchone()
            value=(token_hash,owner_key,work_key,'accept-candidate',candidate_id,candidate['memory_key'],
                   content_digest,content_digest,created,created+ttl,'issued',None,
                   current['id'] if current else None,current['content_digest'] if current else None)
            db.execute('''INSERT INTO memory_approvals
                          (token_hash,owner_key,work_key,action,subject_id,memory_key,source_digest,
                           content_digest,created,expires,state,result_id,expected_memory_id,expected_memory_digest)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',value)
        return {'approval_token':token,'action':'accept-candidate','subject_id':candidate_id,
                'memory_key':candidate['memory_key'],'source_digest':content_digest,
                'content_digest':content_digest,'expires_at':created+ttl,'state':'issued'}

    def issue_correction_memory_approval(self, owner_id, work_id, memory_id, memory_key,
                                         current_digest, replacement_digest, ttl=600, now=None):
        """Validate current Memory and insert its correction approval atomically."""
        if not isinstance(memory_id,str) or not memory_id or not isinstance(memory_key,str) or not memory_key:raise ValueError('승인 대상을 확인하세요.')
        if any(not isinstance(value,str) or len(value)!=64 for value in (current_digest,replacement_digest)):raise ValueError('승인 내용을 확인하세요.')
        if isinstance(ttl,bool) or not isinstance(ttl,(int,float)) or not 1<=ttl<=900:raise ValueError('승인 유효 시간을 확인하세요.')
        created=time.time() if now is None else float(now);token=secrets.token_urlsafe(32)
        owner_key=self._memory_binding(owner_id);work_key=self._work_binding(work_id)
        token_hash=self._exact_memory_token_hash(token)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute(
                "SELECT memory_key,content_digest FROM memories WHERE id=? AND owner_key=? AND state='current'",
                (memory_id,owner_key),
            ).fetchone()
            if (not current or current['memory_key']!=memory_key
                    or not hmac.compare_digest(str(current['content_digest']),current_digest)):
                raise ValueError('수정할 기억을 다시 확인하세요.')
            value=(token_hash,owner_key,work_key,'correct-memory',memory_id,memory_key,
                   current_digest,replacement_digest,created,created+ttl,'issued',None)
            db.execute('''INSERT INTO memory_approvals
                          (token_hash,owner_key,work_key,action,subject_id,memory_key,source_digest,
                           content_digest,created,expires,state,result_id)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',value)
        return {'approval_token':token,'action':'correct-memory','subject_id':memory_id,
                'memory_key':memory_key,'source_digest':current_digest,
                'content_digest':replacement_digest,'expires_at':created+ttl,'state':'issued'}

    def _exact_memory_token_hash(self, token):
        secret=self.secret('memory_exact_approval_secret',create=lambda:secrets.token_hex(32))
        return hmac.new(secret.encode(),token.encode(),hashlib.sha256).hexdigest()

    def _exact_memory_token_lookup(self, approval_token):
        """Hash an approval token before any write transaction opens.

        ``secret()`` reads the secret file under an inter-process ``flock`` and
        may fsync a first-use write.  Doing that while holding a
        ``BEGIN IMMEDIATE`` SQLite write lock would hold the database lock for
        the duration of unrelated file I/O, so every caller hashes first, as
        the two issuing paths already do.
        """
        if not isinstance(approval_token,str) or not approval_token:raise ValueError('정확한 승인이 필요합니다.')
        return self._exact_memory_token_hash(approval_token)

    def _exact_approval(self, db, token_hash, owner_id, work_id, action, subject_id,
                        memory_key, source_digest, content_digest, now):
        row=db.execute('SELECT * FROM memory_approvals WHERE token_hash=?',(token_hash,)).fetchone()
        if not row:raise ValueError('정확한 승인이 필요합니다.')
        if row['state']=='revoked':
            # A revoked row no longer carries its memory key, so the full
            # binding check below cannot run.  Explaining *why* a revoked token
            # stopped working would mean comparing the caller-supplied
            # owner/work/action/subject against the stored row and reporting a
            # distinguishable error, which is an oracle telling a token holder
            # whether its guessed binding matched.  Revocation is therefore
            # reported exactly like any unusable token; the owner surface
            # re-reads current Memory state to explain what changed.
            raise ValueError('정확한 승인이 필요합니다.')
        expected=(self._memory_binding(owner_id),self._work_binding(work_id),action,subject_id,memory_key,source_digest,content_digest)
        observed=tuple(row[key] for key in ('owner_key','work_key','action','subject_id','memory_key','source_digest','content_digest'))
        if any(not hmac.compare_digest(str(left),str(right)) for left,right in zip(expected,observed)):
            raise ValueError('정확한 승인이 필요합니다.')
        if row['state']=='consumed':return row
        if row['state']!='issued' or float(row['expires'])<=now:
            if row['state']=='issued':
                db.execute("UPDATE memory_approvals SET state='expired' WHERE token_hash=?",(row['token_hash'],))
                db.commit()
            raise ValueError('승인이 만료되었습니다.')
        return row

    def accept_memory_candidate(self, owner_id, work_id, candidate_id, content_digest, approval_token, now=None):
        observed=time.time() if now is None else float(now);owner_key=self._memory_binding(owner_id);work_key=self._work_binding(work_id)
        token_hash=self._exact_memory_token_lookup(approval_token)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            candidate=db.execute('SELECT * FROM memory_candidates WHERE id=? AND owner_key=? AND work_key=?',(candidate_id,owner_key,work_key)).fetchone()
            if not candidate or candidate['content_digest']!=content_digest:raise ValueError('기억 후보를 다시 확인하세요.')
            approval=self._exact_approval(db,token_hash,owner_id,work_id,'accept-candidate',candidate_id,
                                          candidate['memory_key'],candidate['content_digest'],candidate['content_digest'],observed)
            if approval['state']=='consumed':
                result=self._memory_row(db.execute('SELECT * FROM memories WHERE id=?',(approval['result_id'],)).fetchone())
                if result:return result
                raise ValueError('승인 결과를 확인할 수 없습니다.')
            if candidate['state']!='pending':raise ValueError('이미 결정된 기억 후보입니다.')
            current=db.execute(
                "SELECT id,content_digest FROM memories WHERE owner_key=? AND memory_key=? AND state='current' ORDER BY created DESC LIMIT 1",
                (owner_key,candidate['memory_key']),
            ).fetchone()
            expected_state=(approval['expected_memory_id'],approval['expected_memory_digest'])
            current_state=(current['id'],current['content_digest']) if current else (None,None)
            if expected_state!=current_state:
                db.execute("UPDATE memory_approvals SET state='revoked',memory_key='' WHERE token_hash=? AND state='issued'",
                           (approval['token_hash'],))
                db.commit()
                raise ValueError('승인 이후 현재 기억이 변경되었습니다.')
            result=self._save_memory(db,candidate['memory_key'],candidate['content'],owner_key,work_key,candidate_id,
                                     preserve_correction_token=approval['token_hash'])
            db.execute("UPDATE memory_candidates SET state='accepted',decided=?,resulting_memory_id=? WHERE id=? AND state='pending'",(observed,result['id'],candidate_id))
            db.execute("UPDATE memory_approvals SET state='consumed',result_id=? WHERE token_hash=? AND state='issued'",(result['id'],approval['token_hash']))
            db.execute("""UPDATE memory_approvals SET state='revoked',memory_key=''
                          WHERE owner_key=? AND work_key=? AND action='accept-candidate'
                            AND subject_id=? AND token_hash<>? AND state='issued'""",
                       (owner_key,work_key,candidate_id,approval['token_hash']))
            return result

    def reject_memory_candidate(self, owner_id, work_id, candidate_id, content_digest, now=None):
        owner_key=self._memory_binding(owner_id);work_key=self._work_binding(work_id)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM memory_candidates WHERE id=? AND owner_key=? AND work_key=?',
                           (candidate_id,owner_key,work_key)).fetchone()
            if not row or not hmac.compare_digest(str(row['content_digest']),str(content_digest)):raise ValueError('기억 후보를 다시 확인하세요.')
            if row['state']=='rejected':
                return {key:row[key] for key in ('id','memory_key','content','created','state','content_digest','decided','resulting_memory_id')}
            if row['state']!='pending':raise ValueError('이미 결정된 기억 후보입니다.')
            db.execute('DELETE FROM memory_approvals WHERE owner_key=? AND work_key=? AND subject_id=?',
                       (owner_key,work_key,candidate_id))
            db.execute("UPDATE memory_candidates SET state='rejected',decided=?,memory_key='',content='' WHERE id=? AND state='pending'",(time.time() if now is None else float(now),candidate_id))
            result=db.execute('SELECT * FROM memory_candidates WHERE id=?',(candidate_id,)).fetchone()
            return {key:result[key] for key in ('id','memory_key','content','created','state','content_digest','decided','resulting_memory_id')}

    def correct_memory(self, owner_id, work_id, memory_id, memory_key, current_digest, content,
                       approval_token, now=None):
        memory_key,content=self._memory_value(memory_key,content);replacement_digest=self.memory_digest(memory_key,content)
        observed=time.time() if now is None else float(now);owner_key=self._memory_binding(owner_id);work_key=self._work_binding(work_id)
        token_hash=self._exact_memory_token_lookup(approval_token)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            approval=self._exact_approval(db,token_hash,owner_id,work_id,'correct-memory',memory_id,memory_key,current_digest,replacement_digest,observed)
            if approval['state']=='consumed':
                result=self._memory_row(db.execute('SELECT * FROM memories WHERE id=?',(approval['result_id'],)).fetchone())
                if result:return result
                raise ValueError('승인 결과를 확인할 수 없습니다.')
            current=db.execute("SELECT * FROM memories WHERE id=? AND owner_key=? AND state='current'",(memory_id,owner_key)).fetchone()
            if not current or current['memory_key']!=memory_key or not hmac.compare_digest(str(current['content_digest']),str(current_digest)):
                raise ValueError('수정할 기억을 다시 확인하세요.')
            result=self._save_memory(db,memory_key,content,owner_key,work_key,
                                     preserve_correction_token=approval['token_hash'])
            db.execute("UPDATE memory_approvals SET state='consumed',result_id=? WHERE token_hash=? AND state='issued'",(result['id'],approval['token_hash']))
            return result

    def _delete_memory_chain(self, owner_key, memory_id):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute("SELECT id,supersedes,memory_key FROM memories WHERE id=? AND owner_key=? AND state='current'",(memory_id,owner_key)).fetchone()
            if not current:return {'deleted':False,'id':memory_id,'kind':'memory','deleted_memory_count':0,'deleted_candidate_count':0,'deleted_approval_count':0,'retained_private_copies':'unknown_outside_store','external_archives_affected':False}
            memory_ids=[];cursor=current
            while cursor:
                memory_ids.append(cursor['id'])
                cursor=(db.execute('SELECT id,supersedes FROM memories WHERE id=? AND owner_key=?',(cursor['supersedes'],owner_key)).fetchone()
                        if cursor['supersedes'] else None)
            marks=','.join('?' for _ in memory_ids)
            candidates=[row['id'] for row in db.execute(
                f'SELECT id FROM memory_candidates WHERE owner_key=? AND state=\'accepted\' AND resulting_memory_id IN ({marks})',
                (owner_key,*memory_ids))]
            approval_subjects=memory_ids+candidates
            approval_deleted=0
            if approval_subjects:
                approval_marks=','.join('?' for _ in approval_subjects)
                approval_deleted=db.execute(
                    f'DELETE FROM memory_approvals WHERE owner_key=? AND (subject_id IN ({approval_marks}) OR result_id IN ({approval_marks}))',
                    (owner_key,*approval_subjects,*approval_subjects)).rowcount
            # An approval issued against this key must not survive the delete
            # and re-apply once the key is absent again.
            approval_deleted+=db.execute(
                "DELETE FROM memory_approvals WHERE owner_key=? AND memory_key=? AND state='issued'",
                (owner_key,current['memory_key'])).rowcount
            candidate_deleted=0
            if candidates:
                candidate_marks=','.join('?' for _ in candidates)
                candidate_deleted=db.execute(f'DELETE FROM memory_candidates WHERE owner_key=? AND id IN ({candidate_marks})',(owner_key,*candidates)).rowcount
            memory_deleted=db.execute(f'DELETE FROM memories WHERE owner_key=? AND id IN ({marks})',(owner_key,*memory_ids)).rowcount
        return {'deleted':bool(memory_deleted),'id':memory_id,'kind':'memory','deleted_memory_count':memory_deleted,
                'deleted_candidate_count':candidate_deleted,'deleted_approval_count':approval_deleted,
                'retained_private_copies':'unknown_outside_store','external_archives_affected':False}

    def delete_memory(self, owner_id, memory_id):
        if not isinstance(memory_id,str) or not memory_id:raise ValueError('삭제할 기억을 확인하세요.')
        return self._delete_memory_chain(self._memory_binding(owner_id),memory_id)

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

    def personal_records(self, query='', record_filter='all', limit=100, offset=0):
        if not isinstance(query,str) or len(query)>160:
            raise ValueError('기록 검색어를 확인하세요.')
        if record_filter not in ('all','saved','note','memory','temporary','artifact'):
            raise ValueError('기록 유형을 확인하세요.')
        if (isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=100 or
                isinstance(offset,bool) or not isinstance(offset,int) or not 0<=offset<=2_147_483_647):
            raise ValueError('기록 페이지 범위를 확인하세요.')
        now=time.time()
        union='''
            SELECT id,'note' AS type,'메모' AS label,'' AS memory_key,content,created,
                   NULL AS expires_at,'' AS sharing_state,'' AS source_kind,'' AS source_app,
                   '' AS workspace_id,'' AS job_id,'memories' AS deleteKind FROM notes
            UNION ALL
            SELECT id,'memory','기억',memory_key,content,created,NULL,'','','','','','memories'
              FROM memories WHERE state='current'
            UNION ALL
            SELECT id,'temporary','임시 자료','',source_kind||' · '||source_app||' · '||sharing_state,
                   captured_at,expires_at,sharing_state,source_kind,source_app,'','',''
              FROM context_events WHERE expires_at>?
            UNION ALL
            SELECT id,'artifact','저장된 결과','',content,created,NULL,'','','',workspace_id,job_id,'results'
              FROM workspace_results
        '''
        escaped=unicodedata.normalize('NFKC',query).casefold().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        needle=f'%{escaped}%'
        where='''
            WHERE (?='all' OR (?='saved' AND type IN ('note','memory')) OR type=?)
              AND (?='' OR unicode_search_key(coalesce(memory_key,'')||' '||content||' '||source_kind||' '||source_app)
                   LIKE ? ESCAPE '\\')
        '''
        params=(now,record_filter,record_filter,record_filter,query,needle)
        with self.db() as db:
            db.execute('DELETE FROM context_events WHERE expires_at<=?',(now,))
            rows=[dict(row) for row in db.execute(
                f'SELECT * FROM ({union}) {where} ORDER BY created DESC,id DESC LIMIT ? OFFSET ?',
                (*params,limit,offset),
            )]
            match_count=db.execute(f'SELECT COUNT(*) FROM ({union}) {where}',params).fetchone()[0]
            counts={
                'note':db.execute('SELECT COUNT(*) FROM notes').fetchone()[0],
                'memory':db.execute("SELECT COUNT(*) FROM memories WHERE state='current'").fetchone()[0],
                'temporary':db.execute('SELECT COUNT(*) FROM context_events WHERE expires_at>?',(now,)).fetchone()[0],
                'artifact':db.execute('SELECT COUNT(*) FROM workspace_results').fetchone()[0],
            }
        return {'items':rows,'counts':counts,'match_count':match_count,'offset':offset,'limit':limit,
                'has_more':offset+len(rows)<match_count}

    def delete_personal_space_item(self, kind, item_id):
        if kind not in ('memories','memory_candidates','results') or not isinstance(item_id,str) or not item_id:
            raise ValueError('삭제할 Personal Space 항목을 확인하세요.')
        if kind=='memories':
            with self.db() as db: memory=db.execute("SELECT owner_key FROM memories WHERE id=? AND state='current'",(item_id,)).fetchone()
            if memory:
                result=self._delete_memory_chain(memory['owner_key'],item_id)
                return {**result,'kind':'memories'}
        with self.db() as db:
            workspace_id=None
            if kind=='results':
                row=db.execute('SELECT workspace_id FROM workspace_results WHERE id=?',(item_id,)).fetchone()
                workspace_id=row['workspace_id'] if row else None
                deleted=db.execute('DELETE FROM workspace_results WHERE id=?',(item_id,)).rowcount
                if deleted:db.execute('UPDATE workspaces SET updated=? WHERE id=?',(time.time(),workspace_id))
            elif kind=='memory_candidates':
                db.execute('BEGIN IMMEDIATE')
                candidate=db.execute("SELECT owner_key FROM memory_candidates WHERE id=? AND state IN ('pending','rejected')",(item_id,)).fetchone()
                deleted_approvals=(db.execute('DELETE FROM memory_approvals WHERE owner_key=? AND subject_id=?',(candidate['owner_key'],item_id)).rowcount
                                   if candidate else 0)
                deleted=(db.execute("DELETE FROM memory_candidates WHERE id=? AND owner_key=? AND state IN ('pending','rejected')",(item_id,candidate['owner_key'])).rowcount
                         if candidate else 0)
            else:
                # A current memory is already routed through the approval-aware
                # chain above, so only a superseded row, or a note sharing the
                # Personal Space 'memories' bucket, can reach this path. Keep
                # the owner predicate, remove approvals bound to the row, and
                # splice the row out of the supersession chain: leaving a
                # dangling 'supersedes' pointer would stop a later chain delete
                # early and orphan the remaining ancestors while reporting an
                # untruthful deleted_memory_count.
                db.execute('BEGIN IMMEDIATE')
                superseded=db.execute("SELECT owner_key,supersedes FROM memories WHERE id=? AND state='superseded'",(item_id,)).fetchone()
                if superseded:
                    owner_key=superseded['owner_key']
                    deleted_approvals=db.execute('DELETE FROM memory_approvals WHERE owner_key=? AND (subject_id=? OR result_id=?)',
                                                 (owner_key,item_id,item_id)).rowcount
                    db.execute('UPDATE memories SET supersedes=? WHERE supersedes=? AND owner_key=?',
                               (superseded['supersedes'],item_id,owner_key))
                    # Mirror _delete_memory_chain: the accepted candidate holds a
                    # plaintext copy of the same value, so it must not outlive it.
                    deleted_candidates=db.execute("DELETE FROM memory_candidates WHERE owner_key=? AND state='accepted' AND resulting_memory_id=?",
                                                  (owner_key,item_id)).rowcount
                    memory_deleted=db.execute('DELETE FROM memories WHERE id=? AND owner_key=?',(item_id,owner_key)).rowcount
                else:
                    memory_deleted=deleted_candidates=0
                deleted=memory_deleted or db.execute('DELETE FROM notes WHERE id=?',(item_id,)).rowcount
        result={'deleted':bool(deleted),'id':item_id,'kind':kind,'workspace_id':workspace_id}
        if kind=='memory_candidates':
            result.update(deleted_approval_count=deleted_approvals,
                          retained_private_copies='unknown_outside_store',external_archives_affected=False)
        elif kind=='memories' and memory_deleted:
            result.update(deleted_memory_count=memory_deleted,deleted_candidate_count=deleted_candidates,
                          deleted_approval_count=deleted_approvals,
                          retained_private_copies='unknown_outside_store',external_archives_affected=False)
        return result

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
            inserted=db.execute('INSERT INTO workspace_results VALUES (?,?,?,?,?,?) ON CONFLICT(workspace_id,job_id) DO NOTHING',(str(uuid.uuid4()),workspace_id,job_id,job['response'] or '',evidence,time.time())).rowcount
            if not inserted:raise ValueError('이미 프로젝트에 저장된 완료 결과입니다.')
            db.execute('UPDATE workspaces SET updated=? WHERE id=?',(time.time(),workspace_id))
        return self.workspace_detail(workspace_id)

    def workspace_detail(self, workspace_id):
        workspace=self.workspace(workspace_id)
        if not workspace:return None
        with self.db() as db:
            workspace['results']=[dict(row) for row in db.execute('SELECT id,job_id,content,created FROM workspace_results WHERE workspace_id=? ORDER BY created DESC LIMIT 30',(workspace_id,))]
            workspace['result_count']=db.execute('SELECT COUNT(*) FROM workspace_results WHERE workspace_id=?',(workspace_id,)).fetchone()[0]
            workspace['saved_job_ids']=[row['job_id'] for row in db.execute('SELECT job_id FROM workspace_results WHERE workspace_id=? AND job_id IN (SELECT id FROM jobs ORDER BY created DESC LIMIT 40)',(workspace_id,))]
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

    def reserve_task_card(self, job_id, chat_id):
        """Claim the one card slot before the Telegram send can race the worker."""
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            job=db.execute('SELECT status FROM jobs WHERE id=?',(job_id,)).fetchone()
            if not job or job['status'] not in ('queued','running'):
                return None
            inserted=db.execute('INSERT OR IGNORE INTO telegram_task_cards VALUES (?,?,?,?,?)',
                                (job_id,chat_id,-1,job['status'],time.time())).rowcount
            return job['status'] if inserted else None

    def release_task_card_reservation(self, job_id):
        with self.db() as db:
            db.execute('DELETE FROM telegram_task_cards WHERE job_id=? AND message_id=-1',(job_id,))

    def save_task_card(self, job_id, chat_id, message_id, state):
        with self.db() as db:
            db.execute('INSERT INTO telegram_task_cards VALUES (?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET chat_id=excluded.chat_id,message_id=excluded.message_id,state=excluded.state,created=CASE WHEN telegram_task_cards.message_id=-1 THEN excluded.created ELSE telegram_task_cards.created END',
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
