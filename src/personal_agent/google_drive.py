"""Contract-first, read-only Google Drive adapter with injected transport."""
import secrets
import time
from urllib.parse import quote, urlencode

from oauthlib.oauth2 import WebApplicationClient

DRIVE_READONLY = "https://www.googleapis.com/auth/drive.readonly"
AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
FILES_ENDPOINT = "https://www.googleapis.com/drive/v3/files"
PENDING_SECRET = "google_drive_oauth_pending"
TOKEN_SECRET = "google_drive_tokens"
CONNECTION_CONFIG = "google_drive_connection"


class DriveAuthorizationError(ValueError):
    pass


def _pkce_pair():
    # Same path as gmail.py and drive_web_oauth.py since #429.  "S256" is
    # passed explicitly: ``create_code_challenge`` silently falls back to the
    # unprotected ``plain`` transform when the method is omitted.
    client = WebApplicationClient("")
    verifier = client.create_code_verifier(96)
    return verifier, client.create_code_challenge(verifier, "S256")


class GoogleDrive:
    def __init__(self, transport, token):
        if not isinstance(token, str) or not token:
            raise DriveAuthorizationError("Google Drive access token is required.")
        self.transport, self.token = transport, token

    def _request(self, url):
        return self.transport(url, None, {"Authorization": "Bearer " + self.token})

    def search(self, query):
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Search text is required.")
        escaped = query.strip().replace("'", "\\'")
        url = FILES_ENDPOINT + "?" + urlencode({"q": "name contains '" + escaped + "'", "fields": "files(id,name,mimeType,modifiedTime)", "pageSize": 20})
        return [{"id": item["id"], "name": item.get("name", ""), "mime_type": item.get("mimeType", ""), "modified_time": item.get("modifiedTime", "")} for item in self._request(url).get("files", [])]

    def read(self, file_id):
        if not isinstance(file_id, str) or not file_id:
            raise ValueError("A Drive file ID is required.")
        return self._request(FILES_ENDPOINT + "/" + quote(file_id, safe="") + "?alt=media")

    def health(self):
        try:
            self._request(FILES_ENDPOINT + "?" + urlencode({"pageSize": 1, "fields": "files(id)"}))
        except Exception as error:
            return {"ok": False, "error": type(error).__name__}
        return {"ok": True}


