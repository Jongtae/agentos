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
from contextlib import contextmanager
from dataclasses import dataclass
from email.errors import HeaderParseError
from email.header import decode_header
from email.headerregistry import HeaderRegistry
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
# Bound the number of body parts that survive MIME selection, i.e. the parts a
# reader would actually see. Counting at admission instead measured a quantity
# no reader observes: ``multipart/alternative`` discards one of each
# plain/html pair afterwards, so an ordinary 11-message forwarded thread
# admitted 22 parts, kept 11, and was still rejected. The traversal cap of 100
# visited nodes still bounds the pre-selection work, and this cap bounds the
# per-candidate attachment fetches and decodes that follow selection.
_MAX_BODY_CANDIDATES = 32
# RFC 2045 section 5.2: a text/* entity without an explicit charset parameter
# defaults to us-ascii. Both the "Content-Type present without charset" and the
# "no Content-Type header at all" paths use this single default so the strict
# decode below is actually enforceable; two different defaults would let an
# undeclared part decode bytes that an identically declared part rejects.
_DEFAULT_TEXT_CHARSET = "us-ascii"
# Every owner-rendered decode is gated by an allowlist rather than a denylist.
# The hazard is any codec that turns innocuous-looking source bytes into ASCII
# markup a downstream renderer may re-interpret, and that class is open-ended:
# utf-7 spells "<" as "+ADw-", unicode-escape and raw-unicode-escape spell it
# as "\\u003c", and idna/punycode/rot-13/base64/quopri are transforms rather
# than mail charsets at all. Enumerating those one at a time left a new hole
# open after each fix, so the gate names the charsets that legitimately carry
# mail text instead. Entries are canonical ``codecs.lookup(...).name`` values,
# so every alias of a listed charset ("UTF-8", "latin-1", "sjis",
# "ks_c_5601-1987") resolves onto it and every alias of an unlisted one
# ("utf7", "unicode-1-1-utf-7") resolves off it.
#
# EBCDIC codepages are excluded on purpose: cp1026/cp1140/cp875 map byte 0x4C
# to "<", so admitting them would defeat this gate's own stated threat from
# source bytes containing no 0x3C. No mail declares EBCDIC.
_ALLOWED_CHARSETS = frozenset({
    "ascii", "big5", "big5hkscs", "cp1006", "cp1125", "cp1250", "cp1251",
    "cp1252", "cp1253", "cp1254", "cp1255", "cp1256", "cp1257", "cp1258", "cp437", "cp720",
    "cp737", "cp775", "cp850", "cp852", "cp855", "cp856", "cp857", "cp858", "cp860", "cp861",
    "cp862", "cp863", "cp864", "cp865", "cp866", "cp869", "cp874", "cp932", "cp949", "cp950",
    "euc_jis_2004", "euc_jisx0213", "euc_jp", "euc_kr", "gb18030", "gb2312", "gbk", "hz",
    "iso2022_jp", "iso2022_jp_1", "iso2022_jp_2", "iso2022_jp_2004", "iso2022_jp_3",
    "iso2022_jp_ext", "iso2022_kr", "iso8859-1", "iso8859-10", "iso8859-11", "iso8859-13",
    "iso8859-14", "iso8859-15", "iso8859-16", "iso8859-2", "iso8859-3", "iso8859-4",
    "iso8859-5", "iso8859-6", "iso8859-7", "iso8859-8", "iso8859-9", "johab", "koi8-r",
    "koi8-t", "koi8-u", "kz1048", "mac-arabic", "mac-croatian", "mac-cyrillic", "mac-farsi",
    "mac-greek", "mac-iceland",
    "mac-latin2", "mac-roman", "mac-romanian", "mac-turkish", "ptcp154", "shift_jis",
    "shift_jis_2004", "shift_jisx0213", "tis-620", "utf-16", "utf-16-be", "utf-16-le",
    "utf-32", "utf-32-be", "utf-32-le", "utf-8", "utf-8-sig",
})
# One registry, and one cached header class per structured header this module
# reads. ``HeaderRegistry.__getitem__`` builds a fresh class on every lookup, so
# caching keeps the bounded per-part header walk from rebuilding two types for
# every part of every message.
_HEADER_REGISTRY = HeaderRegistry()
_MIME_HEADER_CLASSES = {
    name: _HEADER_REGISTRY[name] for name in ("Content-Type", "Content-Disposition")
}
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

    def as_evidence(self) -> dict:
        """Return portable source evidence without private header metadata.

        ``as_dict`` carries subject/sender/date, which are private mail
        metadata. Integration code that persists evidence must use this
        method, mirroring :meth:`GmailMessage.as_evidence`.
        """
        return {"source": self.source, "metadata_included": False}

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


