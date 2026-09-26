"""Owner-bound Google Calendar OAuth with separate read and write grants.

This module is the missing credential path for the Calendar connectors that
:mod:`personal_agent.calendar` already defines. It mirrors the Gmail pattern in
:mod:`personal_agent.gmail`: OAuth state and tokens stay inside an encrypted
owner-local secret boundary, only redacted lifecycle metadata reaches
:mod:`personal_agent.connector_contract`, and the client secret is never handed
to this module at all - the token exchange is an injected callable.

Two things are deliberately different from Gmail:

* Calendar has **two** connectors, ``google-calendar`` (read) and
  ``google-calendar-write``. They are authorized independently and stored in
  independent secret slots, so a read grant can never be spent as a write
  grant. One OAuth callback route serves both; see :meth:`CalendarOAuth._pending`
  for how the signed state carries which grant is completing.
* This module performs no Calendar mutation. :func:`calendar_transport` is a
  read-only credential transport for ``GoogleCalendar.query``; it refuses every
  non-GET method before it resolves a token. A write-capable transport is not
  provided here on purpose.

Nothing in this module constructs :class:`personal_agent.calendar.CalendarConnector`.
Importing it registers no connector and grants no authority; only constructing
:class:`CalendarOAuth` - which is the act of wiring a callback route that can
actually complete an authorization - registers the two connector definitions.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import hmac
import json
import math
import re
import secrets
import threading
import time
from typing import Callable
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from oauthlib.oauth2 import WebApplicationClient

from .calendar import CALENDAR_SPEC, CALENDAR_WRITE_SPEC
from .connector_contract import (
    ConnectorContractError,
    ConnectorRegistry,
    ConnectorSpec,
    ConnectorState,
)
from .google_calendar import CALENDAR_API, GoogleCalendarHTTPError


AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
PENDING_SECRET_KEY = "calendar_oauth_pending"
TOKEN_SECRET_KEY = "calendar_oauth_tokens"
READ_GRANT = "read"
WRITE_GRANT = "write"
# The two grants are named by the connector definitions that already exist in
# ``personal_agent.calendar``; the scope set committed to the registry is read
# from the spec so this module can never grant a scope the connector does not
# require, and cannot drift if the spec changes.
_GRANTS: dict[str, ConnectorSpec] = {
    READ_GRANT: CALENDAR_SPEC,
    WRITE_GRANT: CALENDAR_WRITE_SPEC,
}
# A Calendar secret must never be reachable through a Gmail-namespaced key even
# when both stores wrap the same owner store with the same local key. See the
# closure-capture finding recorded in ``quickstart.py``: two connectors that
# each looked correct in isolation shared one name and one connector's secret
# reached the other connector's external destination. The namespace here is a
# fixed literal prefix, so no caller-supplied key can address another
# connector's slot: the key ``"encrypted:gmail:x"`` resolves to
# ``"encrypted:calendar:encrypted:gmail:x"``.
_SECRET_NAMESPACE = "encrypted:calendar:"
_NONCE = re.compile(r"[A-Za-z0-9_-]{22,128}\Z")
_SIGNATURE = re.compile(r"[0-9a-f]{64}\Z")
_VERIFIER = re.compile(r"[A-Za-z0-9._~-]{43,128}\Z")
_MAX_RESPONSE_BYTES = 1_048_576
_OAUTH_LOCK = threading.RLock()


class CalendarOAuthError(ValueError):
    """A fail-closed error whose text never discloses owner or OAuth data."""

    def __init__(self, reason: str = "rejected"):
        super().__init__("Calendar authorization request rejected")
        self.reason = reason


class CalendarReauthenticationRequired(CalendarOAuthError):
    pass


class EncryptedCalendarSecretStore:
    """Encrypt Calendar-only OAuth secrets using a caller-owned local key.

    The key is never persisted here, and the namespace is Calendar-only, so a
    Calendar secret is not readable through a Gmail-namespaced key and vice
    versa even when both stores are given the same owner store and key.
    """

    encrypted_secrets = True

    def __init__(self, store, key: str | bytes):
        if not isinstance(key, (str, bytes)):
            raise ValueError("A local encryption key is required for Calendar OAuth.")
        try:
            self._cipher = Fernet(key.encode() if isinstance(key, str) else key)
        except (TypeError, ValueError) as exc:
            raise ValueError("A valid local encryption key is required for Calendar OAuth.") from exc
        self._store = store

    def secret(self, key: str, value=None):
        namespaced = _SECRET_NAMESPACE + key
        if value is not None:
            payload = json.dumps(value, separators=(",", ":")).encode()
            self._store.secret(namespaced, self._cipher.encrypt(payload).decode())
        raw = self._store.secret(namespaced)
        if not raw:
            return ""
        try:
            return json.loads(self._cipher.decrypt(str(raw).encode()).decode())
        except (InvalidToken, TypeError, ValueError, json.JSONDecodeError):
            raise CalendarOAuthError("unreadable_secret") from None

    def config(self, key: str, default=None):
        return self._store.config(key, default)

    def put(self, key: str, value) -> None:
        self._store.put(key, value)


def _owner_key(owner_id: str) -> str:
    if not isinstance(owner_id, str) or not owner_id.strip() or len(owner_id) > 200:
        raise CalendarOAuthError("invalid_owner")
    return hashlib.sha256(owner_id.encode()).hexdigest()


def _grant_label(write: object) -> str:
    if not isinstance(write, bool):
        raise CalendarOAuthError("invalid_grant")
    return WRITE_GRANT if write else READ_GRANT


def _spec(grant: str) -> ConnectorSpec:
    spec = _GRANTS.get(grant)
    if spec is None:
        raise CalendarOAuthError("invalid_grant")
    return spec


def _secret_slot(prefix: str, grant: str, owner_id: str) -> str:
    """Return a non-identifying per-owner, per-grant secret slot.

    The grant is part of the slot, so a read authorization and a write
    authorization can be pending, stored and revoked independently.
    """
    return f"{prefix}:{_spec(grant).connector_id}:{_owner_key(owner_id)}"


def _finite_now(now: Callable[[], float]) -> float:
    value = now()
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise CalendarOAuthError("invalid_clock")
    return float(value)


# The REUSE-R1b (#427) Existing Solutions Review recorded in ``drive_web_oauth``
# governs this decision too: ``oauthlib`` is adopted for authorization-request
# and PKCE construction only. The token exchange stays an injected callable and
# ``_validated_tokens`` below enforces the granted scope itself, because
# ``parse_request_body_response`` is not an authority boundary.
def _pkce_pair() -> tuple[str, str]:
    # "S256" is passed explicitly: ``create_code_challenge`` silently falls back
    # to the unprotected ``plain`` transform when the method is omitted.
    client = WebApplicationClient("")
    verifier = client.create_code_verifier(96)
    return verifier, client.create_code_challenge(verifier, "S256")


@contextmanager
def _lifecycle_guard(registry: ConnectorRegistry, owner_id: str, connector_id: str):
    """Hold the repository-wide ``dispatch -> authority`` lock order.

    ``ConnectorRegistry.transition``, ``personal_agent.gmail`` and
    ``personal_agent.calendar`` all take the per-owner/connector dispatch lock
    before the process-wide authority lock. The authority lock is a single
    module-global, so one inversion can wedge the process; every authority
    check here that may be followed by a transition enters through this guard.
    Both locks are reentrant, so nesting inside this guard is safe.
    """
    _owner_key(owner_id)
    with registry._dispatch_guard(owner_id, (connector_id,)):
        with registry._authority_guard():
            yield


def _contract_error(exc: ConnectorContractError) -> CalendarOAuthError:
    known = {"already_connected", "unknown_connector", "scope_mismatch", "invalid_stored_state"}
    return CalendarOAuthError(exc.reason if exc.reason in known else "invalid_connector_state")


def _mark_reauthentication_required(
    store,
    registry: ConnectorRegistry,
    owner_id: str,
    grant: str,
    *,
    expected_revision: str | None = None,
) -> dict:
    """Clear this grant's credentials and fail closed after expiry/revocation.

    Only the named grant is revoked. A read expiry must not revoke a write
    grant the owner authorized separately, and the reverse.
    """
    connector_id = _spec(grant).connector_id
    with _lifecycle_guard(registry, owner_id, connector_id):
        current = registry.status(owner_id, connector_id)
        if expected_revision is not None and current.connection_revision != expected_revision:
            return current.as_dict()
        store.secret(_secret_slot(TOKEN_SECRET_KEY, grant, owner_id), {})
        if current.state is ConnectorState.CONNECTED:
            registry.transition(owner_id, connector_id, ConnectorState.REAUTH_REQUIRED)
        return registry.status(owner_id, connector_id).as_dict()


def _stored_credential_usable(tokens, owner_id: str, grant: str, now: Callable[[], float]) -> bool:
    """Whether one stored grant credential passes every local request check.

    Pure: local owner, grant, scope and expiry only.  No refresh, network
    request or lifecycle transition, so read-only status surfaces can use it.
    """
    spec = _spec(grant)
    access_token = tokens.get("access_token") if isinstance(tokens, dict) else None
    expires_at = tokens.get("expires_at") if isinstance(tokens, dict) else None
    return not (
        not isinstance(tokens, dict)
        or tokens.get("owner") != _owner_key(owner_id)
        or tokens.get("grant") != grant
        or sorted(tokens.get("scope") or ()) != sorted(spec.required_scopes)
        or not isinstance(access_token, str)
        or not access_token
        or isinstance(expires_at, bool)
        or not isinstance(expires_at, (int, float))
        or not math.isfinite(expires_at)
        or _finite_now(now) >= expires_at
    )


def _authorization_context(
    store,
    registry: ConnectorRegistry,
    owner_id: str,
    grant: str,
    now: Callable[[], float],
) -> tuple[str, str]:
    """Resolve one currently usable access token and its connection revision.

    This is deliberately called per request rather than once per client: a
    long-lived ``GoogleCalendar`` built with a construction-time token would
    keep presenting a token after expiry, refresh, revocation or a lifecycle
    transition, and would keep reporting that stale authority as usable.
    """
    spec = _spec(grant)
    with _lifecycle_guard(registry, owner_id, spec.connector_id):
        try:
            status = registry.require_connected(owner_id, spec.connector_id, spec.required_scopes)
        except ConnectorContractError as exc:
            if exc.reason == ConnectorState.REAUTH_REQUIRED.value:
                raise CalendarReauthenticationRequired("reauth_required") from None
            raise CalendarOAuthError("connection_required") from None
        token_slot = _secret_slot(TOKEN_SECRET_KEY, grant, owner_id)
        try:
            tokens = store.secret(token_slot)
        except CalendarOAuthError:
            # The key or ciphertext is no longer usable. Revoke connector
            # authority before offering recovery; never report structurally
            # connected metadata as usable authority.
            _mark_reauthentication_required(store, registry, owner_id, grant)
            raise CalendarReauthenticationRequired("reauth_required") from None
        if (
            not _stored_credential_usable(tokens, owner_id, grant, now)
            or not isinstance(status.connection_revision, str)
        ):
            _mark_reauthentication_required(store, registry, owner_id, grant)
            raise CalendarReauthenticationRequired("reauth_required")
        return tokens["access_token"], status.connection_revision


def _assert_current_request(
    store,
    registry: ConnectorRegistry,
    owner_id: str,
    grant: str,
    connection_revision: str,
    access_token: str,
) -> None:
    """Refuse a response whose authority changed while the call was in flight."""
    connector_id = _spec(grant).connector_id
    with _lifecycle_guard(registry, owner_id, connector_id):
        current = registry.status(owner_id, connector_id)
        try:
            tokens = store.secret(_secret_slot(TOKEN_SECRET_KEY, grant, owner_id))
        except CalendarOAuthError:
            raise CalendarOAuthError("superseded_connection") from None
        if (
            current.state is not ConnectorState.CONNECTED
            or current.connection_revision != connection_revision
            or not isinstance(tokens, dict)
            or tokens.get("owner") != _owner_key(owner_id)
            or tokens.get("access_token") != access_token
        ):
            raise CalendarOAuthError("superseded_connection")


def _assert_calendar_url(url: object) -> str:
    """Bound where a resolved bearer token may be sent."""
    if not isinstance(url, str) or len(url) > 4096 or not url.startswith(CALENDAR_API + "/"):
        raise CalendarOAuthError("unsupported_destination")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username is not None or parsed.password is not None:
        raise CalendarOAuthError("unsupported_destination")
    return url


def _https_json_opener(timeout: float) -> Callable:
    """Return the default owner-local HTTPS opener.

    It is built lazily and is always replaceable, so tests and offline owners
    never reach the network.
    """
    from urllib.error import HTTPError
    from urllib.request import Request

    from .connector_http import contained_opener

    def permitted(candidate):
        try:
            _assert_calendar_url(candidate)
        except CalendarOAuthError:
            return False
        return True

    # The destination check has to hold on every redirect hop, not only on
    # the URL the caller named. `urllib`'s default handler keeps
    # `Authorization` across a cross-host redirect and permits an
    # https->http downgrade, so a single redirect from an allowlisted host
    # would carry the owner's Calendar token off it -- the same exposure
    # independent review demonstrated on the Gmail transport.
    contained = contained_opener(permitted)

    def opener(method: str, url: str, body, headers: dict):
        payload = None if body is None else json.dumps(body).encode()
        request = Request(url, payload, dict(headers), method=method)
        try:
            with contained.open(request, timeout=timeout) as response:
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
        except HTTPError as error:
            raise GoogleCalendarHTTPError(int(error.code)) from None
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise CalendarOAuthError("oversized_provider_response")
        if not raw:
            return {}
        return json.loads(raw.decode())

    return opener


def calendar_transport(
    secret_store,
    registry: ConnectorRegistry,
    owner_id: str,
    *,
    allow_writes: bool = False,
    opener: Callable | None = None,
    now: Callable[[], float] = time.time,
    timeout: float = 20.0,
) -> Callable:
    """Return a read-only ``(method, url, body, headers)`` Calendar transport.

    Pass the result to ``GoogleCalendar(transport, access_token=None)``. The
    token is resolved **inside every call**, not captured at construction:
    ``GoogleCalendar._headers`` omits ``Authorization`` when ``access_token`` is
    ``None``, so this transport owns the credential and each call re-checks
    connector state, connection revision, grant, scope and token freshness.

    The HTTP method selects the grant, and that is the authority rule: ``GET``
    spends the read grant, every mutating method spends the write grant, and
    the two are separate credentials in separate secret slots.
    ``CalendarConnector`` injects one ``GoogleCalendar`` provider for both
    reads and writes, so a transport that refused mutations outright would
    make the write grant obtainable and unspendable.

    With ``allow_writes=False`` (the default) a mutating method is refused
    before any credential is resolved, so a refused mutation never even loads
    a token. A caller with no business writing keeps that guarantee by not
    asking for it.
    """
    if not getattr(secret_store, "encrypted_secrets", False):
        raise ValueError("Calendar OAuth requires an encrypted owner-local secret store.")
    if not isinstance(registry, ConnectorRegistry):
        raise ValueError("A connector registry is required for a Calendar transport.")
    _owner_key(owner_id)
    if opener is None:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 120:
            raise ValueError("Calendar transport timeout must be between zero and 120 seconds.")
        opener = _https_json_opener(float(timeout))
    if not callable(opener):
        raise ValueError("The Calendar HTTP opener must be callable.")

    def transport(method, url, body, headers):
        reading = method == "GET"
        if not reading and not allow_writes:
            raise CalendarOAuthError("mutation_not_permitted")
        if reading and body is not None:
            raise CalendarOAuthError("mutation_not_permitted")
        url = _assert_calendar_url(url)
        # The grant follows the method. A read can never spend the write
        # credential and a write can never be satisfied by the read one:
        # `_authorization_context` checks scope-set equality against the
        # named grant's spec.
        grant = READ_GRANT if reading else WRITE_GRANT
        access_token, connection_revision = _authorization_context(
            secret_store, registry, owner_id, grant, now
        )
        request_headers = {
            **(headers or {}),
            # Ours wins over any caller-supplied Authorization header.
            "Authorization": "Bearer " + access_token,
            "Accept": "application/json",
        }
        try:
            response = opener(method, url, body if not reading else None, request_headers)
        except GoogleCalendarHTTPError as error:
            if error.status == 401:
                # Revoke the exact revision this call used, then re-raise so
                # ``GoogleCalendar`` still classifies it as ``scope-expired``.
                _mark_reauthentication_required(
                    secret_store,
                    registry,
                    owner_id,
                    grant,
                    expected_revision=connection_revision,
                )
            raise
        _assert_current_request(
            secret_store, registry, owner_id, grant, connection_revision, access_token
        )
        return response

    return transport


class CalendarOAuth:
    """Minimum-authority Google Calendar OAuth for two independent grants."""

    #: Held by ``complete_oauth``/``refresh`` through token commit;
    #: provider-revocation retry (#588) holds it so no completion interleaves.
    oauth_lock = _OAUTH_LOCK

    def __init__(
        self,
        store,
        client_id: str,
        redirect_uri: str,
        *,
        registry: ConnectorRegistry | None = None,
        now: Callable[[], float] = time.time,
        oauth_ttl_seconds: float = 600,
        allow_localhost: bool = False,
    ):
        if not getattr(store, "encrypted_secrets", False):
            raise ValueError("Calendar OAuth requires an encrypted owner-local secret store.")
        if not isinstance(client_id, str) or not client_id.strip() or len(client_id) > 512:
            raise ValueError("A Calendar OAuth client id is required.")
        parsed = urlsplit(redirect_uri) if isinstance(redirect_uri, str) else None
        is_loopback = bool(
            parsed
            and parsed.scheme == "http"
            and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        )
        if (
            not parsed
            or not parsed.hostname
            or len(redirect_uri) > 2048
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or (parsed.scheme != "https" and not (allow_localhost and is_loopback))
        ):
            raise ValueError(
                "The Calendar OAuth callback must use HTTPS or an explicitly allowed loopback URL."
            )
        if (
            isinstance(oauth_ttl_seconds, bool)
            or not isinstance(oauth_ttl_seconds, (int, float))
            or not 1 <= oauth_ttl_seconds <= 1800
        ):
            raise ValueError("Calendar OAuth state lifetime must be between one and 1,800 seconds.")
        self.store = store
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.now = now
        self.oauth_ttl_seconds = float(oauth_ttl_seconds)
        self.registry = registry or ConnectorRegistry(store, (), clock=now)
        # Definition only. ``register`` writes no owner row, so both connectors
        # keep reading DISCONNECTED until an owner completes an authorization
        # here and ``transition`` commits the exact required scope set.
        # Registering is honest at this point precisely because constructing
        # this object means a callback route exists that can complete one.
        self.registry.register(CALENDAR_SPEC)
        self.registry.register(CALENDAR_WRITE_SPEC)

    def status(self, owner_id: str, *, write: bool = False) -> dict:
        """Return restart-safe lifecycle metadata with no OAuth or event data."""
        grant = _grant_label(write)
        try:
            return self.registry.status(owner_id, _spec(grant).connector_id).as_dict()
        except ConnectorContractError as exc:
            raise _contract_error(exc) from None

    def credential_current(self, owner_id: str, *, write: bool = False) -> bool:
        """Read-only: would the next request for this grant accept its stored credential?

        A CONNECTED row stays CONNECTED until a request finds the token
        expired; status surfaces use this to report that truthfully without
        recording the transition, refreshing, or contacting Google.
        """
        grant = _grant_label(write)
        try:
            tokens = self.store.secret(_secret_slot(TOKEN_SECRET_KEY, grant, owner_id))
            return _stored_credential_usable(tokens, owner_id, grant, self.now)
        except CalendarOAuthError:
            return False

    def connection_required(self, owner_id: str, *, write: bool = False) -> dict:
        grant = _grant_label(write)
        try:
            return self.registry.required_result(owner_id, _spec(grant).connector_id).as_dict()
        except ConnectorContractError as exc:
            raise _contract_error(exc) from None

    def begin_oauth(self, owner_id: str, *, write: bool = False) -> dict:
        """Start one grant's authorization and return its redirect offer."""
        grant = _grant_label(write)
        spec = _spec(grant)
        owner = _owner_key(owner_id)
        created_at = _finite_now(self.now)
        verifier, challenge = _pkce_pair()
        nonce = secrets.token_urlsafe(32)
        signing_key = secrets.token_bytes(32)
        signature = hmac.new(
            signing_key, f"{owner}:{grant}:{nonce}".encode(), hashlib.sha256
        ).hexdigest()
        # One callback route serves both Calendar grants, so the state has to
        # say which grant is completing. The label is the first segment; it
        # selects which pending slot to load and is covered by the HMAC, whose
        # per-authorization signing key lives only in that slot. A relabelled
        # state therefore addresses the other grant's slot, where its signature
        # does not verify - the label is a routing hint, never the authority.
        state = f"{grant}.{nonce}.{signature}"
        with _OAUTH_LOCK:
            with _lifecycle_guard(self.registry, owner_id, spec.connector_id):
                current = self.registry.status(owner_id, spec.connector_id)
                if current.state is ConnectorState.CONNECTED:
                    raise CalendarOAuthError("already_connected")
                if current.state is ConnectorState.BLOCKED:
                    raise CalendarOAuthError("blocked")
                pending = {
                    "status": "pending",
                    "owner": owner,
                    "grant": grant,
                    "signing_key": base64.urlsafe_b64encode(signing_key).decode(),
                    "verifier": verifier,
                    "created_at": created_at,
                    "expires_at": created_at + self.oauth_ttl_seconds,
                    "connector_state": current.state.value,
                    "connection_revision": current.connection_revision,
                }
                self.store.secret(_secret_slot(PENDING_SECRET_KEY, grant, owner_id), pending)
        authorization_url = WebApplicationClient(self.client_id).prepare_request_uri(
            AUTHORIZATION_ENDPOINT,
            redirect_uri=self.redirect_uri,
            scope=list(spec.required_scopes),
            state=state,
            code_challenge=challenge,
            code_challenge_method="S256",
            access_type="offline",
            # Never widen the grant to scopes this owner approved elsewhere: a
            # read authorization must not return a write scope because the
            # owner once granted one.
            include_granted_scopes="false",
        )
        required = self.connection_required(owner_id, write=write)
        return {
            **required,
            "grant": grant,
            "authorization_url": authorization_url,
            "expires_at": pending["expires_at"],
        }

    @staticmethod
    def pending_grant(callback) -> str | None:
        """Which grant a callback *claims* to be completing. A hint, not authority.

        The caller needs this before `complete_oauth` runs, because which
        grant is completing decides which owner identity may complete it and
        which parked record to read -- and `complete_oauth` consumes the
        pending state, so it is too late afterwards.

        This reads the leading label off the state and nothing else. It does
        NOT verify the signature: `_pending` does that, against the slot the
        label selects, and a relabelled state lands on the other grant's slot
        where its HMAC does not verify. So a lie here changes which slot is
        consulted and cannot mint authority. Returning `None` for anything
        unrecognised keeps the caller on the read grant, which is the
        narrower of the two.
        """
        if not isinstance(callback, dict):
            return None
        state = callback.get("state")
        if not isinstance(state, str):
            return None
        label = state.split(".", 1)[0]
        return label if label in (READ_GRANT, WRITE_GRANT) else None

    def complete_oauth(self, owner_id: str, callback: dict, exchange: Callable[[dict], dict]) -> dict:
        """Complete whichever grant the signed callback state identifies."""
        if not isinstance(callback, dict) or not callable(exchange):
            raise CalendarOAuthError("invalid_callback")
        with _OAUTH_LOCK:
            grant, pending = self._pending(owner_id, callback.get("state"))
            spec = _spec(grant)
            pending_slot = _secret_slot(PENDING_SECRET_KEY, grant, owner_id)
            # Consume before inspecting the code or contacting the provider so
            # every callback, including a failing one, is single use.
            self.store.secret(pending_slot, {"status": "used"})
            if callback.get("error"):
                raise CalendarOAuthError("authorization_denied")
            code = callback.get("code")
            if not isinstance(code, str) or not code or len(code) > 4096:
                raise CalendarOAuthError("invalid_callback")
            self._assert_unchanged_authority(owner_id, spec, pending)
            request = {
                "code": code,
                "code_verifier": pending["verifier"],
                "redirect_uri": self.redirect_uri,
                "client_id": self.client_id,
                "grant_type": "authorization_code",
            }
            try:
                response = exchange(request)
            except Exception:
                # The injected exchange holds the client secret. Never let its
                # text, arguments or chained context escape this boundary.
                raise CalendarOAuthError("token_exchange_failed") from None
            tokens = self._validated_tokens(response, pending["owner"], grant)
            with _lifecycle_guard(self.registry, owner_id, spec.connector_id):
                self._assert_unchanged_authority(owner_id, spec, pending)
                token_slot = _secret_slot(TOKEN_SECRET_KEY, grant, owner_id)
                self.store.secret(token_slot, tokens)
                try:
                    self.registry.transition(
                        owner_id,
                        spec.connector_id,
                        ConnectorState.CONNECTED,
                        granted_scopes=spec.required_scopes,
                    )
                except Exception:
                    # Never leave usable credentials behind if durable
                    # lifecycle metadata cannot be committed.
                    self.store.secret(token_slot, {})
                    raise CalendarOAuthError("connection_commit_failed") from None
            return self.status(owner_id, write=(grant == WRITE_GRANT))

    def refresh(self, owner_id: str, exchange: Callable[[dict], dict], *, write: bool = False) -> dict:
        """Replace one grant's access token without changing its authority.

        The refresh is grant-scoped and revision-pinned: it never widens the
        scope set, never revives a disconnected grant, and never writes a token
        for a connection that was rotated while the exchange was in flight.
        """
        if not callable(exchange):
            raise CalendarOAuthError("invalid_callback")
        grant = _grant_label(write)
        spec = _spec(grant)
        owner = _owner_key(owner_id)
        with _OAUTH_LOCK:
            token_slot = _secret_slot(TOKEN_SECRET_KEY, grant, owner_id)
            with _lifecycle_guard(self.registry, owner_id, spec.connector_id):
                try:
                    status = self.registry.require_connected(
                        owner_id, spec.connector_id, spec.required_scopes
                    )
                except ConnectorContractError:
                    raise CalendarReauthenticationRequired("reauth_required") from None
                tokens = self.store.secret(token_slot)
                refresh_token = tokens.get("refresh_token") if isinstance(tokens, dict) else None
                if (
                    not isinstance(tokens, dict)
                    or tokens.get("owner") != owner
                    or tokens.get("grant") != grant
                    or not isinstance(refresh_token, str)
                    or not refresh_token
                ):
                    raise CalendarOAuthError("refresh_unavailable")
                revision = status.connection_revision
            try:
                response = exchange(
                    {
                        "refresh_token": refresh_token,
                        "client_id": self.client_id,
                        "grant_type": "refresh_token",
                    }
                )
            except Exception:
                raise CalendarOAuthError("token_refresh_failed") from None
            renewed = self._validated_tokens(
                response, owner, grant, carry_refresh=refresh_token, scope_optional=True
            )
            with _lifecycle_guard(self.registry, owner_id, spec.connector_id):
                current = self.registry.status(owner_id, spec.connector_id)
                if (
                    current.state is not ConnectorState.CONNECTED
                    or current.connection_revision != revision
                ):
                    raise CalendarOAuthError("superseded_connection")
                self.store.secret(token_slot, renewed)
        return self.status(owner_id, write=write)

    def mark_reauthentication_required(
        self,
        owner_id: str,
        *,
        write: bool = False,
        expected_revision: str | None = None,
    ) -> dict:
        return _mark_reauthentication_required(
            self.store,
            self.registry,
            owner_id,
            _grant_label(write),
            expected_revision=expected_revision,
        )

    def disconnect(self, owner_id: str, stash: Callable[[dict | None], None], *, write: bool = False) -> dict:
        """Owner disconnect of exactly one grant (CONNECTOR-REVOKE-01 #588).

        Same shape as ``GmailConnector.disconnect``: ``stash`` sees the stored
        credential before it is cleared, the grant's pending authorization is
        consumed, and the row moves to DISCONNECTED with a new revision so an
        in-flight request or refresh for the old revision is refused. The
        other grant is untouched locally. A BLOCKED row stays BLOCKED.
        """
        grant = _grant_label(write)
        spec = _spec(grant)
        with _OAUTH_LOCK:
            with _lifecycle_guard(self.registry, owner_id, spec.connector_id):
                current = self.registry.status(owner_id, spec.connector_id)
                token_slot = _secret_slot(TOKEN_SECRET_KEY, grant, owner_id)
                try:
                    tokens = self.store.secret(token_slot)
                except CalendarOAuthError:
                    tokens = None
                stash(tokens if isinstance(tokens, dict) and tokens else None)
                self.store.secret(token_slot, {})
                self.store.secret(_secret_slot(PENDING_SECRET_KEY, grant, owner_id), {"status": "used"})
                if current.state not in (ConnectorState.DISCONNECTED, ConnectorState.BLOCKED):
                    self.registry.transition(owner_id, spec.connector_id, ConnectorState.DISCONNECTED)
        return self.status(owner_id, write=write)

    def _assert_unchanged_authority(self, owner_id: str, spec: ConnectorSpec, pending: dict) -> None:
        with _lifecycle_guard(self.registry, owner_id, spec.connector_id):
            current = self.registry.status(owner_id, spec.connector_id)
            if (
                current.state.value != pending.get("connector_state")
                or current.connection_revision != pending.get("connection_revision")
            ):
                raise CalendarOAuthError("connector_authority_changed")

    def _pending(self, owner_id: str, state: object) -> tuple[str, dict]:
        """Resolve the signed callback state to exactly one pending grant.

        Every predicate below is the sole guard for one failure it names; the
        full state string is intentionally not stored and re-compared, so no
        check here is shadowed by another.
        """
        owner = _owner_key(owner_id)
        if not isinstance(state, str) or not 1 <= len(state) <= 512:
            raise CalendarOAuthError("invalid_state")
        parts = state.split(".")
        if len(parts) != 3:
            raise CalendarOAuthError("invalid_state")
        grant, nonce, signature = parts
        if (
            grant not in _GRANTS
            or _NONCE.fullmatch(nonce) is None
            or _SIGNATURE.fullmatch(signature) is None
        ):
            raise CalendarOAuthError("invalid_state")
        pending_slot = _secret_slot(PENDING_SECRET_KEY, grant, owner_id)
        pending = self.store.secret(pending_slot)
        if not isinstance(pending, dict) or pending.get("status") != "pending":
            raise CalendarOAuthError("missing_or_replayed_state")
        if pending.get("grant") != grant:
            raise CalendarOAuthError("invalid_state")
        stored_owner = pending.get("owner")
        if not isinstance(stored_owner, str) or not secrets.compare_digest(stored_owner, owner):
            raise CalendarOAuthError("wrong_owner")
        try:
            encoded_key = pending["signing_key"]
            if not isinstance(encoded_key, str):
                raise ValueError("signing key")
            signing_key = base64.b64decode(
                encoded_key + "=" * (-len(encoded_key) % 4),
                altchars=b"-_",
                validate=True,
            )
            if len(signing_key) != 32:
                raise ValueError("signing key")
        except (KeyError, TypeError, ValueError):
            raise CalendarOAuthError("invalid_state") from None
        # The owner and the grant are inside the signed message, so a state
        # issued for the read grant cannot be relabelled into a write
        # completion and a state issued for another owner cannot be replayed
        # into this owner's pending authorization.
        expected = hmac.new(
            signing_key, f"{owner}:{grant}:{nonce}".encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise CalendarOAuthError("state_mismatch")
        expires_at = pending.get("expires_at")
        if (
            isinstance(expires_at, bool)
            or not isinstance(expires_at, (int, float))
            or not math.isfinite(expires_at)
        ):
            raise CalendarOAuthError("invalid_state")
        if _finite_now(self.now) >= expires_at:
            self.store.secret(pending_slot, {"status": "used"})
            raise CalendarOAuthError("state_expired")
        verifier = pending.get("verifier")
        if not isinstance(verifier, str) or _VERIFIER.fullmatch(verifier) is None:
            raise CalendarOAuthError("invalid_state")
        return grant, pending

    def _validated_tokens(
        self,
        response: object,
        owner: str,
        grant: str,
        *,
        carry_refresh: str | None = None,
        scope_optional: bool = False,
    ) -> dict:
        """Accept a token response only for this grant's exact scope set."""
        spec = _spec(grant)
        if not isinstance(response, dict):
            raise CalendarOAuthError("token_exchange_failed")
        access_token = response.get("access_token")
        expires_in = response.get("expires_in")
        granted = response.get("scope")
        if granted is None and scope_optional:
            granted_scopes = set(spec.required_scopes)
        else:
            granted_scopes = set(str(granted).split())
        if (
            not isinstance(access_token, str)
            or not access_token
            or len(access_token) > 16_384
            or isinstance(expires_in, bool)
            or not isinstance(expires_in, (int, float))
            or not math.isfinite(expires_in)
            or expires_in <= 0
            or expires_in > 86_400
            # Exact set equality. A read authorization that comes back carrying
            # the write scope is refused rather than stored: the owner approved
            # one grant, and the connector may only hold what it requires.
            or granted_scopes != set(spec.required_scopes)
        ):
            raise CalendarOAuthError("token_exchange_failed")
        tokens = {
            "owner": owner,
            "grant": grant,
            "access_token": access_token,
            "scope": list(spec.required_scopes),
            "expires_at": _finite_now(self.now) + float(expires_in),
        }
        refresh_token = response.get("refresh_token", carry_refresh)
        if refresh_token is not None:
            if not isinstance(refresh_token, str) or not refresh_token or len(refresh_token) > 16_384:
                raise CalendarOAuthError("token_exchange_failed")
            tokens["refresh_token"] = refresh_token
        return tokens
