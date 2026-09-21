"""Owner-local web OAuth handoff for explicitly selected Google Drive files.

The HTTPS link is a browser entry point only.  This module deliberately has
no control-plane persistence: state, PKCE verifier, callback code exchange,
and tokens stay in the owner's local runtime.
"""
import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from urllib.parse import quote, urlencode, urlsplit

from cryptography.fernet import Fernet, InvalidToken
from oauthlib.oauth2 import WebApplicationClient


DRIVE_FILE = "https://www.googleapis.com/auth/drive.file"
AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
PENDING_KEY = "drive_web_oauth_pending"
TOKEN_KEY = "drive_web_oauth_tokens"
STATUS_KEY = "drive_web_oauth_status"
SELECTED_FILES_KEY = "drive_web_oauth_selected_files"
PICKER_GRANT_KEY = "drive_web_oauth_picker_grant"
FILES_ENDPOINT = "https://www.googleapis.com/drive/v3/files"
PICKER_GRANT_LOCK = threading.Lock()


class DriveWebOAuthError(ValueError):
    pass


class DriveScopeError(DriveWebOAuthError):
    pass


class EncryptedDriveSecretStore:
    """Encrypt Drive-only secrets with a local-runtime key kept outside storage.

    The caller supplies the key from its local secret/keychain boundary.  The
    key is never persisted by this class, so copying the local data directory
    alone cannot reveal OAuth tokens or PKCE state.
    """
    encrypted_secrets = True

    def __init__(self, store, key):
        if not isinstance(key, (str, bytes)):
            raise ValueError("A local encryption key is required for Drive OAuth.")
        try:
            self.cipher = Fernet(key.encode() if isinstance(key, str) else key)
        except (ValueError, TypeError) as exc:
            raise ValueError("A valid local encryption key is required for Drive OAuth.") from exc
        self.store = store

    def secret(self, key, value=None):
        if value is not None:
            payload = json.dumps(value, separators=(",", ":")).encode()
            self.store.secret("encrypted:" + key, self.cipher.encrypt(payload).decode())
        raw = self.store.secret("encrypted:" + key)
        if not raw:
            return ""
        try:
            return json.loads(self.cipher.decrypt(str(raw).encode()).decode())
        except (InvalidToken, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise DriveWebOAuthError("Encrypted Google Drive credentials cannot be read locally.") from exc

    def put(self, key, value):
        self.store.put(key, value)

    def config(self, key, default=None):
        return self.store.config(key, default)


# REUSE-R1b (#427) Existing Solutions Review.  Authorization-request
# construction below is ``oauthlib`` (Adopt); token handling stays
# AgentOS-owned (Build), for reasons recorded per mechanic:
#
#   * ``google-auth`` -- rejected.  It has no authorization-code grant at all
#     (``authorization_code`` appears nowhere in the package) and no PKCE or
#     authorization-URL builder.  ``Credentials.expired`` reads a module-global
#     clock with a 3m45s skew instead of the injected ``now``, and
#     ``before_request`` refreshes silently, which this connector must not do.
#   * ``google-auth-oauthlib`` -- rejected.  It supplies PKCE but performs the
#     token call itself through ``requests``, replacing the injected
#     ``exchange`` seam with a new egress path and TLS trust store.
#   * ``oauthlib`` -- adopted for PKCE and the authorization URL only.  It is
#     BSD-3-Clause, Production/Stable, and has zero mandatory dependencies
#     (every ``Requires-Dist`` is an extra); it imports no HTTP library, so the
#     injected ``exchange`` seam is preserved unchanged.
#
# Deliberately NOT adopted, and why -- do not "finish the job" without
# re-reviewing these:
#   * ``prepare_request_body()`` returns a form-encoded string.  The ``exchange``
#     seam passes a dict precisely so ``client_secret`` is added only at the
#     owner-local egress transport and never enters this policy module.
#     Adopting it would widen where the secret is handled.
#   * ``parse_request_body_response()`` cannot be the scope-enforcement point:
#     its over-grant guard raises a bare builtin ``Warning`` and is silently
#     disabled by the ``OAUTHLIB_RELAX_TOKEN_SCOPE`` environment variable.  It
#     also derives ``expires_at`` from a module-global ``time.time()``, which
#     defeats the injected ``now`` -- the same two defects that disqualified
#     ``google-auth``.  Scope and expiry stay enforced in ``complete`` below.
def _pkce_pair():
    # ``create_code_verifier`` draws from ``random.SystemRandom`` (os.urandom).
    # "S256" is passed explicitly: ``create_code_challenge`` silently falls back
    # to the unprotected ``plain`` transform when the method is omitted.
    client = WebApplicationClient("")
    verifier = client.create_code_verifier(96)
    return verifier, client.create_code_challenge(verifier, "S256")


class DriveWebOAuthHandoff:
    """One-time OAuth state bound to one paired Telegram owner.

    ``store`` must be an owner-local encrypted secret store in production.
    It needs ``secret(key[, value])`` and ``put(key, value)`` methods.  The
    public handoff URL is opaque and never contains a token, code, verifier,
    Telegram message, or file content.
    """
    def __init__(self, store, client_id, redirect_uri, handoff_url, now=time.time, ttl_seconds=600,
                 allow_localhost=False, local_only=False):
        if not all(isinstance(value, str) and value for value in (client_id, redirect_uri, handoff_url)):
            raise ValueError("Web OAuth client, callback, and HTTPS handoff URL are required.")
        callback, handoff = urlsplit(redirect_uri), urlsplit(handoff_url)
        local_callback = callback.scheme == "http" and callback.hostname == "localhost"
        # ``agentos.localhost`` is a browser-reserved loopback name.  Unlike
        # bare ``localhost``, Telegram accepts it as an inline-button URL.
        local_handoff = handoff.scheme in ("http", "https") and handoff.hostname in ("localhost", "agentos.localhost")
        local_urls = local_callback and local_handoff
        if local_only and not local_urls:
            raise ValueError("Local-only Drive OAuth requires a localhost callback and handoff URL.")
        # Telegram rejects an inline keyboard button with an HTTP localhost
        # URL.  The local handoff may therefore be HTTPS while Google's
        # loopback callback remains the explicitly allowed HTTP URL.
        if (not handoff_url.startswith("https://") or not redirect_uri.startswith("https://")) and not (allow_localhost and local_urls):
            raise ValueError("Web OAuth handoff and callback URLs must use HTTPS.")
        if not getattr(store, "encrypted_secrets", False):
            raise ValueError("Drive OAuth requires an encrypted owner-local secret store.")
        self.store, self.client_id = store, client_id
        self.redirect_uri, self.handoff_url = redirect_uri, handoff_url.rstrip("/")
        self.now, self.ttl_seconds = now, ttl_seconds
        # A store can be reconstructed by another handler instance in the
        # same runtime; this lock must therefore not be instance-local.
        self._picker_grant_lock = PICKER_GRANT_LOCK

    def begin(self, telegram_owner_id, pending_job_id=None):
        if not isinstance(telegram_owner_id, int) or telegram_owner_id <= 0:
            raise DriveWebOAuthError("A paired Telegram owner is required.")
        verifier, challenge = _pkce_pair()
        nonce = secrets.token_urlsafe(32)
        state_key = secrets.token_bytes(32)
        signature = hmac.new(state_key, f"{telegram_owner_id}:{nonce}".encode(), hashlib.sha256).hexdigest()
        state = nonce + "." + signature
        created = self.now()
        pending = {"state": state, "state_key": base64.urlsafe_b64encode(state_key).decode(), "verifier": verifier, "owner": telegram_owner_id,
                   "created_at": created, "expires_at": created + self.ttl_seconds, "status": "pending"}
        self.store.secret(PENDING_KEY, pending)
        self._record("connection-offered", state="connection-offered", owner=telegram_owner_id,
                     pending_job_id=pending_job_id)
        return {
            "state": "connection-required",
            "message": "Google Drive 연결이 필요합니다. 선택한 파일만 읽을 수 있으며 전체 Drive 검색은 하지 않습니다.",
            "button": {"text": "Google Drive 연결하기", "url": self.handoff_url + "/google-drive?" + urlencode({"state": state})},
            "expires_at": pending["expires_at"],
            "code_challenge": challenge,
        }

    def authorization_url(self, state, telegram_owner_id):
        pending = self._pending(state, telegram_owner_id)
        client = WebApplicationClient(self.client_id)
        return client.prepare_request_uri(
            AUTHORIZATION_ENDPOINT,
            redirect_uri=self.redirect_uri,
            scope=[DRIVE_FILE],
            state=pending["state"],
            code_challenge=client.create_code_challenge(pending["verifier"], "S256"),
            code_challenge_method="S256",
            access_type="offline",
            # DEFERRED (REUSE-R1b #427, owned by SEC-DRIVE-SCOPE-01 #432):
            # ``Gmail.begin_oauth`` also sends ``include_granted_scopes="false"``
            # so Google cannot fold previously granted scopes into this grant.
            # This connector does not yet, which is why ``complete`` must keep
            # its own exact-set scope check.  Adding the parameter changes the
            # live authorization request, so it needs owner/live validation and
            # is intentionally NOT changed here.  Do not close this note without
            # either sending the parameter or recording why it is unnecessary.
        )

    def authorization_url_for_state(self, state):
        """Resolve the owner only from the encrypted, one-time local state."""
        pending = self.store.secret(PENDING_KEY)
        if not isinstance(pending, dict):
            raise DriveWebOAuthError("No pending Google Drive connection exists.")
        return self.authorization_url(state, pending.get("owner"))

    def callback_owner(self, state):
        pending = self.store.secret(PENDING_KEY)
        if not isinstance(pending, dict):
            raise DriveWebOAuthError("No pending Google Drive connection exists.")
        self._pending(state, pending.get("owner"))
        return pending["owner"]

    def complete(self, callback, telegram_owner_id, exchange):
        if not isinstance(callback, dict):
            raise DriveWebOAuthError("Google callback is invalid.")
        pending = self._pending(callback.get("state"), telegram_owner_id)
        if callback.get("error"):
            self._finish("denied")
            raise DriveWebOAuthError("Google Drive access was not approved.")
        code = callback.get("code")
        if not isinstance(code, str) or not code:
            self._finish("callback-failed")
            raise DriveWebOAuthError("Google Drive authorization code is missing.")
        try:
            response = exchange({"code": code, "code_verifier": pending["verifier"],
                                 "redirect_uri": self.redirect_uri, "client_id": self.client_id})
        except Exception as exc:
            self._finish("callback-failed")
            raise DriveWebOAuthError("Google Drive token exchange failed.") from exc
        if not isinstance(response, dict) or not isinstance(response.get("access_token"), str):
            self._finish("callback-failed")
            raise DriveWebOAuthError("Google Drive token exchange failed.")
        # Exact-set equality, matching ``Gmail._validated_tokens``.  A subset
        # test would accept a response carrying drive.file *plus* scopes this
        # connector never requested, silently storing a credential with more
        # authority than the owner approved.  Fail closed on any extra scope.
        granted = str(response.get("scope", ""))
        if set(granted.split()) != {DRIVE_FILE}:
            self._finish("scope-rejected")
            raise DriveScopeError("Google Drive file-selection scope was not granted.")
        tokens = {key: response[key] for key in ("access_token", "refresh_token", "expires_in", "scope") if key in response}
        if isinstance(tokens.get("expires_in"), (int, float)):
            tokens["expires_at"] = self.now() + max(0, tokens["expires_in"])
        self.store.secret(TOKEN_KEY, tokens)
        self._finish("connected")
        return self.status()

    def select_files(self, telegram_owner_id, files):
        self._connected(telegram_owner_id)
        if not isinstance(files, list) or not files or len(files) > 20:
            raise DriveScopeError("Choose one to twenty files in Google Picker.")
        selected = []
        for item in files:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
                raise DriveScopeError("Google Picker returned an invalid file.")
            selected.append({"id": item["id"], "name": str(item.get("name", ""))[:240],
                             "mime_type": str(item.get("mime_type", item.get("mimeType", "")))[:160]})
        self.store.put(SELECTED_FILES_KEY, {"owner": telegram_owner_id, "files": selected})
        self._record("files-selected")
        return {"state": "files-selected", "files": selected}

    def create_picker_grant(self, telegram_owner_id):
        """Mint a short-lived, one-use browser grant after OAuth succeeds.

        This is deliberately *not* an OAuth token.  It lets the local Picker
        page submit only the owner's selected file identifiers and is kept in
        the encrypted secret store so neither status APIs nor the ordinary
        local database reveal it.
        """
        self._connected(telegram_owner_id)
        value = {"grant": secrets.token_urlsafe(32), "owner": telegram_owner_id,
                 "expires_at": self.now() + self.ttl_seconds, "used": False}
        self.store.secret(PICKER_GRANT_KEY, value)
        self._record("picker-offered")
        return value["grant"]

    def select_files_for_grant(self, grant, files):
        with self._picker_grant_lock:
            value = self.store.secret(PICKER_GRANT_KEY)
            if (not isinstance(grant, str) or not isinstance(value, dict)
                    or value.get("used") or not secrets.compare_digest(grant, str(value.get("grant", "")))):
                raise DriveWebOAuthError("Google Drive file-selection link is invalid or already used.")
            if self.now() >= value.get("expires_at", 0):
                self.store.secret(PICKER_GRANT_KEY, {"used": True})
                raise DriveWebOAuthError("Google Drive file-selection link expired; request a new link.")
            owner = value.get("owner")
            if not isinstance(owner, int):
                raise DriveWebOAuthError("Google Drive file-selection link is invalid.")
            # Consume before accepting metadata while holding the local server
            # lock, so concurrent browser tabs cannot replace the selection.
            self.store.secret(PICKER_GRANT_KEY, {"used": True})
            return owner, self.select_files(owner, files)

    def mark_reauthentication_required(self):
        """Invalidate a rejected remote token before offering another link."""
        self.store.secret(TOKEN_KEY, {})
        self.store.put(SELECTED_FILES_KEY, {})
        self._finish("reauth-required")

    def picker_grant_active(self, grant):
        value = self.store.secret(PICKER_GRANT_KEY)
        return (isinstance(grant, str) and isinstance(value, dict)
                and not value.get("used") and self.now() < value.get("expires_at", 0)
                and secrets.compare_digest(grant, str(value.get("grant", ""))))

    def assert_selected(self, telegram_owner_id, file_id):
        self._connected(telegram_owner_id)
        selected = self.store.config(SELECTED_FILES_KEY, {})
        if selected.get("owner") != telegram_owner_id or file_id not in {row["id"] for row in selected.get("files", [])}:
            raise DriveScopeError("Choose this file in Google Picker before reading it.")
        return True

    def read_selected(self, telegram_owner_id, file_id, transport):
        """Read one Picker-authorized file without retaining its body.

        The injected transport is the owner-local Drive boundary.  Callers may
        summarize its returned content in memory, but must not place it in
        status/audit/configuration records or relay payloads.
        """
        self.assert_selected(telegram_owner_id, file_id)
        tokens = self.store.secret(TOKEN_KEY)
        if not callable(transport):
            raise DriveWebOAuthError("An owner-local Drive transport is required.")
        selected = self.store.config(SELECTED_FILES_KEY, {})
        row = next(row for row in selected["files"] if row["id"] == file_id)
        exports = {
            "application/vnd.google-apps.document": "text/plain",
            "application/vnd.google-apps.spreadsheet": "text/csv",
            "application/vnd.google-apps.presentation": "text/plain",
        }
        mime_type = exports.get(row.get("mime_type"))
        url = (FILES_ENDPOINT + "/" + quote(file_id, safe="") + "/export?" + urlencode({"mimeType": mime_type})
               if mime_type else FILES_ENDPOINT + "/" + quote(file_id, safe="") + "?alt=media")
        return transport(
            url,
            None,
            {"Authorization": "Bearer " + tokens["access_token"]},
        )

    def consume_pending_job(self, telegram_owner_id):
        value = self.store.config(STATUS_KEY, {})
        if value.get("owner") != telegram_owner_id:
            raise DriveWebOAuthError("This Drive connection belongs to another Telegram owner.")
        job_id = value.get("pending_job_id")
        self._record("drive-job-resumed", pending_job_id=None)
        return job_id

    def search(self, *_args, **_kwargs):
        raise DriveScopeError("drive.file does not allow arbitrary or full-Drive search; choose a file first.")

    def status(self):
        value = self.store.config(STATUS_KEY, {"state": "disconnected", "audit": []})
        return {"state": value.get("state", "disconnected"), "audit": list(value.get("audit", []))}

    def telegram_status_message(self):
        state = self.status()["state"]
        messages = {
            "connected": "Google Drive가 연결되었습니다. Google Picker에서 선택한 파일만 읽을 수 있습니다.",
            "denied": "Google Drive 권한이 허용되지 않았습니다. 필요할 때 다시 연결해 주세요.",
            "expired": "Google Drive 연결 링크가 만료되었습니다. Telegram에서 다시 연결해 주세요.",
            "reauth-required": "Google Drive 연결이 만료되었습니다. 다시 연결해 주세요.",
            "callback-failed": "Google Drive 연결을 완료하지 못했습니다. Telegram에서 새 연결 링크를 요청해 주세요.",
        }
        return messages.get(state, "Google Drive 연결이 필요합니다. 선택한 파일만 읽을 수 있습니다.")

    def _pending(self, state, owner):
        pending = self.store.secret(PENDING_KEY)
        if not isinstance(pending, dict) or pending.get("status") != "pending":
            raise DriveWebOAuthError("No pending Google Drive connection exists.")
        if not isinstance(state, str) or not secrets.compare_digest(state, str(pending.get("state", ""))):
            raise DriveWebOAuthError("Google Drive authorization state did not match.")
        if owner != pending.get("owner"):
            raise DriveWebOAuthError("This Drive connection belongs to another Telegram owner.")
        try:
            nonce, signature = state.rsplit(".", 1)
            state_key = base64.urlsafe_b64decode(pending["state_key"].encode())
            expected = hmac.new(state_key, f"{owner}:{nonce}".encode(), hashlib.sha256).hexdigest()
        except (KeyError, ValueError, TypeError):
            raise DriveWebOAuthError("Google Drive authorization state is invalid.")
        if not hmac.compare_digest(signature, expected):
            raise DriveWebOAuthError("Google Drive authorization state signature did not match.")
        if self.now() >= pending.get("expires_at", 0):
            self._finish("expired")
            raise DriveWebOAuthError("Google Drive connection link expired; request a new link.")
        return pending

    def _connected(self, owner):
        tokens = self.store.secret(TOKEN_KEY)
        if not isinstance(tokens, dict) or not tokens.get("access_token"):
            raise DriveWebOAuthError("Google Drive is not connected.")
        if isinstance(tokens.get("expires_at"), (int, float)) and self.now() >= tokens["expires_at"]:
            self._finish("reauth-required")
            raise DriveWebOAuthError("Google Drive authorization expired; reconnect required.")
        if self.store.config(SELECTED_FILES_KEY, {}).get("owner") not in (None, owner):
            raise DriveWebOAuthError("This Drive connection belongs to another Telegram owner.")

    def _finish(self, state):
        self.store.secret(PENDING_KEY, {"status": "used"})
        self._record(state, state=state)

    def _record(self, event, state=None, owner=None, pending_job_id=...):
        prior = self.store.config(STATUS_KEY, {})
        value = {"state": state if state is not None else prior.get("state", "disconnected"),
                 "audit": [*prior.get("audit", []), event][-50:]}
        if owner is not None: value["owner"] = owner
        elif "owner" in prior: value["owner"] = prior["owner"]
        if pending_job_id is not ...: value["pending_job_id"] = pending_job_id
        elif "pending_job_id" in prior: value["pending_job_id"] = prior["pending_job_id"]
        self.store.put(STATUS_KEY, value)
