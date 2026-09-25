"""Launch a local personal agent and its browser setup, using only Python."""
import argparse
import datetime
import fcntl
import getpass
import ipaddress
import json
import logging
import logging.handlers
import os
from pathlib import Path
import signal
import secrets
import ssl
import stat
import sys
import threading
import time
import webbrowser
from urllib.request import Request, urlopen
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from .quickstart_store import QuickStore
from .calendar import CalendarConnector
from .calendar_oauth import CalendarOAuth, EncryptedCalendarSecretStore, calendar_transport
from .google_calendar import GoogleCalendar
from .quickstart_service import AgentService, CALENDAR_CONNECT_PATH, GMAIL_CONNECT_PATH, LOCAL_ADDRESS_HOST
from .subscription_engines import SubscriptionEngines
from .conversation_handoff import ConversationHandoffError, local_refusal_text
from .plugins import PluginRegistry
from .providers import ProviderError
from .isolated_engine_gateway import IsolatedEngineGateway
from .drive_web_oauth import DriveWebOAuthHandoff, EncryptedDriveSecretStore, DriveWebOAuthError
from .connector_contract import ConnectorRegistry
from .service_control import service_action
from .connector_http import contained_opener
from .gmail import (GMAIL_CONNECTOR, EncryptedGmailSecretStore, GmailConnector,
                    GmailError)
from cryptography.fernet import Fernet
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

WEB=Path(__file__).parent/'web'
ISOLATED_MCP_PATH='/internal/isolated-engine/mcp'


def local_oauth_secret_values(store, path_value, required, label):
    """Load owner-local connector credentials without putting them in process args.

    The JSON file is intentionally outside AgentOS's data directory, owned by
    the current user, a non-symlink regular file, and mode 0600.  It is a
    runtime secret boundary for the Fernet key, the OAuth client secret, and
    any browser-restricted key; none of these values enter settings/status.

    One loader serves every local connector because the boundary is a property
    of the file, not of the connector: a second copy of these checks is a
    second place for one of them to be dropped.
    """
    if not path_value:
        return {}
    path=Path(path_value).expanduser()
    try:
        if not path.is_absolute():
            raise ValueError
        resolved=path.resolve(strict=True)
        data_root=store.root.resolve()
        details=resolved.stat()
        if (not resolved.is_absolute() or data_root==resolved or data_root in resolved.parents
                or not stat.S_ISREG(details.st_mode) or details.st_uid!=os.getuid()
                or details.st_mode & 0o077):
            raise ValueError
        value=json.loads(resolved.read_text())
    except (OSError, ValueError, json.JSONDecodeError):
        raise ValueError(f'{label} secret file must be an owner-only regular JSON file outside AgentOS data.')
    if not isinstance(value,dict):
        raise ValueError(f'{label} secret file must contain a JSON object.')
    values={key:value.get(key,'') for key in required}
    if not all(isinstance(item,str) and item for item in values.values()):
        raise ValueError(f'{label} secret file must contain every required local {label} value.')
    return values


def local_drive_secret_values(store, environ):
    """Owner-local Drive credentials: OAuth client, Fernet key, Picker key."""
    return local_oauth_secret_values(store,environ.get('AGENTOS_DRIVE_SECRET_FILE',''),
                                     ('client_id','client_secret','encryption_key','picker_api_key'),'Drive')


#: Gmail REST hosts this transport may contact. A bearer token must never
#: leave the host it was minted for, so the destination is an allowlist and
#: not "whatever URL the caller built".
#: Only the host the Gmail data plane actually calls. `gmail.py` builds every
#: endpoint from `MESSAGES_ENDPOINT`; `www.googleapis.com` appears there only
#: inside the scope *string*, never as a destination, and allowlisting it
#: widened where a token could be sent to a host no code targets.
_GMAIL_ALLOWED_HOSTS = ('gmail.googleapis.com',)


def gmail_http_transport(opener=None, timeout=20):
    """The owner-local Gmail data plane: `(method, endpoint, params, headers)`.

    `GmailConnector` accepts `transport=None` and production never supplied
    one, so the first real mail search raised `transport_unavailable` with no
    test anywhere (#457). Connection worked end to end; retrieval did not.

    Read-only by construction: anything other than GET is refused before a
    request is built, which matters because the caller has already resolved a
    bearer token into `headers` by the time this runs. Errors are returned as
    `{"status_code": ...}` rather than raised, because that is the shape
    `GmailConnector` inspects -- in particular a 401 is how it learns to move
    the connector to REAUTH_REQUIRED, and raising would lose that.
    """
    def permitted(candidate):
        parts = urlsplit(str(candidate or ''))
        # Reject userinfo outright, as `_assert_calendar_url` already does.
        # `parts.hostname` handles `https://host@evil.test` correctly, but a
        # credential-bearing URL has no legitimate use here and leaving it to
        # a later parser is how that classic bypass survives a refactor.
        if parts.username or parts.password:
            return False
        return parts.scheme == 'https' and parts.hostname in _GMAIL_ALLOWED_HOSTS

    # The allowlist has to hold across redirects, not only on the URL the
    # caller named. The default opener carries `Authorization` verbatim to
    # any host, including an https->http downgrade, for up to ten hops:
    # independent review drove an owner token to a non-allowlisted host in
    # cleartext from a single allowlisted first hop.
    contained = contained_opener(permitted)
    guarded = opener or contained.open

    def transport(method, endpoint, params, headers):
        if method != 'GET':
            raise GmailError('mutation_not_permitted')
        url = str(endpoint or '')
        parts = urlsplit(url)
        if not permitted(url):
            raise GmailError('invalid_provider_endpoint')
        if params:
            # `includeSpamTrash=False` would otherwise go out as the Python
            # literal `False`, which is not what a JSON API expects for a
            # boolean, and would fail the very first real search.
            query = urlencode({key: ('true' if value is True else
                                     'false' if value is False else value)
                               for key, value in dict(params).items()
                               if value is not None}, doseq=True)
            # Every connector endpoint is query-free today; preserving an
            # existing query is kept because dropping it would silently
            # change a caller's request, and it is pinned by a test rather
            # than left as an untested claim.
            url = urlunsplit((parts.scheme, parts.netloc, parts.path,
                              '&'.join(filter(None, (parts.query, query))), ''))
        request = Request(url, headers={**(headers or {}), 'Accept': 'application/json'})
        try:
            with guarded(request, timeout=timeout) as response:
                body = response.read(2_000_001)
                if len(body) > 2_000_000:
                    raise GmailError('provider_response_too_large')
                return json.loads(body or b'{}')
        except HTTPError as error:
            # Hand the status back rather than raising: a 401 is how the
            # connector learns the grant died.
            return {'status_code': error.code}
        except GmailError:
            # `GmailError` subclasses `ValueError`, so without this the size
            # refusal below was swallowed by our own handler and reported as
            # a generic provider failure. A bounded refusal and an unbounded
            # read that produced invalid JSON are different facts.
            raise
        except (OSError, ValueError) as exc:
            raise GmailError('provider_unavailable') from exc

    # Exposed so the wiring itself is assertable: an injected opener is a
    # test's business, but the default must be the contained one.
    transport.destination_guard = permitted
    transport.default_opener = contained
    return transport


