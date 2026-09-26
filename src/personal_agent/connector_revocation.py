"""Owner disconnect and Google-side token revocation (CONNECTOR-REVOKE-01 #588).

Three different effects, reported separately and never merged into one word:

1. **Local disconnect** -- AgentOS stops using the connection: the connector
   row moves to DISCONNECTED with a new revision (Gmail/Calendar) or the Drive
   handoff records ``disconnected``, the stored credential is overwritten, an
   in-progress authorization is consumed, and Work parked for that connection
   is ended explicitly. This always happens once the owner confirms.
2. **Provider revocation** -- one RFC 7009 request to Google's revocation
   endpoint. Its outcome is recorded as observed: ``revoked`` (HTTP 200),
   ``already_invalid`` (HTTP 400 ``invalid_token``: Google says the token is
   not valid any more), ``failed`` (any other answer) or ``unconfirmed`` (no
   answer: network failure/timeout, the request may or may not have arrived).
   ``not_attempted`` means no credential was stored locally to revoke.
3. **Deletion of retained data** -- *not* performed. Owner Artifacts, Work
   results and retained Evidence stay; nothing stored at Google is deleted.

Existing Solutions Review (C15), recorded here because this module encodes it.

*Standards*: RFC 7009 (OAuth 2.0 Token Revocation) and Google's documented
endpoint ``https://oauth2.googleapis.com/revoke`` (POST, form-encoded
``token``; 200 on success, 400 ``invalid_token`` for a token that is already
invalid). Revoking a refresh token ends the grant; revoking an access token
that has a refresh token revokes that refresh token too, so one request per
connection is enough and the refresh token is preferred when stored.

*Adopt*: ``oauthlib`` (already a dependency, 3.3.1, BSD-3-Clause) builds the
RFC 7009 request -- ``Client.prepare_token_revocation_request``. The HTTP hop
adopts the repository's own ``connector_http.contained_opener`` so the token
can only ever reach the revocation host, across redirects too.

*Rejected*: ``google-auth`` has no revocation helper for these hand-held
tokens and is not a dependency (see ``drive_web_oauth`` REUSE-R1b #427);
``requests``/``httpx`` would be a new runtime dependency for one POST
(``connector_http`` records the same decision). ``oauthlib`` does not send
requests, so the transport and the outcome classification are AgentOS-owned.

*Existing AgentOS reuse*: ``ConnectorRegistry.transition`` (new revision on
every change, so stale callbacks/retries/in-flight requests are refused by the
checks every connector already applies), the per-connector encrypted secret
stores, ``ConnectorHandoff.supersede`` for parked Work. *Build* is limited to
the owner-bound single-use confirmation below: the retired Settings draft
control plane (``settings_orchestrator``) deliberately applies nothing, and
``memory_approvals`` is bound to a memory key rather than a connection.

A credential that could not be revoked stays only in the connector's own
encrypted store under a separate ``revocation`` slot that no tool path reads;
it exists solely so the owner can retry revocation, and it is removed as soon
as Google confirms.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from contextlib import nullcontext
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request

from oauthlib.oauth2 import Client as _OAuthClient

from .connector_http import contained_opener


GOOGLE_REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"
GOOGLE_REVOKE_HOST = "oauth2.googleapis.com"
REVOCATION_SLOT = "google_revocation_pending"
CONFIRMATIONS_KEY = "google_disconnect_confirmations"
AUDIT_KEY = "google_disconnect_audit"
CONFIRMATION_TTL_SECONDS = 300

REVOKED = "revoked"
ALREADY_INVALID = "already_invalid"
FAILED = "failed"
UNCONFIRMED = "unconfirmed"
NOT_ATTEMPTED = "not_attempted"
CONFIRMED_OUTCOMES = frozenset({REVOKED, ALREADY_INVALID})

_LOCK = threading.RLock()


class RevocationError(ValueError):
    """Fail-closed refusal whose text is safe to show the owner."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


