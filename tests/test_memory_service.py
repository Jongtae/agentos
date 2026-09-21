import json
import secrets
import sqlite3
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
        self.service = MemoryService(self.store, now=lambda: self.now[0],
                                     private_read_sink=MemoryService.NO_EGRESS_GUARD)

    def _insert_unrelated_owner_approval(self, owner_id, work_id, subject_id, memory_key, digest, ttl=600):
        """Insert an unrelated owner's issued approval row directly.

        No production issuer can mint this row: both real issuers validate that
        the subject belongs to the requesting owner and Work inside the same
        transaction. The row exists only so a test can prove that owner-a's
        lifecycle never revokes, rewrites or deletes another owner's approval.
        """
        token = secrets.token_urlsafe(32)
        with self.store.db() as db:
            db.execute(
                """INSERT INTO memory_approvals
                   (token_hash,owner_key,work_key,action,subject_id,memory_key,source_digest,
                    content_digest,created,expires,state,result_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,'issued',NULL)""",
                (self.store._exact_memory_token_hash(token), self.store._memory_binding(owner_id),
                 self.store._work_binding(work_id), "accept-candidate", subject_id, memory_key,
                 digest, digest, self.now[0], self.now[0] + ttl),
            )
        return token
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
        sibling = self.service.request_candidate_approval(
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
        with self.store.db() as db:
            sibling_row = db.execute(
                "SELECT state,memory_key FROM memory_approvals WHERE token_hash=?",
                (self.store._exact_memory_token_hash(sibling["approval_token"]),),
            ).fetchone()
        self.assertEqual((sibling_row["state"], sibling_row["memory_key"]), ("revoked", ""))
        with self.assertRaises(ValueError):
            self.service.approve_candidate(
                "owner-a", "work-a", candidate["id"], inspected["content_digest"], sibling["approval_token"]
            )

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
        with self.store.db() as db:
            self.assertEqual(db.execute("SELECT state FROM memory_approvals WHERE expires=?", (expiring_approval["expires_at"],)).fetchone()["state"], "expired")

    def test_candidate_approval_is_revoked_if_canonical_memory_changes_after_issue(self):
        candidate = self.service.propose("owner-a", "work-a", "meeting-time", "candidate value")
        approval = self.service.request_candidate_approval(
            "owner-a", "work-a", candidate["id"], candidate["content_digest"]
        )
        owner_value = self.service.remember("owner-a", "work-owner", "meeting-time", "owner value")

        # A revoked token reports the same generic failure as any unusable
        # token: distinguishing revocation would leak the binding a holder
        # guessed. The owner surface re-reads state, asserted below.
        with self.assertRaisesRegex(ValueError, "정확한 승인이 필요합니다"):
            self.service.approve_candidate(
                "owner-a", "work-a", candidate["id"], candidate["content_digest"], approval["approval_token"]
            )

        self.assertEqual(self.service.inspect_memory("owner-a", owner_value["id"])["state"], "current")
        self.assertEqual(self.service.inspect_candidate("owner-a", "work-a", candidate["id"])["state"], "pending")
        with self.store.db() as db:
            row = db.execute(
                "SELECT state,memory_key FROM memory_approvals WHERE token_hash=?",
                (self.store._exact_memory_token_hash(approval["approval_token"]),),
            ).fetchone()
        self.assertEqual((row["state"], row["memory_key"]), ("revoked", ""))

    def test_candidate_approval_does_not_survive_an_absent_present_absent_sequence(self):
        """Comparing only the final row state cannot see the owner's changes."""
        candidate = self.service.propose("owner-a", "work-a", "meeting-time", "afternoon")
        approval = self.service.request_candidate_approval(
            "owner-a", "work-a", candidate["id"], candidate["content_digest"]
        )
        # The key was absent when the approval was issued. The owner then makes
        # and withdraws an explicit choice, returning the key to absent.
        written = self.service.remember("owner-a", "work-owner", "meeting-time", "evening")
        self.store.delete_memory("owner-a", written["id"])
        with self.assertRaisesRegex(ValueError, "정확한 승인이 필요합니다"):
            self.service.approve_candidate(
                "owner-a", "work-a", candidate["id"], candidate["content_digest"],
                approval["approval_token"],
            )
        self.assertEqual(
            [row for row in self.service.list_memories("owner-a")["memories"]
             if row["memory_key"] == "meeting-time"],
            [],
        )
        self.assertEqual(self.service.inspect_candidate("owner-a", "work-a", candidate["id"])["state"], "pending")
        with self.store.db() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM memory_approvals WHERE state='issued'").fetchone()[0], 0)

    def test_expected_state_binding_still_refuses_if_revocation_is_bypassed(self):
        """The second mechanism must hold on its own.

        Owner writes revoke approvals issued against the same key, so the
        expected-memory comparison is normally never reached. Re-arm the
        revoked row to simulate a regression in that first mechanism and prove
        the canonical-state binding independently refuses the stale approval.
        """
        candidate = self.service.propose("owner-a", "work-a", "meeting-time", "candidate value")
        approval = self.service.request_candidate_approval(
            "owner-a", "work-a", candidate["id"], candidate["content_digest"]
        )
        token_hash = self.store._exact_memory_token_hash(approval["approval_token"])
        owner_value = self.service.remember("owner-a", "work-owner", "meeting-time", "owner value")
        with self.store.db() as db:
            db.execute("UPDATE memory_approvals SET state='issued',memory_key='meeting-time' WHERE token_hash=?",
                       (token_hash,))

        with self.assertRaisesRegex(ValueError, "변경"):
            self.service.approve_candidate(
                "owner-a", "work-a", candidate["id"], candidate["content_digest"], approval["approval_token"]
            )

        self.assertEqual(self.service.inspect_candidate("owner-a", "work-a", candidate["id"])["state"], "pending")
        self.assertEqual(self.service.inspect_memory("owner-a", owner_value["id"])["content"], "owner value")
        with self.store.db() as db:
            row = db.execute("SELECT state,memory_key FROM memory_approvals WHERE token_hash=?",
                             (token_hash,)).fetchone()
        self.assertEqual((row["state"], row["memory_key"]), ("revoked", ""))

    def test_candidate_approval_is_bound_to_existing_memory_but_not_unrelated_keys(self):
        original = self.service.remember("owner-a", "work-owner", "meeting-time", "morning")
        stale_candidate = self.service.propose("owner-a", "work-a", "meeting-time", "afternoon")
        stale_approval = self.service.request_candidate_approval(
            "owner-a", "work-a", stale_candidate["id"], stale_candidate["content_digest"]
        )
        self.service.remember("owner-a", "work-owner", "meeting-time", "evening")
        with self.assertRaisesRegex(ValueError, "정확한 승인이 필요합니다"):
            self.service.approve_candidate(
                "owner-a", "work-a", stale_candidate["id"], stale_candidate["content_digest"],
                stale_approval["approval_token"],
            )
        self.assertEqual(self.store.memory(original["id"], "owner-a", current_only=False)["state"], "superseded")

        valid_candidate = self.service.propose("owner-a", "work-a", "timezone", "Asia/Seoul")
        valid_approval = self.service.request_candidate_approval(
            "owner-a", "work-a", valid_candidate["id"], valid_candidate["content_digest"]
        )
        self.service.remember("owner-a", "work-owner", "language", "Korean")
        accepted = self.service.approve_candidate(
            "owner-a", "work-a", valid_candidate["id"], valid_candidate["content_digest"],
            valid_approval["approval_token"],
        )
        self.assertEqual(accepted["content"], "Asia/Seoul")

    def test_existing_approval_table_is_migrated_for_canonical_state_binding(self):
        legacy_root = Path(self.temp.name) / "legacy-state"
        legacy_private = legacy_root / "private"
        legacy_private.mkdir(parents=True)
        with sqlite3.connect(legacy_private / "quickstart.db") as db:
            db.execute("""CREATE TABLE memory_approvals(
                token_hash TEXT PRIMARY KEY, owner_key TEXT NOT NULL, work_key TEXT NOT NULL,
                action TEXT NOT NULL, subject_id TEXT NOT NULL, memory_key TEXT NOT NULL,
                source_digest TEXT NOT NULL, content_digest TEXT NOT NULL, created REAL NOT NULL,
                expires REAL NOT NULL, state TEXT NOT NULL DEFAULT 'issued', result_id TEXT)""")

        migrated = QuickStore(legacy_root)
        with migrated.db() as db:
            columns = {row["name"] for row in db.execute("PRAGMA table_info(memory_approvals)")}
        self.assertTrue({"expected_memory_id", "expected_memory_digest"} <= columns)

    def test_owner_wide_candidate_page_returns_actionable_opaque_work_reference(self):
        candidate = self.service.propose("owner-a", "private-work-name", "timezone", "Asia/Seoul")
        row = self.service.list_candidates("owner-a")["candidates"][0]
        self.assertEqual(row["id"], candidate["id"])
        self.assertRegex(row["work_ref"], r"^workref:[0-9a-f]{64}$")
        self.assertNotIn("private-work-name", json.dumps(row))
        inspected = self.service.inspect_candidate("owner-a", row["work_ref"], row["id"])
        approval = self.service.request_candidate_approval(
            "owner-a", row["work_ref"], row["id"], inspected["content_digest"]
        )
        accepted = self.service.approve_candidate(
            "owner-a", row["work_ref"], row["id"], inspected["content_digest"], approval["approval_token"]
        )
        self.assertEqual(accepted["content"], "Asia/Seoul")

    def _issued_approval_count(self, subject_id):
        with self.store.db() as db:
            return db.execute(
                "SELECT COUNT(*) FROM memory_approvals WHERE owner_key=? AND subject_id=? AND state='issued'",
                (self.store._memory_binding("owner-a"), subject_id),
            ).fetchone()[0]

    def _decide_inside_issue_window(self, decide):
        """Run `decide` in the issuer's last pre-transaction instant.

        The issuing paths hash the approval token before opening their
        BEGIN IMMEDIATE transaction, so patching the hash is a deterministic
        hook for the exact window a barrier race could only hit by luck: the
        competing decision commits first, and the issuer must then observe it
        inside its own transaction.
        """
        original = self.store._exact_memory_token_hash
        state = {"fired": False}

        def hook(token):
            if not state["fired"]:
                state["fired"] = True
                decide()
            return original(token)

        self.store._exact_memory_token_hash = hook
        self.addCleanup(lambda: self.store.__dict__.pop("_exact_memory_token_hash", None))
        return state

    def test_candidate_approval_and_rejection_never_leave_an_issued_approval(self):
        """Both deterministic orderings, instead of a probabilistic barrier race."""
        # Ordering 1: the rejection commits inside the issuer's window.
        candidate = self.service.propose("owner-a", "work-a", "key-one", "value-one")
        window = self._decide_inside_issue_window(lambda: self.service.reject_candidate(
            "owner-a", "work-a", candidate["id"], candidate["content_digest"]))
        with self.assertRaises(MemoryServiceError):
            self.service.request_candidate_approval(
                "owner-a", "work-a", candidate["id"], candidate["content_digest"])
        self.assertTrue(window["fired"])
        self.assertEqual(self._issued_approval_count(candidate["id"]), 0)
        self.assertEqual(
            self.service.inspect_candidate("owner-a", "work-a", candidate["id"])["state"], "rejected")
        self.assertEqual(self.store.memories("owner-a"), [])

        # Ordering 2: the approval is issued first and the rejection must clear it.
        other = self.service.propose("owner-a", "work-b", "key-two", "value-two")
        self.service.request_candidate_approval(
            "owner-a", "work-b", other["id"], other["content_digest"])
        self.assertEqual(self._issued_approval_count(other["id"]), 1)
        self.service.reject_candidate("owner-a", "work-b", other["id"], other["content_digest"])
        self.assertEqual(self._issued_approval_count(other["id"]), 0)
        self.assertEqual(self.store.memories("owner-a"), [])

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

    def test_correction_consumption_revokes_siblings_and_owner_supersession(self):
        original = self.service.remember("owner-a", "work-a", "private-key", "before")
        first = self.service.request_correction(
            "owner-a", "work-a", original["id"], "private-key", "before", "after"
        )
        sibling = self.service.request_correction(
            "owner-a", "work-b", original["id"], "private-key", "before", "after"
        )
        self.service.correct(
            "owner-a", "work-a", original["id"], "private-key", "before", "after", first["approval_token"]
        )
        with self.store.db() as db:
            sibling_row = db.execute(
                "SELECT state,memory_key FROM memory_approvals WHERE token_hash=?",
                (self.store._exact_memory_token_hash(sibling["approval_token"]),),
            ).fetchone()
        self.assertEqual((sibling_row["state"], sibling_row["memory_key"]), ("revoked", ""))

        current = self.service.list_memories("owner-a")["memories"][0]
        superseded_approval = self.service.request_correction(
            "owner-a", "work-c", current["id"], "private-key", "after", "later"
        )
        self.service.remember("owner-a", "work-owner", "private-key", "owner replacement")
        with self.store.db() as db:
            superseded_row = db.execute(
                "SELECT state,memory_key FROM memory_approvals WHERE token_hash=?",
                (self.store._exact_memory_token_hash(superseded_approval["approval_token"]),),
            ).fetchone()
        self.assertEqual((superseded_row["state"], superseded_row["memory_key"]), ("revoked", ""))

    def test_correction_approval_and_delete_never_leave_an_orphan_approval(self):
        """Both deterministic orderings, instead of a probabilistic barrier race."""
        # Ordering 1: the delete commits inside the issuer's window.
        memory = self.service.remember("owner-a", "work-a", "key-one", "before")
        window = self._decide_inside_issue_window(lambda: self.service.delete("owner-a", memory["id"]))
        with self.assertRaises(MemoryServiceError):
            self.service.request_correction(
                "owner-a", "work-a", memory["id"], "key-one", "before", "after")
        self.assertTrue(window["fired"])
        self.assertEqual(self._issued_approval_count(memory["id"]), 0)
        self.assertEqual(self.store.memory(memory["id"], "owner-a", current_only=False), None)

        # Ordering 2: the approval is issued first and the delete must clear it.
        other = self.service.remember("owner-a", "work-b", "key-two", "before")
        approval = self.service.request_correction(
            "owner-a", "work-b", other["id"], "key-two", "before", "after")
        self.assertEqual(self._issued_approval_count(other["id"]), 1)
        self.service.delete("owner-a", other["id"])
        self.assertEqual(self._issued_approval_count(other["id"]), 0)
        with self.assertRaises(ValueError):
            self.service.correct("owner-a", "work-b", other["id"], "key-two", "before", "after",
                                 approval["approval_token"])
        self.assertEqual(self.store.memories("owner-a"), [])

    def test_candidate_rejection_is_exact_and_never_creates_memory(self):
        candidate = self.service.propose("owner-a", "work-a", "food", "vegetarian")
        self.service.request_candidate_approval(
            "owner-a", "work-a", candidate["id"], candidate["content_digest"]
        )
        self._insert_unrelated_owner_approval(
            "owner-b", "work-b", candidate["id"], "other-owner-key", candidate["content_digest"]
        )
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
        self.assertEqual(rejected["content"], "")
        self.assertEqual(rejected["memory_key"], "")
        with self.store.db() as db:
            stored = db.execute("SELECT memory_key,content FROM memory_candidates WHERE id=?", (candidate["id"],)).fetchone()
            approvals = db.execute("SELECT owner_key,memory_key FROM memory_approvals WHERE subject_id=?", (candidate["id"],)).fetchall()
        self.assertEqual((stored["memory_key"], stored["content"]), ("", ""))
        self.assertEqual([(row["owner_key"], row["memory_key"]) for row in approvals], [
            (self.store._memory_binding("owner-b"), "other-owner-key")
        ])
        archive = export_owner_state(self.root, self.root / "rejected-owner.tar.gz")
        restored = QuickStore(restore_owner_state(archive, self.root.parent / "restored-rejected"))
        with restored.db() as db:
            restored_candidate = db.execute("SELECT memory_key,content FROM memory_candidates WHERE id=?", (candidate["id"],)).fetchone()
            restored_approvals = db.execute("SELECT owner_key,memory_key,state FROM memory_approvals WHERE subject_id=?", (candidate["id"],)).fetchall()
        self.assertEqual((restored_candidate["memory_key"], restored_candidate["content"]), ("", ""))
        self.assertEqual([(row["owner_key"], row["memory_key"], row["state"]) for row in restored_approvals], [
            (self.store._memory_binding("owner-b"), "", "revoked")
        ])
        portable_bytes = (Path(restored.root) / "private" / "quickstart.db").read_bytes()
        self.assertNotIn(b"vegetarian", portable_bytes)
        self.assertNotIn(b"food", portable_bytes)
        self.assertEqual(self.store.memories("owner-a"), [])

    def test_personal_space_candidate_delete_atomically_revokes_issued_approval(self):
        candidate = self.service.propose("owner-a", "work-a", "private-key", "private candidate")
        self.service.request_candidate_approval(
            "owner-a", "work-a", candidate["id"], candidate["content_digest"]
        )
        self._insert_unrelated_owner_approval(
            "owner-b", "work-b", candidate["id"], candidate["memory_key"], candidate["content_digest"]
        )
        deleted = self.store.delete_personal_space_item("memory_candidates", candidate["id"])
        self.assertTrue(deleted["deleted"])
        self.assertEqual(deleted["deleted_approval_count"], 1)
        self.assertEqual(deleted["retained_private_copies"], "unknown_outside_store")
        self.assertFalse(deleted["external_archives_affected"])
        with self.store.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM memory_candidates WHERE id=?", (candidate["id"],)).fetchone()[0], 0)
            retained = db.execute("SELECT owner_key FROM memory_approvals WHERE subject_id=?", (candidate["id"],)).fetchall()
        self.assertEqual(len(retained), 1)
        self.assertEqual(retained[0]["owner_key"], self.store._memory_binding("owner-b"))

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
        self.assertEqual(deleted["retained_private_copies"], "unknown_outside_store")
        self.assertFalse(deleted["external_archives_affected"])
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
        restarted = MemoryService(QuickStore(self.root), now=lambda: self.now[0],
                                  private_read_sink=MemoryService.NO_EGRESS_GUARD)
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
        restored = MemoryService(restored_store, now=lambda: self.now[0],
                                 private_read_sink=MemoryService.NO_EGRESS_GUARD)
        self.assertEqual(restored.inspect_candidate("owner-a", "work-a", candidate["id"])["state"], "pending")
        with restored_store.db() as db:
            portable_approval = db.execute(
                "SELECT state,memory_key FROM memory_approvals WHERE subject_id=?",
                (candidate["id"],),
            ).fetchone()
        self.assertEqual((portable_approval["state"], portable_approval["memory_key"]), ("revoked", ""))
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
        memory_first = self.service.list_memories("owner-a", limit=50)
        memory_second = self.service.list_memories("owner-a", limit=50, offset=memory_first["next_offset"])
        candidate_first = self.service.list_candidates("owner-a", limit=50)
        candidate_second = self.service.list_candidates("owner-a", limit=50, offset=candidate_first["next_offset"])
        self.assertEqual(len({row["id"] for row in memory_first["memories"] + memory_second["memories"]}), 51)
        self.assertEqual(len({row["id"] for row in candidate_first["candidates"] + candidate_second["candidates"]}), 51)
        self.assertIsNone(memory_second["next_offset"])
        self.assertIsNone(candidate_second["next_offset"])
        with self.assertRaises(MemoryServiceError):
            self.service.list_memories("owner-a", limit=101)
        with self.assertRaises(MemoryServiceError):
            self.service.list_candidates("owner-a", offset=-1)
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

    def test_service_requires_an_explicit_same_turn_egress_decision(self):
        """A private read must arm the caller's egress guard or say it did not."""
        with self.assertRaises(TypeError):
            MemoryService(self.store)
        with self.assertRaises(MemoryServiceError):
            MemoryService(self.store, private_read_sink="not-a-sink")

        markers = []
        guarded = MemoryService(self.store, now=lambda: self.now[0], private_read_sink=markers.append)
        stored = self.service.remember("owner-a", "work-a", "private-key", "private value")
        candidate = self.service.propose("owner-a", "work-a", "candidate-key", "candidate value")

        listed = guarded.list_memories("owner-a")
        inspected = guarded.inspect_memory("owner-a", stored["id"])
        listed_candidates = guarded.list_candidates("owner-a")
        inspected_candidate = guarded.inspect_candidate("owner-a", "work-a", candidate["id"])
        for read in (listed, inspected, listed_candidates, inspected_candidate):
            self.assertTrue(read["private_content_included"])
            self.assertTrue(read["egress_guard_armed"])
        self.assertEqual(inspected["content"], "private value")
        self.assertEqual(len(markers), 4)

        # The marker arms the guard without copying private material into it.
        encoded = json.dumps(markers)
        for private in ("private-key", "private value", "candidate-key", "candidate value", "owner-a", "work-a"):
            self.assertNotIn(private, encoded)

        # Counts-only surfaces carry no private content and must not arm it.
        self.assertFalse(guarded.status("owner-a")["private_content_included"])
        guarded.portable_status("owner-a")
        self.assertEqual(len(markers), 4)

        # An explicit opt-out still reports, truthfully, that nothing was armed.
        self.assertFalse(self.service.list_memories("owner-a")["egress_guard_armed"])
        self.assertTrue(self.service.list_memories("owner-a")["private_content_included"])

    def test_write_rejects_an_unknown_origin_instead_of_defaulting(self):
        for origin in ("bogus", "", None, "OWNER"):
            with self.assertRaises(MemoryServiceError):
                self.service.write("owner-a", "work-a", "meeting-time", "morning",
                                   origin=origin, explicit_owner_request=True)
        with self.assertRaises(MemoryServiceError):
            self.service.write("owner-a", "work-a", "meeting-time", "morning",
                               origin="owner", explicit_owner_request="yes")
        self.assertEqual(self.store.memories("owner-a"), [])
        self.assertEqual(self.store.memory_candidates("owner-a"), [])

    def test_delete_fails_closed_rather_than_reporting_a_delete_of_nothing(self):
        """A UI must not be able to render a successful delete of no row."""
        first = self.service.remember("owner-a", "work-a", "food", "vegetarian")
        second = self.service.remember("owner-a", "work-a", "food", "vegan")

        with self.assertRaises(MemoryServiceError):
            self.service.delete("owner-a", "no-such-memory")
        with self.assertRaises(MemoryServiceError):
            self.service.delete("owner-a", first["id"])  # superseded, not current
        with self.assertRaises(MemoryServiceError):
            self.service.delete("owner-b", second["id"])  # another owner's row

        # The store keeps returning a truthful receipt for the same attempts.
        receipt = self.store.delete_memory("owner-a", first["id"])
        self.assertEqual((receipt["deleted"], receipt["deleted_memory_count"]), (False, 0))
        self.assertEqual(self.store.memory(first["id"], "owner-a", current_only=False)["state"], "superseded")
        self.assertEqual([row["id"] for row in self.store.memories("owner-a")], [second["id"]])
        self.assertTrue(self.service.delete("owner-a", second["id"])["deleted"])

    def test_personal_space_delete_of_a_superseded_row_preserves_chain_and_binding(self):
        first = self.service.remember("owner-a", "work-a", "food", "first")
        candidate = self.service.propose("owner-a", "work-a", "food", "second")
        candidate_approval = self.service.request_candidate_approval(
            "owner-a", "work-a", candidate["id"], candidate["content_digest"]
        )
        middle = self.service.approve_candidate(
            "owner-a", "work-a", candidate["id"], candidate["content_digest"],
            candidate_approval["approval_token"]
        )
        correction = self.service.request_correction(
            "owner-a", "work-a", middle["id"], "food", "second", "third"
        )
        head = self.service.remember("owner-a", "work-a", "food", "third")
        unrelated = self.service.remember("owner-b", "work-a", "food", "other owner value")
        with self.store.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM memory_approvals WHERE subject_id=?",
                                        (middle["id"],)).fetchone()[0], 1)

        deleted = self.store.delete_personal_space_item("memories", middle["id"])
        self.assertTrue(deleted["deleted"])
        self.assertEqual(deleted["deleted_memory_count"], 1)
        self.assertEqual(deleted["deleted_candidate_count"], 1)
        # The correction approval bound to the row plus the consumed candidate
        # approval whose result_id is the row.
        self.assertEqual(deleted["deleted_approval_count"], 2)
        self.assertEqual(deleted["retained_private_copies"], "unknown_outside_store")
        self.assertFalse(deleted["external_archives_affected"])
        with self.store.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM memories WHERE id=?", (middle["id"],)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM memory_candidates WHERE id=?", (candidate["id"],)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM memory_approvals WHERE subject_id=?", (middle["id"],)).fetchone()[0], 0)
            # The chain is spliced, not left dangling at the deleted row.
            self.assertEqual(db.execute("SELECT supersedes FROM memories WHERE id=?", (head["id"],)).fetchone()[0], first["id"])
        with self.assertRaises(ValueError):
            self.service.correct("owner-a", "work-a", middle["id"], "food", "second", "third",
                                 correction["approval_token"])

        # The remaining chain delete still reaches the spliced ancestor and
        # reports a truthful count.
        chain = self.service.delete("owner-a", head["id"])
        self.assertEqual(chain["deleted_memory_count"], 2)
        self.assertEqual(self.store.memories("owner-a"), [])
        self.assertEqual(self.service.inspect_memory("owner-b", unrelated["id"])["content"], "other owner value")

    def test_portable_export_redacts_the_memory_label_of_every_approval_row(self):
        candidate = self.service.propose("owner-a", "work-a", "consumed-key", "consumed value")
        approval = self.service.request_candidate_approval(
            "owner-a", "work-a", candidate["id"], candidate["content_digest"]
        )
        self.service.approve_candidate(
            "owner-a", "work-a", candidate["id"], candidate["content_digest"], approval["approval_token"]
        )
        expiring = self.service.propose("owner-a", "work-a", "expired-key", "expired value")
        expiring_approval = self.service.request_candidate_approval(
            "owner-a", "work-a", expiring["id"], expiring["content_digest"], ttl=1
        )
        self.now[0] = expiring_approval["expires_at"]
        with self.assertRaises(ValueError):
            self.service.approve_candidate(
                "owner-a", "work-a", expiring["id"], expiring["content_digest"],
                expiring_approval["approval_token"]
            )
        with self.store.db() as db:
            live = {row["state"]: row["memory_key"] for row in db.execute("SELECT state,memory_key FROM memory_approvals")}
        self.assertEqual(live, {"consumed": "consumed-key", "expired": "expired-key"})

        archive = export_owner_state(self.root, self.root / "approvals.tar.gz")
        restored = QuickStore(restore_owner_state(archive, self.root.parent / "restored-approvals"))
        with restored.db() as db:
            exported = sorted((row["state"], row["memory_key"]) for row in db.execute("SELECT state,memory_key FROM memory_approvals"))
        self.assertEqual(exported, [("consumed", ""), ("expired", "")])


if __name__ == "__main__":
    unittest.main()