def local_calendar_secret_values(store, environ):
    """Owner-local Calendar credentials: OAuth client and Fernet key.

    Calendar-prefixed throughout. The comment above the Gmail block records a
    real defect where one connector's closure captured another connector's
    secret while both looked correct in isolation; separate names and a
    separate Fernet namespace are what keep these two apart.
    """
    return local_oauth_secret_values(store,environ.get('AGENTOS_CALENDAR_SECRET_FILE',''),
                                     ('client_id','client_secret','encryption_key'),'Calendar')


def local_gmail_secret_values(store, environ):
    """Owner-local Gmail credentials: OAuth client and Fernet key, no Picker."""
    return local_oauth_secret_values(store,environ.get('AGENTOS_GMAIL_SECRET_FILE',''),
                                     ('client_id','client_secret','encryption_key'),'Gmail')


def localhost_tls_context(store):
    """Create a private, local-only TLS identity for Telegram browser links.

    Telegram validates inline keyboard URLs and rejects ``http://localhost``.
    This certificate gives the local entry point an HTTPS URL; it is never a
    public endpoint and contains no OAuth credential.  A browser may ask the
    owner to trust the first self-signed localhost visit.
    """
    cert_path=store.private/'drive-localhost-cert.pem'
    key_path=store.private/'drive-localhost-key.pem'
    regenerate=not cert_path.exists() or not key_path.exists()
    if not regenerate:
        try:
            names=x509.load_pem_x509_certificate(cert_path.read_bytes()).extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            regenerate='agentos.localhost' not in names.get_values_for_type(x509.DNSName)
        except (ValueError, x509.ExtensionNotFound, OSError):
            regenerate=True
    if regenerate:
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])
        certificate=(x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(minutes=1))
            .not_valid_after(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=30))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),x509.DNSName('agentos.localhost'),x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False)
            .sign(key,hashes.SHA256()))
        cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.TraditionalOpenSSL,serialization.NoEncryption()))
        cert_path.chmod(0o600); key_path.chmod(0o600)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path,key_path)
    return context


def picker_page(config, grant, nonce):
    """Return the local, no-store page that hosts the Google Picker.

    Only the OAuth client id and a referrer-restricted Picker developer key
    reach this page.  OAuth codes, access tokens, refresh tokens, and the
    server-side selection grant never appear in JavaScript configuration.
    """
    safe_config=json.dumps(config, separators=(',', ':')).replace('<','\\u003c')
    safe_grant=json.dumps(grant).replace('<','\\u003c')
    return f'''<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="referrer" content="no-referrer"><title>Google Drive 파일 선택</title>
<main><h1>Google Drive 파일 선택</h1><p id="status">Google Drive Picker를 준비하고 있습니다.</p><button id="retry" disabled>파일 선택 열기</button></main>
<script src="https://apis.google.com/js/api.js"></script><script src="https://accounts.google.com/gsi/client"></script>
<script nonce="{nonce}">
const pickerConfig={safe_config}; const selectionGrant={safe_grant};
const status=document.getElementById('status'), retry=document.getElementById('retry');
let pickerReady=false;
function fail(message) {{ status.textContent=message; retry.hidden=false; retry.disabled=false; retry.textContent='다시 열기'; }}
window.addEventListener('error',event=>{{
  const source=event.target && event.target.src ? new URL(event.target.src).hostname : '';
  fail('Google Picker 초기화 오류: '+(event.message|| (source ? source+' 스크립트를 불러오지 못했습니다.' : '브라우저에서 스크립트를 차단했습니다.')).slice(0,160));
}},true);
function sendSelection(documents) {{
  const files=documents.map(d=>({{id:d.id,name:d.name||'',mime_type:d.mimeType||''}}));
  fetch('/api/drive/picker-selection',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{grant:selectionGrant,files}})}}).then(async response=>{{
      if(!response.ok) throw new Error('selection rejected');
      status.textContent='파일 선택을 저장했습니다. Telegram에서 결과를 확인하세요.';
    }}).catch(()=>fail('파일 선택을 저장하지 못했습니다. Telegram에서 새 연결을 요청하세요.'));
}}
function openPicker() {{
  retry.disabled=true;
  if(!pickerReady || !window.google || !google.accounts) return fail('Google Picker를 불러오지 못했습니다.');
  const tokenClient=google.accounts.oauth2.initTokenClient({{client_id:pickerConfig.client_id,
    scope:'https://www.googleapis.com/auth/drive.file', callback:token=>{{
      if(token.error) return fail('Google Drive 권한이 필요합니다. 다시 시도하세요.');
      const picker=new google.picker.PickerBuilder().setDeveloperKey(pickerConfig.developer_key)
        .setAppId(pickerConfig.app_id).setOAuthToken(token.access_token)
        .setCallback(data=>{{if(data.action===google.picker.Action.PICKED) sendSelection(data.docs||[]);
          else if(data.action===google.picker.Action.CANCEL) status.textContent='파일 선택을 취소했습니다. Telegram에서 새 연결을 요청하세요.';}})
        .build(); picker.setVisible(true);
    }}}}); tokenClient.requestAccessToken({{prompt:''}});
}}
gapi.load('picker',{{callback:()=>{{pickerReady=true; status.textContent='준비되었습니다. 아래 버튼을 눌러 파일을 선택하세요.'; retry.disabled=false;}},
  onerror:()=>fail('Google Picker를 불러오지 못했습니다. API 및 브라우저 설정을 확인하세요.'),
  timeout:7000, ontimeout:()=>fail('Google Picker 로딩 시간이 초과되었습니다. 다시 열어 보세요.')}});
retry.addEventListener('click',openPicker);
</script></html>'''.encode()