REFUSALS = {
    "unknown_connection": "해제할 Google 연결을 찾지 못했습니다.",
    "invalid_confirmation": "확인 정보가 올바르지 않습니다. 연결 해제를 처음부터 다시 진행해 주세요.",
    "replayed_confirmation": "이미 사용한 확인입니다. 연결 해제를 다시 하려면 새로 확인해 주세요.",
    "expired_confirmation": "확인 시간이 지났습니다. 연결 해제를 다시 확인해 주세요.",
    "wrong_owner": "다른 로그인 세션에서 만든 확인이라 사용할 수 없습니다.",
    "connection_changed": "확인 이후 연결 상태가 바뀌었습니다. 현재 상태를 다시 확인한 뒤 해제해 주세요.",
    "nothing_to_retry": "Google에 다시 취소를 요청할 항목이 없습니다.",
    "reconnected": "그 사이 다시 연결되어, 이전 토큰 취소를 재시도하면 새 연결까지 끊길 수 있어 요청하지 않았습니다.",
}


def _refuse(reason: str) -> RevocationError:
    return RevocationError(reason, REFUSALS[reason])


class DestinationRefused(ValueError):
    """Raised before anything is sent: the request provably never left."""


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# -- the provider hop --------------------------------------------------------
def google_revoke_transport(opener=None, timeout: float = 15):
    """The owner-local revocation hop: ``(url, body, headers) -> (status, body)``.

    Only ``https://oauth2.googleapis.com`` is reachable, on every redirect hop.
    An HTTP error answer is returned as its status, not raised, because it is
    an observed provider answer; only a missing answer raises.
    """

    def permitted(candidate):
        parts = urlsplit(str(candidate or ""))
        if parts.username or parts.password:
            return False
        return parts.scheme == "https" and parts.hostname == GOOGLE_REVOKE_HOST

    guarded = opener or contained_opener(permitted).open

    def transport(url, body, headers):
        if not permitted(url):
            raise DestinationRefused("revocation destination refused")
        try:
            with guarded(Request(url, body, headers, method="POST"), timeout=timeout) as response:
                return response.status, response.read(4096)
        except HTTPError as exc:
            try:
                payload = exc.read(4096)
            except Exception:
                payload = b""
            return exc.code, payload

    return transport


def revoke_google_tokens(credentials, transport) -> tuple[str, list]:
    """Revoke every held credential; return (overall outcome, still-unconfirmed)."""
    outcomes, remaining = [], []
    for credential in credentials or []:
        outcome = revoke_google_token(credential, transport)
        if outcome == NOT_ATTEMPTED:
            if credential:
                remaining.append(credential)  # never sent: keep it for a retry
            continue
        outcomes.append(outcome)
        if outcome not in CONFIRMED_OUTCOMES:
            remaining.append(credential)
    for worst in (UNCONFIRMED, FAILED, REVOKED, ALREADY_INVALID):
        if worst in outcomes:
            return worst, remaining
    return NOT_ATTEMPTED, remaining


def revoke_google_token(credential: dict | None, transport) -> str:
    """Send one RFC 7009 revocation and classify only what was observed."""
    if not isinstance(credential, dict):
        return NOT_ATTEMPTED
    refresh = credential.get("refresh_token")
    access = credential.get("access_token")
    if isinstance(refresh, str) and refresh:
        token, hint = refresh, "refresh_token"
    elif isinstance(access, str) and access:
        token, hint = access, "access_token"
    else:
        return NOT_ATTEMPTED
    url, headers, body = _OAuthClient("").prepare_token_revocation_request(
        GOOGLE_REVOKE_ENDPOINT, token, token_type_hint=hint
    )
    if not callable(transport):
        return UNCONFIRMED
    try:
        status, payload = transport(url, body.encode(), headers)
    except DestinationRefused:
        return NOT_ATTEMPTED
    except Exception:
        # No provider answer: the request may or may not have reached Google.
        # Never chain the exception: it can carry the request body.
        return UNCONFIRMED
    if status == 200:
        return REVOKED
    if status == 400:
        try:
            error = json.loads((payload or b"{}").decode("utf-8", "replace")).get("error")
        except (ValueError, AttributeError):
            error = None
        if error == "invalid_token":
            return ALREADY_INVALID
    return FAILED