def _assert_renderable_charset(encoding: object) -> None:
    """Gate every decode whose output is rendered to the owner.

    Both owner-rendered decode paths - the message body and the RFC 2047
    encoded-words in Subject/From/Date - must apply the same charset rule.
    Applying it to only one of them left the other able to smuggle
    ASCII-looking markup past the guard under a different entry point.

    An unknown codec is a malformed provider response; a real codec that is
    not an allowed mail charset is an explicit refusal.
    """
    if not isinstance(encoding, str) or not encoding or len(encoding) > 64:
        raise GmailError("invalid_provider_response")
    try:
        codec = codecs.lookup(encoding)
    except (LookupError, TypeError, ValueError):
        raise GmailError("invalid_provider_response") from None
    if codec.name not in _ALLOWED_CHARSETS:
        raise GmailError("unsupported_charset")


def _decoded_header(value: object, maximum: int) -> str:
    if not isinstance(value, str) or len(value) > 4096:
        raise GmailError("invalid_provider_response")
    try:
        fragments = decode_header(value)
    except (HeaderParseError, LookupError, TypeError, ValueError, UnicodeError):
        raise GmailError("invalid_provider_response") from None
    parts = []
    for fragment, charset in fragments:
        if isinstance(fragment, bytes):
            # RFC 2047 lets the sender name any charset for an encoded-word,
            # and Subject/From are exactly the fields shown to the owner, so
            # the same gate the body uses applies here. GmailError must not be
            # swallowed by the malformed-response handler below, so the gate
            # runs outside the try block.
            encoding = charset if isinstance(charset, str) and charset.strip() else "ascii"
            _assert_renderable_charset(encoding)
            try:
                parts.append(fragment.decode(encoding, errors="strict"))
            except (LookupError, TypeError, ValueError, UnicodeError):
                raise GmailError("invalid_provider_response") from None
        elif isinstance(fragment, str):
            parts.append(fragment)
        else:
            raise GmailError("invalid_provider_response")
    return _bounded_text("".join(parts), maximum)


def _assert_unique_mime_parameters(name: str, value: str) -> None:
    """Refuse a parameter name that repeats once case is folded.

    RFC 2045 parameter names are case-insensitive, but CPython keys duplicate
    detection on the raw spelling, so ``charset=us-ascii; (x) CHARSET=utf-8``
    records no defect and is silently resolved last-wins. The parsed header
    only exposes the folded mapping, so the repeat is invisible there.

    Rather than count parameters or strip comments by hand, hand the same
    parser a case-folded copy. A name that differed only in case becomes a
    literal duplicate, and the parser's own duplicate detection - the signal
    this module already trusts - reports it. Case folding cannot change the
    grammar, so a header that parses cleanly and repeats nothing still parses
    cleanly.

    Three earlier attempts at this check were hand-written and each failed in
    a way its tests did not list: a private parse-tree attribute, then a
    parameter count that refused an ordinary trailing semicolon, then the same
    count crashing on an RFC 2231 extended parameter mixed with a sectioned
    continuation. Reusing the parser removes the surface those shared.
    """
    folded = value.casefold()
    if folded == value:
        return
    if _MIME_HEADER_CLASSES[name](name, folded).defects:
        raise GmailError("invalid_provider_response")