def configured_service(store, environ=None):
    """Build the service with an explicitly configured isolated gateway."""
    environ=os.environ if environ is None else environ
    endpoint=environ.get('AGENTOS_ISOLATED_ENGINE_URL','')
    isolated_engine=IsolatedEngineGateway(endpoint) if endpoint else None
    # The configured sidecar is itself the Codex installation boundary.  Do
    # not inspect the AgentOS container/host PATH for a CLI that intentionally
    # lives only in the isolated engine service.  The sidecar contract supports
    # Codex only, so other engines remain unavailable in this mode.
    isolated_engines=(SubscriptionEngines(
        finder=lambda command: '/isolated-engine/codex' if command=='codex' else None
    ) if isolated_engine else None)
    drive=None
    drive_exchange=None
    drive_read=None
    picker_config=None
    if environ.get('AGENTOS_DRIVE_LOCAL_ONLY')=='1':
        secret_values=local_drive_secret_values(store,environ)
        from_secret_file=bool(environ.get('AGENTOS_DRIVE_SECRET_FILE'))
        client_id=secret_values.get('client_id') if from_secret_file else environ.get('AGENTOS_DRIVE_CLIENT_ID','')
        key=secret_values.get('encryption_key') if from_secret_file else environ.get('AGENTOS_DRIVE_ENCRYPTION_KEY','')
        client_secret=secret_values.get('client_secret') if from_secret_file else environ.get('AGENTOS_DRIVE_CLIENT_SECRET','')
        picker_key=secret_values.get('picker_api_key') if from_secret_file else environ.get('AGENTOS_DRIVE_PICKER_API_KEY','')
        port=environ.get('AGENTOS_DRIVE_LOCAL_PORT','8787')
        handoff_port=environ.get('AGENTOS_DRIVE_HANDOFF_PORT',str(int(port)+1))
        if client_id and key and client_secret and picker_key:
            callback_base=f'http://localhost:{port}'
            handoff_base=f'https://agentos.localhost:{handoff_port}'
            drive=DriveWebOAuthHandoff(EncryptedDriveSecretStore(store,key),client_id,
                callback_base+'/oauth/google/callback',handoff_base,allow_localhost=True,local_only=True)
            def drive_exchange(payload):
                body=urlencode({**payload,'client_secret':client_secret,'grant_type':'authorization_code'}).encode()
                with urlopen(Request('https://oauth2.googleapis.com/token',body,{'Content-Type':'application/x-www-form-urlencoded'}),timeout=15) as response:
                    return json.loads(response.read())
            def drive_read(url, body, headers):
                # This is the sole owner-local transport for selected Drive
                # bytes. Reject oversized responses before retaining them.
                with urlopen(Request(url, body, headers), timeout=20) as response:
                    result=response.read(1_000_001)
                if len(result)>1_000_000:
                    raise DriveWebOAuthError('Selected Google Drive file exceeds the local 1 MB text limit.')
                return result
            # Google Picker requires a browser-visible, referrer-restricted
            # developer key. It is not included in status/settings APIs.
            picker_config={'client_id':client_id,'developer_key':picker_key,
                           'app_id':client_id.split('-',1)[0]}
    connector_registry=None
    gmail=None
    gmail_exchange=None
    # Every name below is Gmail-prefixed on purpose.  `drive_exchange` above
    # is a closure over this function's locals and reads `client_secret` when
    # it is *called*, so reusing that name here would send the Gmail client
    # secret to the Drive token endpoint - one external destination receiving
    # another connector's secret - while both connectors still looked correct
    # in isolation.
    if environ.get('AGENTOS_GMAIL_LOCAL_ONLY')=='1':
        gmail_values=local_gmail_secret_values(store,environ)
        gmail_from_file=bool(environ.get('AGENTOS_GMAIL_SECRET_FILE'))
        gmail_client_id=gmail_values.get('client_id') if gmail_from_file else environ.get('AGENTOS_GMAIL_CLIENT_ID','')
        gmail_key=gmail_values.get('encryption_key') if gmail_from_file else environ.get('AGENTOS_GMAIL_ENCRYPTION_KEY','')
        gmail_client_secret=gmail_values.get('client_secret') if gmail_from_file else environ.get('AGENTOS_GMAIL_CLIENT_SECRET','')
        if gmail_client_id and gmail_key and gmail_client_secret:
            gmail_port=environ.get('AGENTOS_GMAIL_LOCAL_PORT','8787')
            if not str(gmail_port).isdigit() or not 1<=int(gmail_port)<=65535:
                raise ValueError('Local Gmail callback port must be a valid TCP port.')
            # Registration is definition only.  `ConnectorRegistry.register`
            # writes no owner row, and `prerequisite`/`require_connected` keep
            # reading DISCONNECTED until an owner completes an authorization
            # and `transition` commits the exact required scope set.  So this
            # declares that the installation *offers* Gmail; it grants nothing.
            #
            # Calendar used to be deliberately absent here, because
            # PA1-CALENDAR-01 shipped no way to obtain a Calendar credential
            # and registering the specs would have turned a truthful "not
            # configured locally" refusal into Work parked for a connection no
            # shipped route could complete.  That reasoning was right and the
            # condition it depended on is now gone: `calendar_oauth` issues the
            # credential and `/google-calendar` + `/oauth/calendar/callback`
            # below complete it.  Registration still grants nothing - both rows
            # read DISCONNECTED until an owner finishes an authorization - and
            # the construction is deliberately in the same block as the routes,
            # because either one alone is the dead end.
            connector_registry=ConnectorRegistry(store,(GMAIL_CONNECTOR,))
            gmail=GmailConnector(EncryptedGmailSecretStore(store,gmail_key),gmail_client_id,
                                 f'http://localhost:{gmail_port}/oauth/gmail/callback',
                                 registry=connector_registry,allow_localhost=True,
                                 transport=gmail_http_transport())
            def gmail_exchange(payload):
                # The owner-local token endpoint call.  The client secret is
                # added here and never reaches the connector, its state, or
                # any status surface.  `grant_type` is already in `payload`.
                body=urlencode({**payload,'client_secret':gmail_client_secret}).encode()
                with urlopen(Request('https://oauth2.googleapis.com/token',body,{'Content-Type':'application/x-www-form-urlencoded'}),timeout=15) as response:
                    return json.loads(response.read())
    # --- Google Calendar (J4) -------------------------------------------
    # Construction and routes land together, on purpose. `CalendarConnector`
    # registers both specs on construction, and registering them without a
    # completable route converts today's truthful refusal into indefinitely
    # parked Work -- the exact failure the older comment above warned about.
    calendar_factory=calendar_oauth=None
    calendar_exchange=None
    if environ.get('AGENTOS_CALENDAR_LOCAL_ONLY')=='1':
        calendar_values=local_calendar_secret_values(store,environ)
        calendar_from_file=bool(environ.get('AGENTOS_CALENDAR_SECRET_FILE'))
        calendar_client_id=calendar_values.get('client_id') if calendar_from_file else environ.get('AGENTOS_CALENDAR_CLIENT_ID','')
        calendar_key=calendar_values.get('encryption_key') if calendar_from_file else environ.get('AGENTOS_CALENDAR_ENCRYPTION_KEY','')
        calendar_client_secret=calendar_values.get('client_secret') if calendar_from_file else environ.get('AGENTOS_CALENDAR_CLIENT_SECRET','')
        if calendar_client_id and calendar_key and calendar_client_secret:
            calendar_port=environ.get('AGENTOS_CALENDAR_LOCAL_PORT','8787')
            if not str(calendar_port).isdigit() or not 1<=int(calendar_port)<=65535:
                raise ValueError('Local Calendar callback port must be a valid TCP port.')
            calendar_registry=connector_registry or ConnectorRegistry(store,())
            calendar_secrets=EncryptedCalendarSecretStore(store,calendar_key)
            calendar_oauth=CalendarOAuth(calendar_secrets,calendar_client_id,
                                         f'http://localhost:{calendar_port}/oauth/calendar/callback',
                                         registry=calendar_registry,allow_localhost=True)
            # One provider serves reads and writes; the transport picks the
            # grant from the HTTP method, so a read can never spend the write
            # credential and vice versa.
            def calendar_factory(owner_id,_registry=calendar_registry,_secrets=calendar_secrets):
                return CalendarConnector(store,GoogleCalendar(
                    calendar_transport(_secrets,_registry,owner_id,allow_writes=True)),
                    registry=_registry)
            # `CalendarOAuth` already registered both definitions above, so
            # the connect route and the parked-Work guidance agree about what
            # this install offers before any Work builds a connector.
            # Registering again here was dead code: removing it changed
            # nothing observable, which is how the mutation found it.
            connector_registry=calendar_registry
            def calendar_exchange(payload):
                # Same shape as the Gmail exchange: the client secret is added
                # here and never reaches the connector or any status surface.
                body=urlencode({**payload,'client_secret':calendar_client_secret}).encode()
                with urlopen(Request('https://oauth2.googleapis.com/token',body,{'Content-Type':'application/x-www-form-urlencoded'}),timeout=15) as response:
                    return json.loads(response.read())
    service=AgentService(store,subscription_engines=isolated_engines,
                         isolated_engine_adapter=isolated_engine,drive_web_oauth=drive,
                         connector_registry=connector_registry,gmail=gmail,
                         calendar_factory=calendar_factory,calendar_oauth=calendar_oauth)
    service.calendar_token_exchange=calendar_exchange
    service.drive_token_exchange=drive_exchange
    service.drive_read=drive_read
    service.drive_picker_config=picker_config
    service.gmail_token_exchange=gmail_exchange
    return service