# -- per-connection adapters -------------------------------------------------
class _Connection:
    """One disconnectable Google connection and its own secret boundary."""

    def __init__(self, connector_id, label, secret_store, state, marker, disconnect):
        self.connector_id = connector_id
        self.label = label
        self.secret_store = secret_store
        self.state = state  # callable -> current owner-visible state
        self.marker = marker  # callable -> opaque revision marker
        self.disconnect = disconnect  # callable(stash) -> parked work ids to end
        self.residual = lambda: False  # callable -> an unreachable active row remains
        # The connector's own authorization lock: holding it keeps an OAuth
        # completion from committing between a retry's state check and send.
        self.lifecycle = nullcontext
        self.authorizing = lambda: False  # an authorization is mid-flight

    def slot(self) -> str:
        return f"{REVOCATION_SLOT}:{self.connector_id}"

    def pending(self):
        try:
            value = self.secret_store.secret(self.slot())
        except ValueError:
            return None
        return value if isinstance(value, dict) and value.get("credentials") else None

    def credentials(self) -> list:
        return [c for c in (self.pending() or {}).get("credentials", []) if isinstance(c, dict)]


def registry_connection(connector_id, label, holder, owners, *, write=None):
    """Adapter for a ConnectorRegistry-backed connection (Gmail, Calendar).

    ``owners`` returns every owner identity this installation can hold the
    connection under (the paired chat and the local owner). Disconnect acts on
    all of them, so a row authorized under one identity cannot survive because
    Settings resolved the other.
    """
    kwargs = {} if write is None else {"write": write}

    def statuses():
        return [holder.status(owner, **kwargs) for owner in owners()]

    def state():
        states = [row.get("state") for row in statuses()]
        for candidate in ("connected", "reauth_required", "blocked"):
            if candidate in states:
                return candidate
        return "disconnected"

    def disconnect(stash):
        for owner in owners():
            holder.disconnect(owner, stash, **kwargs)
        return []

    def residual():
        """Rows still active under an identity this install could not name.

        Registry rows are keyed by a hashed owner, so an identity that was
        never recorded cannot be disconnected here; it must at least never
        be reported as stopped.
        """
        try:
            rows = holder.registry._rows()
        except Exception:
            return True
        reached = {hashlib.sha256(owner.encode()).hexdigest() for owner in owners()}
        return any(isinstance(by_connector, dict) and isinstance(by_connector.get(connector_id), dict)
                   and by_connector[connector_id].get("state") in ("connected", "reauth_required")
                   and owner_key not in reached
                   for owner_key, by_connector in rows.items())

    connection = _Connection(
        connector_id,
        label,
        holder.store,
        state,
        lambda: "|".join(f"{row.get('state')}:{row.get('connection_revision')}" for row in statuses()),
        disconnect,
    )
    connection.residual = residual
    connection.lifecycle = lambda: holder.oauth_lock
    return connection


def drive_connection(label, drive):
    """Adapter for the Drive web-OAuth handoff, which has no registry row."""

    def disconnect(stash):
        job = drive.disconnect(stash)
        return [job] if job else []

    from .drive_web_oauth import LIFECYCLE_LOCK

    connection = _Connection(
        "google-drive-read",
        label,
        drive.store,
        lambda: drive.effective_status().get("state"),
        drive.revision_marker,
        disconnect,
    )
    connection.lifecycle = lambda: LIFECYCLE_LOCK
    connection.authorizing = drive.authorization_in_progress
    return connection


