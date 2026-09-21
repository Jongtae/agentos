"""Owner-authoritative Memory and MemoryCandidate policy for PA1.

The service deliberately uses :class:`QuickStore` as its only persistence
authority.  Model proposals enter the existing ``memory_candidates`` table;
only an explicit owner operation may write canonical Memory.

Integration requirement for PA1-CONV-01 (#393) and PA1-INT-01 (#394)
--------------------------------------------------------------------
Reading Memory or a MemoryCandidate brings private owner content into the
current Work turn.  ``agent_runtime.Capabilities`` refuses same-turn public
egress (``web_search``, ``public_page_read``) while ``Capabilities.evidence``
or ``document_context`` is non-empty, and its own ``list_memory``/
``save_memory`` actions arm that guard by appending to ``evidence``.

``MemoryService`` is a *second*, independent read surface over the same private
rows.  A conversation layer that calls :meth:`list_memories`,
:meth:`inspect_memory`, :meth:`list_candidates` or :meth:`inspect_candidate`
instead of the ``list_memory`` capability would otherwise leave that guard
unarmed and silently re-open same-Work public egress with private Memory in
context.

Two mechanisms make that impossible to forget:

1. The constructor has no default for ``private_read_sink``.  A runtime
   integration must pass the turn-scoped marker sink, normally
   ``MemoryService(store, private_read_sink=capabilities.evidence.append)``.
   A surface that provably cannot perform public egress in the same turn (an
   offline CLI, an export job, a unit test) must opt out *explicitly* with
   ``private_read_sink=MemoryService.NO_EGRESS_GUARD``.
2. Every private read returns a :class:`PrivateMemoryRead`, which carries
   ``private_content_included`` and ``egress_guard_armed`` so a caller cannot
   drop the marker by accident and an integration test can assert on it.

The marker handed to the sink carries no memory key or content: only the
action, the fact that private content was read, and a row count.  Aggregate
:meth:`status` / :meth:`portable_status` return counts only and therefore do
not arm the guard.
"""

from __future__ import annotations

import time


class MemoryServiceError(ValueError):
    """A fail-closed Memory lifecycle error safe for an owner surface."""


class PrivateMemoryRead(dict):
    """A read result that carries private owner content into the caller's turn.

    Any surface that can also reach a public destination in the same Work turn
    must have armed its egress guard before using this value; see the module
    docstring.
    """

    __slots__ = ()

    def __init__(self, payload, *, egress_guard_armed):
        super().__init__(payload)
        self["private_content_included"] = True
        self["egress_guard_armed"] = bool(egress_guard_armed)

    @property
    def private_content_included(self):
        return True

    @property
    def egress_guard_armed(self):
        return bool(self.get("egress_guard_armed"))


class MemoryService:
    """Bounded owner-facing operations over the existing QuickStore schema."""

    #: Explicit opt-out for a surface that cannot perform same-turn public egress.
    NO_EGRESS_GUARD = "memory-service-no-egress-guard"

    def __init__(self, store, now=time.time, *, private_read_sink):
        if private_read_sink is not self.NO_EGRESS_GUARD and not callable(private_read_sink):
            raise MemoryServiceError(
                "MemoryService requires private_read_sink: pass the turn-scoped egress "
                "marker sink (for example capabilities.evidence.append), or "
                "MemoryService.NO_EGRESS_GUARD for a surface with no same-turn public egress"
            )
        self.store, self.now = store, now
        self.private_read_sink = private_read_sink

    @staticmethod
    def _identity(value, label):
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise MemoryServiceError(f"{label} identification is invalid")
        return value

    def _request(self, owner_id, work_id):
        return self._identity(owner_id, "owner"), self._identity(work_id, "work")

    def _private_read(self, action, payload, row_count):
        """Arm the caller's same-turn egress guard, then mark the result."""
        armed = False
        if self.private_read_sink is not self.NO_EGRESS_GUARD:
            self.private_read_sink({
                "tool": action,
                "result": {"private_content_included": True, "row_count": row_count},
            })
            armed = True
        return PrivateMemoryRead(payload, egress_guard_armed=armed)

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
        page = rows[:limit]
        return self._private_read("memory_service.list_memories", {
            "state": "current", "memories": page,
            "next_offset": offset + limit if len(rows) > limit else None,
        }, len(page))

    def inspect_memory(self, owner_id, memory_id):
        self._identity(owner_id, "owner")
        row = self.store.memory(memory_id, owner_id)
        if not row:
            raise MemoryServiceError("memory not found")
        return self._private_read("memory_service.inspect_memory", row, 1)

    def list_candidates(self, owner_id, work_id=None, *, limit=50, offset=0):
        self._identity(owner_id, "owner")
        if work_id is not None:
            self._identity(work_id, "work")
        limit, offset = self._page(limit, offset)
        rows = self.store.memory_candidates(owner_id, work_id, limit=limit + 1, offset=offset)
        page = rows[:limit]
        return self._private_read("memory_service.list_candidates", {
            "state": "pending", "candidates": page,
            "next_offset": offset + limit if len(rows) > limit else None,
        }, len(page))

    def inspect_candidate(self, owner_id, work_id, candidate_id):
        owner_id, work_id = self._request(owner_id, work_id)
        row = self.store.memory_candidate(candidate_id, owner_id, work_id)
        if not row:
            raise MemoryServiceError("memory candidate not found")
        return self._private_read("memory_service.inspect_candidate", row, 1)

    def request_candidate_approval(self, owner_id, work_id, candidate_id, content_digest, ttl=600):
        """Issue a short-lived approval for the exact inspected candidate."""
        owner_id, work_id = self._request(owner_id, work_id)
        try:
            return self.store.issue_candidate_memory_approval(
                owner_id, work_id, candidate_id, content_digest, ttl=ttl, now=self.now()
            )
        except ValueError:
            raise MemoryServiceError("memory candidate changed or was already decided") from None

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
        current_digest = self.store.memory_digest(memory_key, current_content)
        replacement_digest = self.store.memory_digest(memory_key, replacement_content)
        try:
            return self.store.issue_correction_memory_approval(
                owner_id, work_id, memory_id, memory_key, current_digest,
                replacement_digest, ttl=ttl, now=self.now()
            )
        except ValueError:
            raise MemoryServiceError("memory key or current value changed") from None

    def correct(self, owner_id, work_id, memory_id, memory_key, current_content,
                replacement_content, approval_token):
        owner_id, work_id = self._request(owner_id, work_id)
        current_digest = self.store.memory_digest(memory_key, current_content)
        return self.store.correct_memory(
            owner_id, work_id, memory_id, memory_key, current_digest,
            replacement_content, approval_token, now=self.now()
        )

    def delete(self, owner_id, memory_id):
        """Delete one canonical Memory chain.

        Fails closed rather than returning a silent ``deleted: False`` receipt:
        an owner surface must not be able to report a successful delete of a
        row that was never current (already deleted, superseded, another
        owner's, or unknown).
        """
        self._identity(owner_id, "owner")
        receipt = self.store.delete_memory(owner_id, memory_id)
        if not receipt.get("deleted"):
            raise MemoryServiceError("memory not found or is not the current value")
        return receipt

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