def make_handler(service, public_hosts=(), public_access_token=''):
    store=service.store
    attempts=[]
    attempts_lock=threading.Lock()
    public_hosts={host.strip().lower() for host in public_hosts if host.strip()}
    pairing_lock=threading.Lock()
    pairing_available=bool(public_access_token)
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self,*args):pass

        def reply(self,status,body,content_type='application/json; charset=utf-8',cookie=None,csp=None):
            data=json.dumps(body,ensure_ascii=False).encode() if content_type.startswith('application/json') else body
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',csp or "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if cookie:self.send_header('Set-Cookie',cookie)
            self.end_headers()
            self.wfile.write(data)

        def token(self):
            cookie=SimpleCookie()
            try:cookie.load(self.headers.get('Cookie',''))
            except Exception:return ''
            return cookie['agentos_session'].value if 'agentos_session' in cookie else ''

        def auth(self):
            if store.session(self.token()):return True
            self.reply(401,{'error':'로그인이 필요합니다.'})
            return False

        def local_setup(self):
            return self.server.server_address[0] in ('127.0.0.1', '::1') and self.client_address[0] in ('127.0.0.1', '::1')

        def valid_host(self):
            if self.server.server_address[0] not in ('127.0.0.1', '::1'):return True
            allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}',f'agentos.localhost:{self.server.server_port}',f'[::1]:{self.server.server_port}'}
            if self.headers.get('Host','').lower() in allowed | public_hosts:return True
            self.reply(403,{'error':'로컬 주소로 AgentOS를 열어 주세요.'})
            return False

        def public_host(self):
            return self.headers.get('Host','').lower() in public_hosts

        def owner_local_surface(self):
            """This Mac, reached directly: loopback server, loopback client, no tunnel host.

            A tunnel forwards from loopback too, so the Host check is what keeps a
            phone on the public address from choosing or approving a Mac folder.
            """
            return self.local_setup() and not self.public_host()

        def cookie(self,token,max_age=86400):
            secure='; Secure' if os.environ.get('AGENTOS_SECURE_COOKIE')=='1' or public_hosts else ''
            return f'agentos_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={max_age}{secure}'

        def redirect(self,path,cookie=None):
            self.send_response(303)
            self.send_header('Location',path)
            self.send_header('Cache-Control','no-store')
            self.send_header('Referrer-Policy','no-referrer')
            if cookie:self.send_header('Set-Cookie',cookie)
            self.end_headers()

        def do_GET(self):
            if not self.valid_host():return
            parts=urlsplit(self.path)
            path=parts.path
            if path=='/' and self.public_host() and public_access_token:
                token=parse_qs(parts.query).get('access',[''])[0]
                nonlocal pairing_available
                with pairing_lock:
                    accepted=pairing_available and secrets.compare_digest(token,public_access_token)
                    if accepted:pairing_available=False
                if accepted:return self.redirect('/',self.cookie(store.local_session()))
            if path=='/healthz':return self.reply(200 if service.healthy() else 503,{'ok':service.healthy()})
            if path=='/google-drive':
                try:return self.redirect(service.drive_web_oauth.authorization_url_for_state(parse_qs(parts.query).get('state',[''])[0]))
                except (AttributeError, DriveWebOAuthError):return self.reply(400,b'Google Drive connection link is invalid or expired.','text/plain; charset=utf-8')
            if path=='/oauth/google/callback':
                try:
                    callback={key: values[0] for key,values in parse_qs(parts.query).items()}
                    owner=service.drive_web_oauth.callback_owner(callback.get('state'))
                    if not callable(getattr(service,'drive_token_exchange',None)):
                        raise DriveWebOAuthError('Local OAuth configuration is unavailable.')
                    service.complete_drive_web_oauth(callback,owner,service.drive_token_exchange)
                    if getattr(service,'drive_picker_config',None):
                        grant=service.drive_web_oauth.create_picker_grant(owner)
                        return self.redirect('/google-drive-picker?'+urlencode({'grant':grant}))
                    return self.reply(200,b'Google Drive connected. Return to Telegram.','text/plain; charset=utf-8')
                except (AttributeError, DriveWebOAuthError, OSError, ValueError):
                    return self.reply(400,b'Google Drive connection could not be completed. Return to Telegram and request a new link.','text/plain; charset=utf-8')
            if path==GMAIL_CONNECT_PATH:
                # The owner-authenticated half.  Starting an authorization is
                # a state change for this owner's connector row, so unlike the
                # callback it is never anonymous, and a tunnel host is refused
                # because the callback can only ever return to loopback.
                if not self.auth():return
                if self.public_host():
                    return self.reply(400,b'Open AgentOS on its local address to connect Gmail.','text/plain; charset=utf-8')
                try:return self.redirect(service.begin_gmail_connection()['authorization_url'])
                except (AttributeError, ValueError, KeyError):
                    return self.reply(400,b'Gmail connection is unavailable. Check the local Gmail configuration.','text/plain; charset=utf-8')
            if path=='/oauth/gmail/callback':
                # Google redirects a browser here, so a session cookie cannot
                # be required: the cookie is SameSite=Strict and a cross-site
                # redirect never carries it.  Authority comes from the pending
                # state instead - owner-bound, HMAC-signed, single use and
                # consumed before the code is inspected - exactly as the Drive
                # callback above is protected.  One message for every failure,
                # so a guess learns nothing about configuration or state.
                if self.public_host():
                    return self.reply(400,b'Gmail connection could not be completed. Return to Telegram and request a new link.','text/plain; charset=utf-8')
                try:
                    callback={key:values[0] for key,values in parse_qs(parts.query).items()}
                    service.complete_gmail_connection(callback)
                except (AttributeError, ValueError, OSError):
                    return self.reply(400,b'Gmail connection could not be completed. Return to Telegram and request a new link.','text/plain; charset=utf-8')
                # Says only what happened: the connection.  Whether parked Work
                # resumed is reported in the conversation that parked it.
                return self.reply(200,b'Gmail connected. Return to Telegram.','text/plain; charset=utf-8')
            if path==CALENDAR_CONNECT_PATH:
                # Same shape as the Gmail connect route: owner-authenticated,
                # loopback only. The extra piece is `grant`, because read and
                # write are separate connectors and the owner authorizes each
                # deliberately -- there is no path that turns one into both.
                if not self.auth():return
                if self.public_host():
                    return self.reply(400,b'Open AgentOS on its local address to connect Google Calendar.','text/plain; charset=utf-8')
                grant=parse_qs(parts.query).get('grant',['read'])[0]
                try:return self.redirect(service.begin_calendar_connection(grant)['authorization_url'])
                except (AttributeError, ValueError, KeyError):
                    return self.reply(400,b'Google Calendar connection is unavailable. Check the local Calendar configuration.','text/plain; charset=utf-8')
            if path=='/oauth/calendar/callback':
                # Unauthenticated by necessity, exactly as the Gmail callback
                # is: Google redirects a browser here and the SameSite=Strict
                # session cookie never survives a cross-site redirect.
                # Authority is the owner-bound, HMAC-signed, single-use state,
                # which also carries which of the two grants is completing.
                # One message for every failure, so a guess learns nothing.
                if self.public_host():
                    return self.reply(400,b'Google Calendar connection could not be completed. Start the connection again from AgentOS.','text/plain; charset=utf-8')
                try:
                    callback={key:values[0] for key,values in parse_qs(parts.query).items()}
                    service.complete_calendar_connection(callback)
                except (AttributeError, ValueError, OSError):
                    return self.reply(400,b'Google Calendar connection could not be completed. Start the connection again from AgentOS.','text/plain; charset=utf-8')
                return self.reply(200,b'Google Calendar connected. Return to Telegram.','text/plain; charset=utf-8')
            if path=='/google-drive-picker':
                grant=parse_qs(parts.query).get('grant',[''])[0]
                if not (getattr(service,'drive_picker_config',None) and service.drive_web_oauth.picker_grant_active(grant)):
                    return self.reply(400,b'Google Drive file-selection link is invalid or expired. Return to Telegram and request a new link.','text/plain; charset=utf-8')
                nonce=secrets.token_urlsafe(18)
                csp=f"default-src 'self'; script-src 'self' 'nonce-{nonce}' 'unsafe-eval' https://apis.google.com https://accounts.google.com https://*.gstatic.com; style-src 'self' 'unsafe-inline' https://accounts.google.com https://*.gstatic.com; img-src 'self' data: https:; connect-src 'self' https://*.google.com https://*.googleapis.com https://*.gstatic.com; frame-src https://*.google.com https://*.googleapis.com https://*.gstatic.com; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
                return self.reply(200,picker_page(service.drive_picker_config,grant,nonce),'text/html; charset=utf-8',csp=csp)
            if path in ('/','/app.js','/style.css'):
                filename={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[path]
                mime={'/':'text/html; charset=utf-8','/app.js':'text/javascript; charset=utf-8','/style.css':'text/css; charset=utf-8'}[path]
                return self.reply(200,(WEB/filename).read_bytes(),mime)
            if path=='/api/status':
                return self.reply(200,{'claimed':store.claimed(),'authenticated':store.session(self.token()),'local_access':self.local_setup() and store.config('local_access',False)})
            if path=='/api/drive/status':
                if not self.auth():return
                handoff=service.drive_web_oauth
                return self.reply(200,{'configured':bool(handoff),'local_only':bool(handoff),
                                       'state':handoff.status()['state'] if handoff else 'not-configured'})
            if not self.auth():return
            if path=='/api/home':return self.reply(200,service.home())
            if path=='/api/tasks':return self.reply(200,service.task_progress())
            if path=='/api/folder-requests':
                # #505: the owner-local approval surface.  Any owner session may
                # see that a request is waiting; only this Mac may choose/approve.
                return self.reply(200,{**service.local_authority_requests(),'local_surface':self.owner_local_surface()})
            if path.startswith('/api/tasks/'):
                return self.reply(200,service.task_progress(path.rsplit('/',1)[-1]))
            if path=='/api/settings':return self.reply(200,service.conversation_settings_request({'operation':'read'}))
            if path=='/api/personal-knowledge':return self.reply(200,service.personal_knowledge_request({'query':parse_qs(parts.query).get('query',[''])[0]}, channel='local-companion'))
            if path=='/api/personal-space/memory-candidates':
                return self.reply(200,service.memory_candidate_request({'operation':'list'}))
            if path=='/api/calendar/drafts':
                # The owner's own surface. A draft the model proposed is
                # inert until the owner approves and applies it here.
                #
                # Tunnel host refused, unlike the neighbouring
                # memory-candidate surface it is modelled on. That one has no
                # external effect; this one creates, changes or cancels a
                # real calendar event, and it is the first route in this
                # server that does. Every other Calendar route already
                # refuses a tunnel host and this should not be the exception.
                if self.public_host():
                    return self.reply(400,{'error':'Open AgentOS on its local address to review calendar drafts.'})
                try:return self.reply(200,service.calendar_draft_request({'operation':'list'}))
                except ValueError as exc:return self.reply(400,{'error':str(exc)})
            if path=='/api/personal-space':return self.reply(200,store.personal_space())
            if path=='/api/personal-records':
                values=parse_qs(parts.query)
                try:
                    result=store.personal_records(
                        values.get('query',[''])[0],values.get('filter',['all'])[0],
                        int(values.get('limit',['100'])[0]),int(values.get('offset',['0'])[0]))
                except (TypeError,ValueError) as error:return self.reply(400,{'error':str(error)})
                return self.reply(200,result)
            if path=='/api/workspaces':return self.reply(200,{'workspaces':service.store.workspaces()})
            if path.startswith('/api/workspaces/'):
                return self.reply(200,service.workspace(path.rsplit('/',1)[-1]))
            if path=='/api/state':
                jobs=store.jobs()
                return self.reply(200,{'settings':service.settings(),'messages':store.history(),'jobs':jobs,'notes':store.notes(),'tool_events':store.recent_tool_events(),'evidence':{job['id']:store.evidence_summary(job['id']) for job in jobs if job['status'] in ('succeeded','partial')},'healthy':service.healthy()})
            if path=='/api/onboarding':return self.reply(200,service.onboarding())
            self.reply(404,{'error':'경로를 찾을 수 없습니다.'})

        def do_DELETE(self):
            if not self.valid_host() or not self.auth():return
            path=urlsplit(self.path).path
            parts=path.split('/')
            if len(parts)==5 and parts[:3]==['','api','personal-space'] and parts[3] in ('memories','results'):
                return self.reply(200,store.delete_personal_space_item(parts[3],parts[4]))
            self.reply(404,{'error':'경로를 찾을 수 없습니다.'})

        def do_POST(self):
            if not self.valid_host():return
            parts=urlsplit(self.path)
            if parts.path==ISOLATED_MCP_PATH:
                # This is an internal engine callback, not a browser API.  A
                # session cookie never authorizes it and public tunnel hosts
                # cannot route it even when the bearer itself is valid.
                if parts.query or parts.fragment or self.public_host() or self.headers.get('Origin'):
                    return self.reply(403,{'error':'격리 엔진 전용 경로입니다.'})
                if self.headers.get('Content-Type','').split(';')[0].strip().lower()!='application/json':
                    return self.reply(415,{'error':'JSON 요청이 필요합니다.'})
                authorization=self.headers.get('Authorization','')
                prefix='Bearer '
                token=authorization[len(prefix):] if authorization.startswith(prefix) else ''
                task_id=self.headers.get('X-AgentOS-Task-ID','')
                if not token or not task_id:
                    return self.reply(401,{'error':'격리 엔진 인증이 필요합니다.'})
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=65536:raise ValueError
                    raw=self.rfile.read(length)
                except (TypeError,ValueError):
                    return self.reply(400,{'error':'요청 크기가 올바르지 않습니다.'})
                return self.reply(200,service.isolated_mcp_proxy.handle(raw,token=token,task_id=task_id))
            origin=self.headers.get('Origin')
            if origin and (urlsplit(origin).netloc!=self.headers.get('Host') or urlsplit(origin).scheme not in ('http','https')):
                return self.reply(403,{'error':'다른 사이트에서의 요청은 허용하지 않습니다.'})
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                return self.reply(415,{'error':'JSON 요청이 필요합니다.'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=65536:raise ValueError('요청 크기가 올바르지 않습니다.')
                body=json.loads(self.rfile.read(length))
                if not isinstance(body,dict):raise ValueError('JSON 객체가 필요합니다.')
                path=urlsplit(self.path).path
                if path=='/api/local-login':
                    if not self.local_setup() or not store.config('local_access',False):
                        return self.reply(403,{'error':'이 환경에서는 로그인이 필요합니다.'})
                    token=store.local_session()
                    return self.reply(200,{'ok':True},cookie=f'agentos_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400')
                if path=='/api/drive/picker-selection':
                    result=service.select_drive_picker_files(body.get('grant'),body.get('files'))
                    return self.reply(200,{'state':result['state']})
                if path in ('/api/claim','/api/login'):
                    with attempts_lock:
                        attempts[:]=[t for t in attempts if t>time.time()-60]
                        if len(attempts)>=10:return self.reply(429,{'error':'로그인 시도가 많습니다. 1분 뒤 다시 시도하세요.'})
                        attempts.append(time.time())
                    if path=='/api/claim':
                        code=body.get('code','')
                        if self.local_setup() and store.bootstrap.exists():code=store.bootstrap.read_text()
                        password=body.get('password','')
                        local_access=not password and self.local_setup()
                        if local_access:password=secrets.token_urlsafe(32)
                        store.claim(code,password,local_access=local_access)
                        body['password']=password
                    token=store.login(body.get('password',''))
                    if not token:return self.reply(401,{'error':'비밀번호가 올바르지 않습니다.'})
                    return self.reply(200,{'ok':True},cookie=self.cookie(token))
                if not self.auth():return
                if path=='/api/logout':
                    store.logout(self.token())
                    return self.reply(200,{'ok':True},cookie='agentos_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
                if path=='/api/openrouter/connect':return self.reply(200,service.connect_openrouter(body))
                if path=='/api/subscription-engines/connect':return self.reply(200,service.connect_subscription_engine(body))
                if path=='/api/subscription-engines/login-status':return self.reply(200,service.check_engine_login(body.get('engine','') if isinstance(body,dict) else ''))
                if path=='/api/subscription-engines/credential':return self.reply(200,service.save_engine_credential(body))
                if path=='/api/ai-route':return self.reply(200,service.select_ai_route(body))
                # DecisionEngine route (#580): explicit owner actions, separate from the Work route above.
                if path=='/api/decision-route/activate':return self.reply(200,service.activate_decision_route(body))
                if path=='/api/decision-route/credential':return self.reply(200,service.save_decision_route_credential(body))
                if path=='/api/decision-route/capabilities':return self.reply(200,service.check_decision_cli_capabilities(body))
                if path=='/api/openrouter/models':return self.reply(200,service.free_models())
                if path=='/api/ollama/models':return self.reply(200,service.local_models())
                if path in ('/api/folder-requests/select','/api/folder-requests/approve','/api/folder-requests/deny'):
                    # #505: choosing and approving a Mac folder happens only on this
                    # Mac.  Declining removes authority, so any owner session may.
                    action=path.rsplit('/',1)[-1]
                    if action!='deny' and not self.owner_local_surface():
                        return self.reply(403,{'error':'Mac에서 계속: 폴더 선택과 허용은 이 Mac에서 AgentOS를 직접 열어야 할 수 있습니다. 요청은 그대로 기다립니다.'})
                    try:
                        handler={'select':service.select_local_folder,'approve':service.approve_local_folder,'deny':service.deny_local_folder}[action]
                        return self.reply(200,handler(body))
                    except ConversationHandoffError as exc:
                        return self.reply(409,{'error':local_refusal_text(exc.reason),'reason':exc.reason})
                if path=='/api/files/roots':return self.reply(200,service.save_roots(body))
                if path=='/api/file-workspace':return self.reply(200,service.configure_file_workspace(body))
                if path=='/api/context-inbox/config':return self.reply(200,service.context_inbox().configure(body))
                if path=='/api/context-inbox/capture':return self.reply(200,service.context_inbox().capture(body))
                if path=='/api/context-inbox/delete':return self.reply(200,service.context_inbox().delete(body.get('id')))
                if path=='/api/context-inbox/share-policy':return self.reply(200,service.context_inbox().set_policy(body))
                if path=='/api/context-inbox/share':return self.reply(200,service.context_inbox().share(body))
                if path=='/api/settings/request':return self.reply(200,service.conversation_settings_request(body))
                if path=='/api/personal-knowledge':return self.reply(200,service.personal_knowledge_request(body, channel='local-companion'))
                if path=='/api/personal-space/memory-candidates/request':
                    return self.reply(200,service.memory_candidate_request(body))
                if path=='/api/calendar/drafts/request':
                    # See the GET above: this one applies a real external
                    # effect, so loopback only.
                    if self.public_host():
                        return self.reply(400,{'error':'Open AgentOS on its local address to approve a calendar change.'})
                    try:return self.reply(200,service.calendar_draft_request(body))
                    except ValueError as exc:return self.reply(400,{'error':str(exc)})
                if path=='/api/context-inbox/telegram-policy':return self.reply(200,service.set_context_telegram_policy(body))
                if path=='/api/documents/approval':return self.reply(200,service.set_document_approval(body))
                if path=='/api/public-pages/approval':return self.reply(200,service.set_public_page_approval(body))
                if path=='/api/model':return self.reply(200,service.save_model(body,strict=True))
                if path=='/api/model/test':return self.reply(200,service.test_model(body or None,strict=True))
                if path=='/api/telegram':return self.reply(200,service.connect_telegram(body))
                if path=='/api/telegram/pair':return self.reply(200,service.pair_telegram())
                if path=='/api/telegram/verify':return self.reply(202,service.queue_telegram_connection_verification())
                if path=='/api/telegram/disconnect':return self.reply(200,service.disconnect_telegram())
                if path=='/api/workspaces':return self.reply(201,service.create_workspace(body))
                if path.startswith('/api/workspaces/') and path.endswith('/save-result'):
                    return self.reply(200,service.save_workspace_result(path.split('/')[3],body))
                if path.startswith('/api/workspaces/'):
                    return self.reply(200,service.update_workspace(path.rsplit('/',1)[-1],body))
                if path=='/api/chat':return self.reply(202,{'id':store.enqueue(body.get('message'),body.get('request_key'),workspace_id=body.get('workspace_id'))})
                self.reply(404,{'error':'경로를 찾을 수 없습니다.'})
            except (ValueError,UnicodeDecodeError) as exc:self.reply(400,{'error':str(exc)})
            except ProviderError as exc:self.reply(502,{'error':str(exc)})
            except Exception:self.reply(500,{'error':'처리 중 오류가 발생했습니다. 저장소와 서버 상태를 확인하세요.'})
    return Handler


def plugins_main(argv):
    """Manage declaration-only plugins without loading third-party code."""
    parser=argparse.ArgumentParser(description='Manage local AgentOS plugin manifests.')
    parser.add_argument('--data',default=os.environ.get('AGENTOS_DATA',str(Path.home()/'.local/share/agentos')))
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('list')
    install=sub.add_parser('install');install.add_argument('manifest')
    enabled=sub.add_parser('enable');enabled.add_argument('id')
    disabled=sub.add_parser('disable');disabled.add_argument('id')
    remove=sub.add_parser('remove');remove.add_argument('id')
    args=parser.parse_args(argv);registry=PluginRegistry(Path(args.data))
    if args.command=='list':result=registry.list()
    elif args.command=='install':result={'installed':registry.install(args.manifest)}
    elif args.command=='enable':result=registry.set_enabled(args.id,True)
    elif args.command=='disable':result=registry.set_enabled(args.id,False)
    else:registry.remove(args.id);result={'removed':args.id}
    print(json.dumps(result,ensure_ascii=False))


def _local_oauth_secret_target(parser, path_value):
    """Resolve the ``--secret-file`` destination, refusing a relative path.

    A relative path is refused rather than resolved against the working
    directory: the runtime later re-reads this file by the absolute value the
    owner recorded, so a path that means one thing when the file is created
    and another when the service starts must not be accepted at all.
    """
    target=Path(path_value).expanduser()
    if not target.is_absolute():
        parser.error('--secret-file must be an absolute path.')
    return target


def _local_oauth_client(parser, source):
    """Read ``client_id``/``client_secret`` from a downloaded Google *web* client."""
    try:
        client=json.loads(source.read_text()).get('web',{})
        return client['client_id'],client['client_secret']
    except (OSError, ValueError, KeyError, TypeError):
        parser.error('--oauth-client-json must be a Google web OAuth client download.')


def _write_local_oauth_secret_file(parser, target, values, label):
    """Create the owner-only 0600 file ``local_oauth_secret_values`` accepts.

    One writer serves every local connector for the same reason one loader
    reads them: the 0700 parent, the ``O_EXCL`` create, the 0600 mode and the
    refusal to replace an existing file are properties of the secret-file
    boundary rather than of the connector, and a second copy of those checks
    is a second place for one of them to be dropped.  Nothing here prints a
    credential, and the file never enters process arguments or environment.
    """
    try:
        target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        if target.exists():
            parser.error(f'Refusing to replace an existing {label} secret file.')
        descriptor=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'w') as output:
            json.dump(values,output,separators=(',',':'))
        os.chmod(target,0o600)
    except OSError as exc:
        parser.error(f'Could not create the owner-only {label} secret file: '+str(exc))
    print(f'Created owner-only local {label} credential file.',flush=True)


def drive_config_main(argv):
    """Create a local-only Drive secret file without printing its contents."""
    parser=argparse.ArgumentParser(description='Create an owner-only local Google Drive credential file.')
    parser.add_argument('--oauth-client-json',required=True)
    parser.add_argument('--secret-file',required=True)
    parser.add_argument('--picker-key-stdin',action='store_true',help='Read the restricted Picker API key from standard input.')
    args=parser.parse_args(argv)
    source=Path(args.oauth_client_json).expanduser().resolve(strict=True)
    target=_local_oauth_secret_target(parser,args.secret_file)
    client_id,client_secret=_local_oauth_client(parser,source)
    picker_key=sys.stdin.read().strip() if args.picker_key_stdin else getpass.getpass('Restricted Google Picker API key: ').strip()
    if not picker_key:
        parser.error('A restricted Google Picker API key is required.')
    values={'client_id':client_id,'client_secret':client_secret,'picker_api_key':picker_key,
            'encryption_key':Fernet.generate_key().decode()}
    _write_local_oauth_secret_file(parser,target,values,'Drive')


def gmail_config_main(argv):
    """Create a local-only Gmail secret file without printing its contents.

    Deliberately the same shape as ``drive-config`` above: the same two
    arguments, the same absolute-path refusal, the same locally generated
    Fernet key, the same 0600 exclusive create, the same refusal to replace an
    existing file.  The one difference is that Gmail has no browser-visible
    Picker key to collect, so the file holds exactly the three values
    ``local_gmail_secret_values`` requires and nothing more.

    Writing this file is not a Grant and connects nothing.  It only lets the
    installation *offer* Gmail; the connector row stays DISCONNECTED until the
    owner completes an authorization through the ``/google-gmail`` route.
    """
    parser=argparse.ArgumentParser(description='Create an owner-only local Gmail credential file.')
    parser.add_argument('--oauth-client-json',required=True)
    parser.add_argument('--secret-file',required=True)
    args=parser.parse_args(argv)
    source=Path(args.oauth_client_json).expanduser().resolve(strict=True)
    target=_local_oauth_secret_target(parser,args.secret_file)
    client_id,client_secret=_local_oauth_client(parser,source)
    values={'client_id':client_id,'client_secret':client_secret,
            'encryption_key':Fernet.generate_key().decode()}
    _write_local_oauth_secret_file(parser,target,values,'Gmail')


def calendar_config_main(argv):
    """Create a local-only Calendar secret file without printing its contents.

    The same shape as ``gmail-config``: the same two arguments, the same
    absolute-path refusal, a locally generated Fernet key, the same 0600
    exclusive create, the same refusal to replace an existing file.

    Writing this file is not a Grant and connects nothing. It lets the
    installation *offer* Calendar; both `google-calendar` and
    `google-calendar-write` stay DISCONNECTED until the owner completes an
    authorization through ``/google-calendar``, and they are authorized
    separately so a read grant never widens into a write grant.
    """
    parser=argparse.ArgumentParser(description='Create an owner-only local Google Calendar credential file.')
    parser.add_argument('--oauth-client-json',required=True)
    parser.add_argument('--secret-file',required=True)
    args=parser.parse_args(argv)
    source=Path(args.oauth_client_json).expanduser().resolve(strict=True)
    target=_local_oauth_secret_target(parser,args.secret_file)
    client_id,client_secret=_local_oauth_client(parser,source)
    values={'client_id':client_id,'client_secret':client_secret,
            'encryption_key':Fernet.generate_key().decode()}
    _write_local_oauth_secret_file(parser,target,values,'Calendar')


def service_main(argv):
    """Expose the installed background-service lifecycle to the owner CLI.

    The lifecycle itself is owned by PA1-INSTALL-01 and is not reimplemented
    here: this is only the central-CLI wiring for its ``service_action`` seam.
    The seam's receipt is printed exactly as it was reported, so a launchd
    operation that was refused can never be rendered here as a success.
    """
    parser=argparse.ArgumentParser(prog='agentos service',description='Manage the macOS launchd background service for this owner.')
    parser.add_argument('action',choices=('install','upgrade','start','stop','restart','status','uninstall'))
    # Unlike the sibling subcommands this deliberately resolves no default data
    # directory. ServiceController recovers the directory from the installed
    # service definition when none is supplied, so injecting a default here
    # would make status/stop/uninstall report a directory the installed
    # service does not actually use.
    parser.add_argument('--data',default=None,help='Override the data directory (default: AGENTOS_DATA, else the installed service definition).')
    parser.add_argument('--cli-path',default=None,help='Override the agentos executable recorded in the service definition.')
    args=parser.parse_args(argv)
    options={name:value for name,value in (('data_dir',args.data),('cli_path',args.cli_path)) if value is not None}
    receipt=service_action(args.action,**options)
    print(json.dumps(receipt,ensure_ascii=False,sort_keys=True))
    return 0 if receipt.get('ok') else 1


def configure_logging(store):
    """Send AgentOS operational logs to stderr and a bounded private file.

    Callers log only ids, classes, exit codes and redacted reasons; prompt
    text, message bodies and credentials are never passed to these loggers.
    """
    logger=logging.getLogger('personal_agent')
    if logger.handlers:return
    folder=store.private/'logs';folder.mkdir(mode=0o700,exist_ok=True);folder.chmod(0o700)
    path=folder/'agentos.log'
    # Create the file owner-only before the handler opens it, independent of umask.
    os.close(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600));path.chmod(0o600)
    formatter=logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    for handler in (logging.StreamHandler(sys.stderr),
                    logging.handlers.RotatingFileHandler(path,maxBytes=1_000_000,backupCount=3,encoding='utf-8')):
        handler.setFormatter(formatter);logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate=False


def main():
    if len(sys.argv)>1 and sys.argv[1]=='plugins':
        return plugins_main(sys.argv[2:])
    if len(sys.argv)>1 and sys.argv[1]=='drive-config':
        return drive_config_main(sys.argv[2:])
    if len(sys.argv)>1 and sys.argv[1]=='calendar-config':
        return calendar_config_main(sys.argv[2:])
    if len(sys.argv)>1 and sys.argv[1]=='gmail-config':
        return gmail_config_main(sys.argv[2:])
    if len(sys.argv)>1 and sys.argv[1]=='service':
        return service_main(sys.argv[2:])
    if len(sys.argv)>1 and sys.argv[1]=='guide':
        guide=argparse.ArgumentParser(description='Show credential-free AgentOS onboarding and recovery guidance.')
        guide.add_argument('--data',default=os.environ.get('AGENTOS_DATA',str(Path.home()/'.local/share/agentos')))
        args=guide.parse_args(sys.argv[2:])
        print(json.dumps(AgentService(QuickStore(args.data)).onboarding(),ensure_ascii=False,indent=2))
        return
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',nargs='?',choices=['start'],default='start')
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8787)
    parser.add_argument('--drive-handoff-port',type=int,default=None,help='Local HTTPS entry port for Telegram Drive buttons (default: port + 1).')
    parser.add_argument('--data',default=os.environ.get('AGENTOS_DATA',str(Path.home()/'.local/share/agentos')))
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--public-tunnel-host',action='append',default=[],help='Allow one exact HTTPS tunnel host for mobile access.')
    parser.add_argument('--public-access-token',default=os.environ.get('AGENTOS_PUBLIC_ACCESS_TOKEN',''),help='One-time mobile pairing token. Generated when omitted.')
    args=parser.parse_args()
    os.umask(0o077)
    store=QuickStore(args.data)
    instance_lock=(store.private/'instance.lock').open('a')
    try:fcntl.flock(instance_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:parser.exit(1,'이 데이터 폴더의 AgentOS가 이미 실행 중입니다.\n')
    configure_logging(store)
    handoff_port=args.drive_handoff_port or args.port+1
    if handoff_port==args.port:parser.exit(2,'Drive handoff port must differ from the HTTP callback port.\n')
    env=dict(os.environ);env['AGENTOS_DRIVE_LOCAL_PORT']=str(args.port);env['AGENTOS_DRIVE_HANDOFF_PORT']=str(handoff_port)
    # The Gmail callback is served by this same HTTP listener, so the redirect
    # URI must name the port actually bound rather than a separately guessed one.
    env['AGENTOS_GMAIL_LOCAL_PORT']=str(args.port)
    service=configured_service(store,env)
    public_hosts=args.public_tunnel_host
    public_token=args.public_access_token
    if public_hosts and not public_token:public_token=secrets.token_urlsafe(24)
    try:server=ThreadingHTTPServer((args.host,args.port),make_handler(service,public_hosts,public_token))
    except OSError as exc:parser.exit(1,f'시작할 수 없습니다: {exc}\n다른 포트는 --port로 지정하세요.\n')
    service.local_server_port=server.server_port
    handoff_server=None
    if service.drive_web_oauth:
        try:
            handoff_server=ThreadingHTTPServer((args.host,handoff_port),make_handler(service))
            handoff_server.socket=localhost_tls_context(store).wrap_socket(handoff_server.socket,server_side=True)
        except (OSError, ValueError, ssl.SSLError) as exc:
            server.server_close()
            parser.exit(1,f'Google Drive local HTTPS handoff could not start: {exc}\n')
    service.start()
    if handoff_server:
        threading.Thread(target=handoff_server.serve_forever,daemon=True).start()
    # One source for the address AgentOS advertises, so the banner, the setup
    # link, the browser AgentOS opens and any connector connect link that has
    # to land on the owner's existing session can never name different hosts.
    url=f'http://{LOCAL_ADDRESS_HOST}:{server.server_port}/'
    home=url
    if not store.claimed():url+='#setup='+store.bootstrap.read_text()
    store.write_private(store.private/'setup-link.txt',url)
    print(f'AgentOS: {home}',flush=True)
    if public_hosts:
        print(f'Mobile pairing URL: https://{public_hosts[0]}/?access={public_token}',flush=True)
    if not store.claimed():print(f'초기 설정 링크: {store.private / "setup-link.txt"} (개인 파일)',flush=True)
    if not args.no_browser:threading.Timer(.6,lambda:webbrowser.open(url)).start()
    def shutdown(signum,frame):
        service.stop.set()
        threading.Thread(target=server.shutdown,daemon=True).start()
        if handoff_server:threading.Thread(target=handoff_server.shutdown,daemon=True).start()
    signal.signal(signal.SIGINT,shutdown)
    signal.signal(signal.SIGTERM,shutdown)
    try:server.serve_forever()
    finally:
        service.stop.set()
        server.server_close()
        if handoff_server:handoff_server.server_close()
        for thread in service.threads:thread.join(timeout=2)


if __name__=='__main__':sys.exit(main())
