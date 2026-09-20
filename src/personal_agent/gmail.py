"""Owner-bound, read-only Gmail connector for the PA1 first completion.

OAuth state and credentials stay in the encrypted owner-local secret boundary.
Only redacted lifecycle metadata is delegated to :mod:`connector_contract`.
The provider surface is deliberately limited to bounded search/metadata reads
and an explicit selected-message body read; this module has no Gmail mutation
request primitive.
"""

from __future__ import annotations

import base64
import codecs
from dataclasses import dataclass
from email.errors import HeaderParseError
from email.header import decode_header
from email.message import Message
import hashlib
import hmac
import json
import math
import re
import secrets
import threading
import time
from typing import Callable
from urllib.parse import quote, urlencode, urlsplit

from cryptography.fernet import Fernet, InvalidToken

from .connector_contract import (
    ConnectorContractError,
    ConnectorRegistry,
    ConnectorSpec,
    ConnectorState,
)


GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_CONNECTOR_ID = "google-gmail-read"
GMAIL_CONNECTOR = ConnectorSpec(GMAIL_CONNECTOR_ID, (GMAIL_READONLY_SCOPE,))
AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
MESSAGES_ENDPOINT = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
PENDING_SECRET_KEY = "gmail_oauth_pending"
TOKEN_SECRET_KEY = "gmail_oauth_tokens"
_MAX_RESULTS = 20
_MAX_QUERY_LENGTH = 512
_MAX_BODY_BYTES = 1_048_576
_MESSAGE_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_ATTACHMENT_ID = re.compile(r"[A-Za-z0-9_-]{1,4096}\Z")
_OAUTH_LOCK = threading.RLock()


class GmailError(ValueError):
    """A fail-closed Gmail error whose text does not disclose private data."""

    def __init__(self, reason: str = "rejected"):
        super().__init__("Gmail request rejected")
        self.reason = reason


class GmailReauthenticationRequired(GmailError):
    pass


class EncryptedGmailSecretStore:
    """Encrypt Gmail-only OAuth secrets using a caller-owned local key.

    The key is never persisted here. Copying the ordinary owner database or
    its connection file alone therefore does not reveal OAuth state or tokens.
    """

    encrypted_secrets = True

    def __init__(self, store, key: str | bytes):
        if not isinstance(key, (str, bytes)):
            raise ValueError("A local encryption key is required for Gmail OAuth.")
        try:
            self._cipher = Fernet(key.encode() if isinstance(key, str) else key)
        except (TypeError, ValueError) as exc:
            raise ValueError("A valid local encryption key is required for Gmail OAuth.") from exc
        self._store = store

    def secret(self, key: str, value=None):
        namespaced = "encrypted:gmail:" + key
        if value is not None:
            payload = json.dumps(value, separators=(",", ":")).encode()
            self._store.secret(namespaced, self._cipher.encrypt(payload).decode())
        raw = self._store.secret(namespaced)
        if not raw:
            return ""
        try:
            return json.loads(self._cipher.decrypt(str(raw).encode()).decode())
        except (InvalidToken, TypeError, ValueError, json.JSONDecodeError):
            raise GmailError("unreadable_secret") from None

    def config(self, key: str, default=None):
        return self._store.config(key, default)

    def put(self, key: str, value) -> None:
        self._store.put(key, value)


@dataclass(frozen=True, repr=False)
class GmailSearchResult:
    message_id: str
    thread_id: str
    connection_revision: str
    subject: str
    sender: str
    date: str

    @property
    def source(self) -> dict:
        return {
            "provider": "gmail",
            "resource": "message",
            "message_id": self.message_id,
            "thread_id": self.thread_id,
            "connection_revision": self.connection_revision,
        }

    def as_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "thread_id": self.thread_id,
            "subject": self.subject,
            "sender": self.sender,
            "date": self.date,
            "source": self.source,
        }

    def __repr__(self) -> str:
        return f"GmailSearchResult(message_id={self.message_id!r}, metadata=<redacted>)"


