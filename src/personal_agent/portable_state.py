"""Portable, secret-free owner-state export and restore."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tarfile
import tempfile
import os

from .manifests import validate

FORMAT = "agentos-owner-state-v1"
ROOT = "agentos-owner-state"
DB_RELATIVE = "private/quickstart.db"
_RESET_CONFIG = ("telegram", "telegram_status", "model", "model_test", "model_draft_test", "subscription_engine", "document_sharing", "tool_run", "file_roots", "file_workspace", "file_workspace_document_jobs", "capability_registry", "connector_contract_state", "connector_pending_work")

def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()

def _portable_db(source, target):
    """Snapshot SQLite then remove data which can authenticate or target a host."""
    with sqlite3.connect(source) as original, sqlite3.connect(target) as copy:
        original.backup(copy)
        tables = {row[0] for row in copy.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"auth", "sessions", "config"} <= tables: raise ValueError("AgentOS owner database has an unsupported schema.")
        copy.execute("DELETE FROM auth");copy.execute("DELETE FROM sessions")
        # #570: developer-mode provenance is owner-local diagnostics, not portable state.
        if 'turn_provenance' in tables:copy.execute("DELETE FROM turn_provenance")
        copy.executemany("DELETE FROM config WHERE key=?", ((key,) for key in _RESET_CONFIG))
        # Grants and result paths are valid only in the original runtime. Keep
        # durable result IDs/provenance as owner work evidence, but detach each
        # path so a restored runtime must reconnect folders before it can read
        # or write anything at the old location.
        if "file_workspace_results" in tables:
            copy.execute("UPDATE file_workspace_results SET path=NULL, workspace_id=NULL, state='detached'")
        # A portable restore is a new runtime boundary. Work which had not
        # reached a terminal state before export must require a new owner
        # request after restore; preserving it as queued/running would replay
        # an external action when the restored service starts.
        if "jobs" in tables:
            copy.execute("""UPDATE jobs
                            SET status='interrupted',
                                error='Restored work was quarantined; submit a new request to retry.',
                                delivery=CASE WHEN delivery IN ('sending','pending') THEN 'unknown' ELSE delivery END
                            WHERE status IN ('queued','running')""")
        if "memory_approvals" in tables:
            # Approval tokens are runtime-secret-bound and cannot survive a
            # portable boundary. Quarantine every outstanding row, and remove
            # the raw owner memory label from *all* approval rows: a consumed
            # or expired row keeps no useful function after restore, while its
            # memory_key is a plaintext owner label.
            copy.execute("UPDATE memory_approvals SET state='revoked' WHERE state='issued'")
            copy.execute("UPDATE memory_approvals SET memory_key=''")
        row = copy.execute("SELECT value FROM config WHERE key='a2a_delegations'").fetchone()
        if row:
            try: delegations = json.loads(row[0])
            except ValueError: delegations = {}
            if isinstance(delegations, dict):
                safe = {ident: {key: item[key] for key in ('id','state','peer','skill','created_at','updated_at','error') if key in item}
                        for ident, item in delegations.items() if isinstance(item, dict)}
                copy.execute("UPDATE config SET value=? WHERE key='a2a_delegations'", (json.dumps(safe, sort_keys=True),))
        row = copy.execute("SELECT value FROM config WHERE key='calendar_create'").fetchone()
        if row:
            try: drafts = json.loads(row[0])
            except ValueError: drafts = {}
            if isinstance(drafts, dict):
                # Approval IDs, event contents, owners, and idempotency material
                # never leave the owner runtime.  Keep only recovery-safe state.
                safe = {}
                for ident, item in drafts.items():
                    if not isinstance(item, dict):
                        continue
                    record = {key: item[key] for key in ('id', 'state', 'hash', 'error_class', 'action', 'recovery') if key in item}
                    if isinstance(item.get('result'), dict) and isinstance(item['result'].get('id'), str):
                        record['result'] = {'id': item['result']['id']}
                    safe[ident] = record
                copy.execute("UPDATE config SET value=? WHERE key='calendar_create'", (json.dumps(safe, sort_keys=True),))
        # Selected Drive content and approvals are owner-local, one-use context.
        copy.execute("DELETE FROM config WHERE key='drive_excerpt_approvals'")
        # Settings previews carry owner/channel binding and confirmation
        # material. Restores preserve only terminal, redacted audit evidence.
        copy.execute("DELETE FROM config WHERE key='settings_change_drafts'")
        row = copy.execute("SELECT value FROM config WHERE key='settings_audit'").fetchone()
        if row:
            try: audit = json.loads(row[0])
            except ValueError: audit = []
            if isinstance(audit, list):
                safe = [{key: item[key] for key in ('at','draft_ref','target','before','after','terminal','error_class') if key in item}
                        for item in audit if isinstance(item, dict)]
                copy.execute("UPDATE config SET value=? WHERE key='settings_audit'", (json.dumps(safe, sort_keys=True),))
        row = copy.execute("SELECT value FROM config WHERE key='personal_knowledge_audit'").fetchone()
        if row:
            try: audit = json.loads(row[0])
            except ValueError: audit = []
            if isinstance(audit, list):
                safe = [{key: item[key] for key in ('at','categories','terminal','error_class','recovery') if key in item}
                        for item in audit if isinstance(item, dict)]
                copy.execute("UPDATE config SET value=? WHERE key='personal_knowledge_audit'", (json.dumps(safe, sort_keys=True),))
        copy.commit();copy.execute("VACUUM")

def export_owner_state(data, archive):
    data, archive = Path(data).expanduser().resolve(), Path(archive).expanduser().resolve()
    database = data / DB_RELATIVE
    if not database.is_file(): raise ValueError("AgentOS owner database does not exist.")
    archive = archive if archive.name.endswith(".tar.gz") else archive.with_name(archive.name + ".tar.gz")
    with tempfile.TemporaryDirectory() as temporary:
        staging = Path(temporary) / ROOT;(staging / "private").mkdir(parents=True, mode=0o700)
        portable_db = staging / DB_RELATIVE;_portable_db(database, portable_db);portable_db.chmod(0o600)
        files = {DB_RELATIVE: _sha256(portable_db)}
        plugins = data / "plugins"
        if plugins.is_dir():
            for source in sorted(plugins.glob("*.json")):
                validate(json.loads(source.read_text()))
                relative = "plugins/" + source.name;target = staging / relative;target.parent.mkdir(mode=0o700, exist_ok=True)
                shutil.copyfile(source, target);target.chmod(0o600);files[relative] = _sha256(target)
        manifest = {"format": FORMAT, "files": files, "connections_included": False,
                    "restore_notice": "Claim this runtime and reconnect engines, Telegram, models, and local folders."}
        (staging / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
        archive.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "w:gz") as bundle:
            for path in sorted(staging.rglob("*")): bundle.add(path, arcname=str(Path(ROOT) / path.relative_to(staging)), recursive=False)
    return archive

def _safe_members(bundle):
    members = bundle.getmembers()
    for member in members:
        path = Path(member.name)
        if member.issym() or member.islnk() or path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != ROOT: raise ValueError("Unsafe owner-state archive.")
    return members

def restore_owner_state(archive, data):
    archive, data = Path(archive).expanduser().resolve(), Path(data).expanduser().resolve()
    if not archive.is_file(): raise ValueError("Owner-state archive does not exist.")
    if data.exists() and any(data.iterdir()): raise ValueError("Restore target must be empty.")
    # Stage on the target filesystem so the final rename is atomic. Validation
    # finishes before the empty destination is touched, preventing a malformed
    # archive or copy failure from leaving a partly restored runtime.
    data.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as bundle, tempfile.TemporaryDirectory(
            dir=data.parent, prefix=".agentos-restore-") as temporary:
        bundle.extractall(temporary, members=_safe_members(bundle), filter="data");staged = Path(temporary) / ROOT
        try: manifest = json.loads((staged / "manifest.json").read_text())
        except (OSError, ValueError) as exc: raise ValueError("Invalid owner-state archive.") from exc
        files = manifest.get("files") if isinstance(manifest, dict) else None
        if manifest.get("format") != FORMAT or not isinstance(files, dict) or DB_RELATIVE not in files: raise ValueError("Unsupported owner-state archive.")
        expected = set(files) | {"manifest.json"};actual = {str(path.relative_to(staged)) for path in staged.rglob("*") if path.is_file()}
        if actual != expected or any(not isinstance(name, str) or not isinstance(digest, str) for name, digest in files.items()): raise ValueError("Invalid owner-state archive contents.")
        for name, digest in files.items():
            path = staged / name
            if Path(name).is_absolute() or ".." in Path(name).parts or _sha256(path) != digest: raise ValueError("Owner-state archive integrity check failed.")
            if name.startswith("plugins/"): validate(json.loads(path.read_text()))
        with sqlite3.connect(staged / DB_RELATIVE) as db:
            if not db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config'").fetchone(): raise ValueError("Invalid owner-state database.")
        if data.exists():
            # rmdir is deliberately race-safe: if anything appeared after the
            # initial emptiness check, restoration refuses instead of merging.
            try: data.rmdir()
            except OSError as exc: raise ValueError("Restore target must remain empty.") from exc
        os.replace(staged, data)
    (data / "private").chmod(0o700);(data / DB_RELATIVE).chmod(0o600)
    return data