# -- the owner-facing operation ---------------------------------------------
class GoogleConnectionRevoker:
    """Preview -> owner-bound confirmation -> local disconnect -> provider revocation."""

    def __init__(self, store, connections, transport, *, now=time.time,
                 on_disconnected: Callable[[str, list], None] | None = None,
                 ttl_seconds: float = CONFIRMATION_TTL_SECONDS):
        self.store = store
        self.connections = {c.connector_id: c for c in connections}
        self.transport = transport
        self.now = now
        self.on_disconnected = on_disconnected
        self.ttl_seconds = ttl_seconds

    def _connection(self, connector_id) -> _Connection:
        if not isinstance(connector_id, str) or connector_id not in self.connections:
            raise _refuse("unknown_connection")
        return self.connections[connector_id]

    @staticmethod
    def _session(session) -> str:
        if not isinstance(session, str) or not session:
            raise _refuse("wrong_owner")
        return _digest("session:" + session)

    def _confirmations(self) -> dict:
        rows = self.store.secret(CONFIRMATIONS_KEY)
        return dict(rows) if isinstance(rows, dict) else {}

    def preview(self, session, connector_id) -> dict:
        """The exact effects, and a single-use confirmation bound to this session."""
        connection = self._connection(connector_id)
        owner = self._session(session)
        token = secrets.token_urlsafe(32)
        expires_at = self.now() + self.ttl_seconds
        with _LOCK:
            rows = {key: row for key, row in self._confirmations().items()
                    if isinstance(row, dict) and row.get("expires_at", 0) > self.now() - 3600}
            rows[_digest(token)] = {"owner": owner, "connector_id": connector_id,
                                    "marker": connection.marker(), "expires_at": expires_at,
                                    "used": False}
            self.store.secret(CONFIRMATIONS_KEY, rows)
        return {
            "connector_id": connector_id,
            "label": connection.label,
            "state": connection.state(),
            "confirmation": token,
            "expires_at": expires_at,
            "effects": {
                "local_access": "stop",
                "local_credentials": "delete",
                "provider_revocation": "request",
                "provider_destination": GOOGLE_REVOKE_HOST,
                "retained_data": "preserve",
                "remote_data_deletion": "none",
            },
            "message": (f"{connection.label} 연결을 해제하면 AgentOS가 즉시 이 연결을 쓰지 않고, "
                        f"이 기기에 저장된 인증 정보를 삭제하며, Google({GOOGLE_REVOKE_HOST})에 "
                        "권한 취소를 요청합니다. 저장된 결과물과 기록은 지우지 않고, Google에 있는 "
                        "데이터도 삭제하지 않습니다."),
        }

    def _consume(self, session, connector_id, confirmation) -> _Connection:
        connection = self._connection(connector_id)
        owner = self._session(session)
        if not isinstance(confirmation, str) or not confirmation or len(confirmation) > 256:
            raise _refuse("invalid_confirmation")
        key = _digest(confirmation)
        with _LOCK:
            rows = self._confirmations()
            row = rows.get(key)
            if not isinstance(row, dict) or row.get("connector_id") != connector_id:
                raise _refuse("invalid_confirmation")
            if not secrets.compare_digest(str(row.get("owner", "")), owner):
                raise _refuse("wrong_owner")
            if row.get("used"):
                raise _refuse("replayed_confirmation")
            # Consumed before any check that could fail later, so a refusal
            # below still spends it: every confirmation is single use.
            row["used"] = True
            rows[key] = row
            self.store.secret(CONFIRMATIONS_KEY, rows)
            if self.now() >= row.get("expires_at", 0):
                raise _refuse("expired_confirmation")
            if row.get("marker") != connection.marker():
                raise _refuse("connection_changed")
        return connection

    def disconnect(self, session, connector_id, confirmation) -> dict:
        connection = self._consume(session, connector_id, confirmation)
        stashed = {}

        def stash(credential):
            kept = {k: credential[k] for k in ("refresh_token", "access_token")
                    if isinstance(credential, dict) and isinstance(credential.get(k), str) and credential[k]}
            if kept:
                stashed["credential"] = kept
                # Kept before the live slot is cleared, so a crash in between
                # cannot lose the only copy provider revocation needs. An
                # earlier still-unconfirmed credential is kept alongside.
                connection.secret_store.secret(connection.slot(), {
                    "credentials": [*connection.credentials(), kept],
                    "since": (connection.pending() or {}).get("since") or self.now()})

        with _LOCK:
            parked = connection.disconnect(stash)
        if self.on_disconnected:
            self.on_disconnected(connection.connector_id, parked)
        receipt = self._revoke(connection, local_credentials="deleted" if stashed.get("credential") else "none_stored")
        if connection.residual():
            receipt.update(local_access="incomplete", message=(
                f"{connection.label} 연결 중 이 기기에서 확인할 수 없는 소유자(예: 이전에 연결했던 Telegram 계정)로 "
                "남아 있는 연결이 있어 모두 해제하지 못했습니다. 이 연결은 아직 사용될 수 있습니다. "
                "Google 계정의 타사 앱 액세스에서 AgentOS 권한을 직접 제거해 주세요."))
            self._audit_residual(connection)
        return receipt

    def _audit_residual(self, connection):
        audit = self.store.config(AUDIT_KEY, [])
        if isinstance(audit, list) and audit:
            audit[-1] = {**audit[-1], "local_access": "incomplete"}
            self.store.put(AUDIT_KEY, audit)

    def retry(self, connector_id) -> dict:
        connection = self._connection(connector_id)
        # Order: revoker lock -> connector authorization lock, the same order
        # disconnect uses. Under both, no OAuth completion can commit between
        # the reconnect check below and the revocation it guards.
        with _LOCK, connection.lifecycle():
            if not connection.credentials():
                raise _refuse("nothing_to_retry")
            if connection.state() in ("connected", "reauth_required") or connection.authorizing():
                raise _refuse("reconnected")
            return self._revoke(connection, local_credentials="deleted", retry=True)

    def pending_revocations(self) -> list:
        return [{"connector_id": c.connector_id, "label": c.label, "since": c.pending().get("since")}
                for c in self.connections.values() if c.pending()]

    def _revoke(self, connection, *, local_credentials, retry=False) -> dict:
        with _LOCK:
            pending = connection.pending() or {}
            outcome, remaining = revoke_google_tokens(connection.credentials(), self.transport)
            connection.secret_store.secret(
                connection.slot(), {"credentials": remaining, "since": pending.get("since")} if remaining else {})
        retry_available = bool(remaining)
        event = {"at": self.now(), "connector_id": connection.connector_id,
                 "operation": "retry_revocation" if retry else "disconnect",
                 "local_access": "stopped", "local_credentials": local_credentials,
                 "provider_revocation": outcome,
                 "provider_request": ("not_sent" if outcome == NOT_ATTEMPTED else
                                      "observed" if outcome in (REVOKED, ALREADY_INVALID, FAILED) else "unknown"),
                 "provider_destination": GOOGLE_REVOKE_HOST if outcome != NOT_ATTEMPTED else None,
                 "retained_data": "preserved", "retry_available": retry_available}
        audit = self.store.config(AUDIT_KEY, [])
        audit = audit if isinstance(audit, list) else []
        self.store.put(AUDIT_KEY, [*audit, event][-100:])
        return {**{k: v for k, v in event.items() if k != "at"},
                "label": connection.label, "state": connection.state(),
                "message": _message(connection.label, outcome)}