@dataclass(frozen=True, repr=False)
class GmailMessage:
    """An ephemeral explicit body read; callers must not persist ``body``."""

    message_id: str
    thread_id: str
    connection_revision: str
    mime_type: str
    body: str

    @property
    def source(self) -> dict:
        return {
            "provider": "gmail",
            "resource": "message",
            "message_id": self.message_id,
            "thread_id": self.thread_id,
            "connection_revision": self.connection_revision,
        }

    def as_dict(self) -> dict:
        """Return the private task result for the immediate authorized caller."""
        return {
            "message_id": self.message_id,
            "thread_id": self.thread_id,
            "mime_type": self.mime_type,
            "body": self.body,
            "source": self.source,
        }

    def as_evidence(self) -> dict:
        """Return portable source evidence without private message content."""
        return {"source": self.source, "body_included": False}

    def __repr__(self) -> str:
        return f"GmailMessage(message_id={self.message_id!r}, body=<redacted>)"


def _owner_key(owner_id: str) -> str:
    if not isinstance(owner_id, str) or not owner_id.strip() or len(owner_id) > 200:
        raise GmailError("invalid_owner")
    return hashlib.sha256(owner_id.encode()).hexdigest()


def _owner_secret_key(prefix: str, owner_id: str) -> str:
    """Return a non-identifying per-owner secret slot."""
    return f"{prefix}:{_owner_key(owner_id)}"


def _finite_now(now: Callable[[], float]) -> float:
    value = now()
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise GmailError("invalid_clock")
    return float(value)


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _bounded_text(value: object, maximum: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:maximum]


def _decoded_header(value: object, maximum: int) -> str:
    if not isinstance(value, str) or len(value) > 4096:
        raise GmailError("invalid_provider_response")
    try:
        parts = []
        for fragment, charset in decode_header(value):
            if isinstance(fragment, bytes):
                parts.append(fragment.decode(charset or "ascii"))
            elif isinstance(fragment, str):
                parts.append(fragment)
            else:
                raise TypeError("invalid header fragment")
        return _bounded_text("".join(parts), maximum)
    except (HeaderParseError, LookupError, TypeError, ValueError, UnicodeError):
        raise GmailError("invalid_provider_response") from None


