import tempfile
from pathlib import Path
import pytest
from personal_agent.connector_contract import (
    CONNECTOR_STATE_KEY,
    PENDING_WORK_KEY,
    ConnectorRegistry,
    ConnectorSpec,
    ConnectorState,
    PendingWorkRegistry,
)
from personal_agent.portable_state import export_owner_state,restore_owner_state
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore


def test_restore_refuses_nonempty_target_and_never_nests_state():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder); source=QuickStore(root/"source"); archive=export_owner_state(source.root,root/"owner.tar.gz")
        target=root/"target"; target.mkdir(); (target/"existing").write_text("preserve")
        with pytest.raises(ValueError,match="empty"):restore_owner_state(archive,target)
        assert (target/"existing").read_text()=="preserve"
        (target/"existing").unlink(); restore_owner_state(archive,target)
        assert (target/"private"/"quickstart.db").is_file(); assert not (target/"agentos-owner-state").exists()


def test_restore_quarantines_incomplete_jobs_without_replay_or_duplicate():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder); source=QuickStore(root/"source")
        queued=source.enqueue("queued work","restore-queued"); running=source.enqueue("running work","restore-running")
        with source.db() as db:db.execute("UPDATE jobs SET status='running',delivery='sending' WHERE id=?",(running,))
        connector=ConnectorSpec("google-gmail-read",("gmail.readonly",))
        registry=ConnectorRegistry(source,(connector,))
        registry.transition("owner-a",connector.connector_id,ConnectorState.CONNECTED,granted_scopes=connector.required_scopes)
        pending=PendingWorkRegistry(source,registry)
        pending.issue("owner-a","11111111-1111-4111-8111-111111111111",connector.connector_id,connector.required_scopes)
        claimed=pending.issue("owner-a","22222222-2222-4222-8222-222222222222",connector.connector_id,connector.required_scopes)
        pending.claim(claimed.token,"owner-a",connector.connector_id,connector.required_scopes,"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        completed=pending.issue("owner-a","33333333-3333-4333-8333-333333333333",connector.connector_id,connector.required_scopes)
        pending.claim(completed.token,"owner-a",connector.connector_id,connector.required_scopes,"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
        pending.complete(completed.token,"owner-a",connector.connector_id,"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
        source.put("durable_evidence",{"receipt":"preserved"})
        assert source.config(CONNECTOR_STATE_KEY); assert source.config(PENDING_WORK_KEY)
        restored=QuickStore(restore_owner_state(export_owner_state(source.root,root/"owner.tar.gz"),root/"restored"))
        assert restored.job(queued)["status"]=="interrupted"; assert restored.job(running)["status"]=="interrupted"
        assert restored.job(running)["delivery"]=="unknown"
        assert restored.config(CONNECTOR_STATE_KEY) is None; assert restored.config(PENDING_WORK_KEY) is None
        assert restored.config("durable_evidence")=={"receipt":"preserved"}
        assert restored.enqueue("queued work","restore-queued")==queued; assert AgentService(restored).run_one() is False


def test_portable_restore_excludes_engine_profile_and_selection():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder); source=QuickStore(root/"source"); source.put("subscription_engine",{"id":"codex"})
        profile=source.root.parent/"engine-profile"; profile.mkdir(); (profile/"auth.json").write_text("fixture-secret")
        restored_path=restore_owner_state(export_owner_state(source.root,root/"owner.tar.gz"),root/"restored")
        assert QuickStore(restored_path).config("subscription_engine") is None
        assert not (restored_path/"engine-profile").exists()
