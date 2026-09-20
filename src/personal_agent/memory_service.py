"""Owner-authoritative Memory and MemoryCandidate policy for PA1.

The service deliberately uses :class:`QuickStore` as its only persistence
authority.  Model proposals enter the existing ``memory_candidates`` table;
only an explicit owner operation may write canonical Memory.
"""

from __future__ import annotations

import time


class MemoryServiceError(ValueError):
    """A fail-closed Memory lifecycle error safe for an owner surface."""


class MemoryService:
    """Bounded owner-facing operations over the existing QuickStore schema."""

    def __init__(self, store, now=time.time):
        self.store, self.now = store, now

    @staticmethod
    def _identity(value, label):
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise MemoryServiceError(f"{label} identification is invalid")
        return value

    def _request(self, owner_id, work_id):
        return self._identity(owner_id, "owner"), self._identity(work_id, "work")

    def remember(self, owner_id, work_id, memory_key, content):
        """Persist one fact only through this explicit owner operation."""
        owner_id, work_id = self._request(owner_id, work_id)
        return self.store.save_memory(memory_key, content, owner_id=owner_id, work_id=work_id)

    def write(self, owner_id, work_id, memory_key, content, *, origin, explicit_owner_request=False):
        """Route non-owner output to a candidate rather than canonical Memory."""
        owner_id, work_id = self._request(owner_id, work_id)
        if origin == "owner" and explicit_owner_request is True:
            return self.remember(owner_id, work_id, memory_key, content)
        if origin not in ("owner", "model") or explicit_owner_request not in (False, True):
            raise MemoryServiceError("memory origin is invalid")
        return self.propose(owner_id, work_id, memory_key, content)

    def propose(self, owner_id, work_id, memory_key, content):
        """Store model-originated text only as pending owner review."""
        owner_id, work_id = self._request(owner_id, work_id)
        return self.store.save_memory_candidate(
            None, memory_key, content, owner_id=owner_id, work_id=work_id
        )

    @staticmethod
    def _page(limit, offset):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise MemoryServiceError("memory page size is invalid")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise MemoryServiceError("memory page offset is invalid")
        return limit, offset

    def list_memories(self, owner_id, *, limit=50, offset=0):
        self._identity(owner_id, "owner")
        limit, offset = self._page(limit, offset)
        rows = self.store.memories(owner_id, limit=limit + 1, offset=offset)
        return {"state": "current", "memories": rows[:limit],
                "next_offset": offset + limit if len(rows) > limit else None}

    def inspect_memory(self, owner_id, memory_id):
        self._identity(owner_id, "owner")
        row = self.store.memory(memory_id, owner_id)
        if not row:
            raise MemoryServiceError("memory not found")
        return row

    def list_candidates(self, owner_id, work_id=None, *, limit=50, offset=0):
        self._identity(owner_id, "owner")
        if work_id is not None:
            self._identity(work_id, "work")
        limit, offset = self._page(limit, offset)
        rows = self.store.memory_candidates(owner_id, work_id, limit=limit + 1, offset=offset)
        return {"state": "pending", "candidates": rows[:limit],
                "next_offset": offset + limit if len(rows) > limit else None}

    def inspect_candidate(self, owner_id, work_id, candidate_id):
        owner_id, work_id = self._request(owner_id, work_id)
        row = self.store.memory_candidate(candidate_id, owner_id, work_id)
        if not row:
            raise MemoryServiceError("memory candidate not found")
        return row

    def request_candidate_approval(self, owner_id, work_id, candidate_id, content_digest, ttl=600):
        """Issue a short-lived approval for the exact inspected candidate."""
        row = self.inspect_candidate(owner_id, work_id, candidate_id)
        if row["state"] != "pending" or row["content_digest"] != content_digest:
            raise MemoryServiceError("memory candidate changed or was already decided")
        return self.store.issue_exact_memory_approval(
            owner_id, work_id, "accept-candidate", candidate_id, row["memory_key"],
            content_digest, content_digest, ttl=ttl, now=self.now()
        )

    def approve_candidate(self, owner_id, work_id, candidate_id, content_digest, approval_token):
        owner_id, work_id = self._request(owner_id, work_id)
        return self.store.accept_memory_candidate(
            owner_id, work_id, candidate_id, content_digest, approval_token, now=self.now()
        )

    def reject_candidate(self, owner_id, work_id, candidate_id, content_digest):
        owner_id, work_id = self._request(owner_id, work_id)
        return self.store.reject_memory_candidate(
            owner_id, work_id, candidate_id, content_digest, now=self.now()
        )

    def request_correction(self, owner_id, work_id, memory_id, memory_key,
                           current_content, replacement_content, ttl=600):
        """Bind correction approval to owner, Work, key, old value, and new value."""
        owner_id, work_id = self._request(owner_id, work_id)
        row = self.inspect_memory(owner_id, memory_id)
        current_digest = self.store.memory_digest(memory_key, current_content)
        replacement_digest = self.store.memory_digest(memory_key, replacement_content)
        if row["memory_key"] != memory_key or row["content_digest"] != current_digest:
            raise MemoryServiceError("memory key or current value changed")
        return self.store.issue_exact_memory_approval(
            owner_id, work_id, "correct-memory", memory_id, memory_key,
            current_digest, replacement_digest, ttl=ttl, now=self.now()
        )

    def correct(self, owner_id, work_id, memory_id, memory_key, current_content,
                replacement_content, approval_token):
        owner_id, work_id = self._request(owner_id, work_id)
        current_digest = self.store.memory_digest(memory_key, current_content)
        return self.store.correct_memory(
            owner_id, work_id, memory_id, memory_key, current_digest,
            replacement_content, approval_token, now=self.now()
        )

    def delete(self, owner_id, memory_id):
        self._identity(owner_id, "owner")
        return self.store.delete_memory(owner_id, memory_id)

    def status(self, owner_id):
        """Return counts only; status never carries private Memory content."""
        self._identity(owner_id, "owner")
        counts = self.store.memory_status_counts(owner_id)
        return {
            "state": "ready",
            **counts,
            "private_content_included": False,
        }

    def portable_status(self, owner_id):
        """Redacted export/restore evidence; no token, owner, Work, key, or content."""
        return {
            **self.status(owner_id),
            "accepted_state": "portable",
            "pending_candidate_state": "pending",
            "approval_state": "requires_fresh_owner_review_after_restore",
        }