class GmailConnector:
    """Minimum-authority Gmail OAuth, bounded search, and explicit body read."""

    def __init__(
        self,
        store,
        client_id: str,
        redirect_uri: str,
        *,
        registry: ConnectorRegistry | None = None,
        transport: Callable | None = None,
        now: Callable[[], float] = time.time,
        oauth_ttl_seconds: float = 600,
        allow_localhost: bool = False,
    ):
        if not getattr(store, "encrypted_secrets", False):
            raise ValueError("Gmail OAuth requires an encrypted owner-local secret store.")
        if not isinstance(client_id, str) or not client_id.strip() or len(client_id) > 512:
            raise ValueError("A Gmail OAuth client id is required.")
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
            raise ValueError("The Gmail OAuth callback must use HTTPS or an explicitly allowed loopback URL.")
        if (
            isinstance(oauth_ttl_seconds, bool)
            or not isinstance(oauth_ttl_seconds, (int, float))
            or not 1 <= oauth_ttl_seconds <= 1800
        ):
            raise ValueError("Gmail OAuth state lifetime must be between one and 1,800 seconds.")
        self.store = store
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.transport = transport
        self.now = now
        self.oauth_ttl_seconds = float(oauth_ttl_seconds)
        self.registry = registry or ConnectorRegistry(store, (GMAIL_CONNECTOR,), clock=now)
        self.registry.register(GMAIL_CONNECTOR)

    def status(self, owner_id: str) -> dict:
        """Return restart-safe lifecycle metadata with no OAuth or mail data."""
        return self.registry.status(owner_id, GMAIL_CONNECTOR_ID).as_dict()

    def portable_status(self, owner_id: str) -> dict:
        return self.status(owner_id)

    def connection_required(self, owner_id: str) -> dict:
        return self.registry.required_result(owner_id, GMAIL_CONNECTOR_ID).as_dict()

    def begin_oauth(self, owner_id: str) -> dict:
        owner = _owner_key(owner_id)
        created_at = _finite_now(self.now)
        verifier, challenge = _pkce_pair()
        nonce = secrets.token_urlsafe(32)
        signing_key = secrets.token_bytes(32)
        signature = hmac.new(signing_key, f"{owner}:{nonce}".encode(), hashlib.sha256).hexdigest()
        state = nonce + "." + signature
        with _OAUTH_LOCK:
            with self.registry._authority_guard():
                current = self.registry.status(owner_id, GMAIL_CONNECTOR_ID)
                if current.state is ConnectorState.CONNECTED:
                    raise GmailError("already_connected")
                if current.state is ConnectorState.BLOCKED:
                    raise GmailError("blocked")
                pending = {
                    "status": "pending",
                    "owner": owner,
                    "state": state,
                    "signing_key": base64.urlsafe_b64encode(signing_key).decode(),
                    "verifier": verifier,
                    "created_at": created_at,
                    "expires_at": created_at + self.oauth_ttl_seconds,
                    "connector_state": current.state.value,
                    "connection_revision": current.connection_revision,
                }
                self.store.secret(f"{PENDING_SECRET_KEY}:{owner}", pending)
        query = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": GMAIL_READONLY_SCOPE,
            "access_type": "offline",
            "include_granted_scopes": "false",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
        required = self.registry.required_result(owner_id, GMAIL_CONNECTOR_ID).as_dict()
        return {
            **required,
            "authorization_url": AUTHORIZATION_ENDPOINT + "?" + urlencode(query),
            "expires_at": pending["expires_at"],
        }

    def complete_oauth(self, owner_id: str, callback: dict, exchange: Callable[[dict], dict]) -> dict:
        if not isinstance(callback, dict) or not callable(exchange):
            raise GmailError("invalid_callback")
        with _OAUTH_LOCK:
            pending = self._pending(owner_id, callback.get("state"))
            # Consume before inspecting the code or contacting the provider so
            # every callback, including failure, is single use across handlers.
            self.store.secret(_owner_secret_key(PENDING_SECRET_KEY, owner_id), {"status": "used"})
            if callback.get("error"):
                raise GmailError("authorization_denied")
            code = callback.get("code")
            if not isinstance(code, str) or not code or len(code) > 4096:
                raise GmailError("invalid_callback")
            with self.registry._authority_guard():
                current = self.registry.status(owner_id, GMAIL_CONNECTOR_ID)
                if (
                    current.state.value != pending.get("connector_state")
                    or current.connection_revision != pending.get("connection_revision")
                ):
                    raise GmailError("connector_authority_changed")
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
                raise GmailError("token_exchange_failed") from None
            tokens = self._validated_tokens(response, pending["owner"])
            with self.registry._authority_guard():
                current = self.registry.status(owner_id, GMAIL_CONNECTOR_ID)
                if (
                    current.state.value != pending.get("connector_state")
                    or current.connection_revision != pending.get("connection_revision")
                ):
                    raise GmailError("connector_authority_changed")
                token_key = _owner_secret_key(TOKEN_SECRET_KEY, owner_id)
                self.store.secret(token_key, tokens)
                try:
                    self.registry.transition(
                        owner_id,
                        GMAIL_CONNECTOR_ID,
                        ConnectorState.CONNECTED,
                        granted_scopes=(GMAIL_READONLY_SCOPE,),
                    )
                except Exception:
                    # Never leave usable credentials behind if durable lifecycle
                    # metadata cannot be committed.
                    self.store.secret(token_key, {})
                    raise GmailError("connection_commit_failed") from None
            return self.status(owner_id)

    def search(self, owner_id: str, query: str, *, max_results: int = 10) -> tuple[GmailSearchResult, ...]:
        if not isinstance(query, str) or not query.strip() or len(query) > _MAX_QUERY_LENGTH:
            raise GmailError("invalid_query")
        if isinstance(max_results, bool) or not isinstance(max_results, int) or not 1 <= max_results <= _MAX_RESULTS:
            raise GmailError("invalid_limit")
        headers, connection_revision, access_token = self._authorization_context(owner_id)
        response = self._get(
            owner_id,
            MESSAGES_ENDPOINT,
            {"q": query.strip(), "maxResults": max_results, "includeSpamTrash": False},
            headers,
            connection_revision,
            access_token,
        )
        messages = response.get("messages", [])
        if not isinstance(messages, list):
            raise GmailError("invalid_provider_response")
        results = []
        for reference in messages[:max_results]:
            if not isinstance(reference, dict):
                raise GmailError("invalid_provider_response")
            message_id = self._message_id(reference.get("id"))
            metadata = self._get(
                owner_id,
                MESSAGES_ENDPOINT + "/" + quote(message_id, safe=""),
                {
                    "format": "metadata",
                    "metadataHeaders": ["Subject", "From", "Date"],
                },
                headers,
                connection_revision,
                access_token,
            )
            result = self._search_result(message_id, metadata, connection_revision)
            self._assert_current_request(owner_id, connection_revision, access_token)
            results.append(result)
        return tuple(results)

    def read_message(
        self,
        owner_id: str,
        message_id: str,
        *,
        expected_connection_revision: str,
    ) -> GmailMessage:
        """Explicitly fetch one attributed body without retaining it locally."""
        message_id = self._message_id(message_id)
        headers, connection_revision, access_token = self._authorization_context(owner_id)
        if (
            not isinstance(expected_connection_revision, str)
            or not expected_connection_revision
            or expected_connection_revision != connection_revision
        ):
            raise GmailError("superseded_connection")
        response = self._get(
            owner_id,
            MESSAGES_ENDPOINT + "/" + quote(message_id, safe=""),
            {"format": "full"},
            headers,
            connection_revision,
            access_token,
        )
        returned_id = self._message_id(response.get("id"))
        if returned_id != message_id:
            raise GmailError("invalid_provider_response")
        thread_id = self._message_id(response.get("threadId"))
        def load_attachment(attachment_id: str) -> str:
            if not _ATTACHMENT_ID.fullmatch(attachment_id):
                raise GmailError("invalid_provider_response")
            attachment = self._get(
                owner_id,
                MESSAGES_ENDPOINT
                + "/"
                + quote(message_id, safe="")
                + "/attachments/"
                + quote(attachment_id, safe=""),
                {},
                headers,
                connection_revision,
                access_token,
            )
            encoded = attachment.get("data")
            if not isinstance(encoded, str):
                raise GmailError("invalid_provider_response")
            return encoded

        body, mime_type = self._body(response.get("payload"), load_attachment)
        self._assert_current_request(owner_id, connection_revision, access_token)
        return GmailMessage(message_id, thread_id, connection_revision, mime_type, body)

    def mark_reauthentication_required(
        self,
        owner_id: str,
        *,
        expected_revision: str | None = None,
    ) -> dict:
        """Clear Gmail credentials and fail closed after expiry or revocation."""
        with self.registry._authority_guard():
            current = self.registry.status(owner_id, GMAIL_CONNECTOR_ID)
            if expected_revision is not None and current.connection_revision != expected_revision:
                return current.as_dict()
            self.store.secret(_owner_secret_key(TOKEN_SECRET_KEY, owner_id), {})
            if current.state is ConnectorState.CONNECTED:
                self.registry.transition(owner_id, GMAIL_CONNECTOR_ID, ConnectorState.REAUTH_REQUIRED)
        return self.status(owner_id)

    def _pending(self, owner_id: str, state: object) -> dict:
        pending_key = _owner_secret_key(PENDING_SECRET_KEY, owner_id)
        pending = self.store.secret(pending_key)
        if not isinstance(pending, dict) or pending.get("status") != "pending":
            raise GmailError("missing_or_replayed_state")
        owner = _owner_key(owner_id)
        if owner != pending.get("owner"):
            raise GmailError("wrong_owner")
        try:
            supplied_state = state.encode("ascii") if isinstance(state, str) and len(state) <= 512 else b""
            expected_state = str(pending.get("state", "")).encode("ascii")
        except UnicodeEncodeError:
            raise GmailError("state_mismatch") from None
        if not supplied_state or not secrets.compare_digest(supplied_state, expected_state):
            raise GmailError("state_mismatch")
        try:
            nonce, signature = state.rsplit(".", 1)
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
            expected = hmac.new(signing_key, f"{owner}:{nonce}".encode(), hashlib.sha256).hexdigest()
        except (AttributeError, KeyError, TypeError, ValueError):
            raise GmailError("invalid_state") from None
        if not hmac.compare_digest(signature, expected):
            raise GmailError("state_mismatch")
        expires_at = pending.get("expires_at")
        if (
            isinstance(expires_at, bool)
            or not isinstance(expires_at, (int, float))
            or not math.isfinite(expires_at)
        ):
            raise GmailError("invalid_state")
        if _finite_now(self.now) >= expires_at:
            self.store.secret(pending_key, {"status": "used"})
            raise GmailError("state_expired")
        verifier = pending.get("verifier")
        if (
            not isinstance(verifier, str)
            or not 43 <= len(verifier) <= 128
            or re.fullmatch(r"[A-Za-z0-9._~-]+", verifier) is None
        ):
            raise GmailError("invalid_state")
        return pending

    def _validated_tokens(self, response: object, owner: str) -> dict:
        if not isinstance(response, dict):
            raise GmailError("token_exchange_failed")
        access_token = response.get("access_token")
        expires_in = response.get("expires_in")
        granted = response.get("scope")
        if (
            not isinstance(access_token, str)
            or not access_token
            or len(access_token) > 16_384
            or isinstance(expires_in, bool)
            or not isinstance(expires_in, (int, float))
            or not math.isfinite(expires_in)
            or expires_in <= 0
            or expires_in > 86_400
            or set(str(granted).split()) != {GMAIL_READONLY_SCOPE}
        ):
            raise GmailError("token_exchange_failed")
        tokens = {
            "owner": owner,
            "access_token": access_token,
            "scope": GMAIL_READONLY_SCOPE,
            "expires_at": _finite_now(self.now) + float(expires_in),
        }
        refresh_token = response.get("refresh_token")
        if refresh_token is not None:
            if not isinstance(refresh_token, str) or not refresh_token or len(refresh_token) > 16_384:
                raise GmailError("token_exchange_failed")
            tokens["refresh_token"] = refresh_token
        return tokens

    def _authorization_context(self, owner_id: str) -> tuple[dict, str, str]:
        with self.registry._authority_guard():
            try:
                status = self.registry.require_connected(owner_id, GMAIL_CONNECTOR_ID, (GMAIL_READONLY_SCOPE,))
            except ConnectorContractError as exc:
                if exc.reason == ConnectorState.REAUTH_REQUIRED.value:
                    raise GmailReauthenticationRequired("reauth_required") from None
                raise GmailError("connection_required") from None
            token_key = _owner_secret_key(TOKEN_SECRET_KEY, owner_id)
            try:
                tokens = self.store.secret(token_key)
            except GmailError:
                # The encryption key or ciphertext is no longer usable. Revoke
                # connector authority before offering recovery; never report the
                # structurally connected metadata as usable.
                self.mark_reauthentication_required(owner_id)
                raise GmailReauthenticationRequired("reauth_required") from None
            if not isinstance(tokens, dict) or tokens.get("owner") != _owner_key(owner_id):
                self.mark_reauthentication_required(owner_id)
                raise GmailReauthenticationRequired("reauth_required")
            access_token = tokens.get("access_token")
            expires_at = tokens.get("expires_at")
            if (
                not isinstance(access_token, str)
                or not access_token
                or isinstance(expires_at, bool)
                or not isinstance(expires_at, (int, float))
                or not math.isfinite(expires_at)
                or _finite_now(self.now) >= expires_at
                or tokens.get("scope") != GMAIL_READONLY_SCOPE
                or not isinstance(status.connection_revision, str)
            ):
                self.mark_reauthentication_required(owner_id)
                raise GmailReauthenticationRequired("reauth_required")
            return (
                {"Authorization": "Bearer " + access_token, "Accept": "application/json"},
                status.connection_revision,
                access_token,
            )

    def _get(
        self,
        owner_id: str,
        endpoint: str,
        params: dict,
        headers: dict,
        connection_revision: str,
        access_token: str,
    ) -> dict:
        self._assert_current_request(owner_id, connection_revision, access_token)
        if not callable(self.transport):
            raise GmailError("transport_unavailable")
        try:
            response = self.transport("GET", endpoint, params, headers)
        except Exception:
            raise GmailError("provider_unavailable") from None
        if isinstance(response, dict):
            self._assert_current_request(owner_id, connection_revision, access_token)
            status = response.get("status_code")
            if status == 401:
                with self.registry._authority_guard():
                    current = self.registry.status(owner_id, GMAIL_CONNECTOR_ID)
                    token_key = _owner_secret_key(TOKEN_SECRET_KEY, owner_id)
                    current_tokens = self.store.secret(token_key)
                    if (
                        current.state is not ConnectorState.CONNECTED
                        or current.connection_revision != connection_revision
                        or not isinstance(current_tokens, dict)
                        or current_tokens.get("access_token") != access_token
                    ):
                        raise GmailError("superseded_connection")
                    self.store.secret(token_key, {})
                    self.registry.transition(owner_id, GMAIL_CONNECTOR_ID, ConnectorState.REAUTH_REQUIRED)
                raise GmailReauthenticationRequired("reauth_required")
            if isinstance(status, int) and status >= 400:
                raise GmailError("provider_rejected")
            return response
        raise GmailError("invalid_provider_response")

    def _assert_current_request(
        self,
        owner_id: str,
        connection_revision: str,
        access_token: str,
    ) -> None:
        with self.registry._authority_guard():
            current = self.registry.status(owner_id, GMAIL_CONNECTOR_ID)
            token_key = _owner_secret_key(TOKEN_SECRET_KEY, owner_id)
            try:
                current_tokens = self.store.secret(token_key)
            except GmailError:
                if (
                    current.state is ConnectorState.CONNECTED
                    and current.connection_revision == connection_revision
                ):
                    self.store.secret(token_key, {})
                    self.registry.transition(owner_id, GMAIL_CONNECTOR_ID, ConnectorState.REAUTH_REQUIRED)
                    raise GmailReauthenticationRequired("reauth_required") from None
                raise GmailError("superseded_connection") from None
            if (
                current.state is not ConnectorState.CONNECTED
                or current.connection_revision != connection_revision
                or not isinstance(current_tokens, dict)
                or current_tokens.get("owner") != _owner_key(owner_id)
                or current_tokens.get("access_token") != access_token
            ):
                raise GmailError("superseded_connection")
            expires_at = current_tokens.get("expires_at")
            if (
                isinstance(expires_at, bool)
                or not isinstance(expires_at, (int, float))
                or not math.isfinite(expires_at)
                or _finite_now(self.now) >= expires_at
            ):
                self.store.secret(token_key, {})
                self.registry.transition(owner_id, GMAIL_CONNECTOR_ID, ConnectorState.REAUTH_REQUIRED)
                raise GmailReauthenticationRequired("reauth_required")

    @staticmethod
    def _message_id(value: object) -> str:
        if not isinstance(value, str) or not _MESSAGE_ID.fullmatch(value):
            raise GmailError("invalid_message_id")
        return value

    def _search_result(
        self,
        requested_id: str,
        response: dict,
        connection_revision: str,
    ) -> GmailSearchResult:
        if not isinstance(response, dict) or self._message_id(response.get("id")) != requested_id:
            raise GmailError("invalid_provider_response")
        thread_id = self._message_id(response.get("threadId"))
        payload = response.get("payload")
        raw_headers = payload.get("headers") if isinstance(payload, dict) else None
        if not isinstance(raw_headers, list):
            raise GmailError("invalid_provider_response")
        if len(raw_headers) > 100:
            raise GmailError("invalid_provider_response")
        headers: dict[str, str] = {}
        for item in raw_headers:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                name = item["name"].lower()
                if name in {"subject", "from", "date"} and name not in headers:
                    headers[name] = _decoded_header(item.get("value"), {"subject": 512, "from": 320, "date": 128}[name])
        return GmailSearchResult(
            requested_id,
            thread_id,
            connection_revision,
            headers.get("subject", ""),
            headers.get("from", ""),
            headers.get("date", ""),
        )

    def _body(self, payload: object, attachment_loader: Callable[[str], str] | None = None) -> tuple[str, str]:
        if not isinstance(payload, dict):
            raise GmailError("invalid_provider_response")
        candidate_count = 0
        visited_count = 0
        exhausted = False

        def visit(part: object, depth: int = 0) -> list[tuple[str, str | None, str | None, str | None]]:
            nonlocal candidate_count, visited_count, exhausted
            if not isinstance(part, dict):
                return []
            if depth > 20 or visited_count >= 100:
                exhausted = True
                return []
            visited_count += 1
            mime_type = part.get("mimeType")
            body = part.get("body")
            filename = part.get("filename")
            headers = part.get("headers", [])
            disposition = ""
            content_type = ""
            if isinstance(headers, list):
                if len(headers) > 100:
                    exhausted = True
                for header in headers[:100]:
                    if not isinstance(header, dict):
                        continue
                    name = header.get("name")
                    value = header.get("value")
                    if not isinstance(name, str) or not isinstance(value, str):
                        continue
                    if name.lower() == "content-disposition" and not disposition:
                        if len(value) > 1024:
                            exhausted = True
                            return []
                        disposition = value
                    elif name.lower() == "content-type" and not content_type:
                        if len(value) > 1024:
                            exhausted = True
                            return []
                        content_type = value
            is_attachment = (
                isinstance(filename, str)
                and bool(filename.strip())
            ) or disposition.split(";", 1)[0].strip().lower() == "attachment"
            if is_attachment:
                return []
            normalized_mime = mime_type.lower() if isinstance(mime_type, str) else ""
            if (
                normalized_mime in {"text/plain", "text/html"}
                and isinstance(body, dict)
                and (
                    isinstance(body.get("data"), str)
                    or isinstance(body.get("attachmentId"), str)
                )
            ):
                charset = None
                if content_type:
                    message = Message()
                    message["content-type"] = content_type
                    charset = message.get_content_charset()
                candidate_count += 1
                return [(
                    normalized_mime,
                    body.get("data") if isinstance(body.get("data"), str) else None,
                    charset,
                    body.get("attachmentId") if isinstance(body.get("attachmentId"), str) else None,
                )]
            # A nested message/rfc822 is an attached message even when Gmail
            # omits filename and Content-Disposition metadata. Its descendants
            # are not part of the current message body.
            if normalized_mime == "message/rfc822" and depth > 0:
                return []
            children: list[list[tuple[str, str | None, str | None, str | None]]] = []
            related_children: list[tuple[object, list[tuple[str, str | None, str | None, str | None]]]] = []
            parts = part.get("parts", [])
            if isinstance(parts, list):
                if len(parts) > 100:
                    exhausted = True
                for child in parts[:100]:
                    if visited_count >= 100:
                        exhausted = True
                        break
                    rendered = visit(child, depth + 1)
                    related_children.append((child, rendered))
                    if rendered:
                        children.append(rendered)
            if normalized_mime == "multipart/alternative":
                return next(
                    (group for group in children if any(item[0] == "text/plain" for item in group)),
                    children[0] if children else [],
                )
            if normalized_mime == "multipart/related":
                if not related_children:
                    return []
                start_values = []
                if content_type:
                    message = Message()
                    message["content-type"] = content_type
                    parameters = message.get_params(header="content-type") or []
                    start_values = [value for name, value in parameters[1:] if str(name).lower() == "start"]
                if not start_values:
                    return related_children[0][1]
                if len(start_values) != 1 or not isinstance(start_values[0], str):
                    raise GmailError("invalid_provider_response")
                start_match = re.fullmatch(r"<([^<>\s\x00-\x1f\x7f]{1,998})>", start_values[0].strip())
                if start_match is None:
                    raise GmailError("invalid_provider_response")
                wanted = start_match.group(1)
                for child, rendered in related_children:
                    child_headers = child.get("headers", []) if isinstance(child, dict) else []
                    if not isinstance(child_headers, list):
                        continue
                    for header in child_headers[:100]:
                        if not isinstance(header, dict) or str(header.get("name", "")).lower() != "content-id":
                            continue
                        value = header.get("value")
                        if not isinstance(value, str) or len(value) > 1024:
                            raise GmailError("invalid_provider_response")
                        content_id_match = re.fullmatch(r"<([^<>\s\x00-\x1f\x7f]{1,998})>", value.strip())
                        if content_id_match is None:
                            raise GmailError("invalid_provider_response")
                        if content_id_match.group(1) == wanted:
                            return rendered
                raise GmailError("invalid_provider_response")
            return [candidate for group in children for candidate in group]

        candidates = visit(payload)
        if exhausted:
            raise GmailError("message_too_complex")
        if not candidates:
            return "", _bounded_text(payload.get("mimeType"), 160)
        decoded_parts: list[str] = []
        decoded_bytes = 0
        for mime_type, encoded, charset, attachment_id in candidates:
            if encoded is None:
                if attachment_id is None or attachment_loader is None:
                    raise GmailError("invalid_provider_response")
                encoded = attachment_loader(attachment_id)
            if len(encoded) > (_MAX_BODY_BYTES * 4 // 3) + 8:
                raise GmailError("body_too_large")
            try:
                decoded = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
            except (TypeError, ValueError):
                raise GmailError("invalid_provider_response") from None
            decoded_bytes += len(decoded)
            if decoded_bytes > _MAX_BODY_BYTES:
                raise GmailError("body_too_large")
            encoding = charset or "utf-8"
            if not isinstance(encoding, str) or len(encoding) > 64:
                raise GmailError("invalid_provider_response")
            try:
                codecs.lookup(encoding)
                decoded_parts.append(decoded.decode(encoding, errors="replace"))
            except (LookupError, TypeError, ValueError, UnicodeError):
                raise GmailError("invalid_provider_response") from None
        mime_types = {item[0] for item in candidates}
        result_mime = candidates[0][0] if len(mime_types) == 1 else _bounded_text(payload.get("mimeType"), 160)
        return "\n\n".join(decoded_parts), result_mime
