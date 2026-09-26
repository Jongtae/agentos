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

import re
import time
from datetime import datetime, timezone

#: SEC-PROFILE-01 (#658): owner profile facts (allergies, food preferences,
#: home/work places, preferred stores) are ordinary canonical Memory rows whose
#: key starts with this namespace.  Nothing here decides *what* is a profile
#: fact - the model (or the owner in Settings) chooses the key; deterministic
#: code validates only the key shape.
PROFILE_PREFIX = 'profile.'
#: ``profile.`` followed by one or more dot-separated, whitespace-free segments.
_PROFILE_KEY = re.compile(r'profile\.[^\s.]+(?:\.[^\s.]+)*')
#: Default byte-agnostic character budget for a prompt snapshot; one line per
#: current row, longest content clipped so one fact cannot crowd out the rest.
PROFILE_SNAPSHOT_CHARS = 1200
PROFILE_LINE_CHARS = 200
#: Hard cap on rows a snapshot will ever read, whatever the char budget.
_PROFILE_ROWS_CAP = 500
#: Tool-description text the runtime may append to ``save_memory`` so the
#: model lands profile facts under this namespace (wired by the runtime owner).
PROFILE_KEY_GUIDANCE = ('For a durable owner profile fact - an allergy, food preference, home/work '
                        'place or preferred store the owner states - use a memory_key that starts '
                        'with "profile." followed by dot-separated segments, for example '
                        'profile.allergy.peanut, profile.food_preference, profile.place.home, '
                        'profile.store.books. One current value per key; saving a key again '
                        'corrects it, so use a distinct key for each separate fact.')


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

    # -- owner profile facts (SEC-PROFILE-01 #658) ---------------------------
    #
    # A profile fact is a canonical Memory row like any other; the only thing
    # that makes it "profile" is its key namespace.  Writes from conversation
    # keep going through ``Capabilities.execute('save_memory')`` and its
    # explicit-request / MemoryCandidate rules; the owner's Settings surface
    # uses ``remember_profile`` (an explicit owner operation) and the runtime
    # reads ``profile_snapshot`` for the turn prompt.

    @staticmethod
    def is_profile_key(memory_key):
        """Shape check only: ``profile.`` plus dot-separated non-blank segments."""
        return isinstance(memory_key, str) and _PROFILE_KEY.fullmatch(memory_key.strip()) is not None

    @classmethod
    def profile_key(cls, memory_key):
        """The validated profile key, or a fail-closed error for an owner surface."""
        if not cls.is_profile_key(memory_key):
            raise MemoryServiceError(
                'profile memory key must be "profile." followed by dot-separated names, '
                'for example profile.allergy.peanut or profile.place.home'
            )
        return memory_key.strip()

    def remember_profile(self, owner_id, work_id, memory_key, content):
        """Explicit owner write of one profile fact; the same key supersedes."""
        return self.remember(owner_id, work_id, self.profile_key(memory_key), content)

    def _profile_rows(self, owner_id):
        """Every current ``profile.*`` row of this owner, ordered by key then value."""
        rows, offset = [], 0
        while len(rows) < _PROFILE_ROWS_CAP:
            page = self.store.memories(owner_id, limit=101, offset=offset, key_prefix=PROFILE_PREFIX)
            rows.extend(row for row in page if self.is_profile_key(row.get('memory_key')))
            if len(page) < 101:
                break
            offset += 101
        rows.sort(key=lambda row: (row['memory_key'], row['content']))
        return rows[:_PROFILE_ROWS_CAP]

    def profile_memories(self, owner_id):
        """The owner's current profile rows, ordered by key; a private read."""
        self._identity(owner_id, 'owner')
        rows = self._profile_rows(owner_id)
        return self._private_read('memory_service.profile_memories', {
            'state': 'current', 'memories': rows, 'memory_count': len(rows),
        }, len(rows))

    @staticmethod
    def _saved_date(created):
        try:
            return datetime.fromtimestamp(float(created), timezone.utc).date().isoformat()
        except (TypeError, ValueError, OverflowError, OSError):
            return 'unknown-date'

    def profile_snapshot(self, owner_id, *, limit_chars=PROFILE_SNAPSHOT_CHARS, line_chars=PROFILE_LINE_CHARS):
        """A bounded, attributable snapshot of ``profile.*`` rows for a turn prompt.

        ``text`` is one line per row - ``key: value (saved YYYY-MM-DD)`` - in
        key order, never longer than ``limit_chars``; a value longer than
        ``line_chars`` is clipped with a marker rather than dropped.  Rows
        that did not fit are counted in ``omitted_count`` so the caller can
        say the snapshot is partial instead of pretending it is complete.
        ``entries`` carries the same rows with their Memory ids and saved
        times, so every line in the prompt is attributable to one row.

        This is a private read like ``list_memories``: it arms the caller's
        turn-scoped egress sink unless the service was built with
        ``NO_EGRESS_GUARD``.
        """
        self._identity(owner_id, 'owner')
        if isinstance(limit_chars, bool) or not isinstance(limit_chars, int) or limit_chars < 1:
            raise MemoryServiceError('profile snapshot size is invalid')
        if isinstance(line_chars, bool) or not isinstance(line_chars, int) or line_chars < 8:
            raise MemoryServiceError('profile snapshot line size is invalid')
        rows = self._profile_rows(owner_id)
        lines, entries, used = [], [], 0
        for row in rows:
            content = ' '.join(str(row.get('content') or '').split())
            if len(content) > line_chars:
                content = content[:line_chars - 6] + ' [...]'
            line = f"{row['memory_key']}: {content} (saved {self._saved_date(row.get('created'))})"
            size = len(line) + (1 if lines else 0)
            if used + size > limit_chars:
                break
            used += size
            lines.append(line)
            entries.append({'id': row['id'], 'memory_key': row['memory_key'], 'content': row['content'],
                            'created': row.get('created')})
        omitted = len(rows) - len(entries)
        return self._private_read('memory_service.profile_snapshot', {
            'state': 'current', 'text': '\n'.join(lines), 'entries': entries,
            'total_count': len(rows), 'omitted_count': omitted, 'truncated': omitted > 0,
            'limit_chars': limit_chars,
        }, len(entries))

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
