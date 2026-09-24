"""Repository-only delivery controller; not part of the installed AgentOS runtime."""
import argparse
import importlib
import hashlib
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from xml.sax.saxutils import escape as xml_escape
from types import SimpleNamespace
from .handoff import GithubCliBoundary, StateHandoffLoop

RETRY_SECONDS = 6 * 60 * 60
DAILY_LIMIT = 4


class DeliveryError(RuntimeError):
    pass


def default_state_path():
    override=os.environ.get('AGENTOS_DELIVERY_STATE')
    if override:return Path(override).expanduser()
    return Path.home()/'Library'/'Application Support'/'personal-agentos-delivery'/'state.json'


class StateStore:
    def __init__(self, path=None):
        self.path=Path(path or default_state_path())
        self.lock_path=self.path.with_suffix('.lock')

    def read(self):
        try:
            value=json.loads(self.path.read_text())
            return value if isinstance(value,dict) else {}
        except FileNotFoundError:return {}
        except (ValueError,OSError):return {'status':'invalid-state','last_error':'Delivery state could not be read.'}

    def write(self, value):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        safe={key:value[key] for key in ('active','completed','blocked','status','milestone','issue','issues','last_validation','last_error','next_retry_at','attempt_day','attempts_today','pr','release','updated_at') if key in value}
        with tempfile.NamedTemporaryFile('w',dir=self.path.parent,delete=False) as handle:
            json.dump(safe,handle,ensure_ascii=False,sort_keys=True)
            handle.write('\n');name=handle.name
        os.chmod(name,0o600);os.replace(name,self.path)
        return safe

    def locked(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        handle=self.lock_path.open('a')
        try:
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close();raise DeliveryError('A delivery loop is already running.')
        return handle


class DeliveryPlan:
    def __init__(self, path):
        try:data=json.loads(Path(path).read_text())
        except (OSError,ValueError) as exc:raise DeliveryError('delivery-plan.yaml must contain valid JSON-compatible YAML.') from exc
        if not isinstance(data,dict) or not isinstance(data.get('iterations'),list):raise DeliveryError('delivery plan has no iterations.')
        self.data=data
        self.items={item['id']:item for item in data['iterations'] if isinstance(item,dict) and isinstance(item.get('id'),str)}
        if len(self.items)!=len(data['iterations']):raise DeliveryError('Each delivery iteration needs a unique id.')
        self.milestones=data.get('milestones',{}) if isinstance(data.get('milestones',{}),dict) else {}

    def documented_completed(self):
        history=self.data.get('history',{})
        rows=history.get('documented_completed_iterations',[]) if isinstance(history,dict) else []
        return {item for item in rows if item in self.items}

    def next_goal(self):
        value=self.data.get('next_goal',{})
        return dict(value) if isinstance(value,dict) else {}

    def milestone_title(self, item):
        configured=self.milestones.get(item.get('milestone'),{})
        if isinstance(configured,dict) and isinstance(configured.get('title'),str):return configured['title']
        title=item.get('milestone_title')
        return title if isinstance(title,str) else None

    def select(self, state):
        completed=set(state.get('completed',[])) if isinstance(state.get('completed'),list) else set()
        declared=self.next_goal()
        active=declared.get('id') if declared.get('status') == 'active' else None
        item=self.items.get(active)
        # Finished work is never selectable, whichever list records it.
        # `state['completed']` is runtime and empty on a fresh clone or after
        # a state reset; the plan's own completed list is durable. Without
        # this, eight iterations recorded complete - GOV-01, TOP-00, SCN-D-01,
        # DRIVE-TG-01, FILE-WS-A/B/C-01 and USE-01 - were still armed and
        # genuinely selectable, and independent review drove one of them far
        # enough for the heartbeat to issue a live `gh` command. Their
        # iteration records are frozen by the pre-GOV-USE preservation
        # contract, so the refusal belongs here rather than in the plan.
        if not item or active in completed or active in self.documented_completed():
            return None
        if item.get('activation_status') != 'owner-activated-goal-ready' or not item.get('issue'):
            return None
        dependencies=item.get('depends_on', [])
        documented=self.documented_completed()
        if not all(dependency in completed or dependency in documented for dependency in dependencies):
            return None
        return item


class CommandRunner:
    def run(self, args, cwd=None, timeout=900):
        try:
            # A stale shell token can override the valid GitHub account held
            # in the macOS keychain. API calls always use that keychain account.
            env=None
            if args and args[0]=='gh':
                env=os.environ.copy();env.pop('GITHUB_TOKEN',None);env.pop('GH_TOKEN',None)
            # Git pushes may need the interactive shell's credential helper,
            # but it must not reintroduce that stale environment token.
            if args[:2]==['git','push']:
                args=['zsh','-ic','source "$HOME/.zshrc" >/dev/null 2>&1; unset GITHUB_TOKEN GH_TOKEN; command "$@"','agentos-auth',*args]
            return subprocess.run(args,cwd=cwd,text=True,capture_output=True,timeout=timeout,env=env)
        except subprocess.TimeoutExpired as exc:
            stdout=exc.stdout.decode() if isinstance(exc.stdout,bytes) else (exc.stdout or '')
            stderr=exc.stderr.decode() if isinstance(exc.stderr,bytes) else (exc.stderr or '')
            return SimpleNamespace(returncode=124,stdout=stdout,stderr=f'{stderr}\nTimed out after {timeout} seconds.')
        except OSError as exc:
            return SimpleNamespace(returncode=127,stdout='',stderr=f'Could not start {args[0]}: {exc}')


def classify_failure(text):
    lowered=(text or '').lower()
    if 'timed out' in lowered or 'timeout' in lowered:return 'delivery-timeout'
    if any(term in lowered for term in ('429','rate limit','quota','free model')):return 'external-rate-limit'
    if any(term in lowered for term in ('oauth','authorization','permission','forbidden','401','403')):return 'blocked-approval'
    if 'enoent' in lowered and 'codex' in lowered:return 'worker-unavailable'
    if 'unexpected argument' in lowered and 'codex' in lowered:return 'worker-incompatible'
    return 'validation-failed'


class DeliveryController:
    def __init__(self, root=None, state_path=None, runner=None, now=None, handoff_workers=None, handoff_github_factory=None):
        self.root=Path(root or Path.cwd()).resolve()
        self.handoff_workers=handoff_workers or {}
        self.handoff_github_factory=handoff_github_factory or GithubCliBoundary
        configured_plan=self.root/'delivery-plan.yaml'
        if not configured_plan.is_file():
            raise DeliveryError('delivery-plan.yaml was not found at the repository root.')
        self.plan=DeliveryPlan(configured_plan)
        self.state_store=StateStore(state_path)
        self.runner=runner or CommandRunner()
        self.now=now or time.time

    def _migrate_stale_state(self, state):
        """Reconcile retired control metadata with documented merged work."""
        state=dict(state)
        stale=False
        retired_deferred=False
        history=self.plan.data.get('history',{})
        reconcile_when=history.get('reconcile_state_when_active',[]) if isinstance(history,dict) else []
        should_reconcile=(state.get('active') in reconcile_when or state.get('blocked') in reconcile_when
                          or state.get('last_validation') == 'migrated-documentation')
        documented=self.plan.documented_completed() if should_reconcile else set()
        deferred={ident for ident,item in self.plan.items.items()
                  if item.get('activation_status') == 'owner-deferred'}
        completed=set(state.get('completed',[])) if isinstance(state.get('completed'),list) else set()
        if not documented <= completed:
            state['completed']=sorted(completed | documented)
            stale=True
        for key in ('active','blocked'):
            value=state.get(key)
            if value and (value not in self.plan.items or value in documented or value in deferred):
                retired_deferred=retired_deferred or value in deferred
                state.pop(key,None)
                stale=True
        issues=state.get('issues')
        if isinstance(issues,dict):
            retained={key:value for key,value in issues.items() if key not in deferred}
            if retained != issues:
                retired_deferred=True
                if retained:state['issues']=retained
                else:state.pop('issues',None)
                stale=True
        if stale and not state.get('active') and not state.get('blocked'):
            for key in ('milestone','issue','pr','release','next_retry_at','last_error','attempt_day','attempts_today'):
                state.pop(key,None)
            if retired_deferred:
                state.update(status='retired-owner-deferred',last_validation='migrated-owner-deferred',updated_at=self.now())
            else:
                state.update(status='reconciled-documentation' if should_reconcile else 'ready-to-run',last_validation='migrated-documentation' if should_reconcile else 'migrated-plan',updated_at=self.now())
        return state

    def status(self):
        previous=self.state_store.read()
        state=self._migrate_stale_state(previous)
        if state != previous:self.state_store.write(state)
        item=self.plan.select(state)
        next_goal=self.plan.next_goal() if item is None else {}
        return {**state,'active':item and item['id'],'milestone':item and item['milestone'],
                'issue':item and self._issue_number(item,state),'summary':item and item['summary'],
                'next_goal':next_goal or None,
                'next_action':'wait for retry' if state.get('status','').startswith('blocked') else ('run current iteration' if item else next_goal.get('action','delivery plan complete'))}

    def due(self, state):
        return not state.get('status','').startswith('blocked')

    def _attempt_allowed(self, state):
        day=dt.datetime.fromtimestamp(self.now(),dt.timezone.utc).date().isoformat()
        attempts=state.get('attempts_today',0) if state.get('attempt_day')==day else 0
        return attempts<DAILY_LIMIT,day,attempts

    def _gh(self, *args):
        return self._command(['gh',*args],cwd=self.root,timeout=60)

    def _command(self, args, cwd=None, timeout=900):
        """Run every child process through one bounded, non-throwing boundary."""
        try:
            return self.runner.run(args,cwd=cwd,timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            stdout=exc.stdout.decode() if isinstance(exc.stdout,bytes) else (exc.stdout or '')
            stderr=exc.stderr.decode() if isinstance(exc.stderr,bytes) else (exc.stderr or '')
            return SimpleNamespace(returncode=124,stdout=stdout,stderr=f'{stderr}\nTimed out after {timeout} seconds.')
        except OSError as exc:
            return SimpleNamespace(returncode=127,stdout='',stderr=f'Could not start {args[0]}: {exc}')

    @staticmethod
    def _issue_number(item, state):
        return item.get('issue') or state.get('issues',{}).get(item['id'])

    def _ensure_issue(self, item, state, dry_run):
        issue=self._issue_number(item,state)
        if issue:
            return issue
        raise DeliveryError('A delivery controller cannot create an issue; an owner-activated goal-ready issue is required.')

    def _record_block(self, item, state, classification, detail, dry_run):
        issue=self._issue_number(item,state)
        state.update(active=item['id'],blocked=item.get('repair_of') or item['id'],milestone=item['milestone'],issue=issue,status='blocked-'+classification,
                     last_validation='failed',last_error=detail[:500],next_retry_at=None,updated_at=self.now())
        return self.state_store.write(state)

    def _complete(self, item, state, dry_run=False):
        raise DeliveryError('Completion rejected: the delivery controller cannot verify merged PR, required CI, requirement-to-evidence audit, and closeout.')

    def _issue_is_closed(self, item, state):
        issue=self._issue_number(item,state)
        if not issue:return False
        result=self._gh('issue','view',str(issue),'--repo',self.plan.data['repository'],'--json','state','--jq','.state')
        if result.returncode:
            raise DeliveryError(result.stderr or 'Could not read delivery issue status.')
        return result.returncode==0 and result.stdout.strip()=='CLOSED'

    @staticmethod
    def _complete_plan(state, now):
        state={**state}
        for key in ('active','milestone','issue','pr','release','blocked','next_retry_at'):
            state.pop(key,None)
        state.update(status='complete',last_validation=state.get('last_validation','passed'),updated_at=now)
        return state

    def reconcile(self, dry_run=False):
        """Never adopt a closed issue as proof of completion; await current evidence."""
        lock=self.state_store.locked()
        try:
            state=self._migrate_stale_state(self.state_store.read());item=self.plan.select(state)
            if not item:return self.state_store.write({**state,'status':'awaiting-owner-activated-goal','updated_at':self.now()})
            if state.get('status','').startswith('blocked'):
                return self.state_store.write({**state,'status':'blocked-awaiting-changed-condition','updated_at':self.now()})
            issue=self._issue_number(item,state)
            if not issue:
                return self.state_store.write({**state,'status':'ready-to-run','updated_at':self.now()})
            try:
                if self._issue_is_closed(item,state):
                    return self.state_store.write({**state,'active':item['id'],'milestone':item['milestone'],
                                                   'issue':issue,'status':'completion-evidence-required',
                                                   'last_error':'A closed issue is not completion evidence.',
                                                   'updated_at':self.now()})
            except DeliveryError as exc:
                return self._record_block(item,state,classify_failure(str(exc)),str(exc),dry_run)
            return self.state_store.write({**state,'active':item['id'],'milestone':item['milestone'],'issue':issue,'status':'ready-to-run','updated_at':self.now()})
        finally:
            lock.close()

    def run_once(self, dry_run=False, scheduled=False):
        lock=self.state_store.locked()
        try:
            state=self._migrate_stale_state(self.state_store.read());item=self.plan.select(state)
            if not item:return self.state_store.write({**state,'status':'awaiting-owner-activated-goal','updated_at':self.now()})
            if state.get('status','').startswith('blocked'):
                return self.state_store.write({**state,'status':'blocked-awaiting-changed-condition','updated_at':self.now()})
            issue=self._issue_number(item,state)
            try:
                issue=self._ensure_issue(item,state,dry_run)
            except DeliveryError as exc:
                return self._record_block(item,state,classify_failure(str(exc)),str(exc),dry_run)
            if issue:state['issues']=dict(state.get('issues',{}),**{item['id']:issue})
            if not dry_run:
                try:
                    if self._issue_is_closed(item,state):
                        return self.state_store.write({**state,'active':item['id'],'milestone':item['milestone'],
                                                       'issue':issue,'status':'completion-evidence-required',
                                                       'last_error':'A closed issue is not completion evidence.',
                                                       'updated_at':self.now()})
                except DeliveryError as exc:
                    return self._record_block(item,state,classify_failure(str(exc)),str(exc),dry_run)
            state.update(active=item['id'],milestone=item['milestone'],issue=issue,status='running',updated_at=self.now())
            state.update(status='manual-governance-execution-required',updated_at=self.now())
            return self.state_store.write(state)
        finally:
            lock.close()

    @staticmethod
    def _next_patch_version(version):
        match=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)',version)
        if not match:raise DeliveryError('Release version must use major.minor.patch.')
        major,minor,patch=(int(part) for part in match.groups())
        return f'{major}.{minor}.{patch+1}'

    @staticmethod
    def _read_project_version(path):
        match=re.search(r'^version\s*=\s*"([^"]+)"\s*$',Path(path).read_text(),re.M)
        if not match:raise DeliveryError('pyproject.toml has no project version.')
        return match.group(1)

    @staticmethod
    def _write_project_version(path, version):
        content=Path(path).read_text()
        updated=re.sub(r'^version\s*=\s*"[^"]+"\s*$',f'version = "{version}"',content,count=1,flags=re.M)
        if updated==content:raise DeliveryError('Could not update the project version.')
        Path(path).write_text(updated)

    def _release_error(self, item, state, result, fallback):
        detail=((getattr(result,'stdout','') or '')+'\n'+(getattr(result,'stderr','') or '')).strip() or fallback
        return self._record_block(item,state,classify_failure(detail),detail,False)

    def _archive_sha256(self, tag):
        url=f'https://github.com/{self.plan.data["repository"]}/archive/refs/tags/{tag}.tar.gz'
        digest=hashlib.sha256()
        try:
            with urllib.request.urlopen(url,timeout=60) as response:
                while chunk:=response.read(1024*1024):digest.update(chunk)
        except OSError as exc:raise DeliveryError(f'Could not download release archive: {exc}') from exc
        return digest.hexdigest()

    def _release_preflight(self, item, state):
        """Require recorded release evidence before any mutable release action."""
        for command in item.get('release_validation',[]):
            checked=self._command(command.split(),cwd=self.root,timeout=900)
            if checked.returncode:
                return self._record_block(item,state,'validation-failed',(checked.stdout or '')+'\n'+(checked.stderr or ''),False)
        return None

    def _run_release(self, item, state):
        """Fail closed: release mutations require the active-goal workflow."""
        return self._record_block(item,state,'manual-governance-execution-required',
                                  'The legacy controller cannot tag, publish, push, merge, install, or complete a release. Use the active goal workflow.',False)
        if not (self.root/'.git').exists():
            return self._record_block(item,state,'delivery-failed','Release requires a git checkout.',False)
        blocked=self._release_preflight(item,state)
        if blocked:return blocked
        fetched=self._command(['git','fetch','origin'],cwd=self.root,timeout=180)
        if fetched.returncode:return self._release_error(item,state,fetched,'Could not fetch the release source.')
        current=self._read_project_version(self.root/'pyproject.toml')
        version=self._next_patch_version(current);tag='v'+version
        release=dict(state.get('release',{}));release.update(version=version,tag=tag)
        state['release']=release
        worktree=self.state_store.path.parent/'worktrees'/('release-'+tag)
        branch='release/'+tag
        if not worktree.exists():
            created=self._command(['git','worktree','add','-b',branch,str(worktree),'origin/main'],cwd=self.root,timeout=180)
            if created.returncode:return self._release_error(item,state,created,'Could not create the release worktree.')
        project=worktree/'pyproject.toml'
        worktree_version=self._read_project_version(project)
        if worktree_version==current:self._write_project_version(project,version)
        elif worktree_version!=version:return self._record_block(item,state,'delivery-failed','Release worktree has an unexpected version.',False)
        for command in item.get('tests',[]):
            checked=self._command(command.split(),cwd=worktree,timeout=900)
            if checked.returncode:return self._release_error(item,state,checked,'Release validation failed.')
        changed=self._command(['git','status','--porcelain'],cwd=worktree,timeout=30)
        if changed.returncode:return self._release_error(item,state,changed,'Could not inspect the release worktree.')
        if changed.stdout.strip():
            committed=self._command(['git','add','pyproject.toml'],cwd=worktree,timeout=30)
            if committed.returncode:return self._release_error(item,state,committed,'Could not stage the release version.')
            committed=self._command(['git','commit','-m',f'Release {tag}'],cwd=worktree,timeout=60)
            if committed.returncode:return self._release_error(item,state,committed,'Could not commit the release version.')
        pushed=self._command(['git','push','-u','origin',branch],cwd=worktree,timeout=180)
        if pushed.returncode:return self._release_error(item,state,pushed,'Could not push the release branch.')
        opened=self._gh('pr','create','--repo',self.plan.data['repository'],'--base','main','--head',branch,'--title',f'Release {tag}','--body',f'Automated verified release for `{item["id"]}`.')
        match=re.search(r'https://github\.com/[^\s]+/pull/\d+',opened.stdout or '')
        if opened.returncode or not match:return self._release_error(item,state,opened,'Could not open the release PR.')
        state['pr']=match.group(0)
        merged=self._gh('pr','merge',state['pr'],'--repo',self.plan.data['repository'],'--squash','--delete-branch')
        if merged.returncode:return self._release_error(item,state,merged,'Could not merge the release PR.')
        published=self._gh('release','create',tag,'--repo',self.plan.data['repository'],'--target','main','--title',f'Personal AgentOS {tag}','--generate-notes')
        if published.returncode:return self._release_error(item,state,published,'Could not publish the GitHub Release.')
        release['url']=f'https://github.com/{self.plan.data["repository"]}/releases/tag/{tag}'
        try:sha=self._archive_sha256(tag)
        except DeliveryError as exc:return self._record_block(item,state,'delivery-failed',str(exc),False)
        tap_repo=item.get('tap_repository','Jongtae/homebrew-agentos');formula=item.get('formula_path','Formula/agentos.rb')
        tap=self.state_store.path.parent/'tap'
        if not (tap/'.git').exists():
            cloned=self._command(['git','clone',f'https://github.com/{tap_repo}.git',str(tap)],cwd=self.state_store.path.parent,timeout=300)
            if cloned.returncode:return self._release_error(item,state,cloned,'Could not clone the Homebrew tap.')
        refreshed=self._command(['git','fetch','origin'],cwd=tap,timeout=180)
        if refreshed.returncode:return self._release_error(item,state,refreshed,'Could not fetch the Homebrew tap.')
        formula_branch='agentos-'+version
        checked=self._command(['git','checkout','-B',formula_branch,'origin/main'],cwd=tap,timeout=60)
        if checked.returncode:return self._release_error(item,state,checked,'Could not prepare the Formula branch.')
        formula_path=tap/formula
        if not formula_path.is_file():return self._record_block(item,state,'delivery-failed','Homebrew Formula file was not found.',False)
        text=formula_path.read_text()
        text=re.sub(r'url "[^"]+/archive/refs/tags/v[^"]+\.tar\.gz"',f'url "https://github.com/{self.plan.data["repository"]}/archive/refs/tags/{tag}.tar.gz"',text,count=1)
        text=re.sub(r'sha256 "[0-9a-f]{64}"',f'sha256 "{sha}"',text,count=1)
        formula_path.write_text(text)
        formula_commit=self._command(['git','add',formula],cwd=tap,timeout=30)
        if formula_commit.returncode:return self._release_error(item,state,formula_commit,'Could not stage the Formula update.')
        formula_commit=self._command(['git','commit','-m',f'agentos {version}'],cwd=tap,timeout=60)
        if formula_commit.returncode:return self._release_error(item,state,formula_commit,'Could not commit the Formula update.')
        formula_push=self._command(['git','push','-u','origin',formula_branch],cwd=tap,timeout=180)
        if formula_push.returncode:return self._release_error(item,state,formula_push,'Could not push the Formula update.')
        tap_pr=self._gh('pr','create','--repo',tap_repo,'--base','main','--head',formula_branch,'--title',f'agentos {version}','--body',f'Updates AgentOS to `{tag}` after verified release.')
        tap_match=re.search(r'https://github\.com/[^\s]+/pull/\d+',tap_pr.stdout or '')
        if tap_pr.returncode or not tap_match:return self._release_error(item,state,tap_pr,'Could not open the Formula PR.')
        release['tap_pr']=tap_match.group(0)
        tap_merge=self._gh('pr','merge',release['tap_pr'],'--repo',tap_repo,'--squash','--delete-branch')
        if tap_merge.returncode:return self._release_error(item,state,tap_merge,'Could not merge the Formula PR.')
        brew=self._command(['brew','update'],cwd=self.root,timeout=900)
        if brew.returncode:return self._release_error(item,state,brew,'Could not update Homebrew.')
        installed=self._command(['brew','upgrade','jongtae/agentos/agentos'],cwd=self.root,timeout=900)
        if installed.returncode:return self._release_error(item,state,installed,'Could not upgrade the Homebrew Formula.')
        verified=self._command(['brew','test','jongtae/agentos/agentos'],cwd=self.root,timeout=900)
        if verified.returncode:return self._release_error(item,state,verified,'Homebrew Formula verification failed.')
        installed_acceptance=self._command(['python3','scripts/quickstart_install_check.py'],cwd=self.root,timeout=900)
        if installed_acceptance.returncode:return self._release_error(item,state,installed_acceptance,'Installed Homebrew acceptance failed.')
        state['release']=release
        return self._complete(item,state,False)

    def _run_worker(self, item, state):
        return self._record_block(item,state,'manual-governance-execution-required',
                                  'The legacy controller cannot run Codex, create branches, push, merge, or close a goal. Use the active goal workflow.',False)

    def _schedule_program(self):
        """Select the same runtime as the selected delivery-plan checkout."""
        if (self.root/'personal_agent'/'quickstart.py').is_file():
            # pyenv interpreters can hang before importing codecs under launchd.
            # The delivery controller path is standard-library-only, so the
            # macOS runtime is a safe source-schedule fallback.
            system_python=Path('/usr/bin/python3')
            return [str(system_python if system_python.is_file() else Path(sys.executable))]
        command=shutil.which('agentos')
        return [command] if command else [sys.executable,'-m','personal_agent.quickstart']

    def install_schedule(self):
        raise DeliveryError('Managed delivery scheduling is disabled; use the one existing goal-resume heartbeat.')
        label='com.jongtae.personal-agentos.delivery';folder=Path.home()/'Library'/'LaunchAgents';path=folder/(label+'.plist')
        folder.mkdir(parents=True,exist_ok=True)
        source_mode=(self.root/'personal_agent'/'quickstart.py').is_file()
        delivery_args=['delivery','run','--once','--scheduled','--root',str(self.root),'--state',str(self.state_store.path)]
        if source_mode:
            # launchd may strip PYTHONPATH, so bootstrap the exact source tree
            # through an absolute sys.path entry rather than inherited state.
            bootstrap=(f'import runpy,sys;sys.path.insert(0,{str(self.root)!r});'
                       f'sys.argv={["agentos",*delivery_args]!r};'
                       "runpy.run_module('personal_agent.quickstart',run_name='__main__')")
            args=[*self._schedule_program(),'-c',bootstrap]
        else:
            args=[*self._schedule_program(),*delivery_args]
        rendered=''.join(f'<string>{xml_escape(str(arg))}</string>' for arg in args)
        working_directory='/' if source_mode else str(self.root)
        payload=(f'<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict>'
                 f'<key>Label</key><string>{label}</string><key>ProgramArguments</key><array>{rendered}</array>'
                 f'<key>WorkingDirectory</key><string>{xml_escape(working_directory)}</string>'
                 f'<key>StartInterval</key><integer>{RETRY_SECONDS}</integer><key>RunAtLoad</key><true/>'
                 f'<key>StandardOutPath</key><string>{xml_escape(str(Path.home()/"Library/Logs/personal-agentos-delivery.log"))}</string>'
                 f'<key>StandardErrorPath</key><string>{xml_escape(str(Path.home()/"Library/Logs/personal-agentos-delivery.error.log"))}</string></dict></plist>')
        path.write_text(payload);os.chmod(path,0o600)
        self._command(['launchctl','bootout',f'gui/{os.getuid()}',str(path)],timeout=30)
        result=self._command(['launchctl','bootstrap',f'gui/{os.getuid()}',str(path)],timeout=30)
        if result.returncode:raise DeliveryError(result.stderr or 'Could not install launchd schedule.')
        health=self._command(['launchctl','print',f'gui/{os.getuid()}/{label}'],timeout=30)
        if health.returncode:raise DeliveryError(health.stderr or 'launchd did not register the delivery schedule.')
        return {'scheduled':True,'path':str(path)}

    def uninstall_schedule(self):
        path=Path.home()/'Library'/'LaunchAgents'/'com.jongtae.personal-agentos.delivery.plist'
        self._command(['launchctl','bootout',f'gui/{os.getuid()}',str(path)],timeout=30)
        path.unlink(missing_ok=True);return {'scheduled':False}

    def handoff_tick(self, role, state_path=None, worker_factory=None):
        """Run the state queue once through the existing delivery CLI.

        This is intentionally dispatch-only.  A scheduler/heartbeat may select
        a goal but cannot manufacture a Codex session, merge a PR, or create a
        second schedule.  Configured role workers supply executor/reviewer
        callables to ``StateHandoffLoop`` in their own bounded process.
        """
        repository = self.plan.data.get('repository')
        if not repository: raise DeliveryError('delivery plan has no repository.')
        path = Path(state_path) if state_path else self.state_store.path.with_name('handoff-state.json')
        # The active delivery selector is the sole authority.  Historical or
        # future goal-ready records are not a queue-wide execution grant.
        item = self.plan.select(self.state_store.read())
        goals = {}
        if item and item.get('issue'):
            configured_review = item.get('independent_review_required', True)
            if not isinstance(configured_review, bool):
                raise DeliveryError('independent_review_required must be true or false when present.')
            goals = {int(item['issue']): {
                'authorized': True,
                'dependencies_satisfied': True,
                'review_required': configured_review,
            }}
        workers = self.handoff_workers
        if worker_factory:
            module, sep, name = worker_factory.partition(':')
            if not sep or not module.startswith('personal_agent.') or not name:
                raise DeliveryError('worker factory must be a personal_agent module:function reference.')
            factory = getattr(importlib.import_module(module), name, None)
            if not callable(factory): raise DeliveryError('worker factory is not callable.')
            configured = factory(role=role, root=self.root)
            if not callable(configured): raise DeliveryError('worker factory must return a bounded callable.')
            workers = {**workers, role: configured}
        github = self.handoff_github_factory(repository, authorized_goals=goals)
        return StateHandoffLoop(github, path, executor=workers.get('implementer'), reviewer=workers.get('reviewer'),
                                worker_id='delivery-cli').tick(role)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('status','run','reconcile','handoff','install-schedule','uninstall-schedule'))
    parser.add_argument('--once',action='store_true');parser.add_argument('--dry-run',action='store_true');parser.add_argument('--scheduled',action='store_true')
    parser.add_argument('--root',default=str(Path.cwd()));parser.add_argument('--state')
    parser.add_argument('--role',choices=('implementer','reviewer'))
    parser.add_argument('--worker-factory')
    args=parser.parse_args(argv);controller=DeliveryController(args.root,args.state)
    if args.command=='status':result=controller.status()
    elif args.command=='run':result=controller.run_once(args.dry_run,args.scheduled)
    elif args.command=='reconcile':result=controller.reconcile(args.dry_run)
    elif args.command=='handoff':
        if not args.role: parser.error('handoff requires --role implementer or reviewer')
        result=controller.handoff_tick(args.role,args.state,args.worker_factory)
    elif args.command=='install-schedule':result=controller.install_schedule()
    else:result=controller.uninstall_schedule()
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))


if __name__=='__main__':main()
