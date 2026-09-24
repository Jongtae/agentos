"""Scoped local file workspace: references stay read-only; results are new files."""
from pathlib import Path
import hashlib, json, os, re, time, uuid
from .document_reader import read as read_document, supported as supported_document
from . import folder_grants


class FileWorkspace:
    """Owner-granted TXT/MD references and a separately writable workspace."""

    def __init__(self, store): self.store=store

    def configure(self, references, workspace):
        if not isinstance(references,list) or not references: raise ValueError('하나 이상의 참고 폴더를 연결하세요.')
        refs=[]
        for value in references:
            path=folder_grants.validate(value,self.store)
            if any(ref['path']==str(path) for ref in refs): continue
            stat=path.stat(); refs.append({'id':hashlib.sha256(f'{stat.st_dev}:{stat.st_ino}'.encode()).hexdigest()[:24],'path':str(path)})
        target=folder_grants.validate(workspace,self.store)
        if any(target==Path(ref['path']) or target.is_relative_to(ref['path']) or Path(ref['path']).is_relative_to(target) for ref in refs): raise ValueError('참고 폴더와 관리 작업공간은 겹치지 않게 연결하세요.')
        target_stat=target.stat(); workspace_id=hashlib.sha256(f'{target_stat.st_dev}:{target_stat.st_ino}'.encode()).hexdigest()[:24]
        self.store.put('file_workspace',{'references':refs,'workspace':str(target),'workspace_id':workspace_id})
        self.store.put('document_sharing',{})
        return self.status()

    def status(self): return self.store.config('file_workspace',{'references':[],'workspace':None})

    def active(self):
        """Stored configuration minus any folder the current grant rules forbid."""
        status=self.status()
        workspace=status.get('workspace')
        usable=workspace and not folder_grants.blocked(workspace,self.store)
        return {**status,'references':[ref for ref in status.get('references',[]) if not folder_grants.blocked(ref['path'],self.store)],
                'workspace':workspace if usable else None,'workspace_id':status.get('workspace_id') if usable else None}

    def projection(self):
        """Owner-facing status with the reason any stored folder is blocked."""
        status=self.status()
        workspace=status.get('workspace')
        return {**status,'references':[{**ref,'blocked':folder_grants.blocked(ref['path'],self.store)} for ref in status.get('references',[])],
                'workspace_blocked':folder_grants.blocked(workspace,self.store) if workspace else None}

    @staticmethod
    def _safe_relative(value):
        path=Path(value)
        if path.is_absolute() or '..' in path.parts or any(part.startswith('.') for part in path.parts): raise ValueError('허용하지 않은 파일 경로입니다.')
        return path

    def _reference(self, ref_id, relative):
        root=next((item for item in self.active()['references'] if item['id']==ref_id),None)
        if not root: raise ValueError('허용된 참고 폴더가 아닙니다.')
        base=Path(root['path']); path=self._safe_relative(relative); candidate=base/path
        if any(part.is_symlink() for part in (base, *candidate.parents) if part.exists()): raise ValueError('심볼릭 링크를 통한 참고 자료 접근은 허용하지 않습니다.')
        resolved=candidate.resolve()
        if (not resolved.is_relative_to(base) or resolved.suffix.lower() not in ('.txt','.md','.pdf','.docx','.xlsx') or not resolved.is_file() or candidate.is_symlink()): raise ValueError('참고 폴더 밖 또는 지원하지 않는 파일입니다.')
        return resolved

    def read(self, ref_id, relative):
        path=self._reference(ref_id,relative)
        if path.suffix.lower() in ('.txt','.md'): content=path.read_text(encoding='utf-8')
        else:
            document=read_document(path); content='\n'.join(f'[{segment["location"]}] {segment["text"]}' for segment in document.segments)
        stat=path.stat()
        return {'reference_id':ref_id,'source_id':hashlib.sha256(f'{stat.st_dev}:{stat.st_ino}'.encode()).hexdigest()[:24],
                'path':str(Path(relative)),'version':hashlib.sha256(content.encode()).hexdigest(),'content':content}

    def find_reference(self, query):
        matches=self.find_references(query, limit=2)
        if not matches: raise ValueError('연결한 참고 폴더에서 일치하는 TXT/MD 자료를 찾지 못했습니다.')
        if len(matches)>1: raise ValueError('일치하는 자료가 여러 개입니다. 더 구체적인 자료 검색어로 다시 요청하세요.')
        return matches[0]

    def find_references(self, query, limit=20):
        if not isinstance(query,str) or not 2<=len(query.strip())<=160: raise ValueError('두 글자 이상의 자료 검색어를 입력하세요.')
        phrase=query.casefold().strip(); alternatives=[item.strip() for item in phrase.split('||') if item.strip()]
        matches=[]
        for root in self.active()['references']:
            base=Path(root['path'])
            for parent,dirs,names in os.walk(base,followlinks=False):
                dirs[:]=[name for name in dirs if not name.startswith('.') and not (Path(parent)/name).is_symlink()]
                for name in names:
                    if name.startswith('.') or Path(name).suffix.lower() not in ('.txt','.md','.pdf','.docx','.xlsx') or not supported_document(Path(parent)/name): continue
                    relative=str((Path(parent)/name).relative_to(base))
                    try: source=self.read(root['id'],relative)
                    except (OSError,UnicodeError,ValueError): continue
                    haystack=(relative+'\n'+source['content']).casefold()
                    matches_query=False
                    for alternative in alternatives:
                        terms=[term for term in re.findall(r'[\w가-힣-]{2,}',alternative) if len(term)>2]
                        candidate=alternative in haystack if alternative else False
                        if not candidate and terms:
                            candidate=(any(term in haystack for term in terms) if len(terms)==1 else all(term in haystack for term in terms))
                        matches_query=matches_query or candidate
                    if matches_query:
                        matches.append(source)
                        if len(matches)>=limit: return matches
        return matches

    @staticmethod
    def _ensure_results_table(db):
        db.execute('CREATE TABLE IF NOT EXISTS file_workspace_results(id TEXT PRIMARY KEY, request_id TEXT UNIQUE, path TEXT UNIQUE, content_hash TEXT, sources TEXT, created REAL, workspace_id TEXT, state TEXT NOT NULL DEFAULT "current")')
        columns={row['name'] for row in db.execute('PRAGMA table_info(file_workspace_results)')}
        if 'state' not in columns: db.execute('ALTER TABLE file_workspace_results ADD COLUMN state TEXT NOT NULL DEFAULT "current"')
        if 'workspace_id' not in columns: db.execute('ALTER TABLE file_workspace_results ADD COLUMN workspace_id TEXT')

    def _workspace_id(self):
        value=self.active().get('workspace_id')
        if not isinstance(value,str) or not value: raise ValueError('관리 작업공간을 먼저 연결하세요.')
        return value

    @staticmethod
    def _source_metadata(source):
        return {key:source[key] for key in ('reference_id','source_id','path','version') if key in source}

    def _result_path(self, relative):
        workspace=self.active().get('workspace')
        root=Path(workspace) if workspace else None
        if root is None or not root.is_absolute() or not root.is_dir() or root.is_symlink(): raise ValueError('관리 작업공간을 먼저 연결하세요.')
        candidate=root/self._safe_relative(relative)
        if candidate.is_symlink() or not candidate.resolve().is_relative_to(root): raise ValueError('관리 작업공간 밖의 결과에는 접근할 수 없습니다.')
        return candidate

    def recover(self):
        """Finalize only a verified publication, and discard unpublised reservations."""
        with self.store.db() as db:
            self._ensure_results_table(db)
            pending=[dict(row) for row in db.execute("SELECT * FROM file_workspace_results WHERE state='pending'")]
        for record in pending:
            if record.get('workspace_id')!=self._workspace_id():
                with self.store.db() as db: db.execute("UPDATE file_workspace_results SET state='detached' WHERE id=?",(record['id'],))
                continue
            try:
                published=self._result_path(record['path'])
                complete=published.is_file() and hashlib.sha256(published.read_bytes()).hexdigest()==record['content_hash']
            except (OSError,ValueError): complete=False
            with self.store.db() as db:
                if complete: db.execute("UPDATE file_workspace_results SET state='current' WHERE id=? AND state='pending'",(record['id'],))
                else: db.execute("DELETE FROM file_workspace_results WHERE id=? AND state='pending'",(record['id'],))

    def _mark_current(self, record):
        with self.store.db() as db: db.execute("UPDATE file_workspace_results SET state='current' WHERE id=? AND state='pending'",(record['id'],))

    def save(self, request_id, title, content, sources):
        if not request_id or not content.strip(): raise ValueError('저장 요청과 내용이 필요합니다.')
        if not isinstance(sources,list) or not sources: raise ValueError('원본 출처가 필요합니다.')
        self.recover()
        safe=''.join(char if char.isalnum() or char in ' -_' else '-' for char in title).strip()[:80] or 'result'
        sources=[self._source_metadata(source) for source in sources]
        if any(set(('reference_id','source_id','path','version'))-set(source) for source in sources): raise ValueError('원본 출처 정보가 올바르지 않습니다.')
        body=content.rstrip()+'\n\n---\nSources:\n'+''.join(f'- {source["path"]} @ {source["version"]}\n' for source in sources)
        with self.store.db() as db:
            self._ensure_results_table(db); db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM file_workspace_results WHERE request_id=?',(request_id,)).fetchone()
            if old:return dict(old)
            suffix=1
            while True:
                target=self._result_path(safe+'.md' if suffix==1 else safe+f'-{suffix}.md')
                if target.exists() or db.execute('SELECT 1 FROM file_workspace_results WHERE path=?',(target.name,)).fetchone(): suffix+=1; continue
                record={'id':str(uuid.uuid4()),'request_id':request_id,'path':target.name,'content_hash':hashlib.sha256(body.encode()).hexdigest(),'sources':json.dumps(sources),'created':time.time(),'workspace_id':self._workspace_id(),'state':'pending'}
                db.execute('INSERT INTO file_workspace_results(id,request_id,path,content_hash,sources,created,workspace_id,state) VALUES (:id,:request_id,:path,:content_hash,:sources,:created,:workspace_id,:state)',record)
                break
        temporary=target.with_name(target.name+'.tmp-'+uuid.uuid4().hex); published=False
        try:
            temporary.write_text(body,encoding='utf-8')
            while True:
                try:
                    os.link(temporary,target); published=True; temporary.unlink(); break
                except FileExistsError:
                    temporary.unlink(missing_ok=True)
                    with self.store.db() as db: db.execute("DELETE FROM file_workspace_results WHERE id=? AND state='pending'",(record['id'],))
                    return self.save(request_id,title,content,sources)
            self._mark_current(record)
            return {**record,'state':'current'}
        except Exception:
            temporary.unlink(missing_ok=True)
            if published: target.unlink(missing_ok=True)
            with self.store.db() as db: db.execute("DELETE FROM file_workspace_results WHERE id=? AND state='pending'",(record['id'],))
            raise

    def _fresh(self, record):
        try: sources=json.loads(record['sources'])
        except (TypeError,json.JSONDecodeError): return False
        try:return bool(sources) and all((current:=self.read(source['reference_id'],source['path']))['version']==source['version'] and current['source_id']==source['source_id'] for source in sources)
        except (KeyError,ValueError,OSError,UnicodeError): return False

    def search(self, query):
        latest=isinstance(query,str) and query.strip() in ('*','__latest__')
        if not latest and (not isinstance(query,str) or not 2<=len(query.strip())<=160): raise ValueError('두 글자 이상의 결과 검색어를 입력하세요.')
        self.recover()
        needle=query.casefold().strip()
        with self.store.db() as db:
            self._ensure_results_table(db); records=[dict(row) for row in db.execute('SELECT * FROM file_workspace_results ORDER BY created DESC LIMIT 100')]
        results=[]
        for record in records:
            if record.get('workspace_id')!=self._workspace_id():
                with self.store.db() as db: db.execute("UPDATE file_workspace_results SET state='detached' WHERE id=?",(record['id'],))
                continue
            fresh=self._fresh(record)
            with self.store.db() as db: db.execute('UPDATE file_workspace_results SET state=? WHERE id=?',('current' if fresh else 'stale',record['id']))
            if not fresh: continue
            try: content=self._result_path(record['path']).read_text(encoding='utf-8')
            except (OSError,UnicodeError,ValueError): continue
            if latest or needle in (record['path']+'\n'+content).casefold(): results.append({'id':record['id'],'path':record['path'],'content':content,'sources':json.loads(record['sources'])})
            if latest and results: break
        return results