class GoogleDriveConnection:
    """Owns local OAuth state, private tokens, and redacted lifecycle metadata."""
    def __init__(self, store, transport, client_id, redirect_uri):
        if not all(isinstance(value, str) and value for value in (client_id, redirect_uri)):
            raise ValueError("A deployment-owned OAuth client and redirect URI are required.")
        self.store, self.transport = store, transport
        self.client_id, self.redirect_uri = client_id, redirect_uri

    def connect(self):
        verifier, challenge = _pkce_pair()
        state = secrets.token_urlsafe(32)
        self.store.secret(PENDING_SECRET, {"state": state, "verifier": verifier, "created_at": time.time()})
        # ``include_granted_scopes="false"`` matches ``Gmail.begin_oauth``: without
        # it Google may fold scopes this owner granted elsewhere into the grant,
        # and the exact-set check below would then hard-fail a connection that
        # previously succeeded.  Refusing the wider grant is correct, but not
        # requesting it in the first place is what keeps the refusal rare.
        query = urlencode({"client_id": self.client_id, "redirect_uri": self.redirect_uri, "response_type": "code", "scope": DRIVE_READONLY, "access_type": "offline", "code_challenge": challenge, "code_challenge_method": "S256", "include_granted_scopes": "false", "state": state})
        return {"authorization_url": AUTHORIZATION_ENDPOINT + "?" + query, "state": state}

    def complete(self, callback):
        pending = self.store.secret(PENDING_SECRET)
        if not isinstance(callback, dict) or not isinstance(pending, dict):
            raise DriveAuthorizationError("No pending Google Drive authorization exists.")
        if not secrets.compare_digest(str(callback.get("state", "")), str(pending.get("state", ""))):
            raise DriveAuthorizationError("Google Drive authorization state did not match.")
        if callback.get("error"):
            self._clear_pending()
            raise DriveAuthorizationError("Google Drive access was not approved.")
        if not isinstance(callback.get("code"), str) or not callback["code"]:
            raise DriveAuthorizationError("Google Drive authorization code is missing.")
        response = self.transport(TOKEN_ENDPOINT, urlencode({"client_id": self.client_id, "code": callback["code"], "code_verifier": pending["verifier"], "grant_type": "authorization_code", "redirect_uri": self.redirect_uri}), {"Content-Type": "application/x-www-form-urlencoded"})
        if not isinstance(response, dict) or not isinstance(response.get("access_token"), str):
            raise DriveAuthorizationError("Google Drive token exchange failed.")
        # Exact-set equality, matching ``Gmail._validated_tokens`` and the
        # drive_web_oauth check.  The previous form defaulted the missing key
        # to DRIVE_READONLY, so a response that omitted ``scope`` entirely
        # passed vacuously, and the substring test accepted drive.readonly
        # *plus* scopes this connector never requested.  Fail closed on both.
        if set(str(response.get("scope", "")).split()) != {DRIVE_READONLY}:
            raise DriveAuthorizationError("Google Drive read-only scope was not granted.")
        tokens = {key: response[key] for key in ("access_token", "refresh_token", "expires_in") if key in response}
        # Store the validated scope rather than the response's, so the
        # use-time check below compares against a value this code decided.
        tokens["scope"] = DRIVE_READONLY
        if isinstance(tokens.get("expires_in"), (int, float)):
            tokens["expires_at"] = time.time() + max(0, tokens["expires_in"])
        self.store.secret(TOKEN_SECRET, tokens)
        self._clear_pending()
        self.store.put(CONNECTION_CONFIG, {"state": "connected", "connected_at": time.time(), "audit": ["connected"]})
        return self.status()

    def status(self):
        value = self.store.config(CONNECTION_CONFIG, {"state": "disconnected", "audit": []})
        return {"state": value.get("state", "disconnected"), "audit": list(value.get("audit", []))}

    def health(self):
        try:
            adapter = self.adapter()
        except DriveAuthorizationError:
            return {"ok": False, "state": self.status()["state"]}
        return {**adapter.health(), "state": self.status()["state"]}

    def disconnect(self):
        prior = self.status()
        self.store.secret(TOKEN_SECRET, "")
        self._clear_pending()
        self.store.put(CONNECTION_CONFIG, {"state": "disconnected", "audit": [*prior["audit"], "disconnected"][-50:]})
        return self.status()

    def adapter(self):
        tokens = self.store.secret(TOKEN_SECRET)
        if not isinstance(tokens, dict) or not tokens.get("access_token"):
            raise DriveAuthorizationError("Google Drive is not connected.")
        if isinstance(tokens.get("expires_at"), (int, float)) and time.time() >= tokens["expires_at"]:
            prior = self.status()
            self.store.put(CONNECTION_CONFIG, {"state": "reauth-required", "audit": [*prior["audit"], "token-expired"][-50:]})
            raise DriveAuthorizationError("Google Drive authorization expired; reconnect required.")
        # Re-validate on use, as Gmail does in ``_authorization_context``.
        # Tightening the exchange alone would leave a credential stored by the
        # earlier vacuous check usable forever; this refuses it instead.
        if set(str(tokens.get("scope", "")).split()) != {DRIVE_READONLY}:
            prior = self.status()
            self.store.put(CONNECTION_CONFIG, {"state": "reauth-required", "audit": [*prior["audit"], "scope-rejected"][-50:]})
            raise DriveAuthorizationError("Google Drive read-only scope was not granted; reconnect required.")
        return GoogleDrive(self.transport, tokens["access_token"])

    def _clear_pending(self):
        self.store.secret(PENDING_SECRET, "")