def _message(label: str, outcome: str) -> str:
    stopped = f"{label} 연결을 해제했습니다. AgentOS는 더 이상 이 연결을 사용하지 않으며, 저장된 결과물과 기록은 그대로 남아 있습니다. "
    return stopped + {
        REVOKED: "Google에서도 권한 취소를 확인했습니다.",
        ALREADY_INVALID: "Google은 이 인증이 이미 유효하지 않다고 답했습니다(이미 취소되었거나 만료됨).",
        FAILED: ("Google이 권한 취소 요청을 거절해 Google 쪽 권한 취소는 확인되지 않았습니다. "
                 "나중에 다시 시도하거나 Google 계정의 타사 앱 액세스에서 직접 제거할 수 있습니다."),
        UNCONFIRMED: ("Google에 연결하지 못해 Google 쪽 권한 취소는 확인되지 않았습니다. "
                      "나중에 다시 시도하거나 Google 계정의 타사 앱 액세스에서 직접 제거할 수 있습니다."),
        NOT_ATTEMPTED: ("이 기기에 남은 인증 정보가 없어 Google에 취소 요청을 보내지 않았습니다. "
                        "Google 쪽 권한이 남아 있을 수 있으니 Google 계정의 타사 앱 액세스에서 확인하세요."),
    }[outcome]