def _parsed_mime_header(name: str, value: str):
    """Parse one Gmail-supplied structured header value with the stdlib parser.

    Gmail's ``format=full`` hands each header over already split into name and
    value, which is exactly the shape :class:`email.headerregistry.HeaderRegistry`
    parses. Delegating to it removes this module's hand-written CFWS/comment,
    quoted-string, control-character and parameter scanners, and with them the
    standing risk that this module's view of a header disagrees with the
    parser's.

    Any defect the stdlib parse records is a refusal. That one general signal
    replaces an enumeration of the malformations we happened to think of: it
    covers a missing media type or disposition, duplicate parameters, an
    unterminated comment or quoted string, and embedded control characters
    such as CR, LF, NUL and DEL, while still accepting the legal constructs
    real mail uses - HTAB folding, nested comments, parentheses inside quoted
    values and RFC 2231 continuations.
    """
    try:
        parsed = _MIME_HEADER_CLASSES[name](name, value)
        if parsed.defects:
            raise GmailError("invalid_provider_response")
        _assert_unique_mime_parameters(name, value)
    except GmailError:
        raise
    except (HeaderParseError, IndexError, LookupError, TypeError, ValueError, UnicodeError):
        # The duplicate check re-reads the header through a second stdlib
        # accessor, which has its own failure modes: mixing an RFC 2231
        # extended parameter with a sectioned continuation makes
        # ``decode_params`` sort ``int`` against ``None`` and raise
        # ``TypeError``. Any such raise is provider data this module cannot
        # interpret, so it refuses like every other malformation rather than
        # escaping the GmailError contract and leaving the connector.
        raise GmailError("invalid_provider_response") from None
    return parsed


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

    @contextmanager
    def _lifecycle_guard(self, owner_id: str):
        """Hold the repository-wide ``dispatch -> authority`` lock order.

        ``ConnectorRegistry.transition`` takes the per-owner/connector dispatch
        lock before the process-wide authority lock, and
        :mod:`personal_agent.calendar` uses the same order. Taking the
        authority lock first and then calling ``transition`` would invert that
        order; because the authority lock is a single module-global lock shared
        by every connector, one such inversion can wedge the whole process.
        Every Gmail authority check that may be followed by a lifecycle
        transition therefore enters through this guard. Both locks are
        reentrant, so nesting inside this guard is safe.
        """
        # Validate through the Gmail owner rule first so an invalid owner
        # raises GmailError rather than a foreign ValueError from the registry.
        _owner_key(owner_id)
        with self.registry._dispatch_guard(owner_id, (GMAIL_CONNECTOR_ID,)):
            with self.registry._authority_guard():
                yield

    @staticmethod
    def _contract_error(exc: ConnectorContractError) -> GmailError:
        """Translate the shared contract error into the Gmail adapter error."""
        known = {"already_connected", "unknown_connector", "scope_mismatch", "invalid_stored_state"}
        return GmailError(exc.reason if exc.reason in known else "invalid_connector_state")

    def status(self, owner_id: str) -> dict:
        """Return restart-safe lifecycle metadata with no OAuth or mail data."""
        _owner_key(owner_id)
        try:
            return self.registry.status(owner_id, GMAIL_CONNECTOR_ID).as_dict()
        except ConnectorContractError as exc:
            raise self._contract_error(exc) from None

    def portable_status(self, owner_id: str) -> dict:
        return self.status(owner_id)

    def connection_required(self, owner_id: str) -> dict:
        _owner_key(owner_id)
        try:
            return self.registry.required_result(owner_id, GMAIL_CONNECTOR_ID).as_dict()
        except ConnectorContractError as exc:
            raise self._contract_error(exc) from None

    def begin_oauth(self, owner_id: str) -> dict:
        owner = _owner_key(owner_id)
        created_at = _finite_now(self.now)
        verifier, challenge = _pkce_pair()
        nonce = secrets.token_urlsafe(32)
        signing_key = secrets.token_bytes(32)
        signature = hmac.new(signing_key, f"{owner}:{nonce}".encode(), hashlib.sha256).hexdigest()
        state = nonce + "." + signature
        with _OAUTH_LOCK:
            with self._lifecycle_guard(owner_id):
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
        required = self.connection_required(owner_id)
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
            with self._lifecycle_guard(owner_id):
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
            with self._lifecycle_guard(owner_id):
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
        with self._lifecycle_guard(owner_id):
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
        with self._lifecycle_guard(owner_id):
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
            has_status = "status_code" in response
            status = response.get("status_code")
            if has_status and (isinstance(status, bool) or not isinstance(status, int)):
                raise GmailError("invalid_provider_response")
            if status == 401:
                with self._lifecycle_guard(owner_id):
                    current = self.registry.status(owner_id, GMAIL_CONNECTOR_ID)
                    token_key = _owner_secret_key(TOKEN_SECRET_KEY, owner_id)
                    try:
                        current_tokens = self.store.secret(token_key)
                    except GmailError:
                        # An unreadable secret must revoke authority here for the
                        # same reason as in ``_assert_current_request``; leaving
                        # the connector CONNECTED with an undecryptable token
                        # would report unusable authority as usable.
                        if (
                            current.state is ConnectorState.CONNECTED
                            and current.connection_revision == connection_revision
                        ):
                            self.store.secret(token_key, {})
                            self.registry.transition(
                                owner_id, GMAIL_CONNECTOR_ID, ConnectorState.REAUTH_REQUIRED
                            )
                            raise GmailReauthenticationRequired("reauth_required") from None
                        raise GmailError("superseded_connection") from None
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
            if isinstance(status, int) and not 200 <= status < 300:
                raise GmailError("provider_rejected")
            return response
        raise GmailError("invalid_provider_response")

    def _assert_current_request(
        self,
        owner_id: str,
        connection_revision: str,
        access_token: str,
    ) -> None:
        with self._lifecycle_guard(owner_id):
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
                if name in {"subject", "from", "date"}:
                    if name in headers:
                        raise GmailError("invalid_provider_response")
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
        visited_count = 0
        exhausted = False
        # Distinguish "this message genuinely carries no text body" from "the
        # parser removed every possible body". Only the first may be reported
        # as a successful empty read.
        dropped_text_parts = 0
        ambiguous_selection = False

        def visit(part: object, depth: int = 0) -> list[tuple[str, str | None, str | None, str | None]]:
            nonlocal visited_count, exhausted
            nonlocal dropped_text_parts, ambiguous_selection
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
            disposition_present = False
            content_type = ""
            security_headers: set[str] = set()
            if "headers" in part and not isinstance(headers, list):
                raise GmailError("invalid_provider_response")
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
                    normalized_name = name.lower()
                    if normalized_name in {"content-disposition", "content-type"}:
                        if normalized_name in security_headers:
                            raise GmailError("invalid_provider_response")
                        security_headers.add(normalized_name)
                    if normalized_name == "content-disposition":
                        if len(value) > 1024:
                            exhausted = True
                            return []
                        disposition = value
                        disposition_present = True
                    elif normalized_name == "content-type":
                        if len(value) > 1024:
                            exhausted = True
                            return []
                        content_type = value
            # A comment is legal CFWS in Content-Disposition too, so
            # ``inline (rendered)`` must stay inline rather than silently
            # becoming an attachment and dropping the body. The stdlib parse
            # resolves the comment; a disposition that does not parse is a
            # malformed provider response rather than an unknown token, so it
            # is refused here instead of being demoted to a heuristic drop.
            disposition_kind = ""
            if disposition_present:
                disposition_kind = (
                    _parsed_mime_header("Content-Disposition", disposition).content_disposition
                    or ""
                ).lower()
            normalized_mime = mime_type.lower() if isinstance(mime_type, str) else ""
            parsed_content_type = None
            charset = None
            content_type_names = False
            if "content-type" in security_headers:
                parsed_content_type = _parsed_mime_header("Content-Type", content_type)
                # Gmail's decomposed ``mimeType`` and the part's own
                # Content-Type must agree. A part that is selected as one media
                # type and decoded as another is not something to guess about,
                # and this equality also rejects a media type the header
                # grammar accepted but Gmail never declared.
                if parsed_content_type.content_type.lower() != normalized_mime:
                    raise GmailError("invalid_provider_response")
                if normalized_mime in {"text/plain", "text/html"}:
                    charset_value = parsed_content_type.params.get("charset")
                    # ``charset=""`` and ``charset=" "`` parse without a defect
                    # and yield a blank value. That must be refused rather than
                    # fall through to the RFC 2045 default below, which would
                    # let an explicitly blank declaration decode as us-ascii.
                    if charset_value is not None and (
                        not isinstance(charset_value, str) or not charset_value.strip()
                    ):
                        raise GmailError("invalid_provider_response")
                    charset = (
                        charset_value.strip()
                        if isinstance(charset_value, str)
                        else _DEFAULT_TEXT_CHARSET
                    )
                    # A ``name`` parameter is the legacy attachment indicator
                    # that predates Content-Disposition; a text part carrying
                    # one is an attachment, not the message body.
                    name_value = parsed_content_type.params.get("name")
                    content_type_names = isinstance(name_value, str) and bool(name_value.strip())
            # RFC 2183 section 2.1 makes Content-Disposition the authoritative
            # statement of a part's role. Gmail's own ``filename`` field and an
            # explicit ``attachment`` disposition are the sender saying so
            # outright; nothing is guessed and nothing is lost by withholding
            # such a part from the body.
            explicit_attachment = (
                (isinstance(filename, str) and bool(filename.strip()))
                or disposition_kind == "attachment"
            )
            # Everything else is this parser guessing. An unrecognised or empty
            # disposition token is genuinely ambiguous, and the ``name``
            # parameter is only the pre-RFC-2183 fallback: it is evidence just
            # when the authoritative header is silent. Letting ``name`` outvote
            # an explicit ``inline`` made ordinary Outlook/Exchange and
            # mailing-list mail (``text/plain; name="message.txt"`` plus
            # ``Content-Disposition: inline``) unreadable.
            heuristic_attachment = (
                (disposition_present and disposition_kind not in {"inline", "attachment"})
                or (content_type_names and disposition_kind != "inline")
            )
            if explicit_attachment or heuristic_attachment:
                if (
                    not explicit_attachment
                    and normalized_mime in {"text/plain", "text/html"}
                    and isinstance(body, dict)
                    and (
                        isinstance(body.get("data"), str)
                        or isinstance(body.get("attachmentId"), str)
                    )
                ):
                    # Only a heuristic removal leaves the outcome unknown. A
                    # sender-declared attachment was classified correctly, so
                    # counting it as a dropped candidate made the plainest
                    # bodyless message hard-fail purely because its attachment
                    # happened to be text/*: an empty message with one .txt
                    # attached raised while the same shape with a .pdf read
                    # fine, and the raise cost the owner subject, sender and
                    # date as well as the body.
                    dropped_text_parts += 1
                return []
            if (
                normalized_mime in {"text/plain", "text/html"}
                and isinstance(body, dict)
                and (
                    isinstance(body.get("data"), str)
                    or isinstance(body.get("attachmentId"), str)
                )
            ):
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
                if parsed_content_type is not None:
                    if "start" in parsed_content_type.params:
                        start_values = [parsed_content_type.params["start"]]
                if not start_values:
                    root = related_children[0][1]
                    if not root and any(rendered for _child, rendered in related_children):
                        # Without a ``start`` parameter the root is the first
                        # part. If that part rendered nothing while a sibling
                        # did, the empty result is a parser outcome rather than
                        # an attributable root body.
                        ambiguous_selection = True
                    return root
                if len(start_values) != 1 or not isinstance(start_values[0], str):
                    raise GmailError("invalid_provider_response")
                start_match = re.fullmatch(r"<([^<>\s\x00-\x1f\x7f]{1,998})>", start_values[0].strip())
                if start_match is None:
                    raise GmailError("invalid_provider_response")
                wanted = start_match.group(1)
                matching_roots: list[list[tuple[str, str | None, str | None, str | None]]] = []
                for child, rendered in related_children:
                    child_headers = child.get("headers", []) if isinstance(child, dict) else []
                    if not isinstance(child_headers, list):
                        continue
                    child_content_ids: list[str] = []
                    for header in child_headers[:100]:
                        if not isinstance(header, dict) or str(header.get("name", "")).lower() != "content-id":
                            continue
                        value = header.get("value")
                        if not isinstance(value, str) or len(value) > 1024:
                            raise GmailError("invalid_provider_response")
                        content_id_match = re.fullmatch(r"<([^<>\s\x00-\x1f\x7f]{1,998})>", value.strip())
                        if content_id_match is None:
                            raise GmailError("invalid_provider_response")
                        child_content_ids.append(content_id_match.group(1))
                    if len(child_content_ids) > 1:
                        raise GmailError("invalid_provider_response")
                    if child_content_ids == [wanted]:
                        matching_roots.append(rendered)
                if len(matching_roots) != 1:
                    raise GmailError("invalid_provider_response")
                return matching_roots[0]
            return [candidate for group in children for candidate in group]

        candidates = visit(payload)
        if exhausted:
            raise GmailError("message_too_complex")
        # Bound the parts that survive selection - the ones actually decoded,
        # fetched and rendered - rather than the ones merely admitted during
        # traversal. This runs before any attachment fetch below, so the
        # per-candidate network work stays bounded.
        if len(candidates) > _MAX_BODY_CANDIDATES:
            raise GmailError("message_too_complex")
        if not candidates:
            if dropped_text_parts or ambiguous_selection:
                # Some text content existed but no part could be attributed as
                # the message body. Returning "" here would present an unknown
                # outcome as a successful read.
                raise GmailError("body_not_attributable")
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
            # A part with no Content-Type header at all uses the same RFC 2045
            # default as a part whose Content-Type omits charset, so the strict
            # decode is enforced identically on both paths.
            encoding = charset or _DEFAULT_TEXT_CHARSET
            _assert_renderable_charset(encoding)
            try:
                decoded_parts.append(decoded.decode(encoding, errors="strict"))
            except (LookupError, TypeError, ValueError, UnicodeError):
                raise GmailError("invalid_provider_response") from None
        mime_types = {item[0] for item in candidates}
        result_mime = candidates[0][0] if len(mime_types) == 1 else _bounded_text(payload.get("mimeType"), 160)
        return "\n\n".join(decoded_parts), result_mime
