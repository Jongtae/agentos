"""State-driven, one-shot GitHub handoff loop.

The loop is deliberately transport-agnostic.  A scheduler may call one tick,
but it cannot invent work: GitHub's single ``agent:*`` label is the queue and
the supplied executor/reviewer are the only code allowed to do work.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
import tempfile
import time
import subprocess

STATES = {"agent:ready", "agent:working", "agent:review", "agent:rework", "agent:approved", "agent:blocked"}


class HandoffError(RuntimeError):
    pass


@dataclass
class Issue:
    number: int
    labels: set[str]
    body: str = ""
    state: str = "OPEN"
    authorized: bool = False
    dependencies_satisfied: bool = False

    def queue_state(self):
        found = self.labels & STATES
        return next(iter(found)) if len(found) == 1 else None


@dataclass
class Candidate:
    issue: int
    pr: int
    head: str
    base: str
    ci: str
    draft: bool = False
    required_checks_known: bool = True
    evidence: str = ""

    def key(self):
        # This is the immutable identity which both the local executor and the
        # GitHub adapter can reconstruct.  CI and local evidence deliberately
        # are not part of it: CI changes while a run is pending and evidence is
        # not published in a receipt.
        return hashlib.sha256(json.dumps({
            "issue": self.issue, "pr": self.pr, "head": self.head, "base": self.base,
        }, sort_keys=True).encode()).hexdigest()[:20]


class HandoffState:
    """Small local state: receipt markers and a lease, never issue content."""
    def __init__(self, path):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(".lock")

    def locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.lock_path.open("a")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close(); raise HandoffError("A handoff tick is already running.")
        return handle

    def read(self):
        try:
            value = json.loads(self.path.read_text())
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def write(self, value):
        # Findings are compact, reviewer-authored receipt data.  Keep them so a
        # rework executor receives the same bounded defect set after a restart;
        # never persist issue bodies, comments, prompts, or source material.
        allowed = {k: value[k] for k in ("lease", "candidate", "feedback", "receipts", "pending") if k in value}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=self.path.parent, delete=False) as f:
            json.dump(allowed, f, sort_keys=True); f.write("\n"); name = f.name
        os.chmod(name, 0o600); os.replace(name, self.path)
        return allowed


class StateHandoffLoop:
    """One writer at a time; GitHub methods are a deliberately narrow boundary.

    Boundary methods: ``issues()``, ``transition(issue, old, new)``,
    ``comment(issue, marker, text)``, ``comment_exists(issue, marker)``,
    ``candidate(issue)``, and ``execution_active(issue, lease)``.
    Executors return a ``Candidate`` after creating/updating their real work;
    reviewers return a list of evidenced finding strings.
    """
    def __init__(self, github, state_path, executor=None, reviewer=None, worker_id="local", now=None, lease_seconds=900):
        self.github, self.state = github, HandoffState(state_path)
        self.executor, self.reviewer, self.worker_id = executor, reviewer, worker_id
        self.now, self.lease_seconds = now or time.time, lease_seconds

    @staticmethod
    def _eligible(issue):
        return (issue.state == "OPEN" and issue.queue_state() in {"agent:ready", "agent:rework"}
                and issue.authorized and issue.dependencies_satisfied)

    @staticmethod
    def _marker(role, issue, identity):
        return f"agentos-handoff:{role}:{issue}:{identity}"

    def _receipt(self, issue, old, new, role, identity, text, state, candidate=None):
        marker = self._marker(role, issue, identity)
        if marker in state.get("receipts", []):
            return {"action": "already-receipted", "issue": issue}
        pending = {"issue": issue, "old": old, "new": new, "marker": marker, "text": text}
        if candidate is not None:
            pending["candidate_key"] = candidate.key()
        state["pending"] = pending; self.state.write(state)
        return self._flush(state)

    def _flush(self, state):
        pending = state.get("pending")
        if not pending: return None
        marker = pending["marker"]
        if not self.github.comment_exists(pending["issue"], marker):
            try:
                self.github.comment(pending["issue"], marker, pending["text"])
            except TimeoutError:
                # A timed-out write may have succeeded.  Re-read before retrying.
                if not self.github.comment_exists(pending["issue"], marker):
                    return {"action": "receipt-write-unknown", "issue": pending["issue"]}
        # A review disposition is valid only for the exact head which was
        # reviewed.  A timeout may leave a comment durable while the PR moves;
        # discard that stale pending disposition rather than replaying it.
        candidate_key = pending.get("candidate_key")
        if candidate_key and pending["old"] == "agent:review":
            current = self.github.candidate(pending["issue"])
            if not current or current.key() != candidate_key:
                state.pop("pending", None)
                if current:
                    state["candidate"] = asdict(current)
                self.state.write(state)
                return {"action": "receipt-candidate-stale", "issue": pending["issue"]}
        if not self.github.transition(pending["issue"], pending["old"], pending["new"]):
            # A transition can have succeeded remotely before its response was
            # lost.  Reconcile the authoritative queue before retrying.
            now = next((row for row in self.github.issues() if row.number == pending["issue"]), None)
            if not now or now.queue_state() != pending["new"]:
                return {"action": "transition-needs-recheck", "issue": pending["issue"]}
        state.setdefault("receipts", []).append(marker)
        state.pop("pending", None); self.state.write(state)
        return {"action": "transitioned", "issue": pending["issue"], "state": pending["new"]}

    def _claim(self, issue, state):
        nonce = hashlib.sha256(f"{issue.number}:{self.worker_id}:{self.now()}".encode()).hexdigest()[:16]
        attempt = issue.queue_state().removeprefix("agent:")
        raw = state.get("candidate")
        cycle = Candidate(**raw).key() if raw and raw.get("issue") == issue.number else "initial"
        marker = f"agentos-handoff:claim:{issue.number}:{attempt}:{cycle}:{self.worker_id}:{nonce}"
        try:
            self.github.comment(issue.number, marker, "Bounded implementer lease claim.")
        except TimeoutError:
            if not self.github.comment_exists(issue.number, marker):
                return None
        # A GitHub label edit has no conditional-update primitive.  A durable,
        # owner-authored claim comment establishes a deterministic winner before
        # any writer transition; losers never invoke an executor.
        if not self.github.claim_winner(issue.number, marker):
            return None
        if not self.github.transition(issue.number, issue.queue_state(), "agent:working"):
            return None
        if not self.github.claim_winner(issue.number, marker):
            return None
        lease = {"issue": issue.number, "owner": self.worker_id, "until": self.now() + self.lease_seconds}
        state["lease"] = lease; self.state.write(state)
        return lease

    def _implement(self, issue, state):
        # A discovery/heartbeat process without a configured bounded executor
        # must not claim an issue merely to leave it stranded in working.
        if self.executor is None:
            return {"action": "dispatch-required", "issue": issue.number}
        lease = state.get("lease")
        retained_lease = bool(lease and lease.get("issue") == issue.number)
        if not lease or lease.get("issue") != issue.number:
            lease = self._claim(issue, state)
            if not lease: return {"action": "claim-raced", "issue": issue.number}
        raw = state.get("candidate")
        if retained_lease and raw and raw.get("issue") == issue.number:
            # Do not re-run an executor merely because asynchronous CI has not
            # finished.  Its retained lease owns the bounded candidate while
            # the adapter refreshes the current check state.
            candidate = Candidate(**raw)
            refresh = getattr(self.github, "refresh_candidate", None)
            current = refresh(issue.number, candidate) if refresh else self.github.candidate(issue.number)
            if not current or current.key() != candidate.key():
                return {"action": "candidate-needs-recovery", "issue": issue.number}
            candidate = Candidate(**{**asdict(candidate), "ci": current.ci,
                                     "draft": current.draft,
                                     "required_checks_known": current.required_checks_known})
        else:
            # A rework worker may run on another host. Prefer the bounded
            # reviewer receipt read from GitHub; local state is only a cache.
            feedback = state.get("feedback")
            remote_feedback = getattr(self.github, "feedback", None)
            if remote_feedback:
                feedback = remote_feedback(issue.number, Candidate(**raw)) if raw else remote_feedback(issue.number, None)
            candidate = self.executor(issue, feedback)
        if not isinstance(candidate, Candidate) or candidate.issue != issue.number:
            return {"action": "executor-no-candidate", "issue": issue.number}
        state["candidate"] = asdict(candidate); self.state.write(state)
        if candidate.ci != "success":
            return {"action": "awaiting-ci", "issue": issue.number, "ci": candidate.ci}
        state.pop("lease", None); self.state.write(state)
        return self._receipt(issue.number, "agent:working", "agent:review", "implementation", candidate.key(),
                             f"Implementation receipt: PR #{candidate.pr}, head `{candidate.head}`, CI `{candidate.ci}`.", state, candidate)

    def _review(self, issue, state):
        raw = state.get("candidate")
        # Reviewer state is intentionally independent from the implementer's
        # local recovery file. GitHub receipt is the role handoff boundary.
        candidate = Candidate(**raw) if raw and raw.get("issue") == issue.number else self.github.candidate(issue.number)
        if not candidate:
            return {"action": "missing-candidate-association", "issue": issue.number}
        state["candidate"] = asdict(candidate); self.state.write(state)
        current = self.github.candidate(issue.number)
        if (not current or current.key() != candidate.key() or candidate.draft or candidate.ci != "success"
                or not candidate.required_checks_known):
            return {"action": "candidate-not-reviewable", "issue": issue.number}
        if self.reviewer is None: return {"action": "review-dispatch-required", "issue": issue.number}
        findings = list(self.reviewer(issue, candidate) or [])
        # Recheck the immutable candidate immediately before publishing disposition.
        latest = self.github.candidate(issue.number)
        if not latest or latest.key() != candidate.key():
            return {"action": "stale-review-rejected", "issue": issue.number}
        digest = hashlib.sha256("\n".join(findings).encode()).hexdigest()[:20]
        if findings:
            state["feedback"] = {"digest": digest, "findings": findings}; self.state.write(state)
            return self._receipt(issue.number, "agent:review", "agent:rework", "review", candidate.key() + ":" + digest,
                                 f"Review receipt: PR #{candidate.pr}, head `{candidate.head}`, repair required — " + "; ".join(findings), state, candidate)
        return self._receipt(issue.number, "agent:review", "agent:approved", "review", candidate.key(),
                             f"Review receipt: PR #{candidate.pr}, head `{candidate.head}` satisfies current fixture evidence; owner merge decision remains.", state, candidate)

    def tick(self, role):
        if role not in {"implementer", "reviewer"}: raise HandoffError("role must be implementer or reviewer")
        lock = self.state.locked()
        try:
            state = self.state.read()
            flushed = self._flush(state)
            if flushed: return flushed
            issues = list(self.github.issues())
            working = [i for i in issues if i.queue_state() == "agent:working" and i.state == "OPEN"]
            lease = state.get("lease", {})
            if role == "implementer" and working:
                mine = next((i for i in working if i.number == lease.get("issue") and lease.get("owner") == self.worker_id), None)
                if mine and (lease.get("until", 0) >= self.now() or not self.github.execution_active(mine.number, lease)):
                    return self._implement(mine, state)
                return {"action": "writer-already-active", "issue": working[0].number}
            if role == "implementer":
                choices = [i for i in issues if self._eligible(i)]
                choices.sort(key=lambda i: (0 if i.queue_state() == "agent:rework" else 1, i.number))
                return self._implement(choices[0], state) if choices else {"action": "idle"}
            choices = [i for i in issues if i.state == "OPEN" and i.queue_state() == "agent:review"]
            choices.sort(key=lambda i: i.number)
            return self._review(choices[0], state) if choices else {"action": "idle"}
        finally:
            lock.close()


class GithubCliBoundary:
    """Small authenticated ``gh`` adapter used by the delivery CLI.

    It deliberately has no method that creates a branch, starts a model,
    merges, or closes an issue.  An existing heartbeat can run a one-shot
    dispatch and hand the selected bounded issue to its configured executor.
    """
    def __init__(self, repository, runner=None, authorized_goals=None, owner_login=None,
                 implementer_logins=None, reviewer_logins=None):
        self.repository, self.runner = repository, runner or self._run
        self._viewer = None
        # This map is supplied by the owner-maintained delivery plan / local
        # controller, not copied from an issue body.
        self.authorized_goals = authorized_goals or {}
        self.owner_login = owner_login
        self.implementer_logins = set(implementer_logins or ())
        self.reviewer_logins = set(reviewer_logins or ())

    @staticmethod
    def _run(args):
        try:
            return subprocess.run(args, text=True, capture_output=True, timeout=60)
        except subprocess.TimeoutExpired as exc:
            # The write may have reached GitHub.  Present the same ambiguous
            # timeout to _flush(), which always reads receipt markers first.
            raise TimeoutError(str(exc)) from exc

    def _json(self, *args):
        result = self.runner(["gh", *args])
        if result.returncode: raise HandoffError((result.stderr or "GitHub command failed").strip())
        try: return json.loads(result.stdout)
        except ValueError as exc: raise HandoffError("GitHub returned invalid JSON.") from exc

    def _viewer_login(self):
        if self._viewer is None: self._viewer = self._json("api", "user")["login"]
        return self._viewer

    def issues(self):
        rows = self._json("issue", "list", "--repo", self.repository, "--state", "open", "--limit", "100",
                          "--json", "number,body,state,labels,author")
        result = []
        for row in rows:
            body = row.get("body") or ""
            authority = self.authorized_goals.get(int(row["number"]), {})
            author = (row.get("author") or {}).get("login")
            # Markers describe a record but never confer authority. Admission
            # requires an externally supplied exact goal/dependency record.
            authorized = bool(authority.get("authorized")) and (not self.owner_login or author == self.owner_login)
            dependencies = bool(authority.get("dependencies_satisfied"))
            result.append(Issue(int(row["number"]), {x["name"] for x in row.get("labels", [])}, body,
                                row.get("state", "OPEN"), authorized, dependencies))
        return result

    def transition(self, number, old, new):
        row = self._json("issue", "view", str(number), "--repo", self.repository, "--json", "state,labels")
        labels = {x["name"] for x in row.get("labels", [])}
        if row.get("state") != "OPEN" or labels & STATES != {old}: return False
        result = self.runner(["gh", "issue", "edit", str(number), "--repo", self.repository,
                              "--remove-label", old, "--add-label", new])
        if result.returncode: return False
        confirmed = self._json("issue", "view", str(number), "--repo", self.repository, "--json", "state,labels")
        return confirmed.get("state") == "OPEN" and {x["name"] for x in confirmed.get("labels", [])} & STATES == {new}

    def _comments(self, number):
        return self._json("api", f"repos/{self.repository}/issues/{number}/comments?per_page=100")

    def comment_exists(self, number, marker):
        viewer = self._viewer_login()
        return any(marker in (row.get("body") or "") and row.get("user", {}).get("login") == viewer
                   for row in self._comments(number))

    def comment(self, number, marker, text):
        result = self.runner(["gh", "issue", "comment", str(number), "--repo", self.repository,
                              "--body", f"<!-- {marker} -->\n{text}"])
        if result.returncode: raise HandoffError((result.stderr or "Could not publish handoff receipt.").strip())

    def claim_winner(self, number, marker):
        viewer = self._viewer_login()
        claims = [row for row in self._comments(number)
                  if row.get("user", {}).get("login") == viewer and "agentos-handoff:claim:" in (row.get("body") or "")]
        # The fifth component is the immutable candidate cycle.  A completed
        # rework claim for an older head must not own a later repair cycle.
        prefix = ":".join(marker.split(":")[:5]) + ":"
        claims = [row for row in claims if prefix in (row.get("body") or "")]
        # GitHub returns comments in creation order.  The earliest claim for
        # this exact ready/rework attempt owns it; a prior completed attempt
        # cannot block a later repair.
        return bool(claims) and marker in (claims[0].get("body") or "")

    def _candidate_from_pr(self, number, pr, receipt_ci="success"):
        row = self._json("pr", "view", pr, "--repo", self.repository,
                         "--json", "number,headRefOid,baseRefName,isDraft")
        # Rollups contain optional checks and mixed CheckRun/StatusContext
        # representations, so they cannot establish required CI.  Ask gh for
        # the required set; unknown, missing, or pending requirements fail
        # closed until a later tick can resolve them.
        required = self.runner(["gh", "pr", "checks", str(pr), "--repo", self.repository,
                                "--required", "--json", "name,state"])
        try:
            required_checks = json.loads(required.stdout)
            known = isinstance(required_checks, list)
        except (TypeError, ValueError):
            required_checks, known = [], False
        success = known and required.returncode == 0 and all(
            isinstance(check, dict) and check.get("state") == "SUCCESS" for check in required_checks)
        return Candidate(number, int(row["number"]), row["headRefOid"], row["baseRefName"],
                         "success" if success and receipt_ci == "success" else "pending", bool(row["isDraft"]), known)

    def _allowed_comments(self, number, roles):
        viewer = self._viewer_login()
        allowed = set(roles) or {viewer}
        return [r for r in self._comments(number) if r.get("user", {}).get("login") in allowed]

    def candidate(self, number):
        comments = self._allowed_comments(number, self.implementer_logins)
        pattern = __import__("re").compile(r"Implementation receipt: PR #(\d+), head `([0-9a-f]{40})`, CI `([^`]+)`")
        matches = [pattern.search(r.get("body") or "") for r in comments]; matches = [m for m in matches if m]
        if not matches: return None
        pr, head, ci = matches[-1].groups()
        candidate = self._candidate_from_pr(number, pr, ci)
        # A receipt for an older pushed head cannot authorise review of a
        # newer PR head.
        return candidate if candidate.head == head else None

    def feedback(self, number, candidate):
        comments = self._allowed_comments(number, self.reviewer_logins)
        pattern = __import__("re").compile(r"Review receipt: PR #(\d+), head `([0-9a-f]{40})`, repair required — (.+)")
        matches = [pattern.search(r.get("body") or "") for r in comments]; matches = [m for m in matches if m]
        if not matches: return None
        pr, head, findings = matches[-1].groups()
        if candidate and (int(pr) != candidate.pr or head != candidate.head): return None
        return {"digest": hashlib.sha256(findings.encode()).hexdigest()[:20],
                "findings": [item.strip() for item in findings.split(";") if item.strip()]}

    def refresh_candidate(self, number, previous):
        """Poll a retained working candidate before its receipt exists."""
        return self._candidate_from_pr(number, str(previous.pr), "success")

    def execution_active(self, number, lease):
        # GitHub labels cannot establish liveness.  An expired local lease is
        # reconciled only when no same-owner process is known locally.
        return False
