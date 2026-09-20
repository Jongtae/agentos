import json
import threading
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from personal_agent.memory_service import MemoryService, MemoryServiceError
from personal_agent.portable_state import export_owner_state, restore_owner_state
from personal_agent.quickstart_store import QuickStore


class MemoryServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "state"
        self.store = QuickStore(self.root)
        self.now = [1000.0]
        self.service = MemoryService(self.store, now=lambda: self.now[0])

    def test_explicit_owner_write_is_canonical_but_model_write_is_only_candidate(self):
        saved = self.service.write(
            "owner-a", "work-a", "meeting-time", "morning",
            origin="owner", explicit_owner_request=True,
        )
        proposed = self.service.write(
            "owner-a", "work-a", "payment-destination", "attacker account",
            origin="model", explicit_owner_request=True,
        )
        unconfirmed = self.service.write(
            "owner-a", "work-a", "timezone", "UTC",
            origin="owner", explicit_owner_request=False,
        )
        self.assertEqual([row["id"] for row in self.store.memories("owner-a")], [saved["id"]])
        self.assertEqual(proposed["state"], "pending")
        self.assertEqual(unconfirmed["state"], "pending")

    def test_candidate_approval_is_exact_expiring_owner_work_bound_and_replay_safe(self):
        candidate = self.service.propose("owner-a", "work-a", "meeting-time", "afternoons")
        inspected = self.service.inspect_candidate("owner-a", "work-a", candidate["id"])
        approval = self.service.request_candidate_approval(
            "owner-a", "work-a", candidate["id"], inspected["content_digest"], ttl=10
        )
        for owner, work, digest in (
            ("owner-b", "work-a", inspected["content_digest"]),
            ("owner-a", "work-b", inspected["content_digest"]),
            ("owner-a", "work-a", "0" * 64),
        ):
            with self.assertRaises(ValueError):
                self.service.approve_candidate(owner, work, candidate["id"], digest, approval["approval_token"])
        accepted = self.service.approve_candidate(
            "owner-a", "work-a", candidate["id"], inspected["content_digest"], approval["approval_token"]
        )
        replayed = self.service.approve_candidate(
            "owner-a", "work-a", candidate["id"], inspected["content_digest"], approval["approval_token"]
        )
        self.assertEqual(replayed["id"], accepted["id"])
        self.assertEqual(len(self.store.memories("owner-a")), 1)
        self.assertEqual(self.service.inspect_candidate("owner-a", "work-a", candidate["id"])["state"], "accepted")

        expiring = self.service.propose("owner-a", "work-a", "timezone", "Asia/Seoul")
        expiring_approval = self.service.request_candidate_approval(
            "owner-a", "work-a", expiring["id"], expiring["content_digest"], ttl=1
        )
        self.now[0] = expiring_approval["expires_at"]
        with self.assertRaisesRegex(ValueError, "만료"):
            self.service.approve_candidate(
                "owner-a", "work-a", expiring["id"], expiring["content_digest"], expiring_approval["approval_token"]
            )
        self.assertEqual(self.service.inspect_candidate("owner-a", "work-a", expiring["id"])["state"], "pending")

    def test_correction_approval_is_rejected_at_exact_expiry(self):
        original = self.service.remember("owner-a", "work-a", "meeting-time", "morning")
        approval = self.service.request_correction(
            "owner-a", "work-a", original["id"], "meeting-time", "morning", "afternoons", ttl=1
        )
        self.now[0] = approval["expires_at"]
        with self.assertRaisesRegex(ValueError, "만료"):
            self.service.correct(
                "owner-a", "work-a", original["id"], "meeting-time", "morning", "afternoons", approval["approval_token"]
            )
        self.assertEqual(self.service.inspect_memory("owner-a", original["id"])["content"], "morning")

    def test_candidate_rejection_is_exact_and_never_creates_memory(self):
        candidate = self.service.propose("owner-a", "work-a", "food", "vegetarian")
        with self.assertRaises(ValueError):
            self.service.reject_candidate("owner-a", "wrong-work", candidate["id"], candidate["content_digest"])
        with self.assertRaises(ValueError):
            self.service.reject_candidate("owner-a", "work-a", candidate["id"], "f" * 64)
        rejected = self.service.reject_candidate(
            "owner-a", "work-a", candidate["id"], candidate["content_digest"]
        )
        replayed = self.service.reject_candidate(
            "owner-a", "work-a", candidate["id"], candidate["content_digest"]
        )
        self.assertEqual(rejected["state"], "rejected")
        self.assertEqual(replayed["state"], "rejected")
        self.assertEqual(self.store.memories("owner-a"), [])

    def test_correction_approval_cannot_be_reused_for_wrong_key_value_owner_or_work(self):
        original = self.service.remember("owner-a", "work-a", "meeting-time", "morning")
        approval = self.service.request_correction(
            "owner-a", "work-a", original["id"], "meeting-time", "morning", "afternoons", ttl=10
        )
        token = approval["approval_token"]
        attempts = (
            ("owner-b", "work-a", "meeting-time", "morning", "afternoons"),
            ("owner-a", "work-b", "meeting-time", "morning", "afternoons"),
            ("owner-a", "work-a", "timezone", "morning", "afternoons"),
            ("owner-a", "work-a", "meeting-time", "evening", "afternoons"),
            ("owner-a", "work-a", "meeting-time", "morning", "evenings"),
        )
        for owner, work, key, old, new in attempts:
            with self.assertRaises(ValueError):
                self.service.correct(owner, work, original["id"], key, old, new, token)
        corrected = self.service.correct(
            "owner-a", "work-a", original["id"], "meeting-time", "morning", "afternoons", token
        )
        replayed = self.service.correct(
            "owner-a", "work-a", original["id"], "meeting-time", "morning", "afternoons", token
        )
        self.assertEqual(corrected["id"], replayed["id"])
        self.assertEqual(corrected["supersedes"], original["id"])
        self.assertEqual(self.store.memories("owner-a")[0]["content"], "afternoons")

    def test_delete_targets_only_selected_canonical_memory(self):
        first = self.service.remember("owner-a", "work-a", "food", "vegetarian")
        second = self.service.remember("owner-a", "work-a", "timezone", "Asia/Seoul")
        with self.store.db() as db:
            db.execute("INSERT INTO notes VALUES (?,?,?)", (first["id"], "unrelated note", 1.0))
            db.execute("INSERT INTO workspaces VALUES (?,?,?,?,?,?)", ("workspace", "title", "", "active", 1.0, 1.0))
            db.execute("INSERT INTO workspace_results VALUES (?,?,?,?,?,?)", ("artifact", "workspace", "work-a", "result", "", 1.0))
        self.assertTrue(self.service.delete("owner-a", first["id"])["deleted"])
        self.assertEqual([row["id"] for row in self.store.memories("owner-a")], [second["id"]])
        self.assertEqual(self.store.notes()[0]["content"], "unrelated note")
        self.assertEqual(self.store.workspace("workspace")["id"], "workspace")

    def test_delete_removes_superseded_chain_candidate_copy_and_bound_approvals(self):
        candidate = self.service.propose("owner-a", "work-a", "food", "vegetarian")
        candidate_approval = self.service.request_candidate_approval(
            "owner-a", "work-a", candidate["id"], candidate["content_digest"]
        )
        accepted = self.service.approve_candidate(
            "owner-a", "work-a", candidate["id"], candidate["content_digest"], candidate_approval["approval_token"]
        )
        correction_approval = self.service.request_correction(
            "owner-a", "work-a", accepted["id"], "food", "vegetarian", "vegan"
        )
        corrected = self.service.correct(
            "owner-a", "work-a", accepted["id"], "food", "vegetarian", "vegan", correction_approval["approval_token"]
        )
        unrelated = self.service.remember("owner-a", "work-b", "timezone", "Asia/Seoul")
        pending = self.service.propose("owner-a", "work-b", "language", "Korean")

        deleted = self.service.delete("owner-a", corrected["id"])
        self.assertEqual(deleted["deleted_memory_count"], 2)
        self.assertEqual(deleted["deleted_candidate_count"], 1)
        self.assertEqual(deleted["deleted_approval_count"], 2)
        self.assertFalse(deleted["retained_private_copies"])
        with self.store.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM memories WHERE id IN (?,?)", (accepted["id"], corrected["id"])).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM memory_candidates WHERE id=?", (candidate["id"],)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM memory_approvals").fetchone()[0], 0)
        archive = export_owner_state(self.root, self.root / "deleted-owner.tar.gz")
        restored = QuickStore(restore_owner_state(archive, self.root.parent / "restored-delete"))
        with restored.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM memories WHERE id IN (?,?)", (accepted["id"], corrected["id"])).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM memory_candidates WHERE id=?", (candidate["id"],)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM memory_approvals").fetchone()[0], 0)
        self.assertEqual(self.service.inspect_memory("owner-a", unrelated["id"])["content"], "Asia/Seoul")
        self.assertEqual(self.service.inspect_candidate("owner-a", "work-b", pending["id"])["state"], "pending")

    def test_personal_space_delete_uses_chain_cleanup_and_preserves_notes(self):
        candidate = self.service.propose("owner-a", "work-a", "food", "vegetarian")
        candidate_approval = self.service.request_candidate_approval(
            "owner-a", "work-a", candidate["id"], candidate["content_digest"]
        )
        accepted = self.service.approve_candidate(
            "owner-a", "work-a", candidate["id"], candidate["content_digest"], candidate_approval["approval_token"]
        )
        correction_approval = self.service.request_correction(
            "owner-a", "work-a", accepted["id"], "food", "vegetarian", "vegan"
        )
        corrected = self.service.correct(
            "owner-a", "work-a", accepted["id"], "food", "vegetarian", "vegan", correction_approval["approval_token"]
        )
        unrelated = self.service.remember("owner-a", "work-b", "timezone", "Asia/Seoul")
        with self.store.db() as db:
            db.execute("INSERT INTO notes VALUES (?,?,?)", (corrected["id"], "unrelated note", 1.0))

        deleted = self.store.delete_personal_space_item("memories", corrected["id"])
        self.assertTrue(deleted["deleted"])
        self.assertEqual(deleted["kind"], "memories")
        self.assertEqual(deleted["deleted_memory_count"], 2)
        self.assertEqual(deleted["deleted_candidate_count"], 1)
        self.assertEqual(deleted["deleted_approval_count"], 2)
        with self.store.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM memories WHERE id IN (?,?)", (accepted["id"], corrected["id"])).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM memory_candidates WHERE id=?", (candidate["id"],)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM memory_approvals").fetchone()[0], 0)
        self.assertEqual(self.store.notes()[0]["content"], "unrelated note")
        self.assertEqual(self.service.inspect_memory("owner-a", unrelated["id"])["content"], "Asia/Seoul")

    def test_restart_preserves_accepted_state_without_promoting_pending(self):
        accepted = self.service.remember("owner-a", "work-a", "food", "vegetarian")
        pending = self.service.propose("owner-a", "work-a", "timezone", "Asia/Seoul")
        restarted = MemoryService(QuickStore(self.root), now=lambda: self.now[0])
        self.assertEqual(restarted.inspect_memory("owner-a", accepted["id"])["content"], "vegetarian")
        self.assertEqual(restarted.inspect_candidate("owner-a", "work-a", pending["id"])["state"], "pending")
        self.assertEqual(len(restarted.list_memories("owner-a")["memories"]), 1)

    def test_status_is_redacted_and_portable_restore_invalidates_live_approval(self):
        self.store.claim(self.store.bootstrap.read_text(), "a-long-test-password")
        self.service.remember("owner-a", "work-a", "private-key", "private value")
        candidate = self.service.propose("owner-a", "work-a", "secret-key", "secret candidate")
        approval = self.service.request_candidate_approval(
            "owner-a", "work-a", candidate["id"], candidate["content_digest"]
        )
        status = self.service.portable_status("owner-a")
        encoded = json.dumps(status)
        for private in ("owner-a", "work-a", "private-key", "private value", "secret-key", "secret candidate", approval["approval_token"]):
            self.assertNotIn(private, encoded)

        archive = export_owner_state(self.root, self.root / "owner.tar.gz")
        restored_store = QuickStore(restore_owner_state(archive, self.root.parent / "restored"))
        restored = MemoryService(restored_store, now=lambda: self.now[0])
        self.assertEqual(restored.inspect_candidate("owner-a", "work-a", candidate["id"])["state"], "pending")
        with self.assertRaises(ValueError):
            restored.approve_candidate(
                "owner-a", "work-a", candidate["id"], candidate["content_digest"], approval["approval_token"]
            )
        self.assertEqual(restored.inspect_candidate("owner-a", "work-a", candidate["id"])["state"], "pending")

    def test_status_counts_all_rows_beyond_paginated_owner_lists(self):
        for index in range(51):
            self.service.remember("owner-a", "work-a", f"memory-{index}", f"value-{index}")
            self.service.propose("owner-a", "work-a", f"candidate-{index}", f"proposal-{index}")
        self.assertEqual(len(self.service.list_memories("owner-a")["memories"]), 50)
        self.assertEqual(len(self.service.list_candidates("owner-a")["candidates"]), 50)
        status = self.service.status("owner-a")
        self.assertEqual(status["current_memory_count"], 51)
        self.assertEqual(status["candidate_counts"], {"pending": 51, "accepted": 0, "rejected": 0})

    def test_service_candidate_never_persists_raw_work_id_in_legacy_or_portable_state(self):
        self.store.claim(self.store.bootstrap.read_text(), "a-long-test-password")
        work_id = "private-work-label"
        candidate = self.service.propose("owner-a", work_id, "food", "vegetarian")
        with self.store.db() as db:
            row = db.execute("SELECT job_id,work_key FROM memory_candidates WHERE id=?", (candidate["id"],)).fetchone()
            self.assertIsNone(row["job_id"])
            self.assertNotEqual(row["work_key"], work_id)
            # Simulate the raw duplicate written by the reviewed pre-fix head.
            db.execute("UPDATE memory_candidates SET job_id=? WHERE id=?", (work_id, candidate["id"]))
        migrated_store = QuickStore(self.root)
        with migrated_store.db() as db:
            self.assertIsNone(db.execute("SELECT job_id FROM memory_candidates WHERE id=?", (candidate["id"],)).fetchone()["job_id"])
        archive = export_owner_state(self.root, self.root / "owner.tar.gz")
        restored_store = QuickStore(restore_owner_state(archive, self.root.parent / "restored-work"))
        with restored_store.db() as db:
            row = db.execute("SELECT job_id,work_key FROM memory_candidates WHERE id=?", (candidate["id"],)).fetchone()
            self.assertIsNone(row["job_id"])
            self.assertNotEqual(row["work_key"], work_id)

    def test_connections_secret_transaction_is_atomic_across_keys_and_store_instances(self):
        second_store = QuickStore(self.root)
        candidate = self.service.propose("owner-a", "work-a", "first", "one")
        barrier = threading.Barrier(2)
        original_write = QuickStore.write_private

        def coordinated_write(path, content):
            if Path(path) == self.store.secret_path:
                try:
                    barrier.wait(timeout=0.2)
                except threading.BrokenBarrierError:
                    pass
            return original_write(path, content)

        QuickStore.write_private = staticmethod(coordinated_write)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                approval_future = pool.submit(
                    self.service.request_candidate_approval, "owner-a", "work-a", candidate["id"], candidate["content_digest"]
                )
                credential_future = pool.submit(second_store.secret, "telegram_token", "telegram-secret")
                approval, credential = approval_future.result(), credential_future.result()
        finally:
            QuickStore.write_private = staticmethod(original_write)
        values = json.loads(self.store.secret_path.read_text())
        self.assertEqual(credential, "telegram-secret")
        self.assertEqual(values["telegram_token"], "telegram-secret")
        self.assertTrue(values["memory_exact_approval_secret"])
        accepted = self.service.approve_candidate(
            "owner-a", "work-a", candidate["id"], candidate["content_digest"], approval["approval_token"]
        )
        self.assertEqual(accepted["content"], "one")

    def test_legacy_memory_approval_secret_first_use_is_atomic_across_store_instances(self):
        second_store = QuickStore(self.root)
        first_job = self.store.enqueue("Remember morning meetings.", "legacy-approval-one")
        second_job = second_store.enqueue("Remember vegetarian food.", "legacy-approval-two")
        barrier = threading.Barrier(2)
        first_secret, second_secret = self.store.secret, second_store.secret

        def coordinated(original):
            def call(key, value=None, create=None):
                result = original(key, value, create)
                # This forces the reviewed separate-get/set implementation to
                # let both instances observe absence before either setter.
                if key == "memory_approval_secret" and value is None and create is None:
                    try:
                        barrier.wait(timeout=0.2)
                    except threading.BrokenBarrierError:
                        pass
                return result
            return call

        self.store.secret = coordinated(first_secret)
        second_store.secret = coordinated(second_secret)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first_future = pool.submit(
                    self.store.issue_memory_approval, first_job, "Remember morning meetings."
                )
                second_future = pool.submit(
                    second_store.issue_memory_approval, second_job, "Remember vegetarian food."
                )
                first_approval, second_approval = first_future.result(), second_future.result()
        finally:
            self.store.secret = first_secret
            second_store.secret = second_secret
        self.assertTrue(self.store.verify_memory_approval(first_approval, first_job))
        self.assertTrue(second_store.verify_memory_approval(second_approval, second_job))

    def test_private_rows_require_exact_owner_binding(self):
        memory = self.service.remember("owner-a", "work-a", "food", "vegetarian")
        candidate = self.service.propose("owner-a", "work-a", "timezone", "Asia/Seoul")
        with self.assertRaises(MemoryServiceError):
            self.service.inspect_memory("owner-b", memory["id"])
        with self.assertRaises(MemoryServiceError):
            self.service.inspect_candidate("owner-a", "work-b", candidate["id"])
        self.assertEqual(self.service.list_memories("owner-b")["memories"], [])
        self.assertEqual(self.service.list_candidates("owner-b")["candidates"], [])


if __name__ == "__main__":
    unittest.main()
