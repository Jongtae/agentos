"""API-READ-01 (#1216): an authenticated API call by secret-slot reference, with response provenance.

C16: the owner's AI does the work - it picks the call, reads the data and
writes the answer.  AgentOS removes one blocker (the AI must call an API that
needs a key it may never hold) and keeps the invariants an AI must not own:

* **Slot.** The owner registers a named slot: its secret (stored with
  ``QuickStore.secret`` like every other owner API key, so
  ``current_context.redact_known_secrets`` covers it), the hosts it may be
  sent to, the header it goes in and, optionally, the subject the key belongs
  to.  The AI passes only the slot name; AgentOS inserts the value.  A
  redirect is never followed, so the credential never leaves a bound host.
* **Effect.** The declared ``agent_runtime.EFFECT`` is never trusted to be
  lower than the method: anything but GET/HEAD is at least ``mutate``.
  Above ``read``/``navigate`` the call needs the owner's per-step approval
  through the existing surface (``browser_session.step_binding`` and the
  service's ``browser_approvals_for``); without one it is refused.  Only a
  read is retried (once, on a transient failure); a non-read is sent once
  with an ``Idempotency-Key`` and a timeout leaves its effect ``unknown``.
* **Provenance.** Every result separates the raw response from what AgentOS
  computed, and says where it came from, when it was retrieved, what time the
  data is as of (a declared field, ``Last-Modified``, or ``unknown``), whether
  it is fresh, and whether it is complete (``partial``) and self-consistent
  (``inconsistent``).  A response for a subject other than the slot's is
  withheld.  These are general Evidence semantics: nothing here knows what
  the API is about.

Field references use the RFC 9535 JSONPath syntax, only the subset ``$``,
``.name``, ``[n]`` and ``[*]``.
"""
import email.utils
import hashlib
import ipaddress
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

#: Owner config row: ``{name: slot}`` (never the secret).
SLOTS_KEY = 'api_slots'
#: ``QuickStore.secret`` key prefix of a slot's value.
SECRET_PREFIX = 'api_slot:'
MAX_SLOTS = 16
NAME = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')
HEADER = re.compile(r'^[A-Za-z0-9-]{1,64}$')
HOST = re.compile(r'^[a-z0-9.-]{1,253}(:[0-9]{1,5})?$')
READ_METHODS = ('GET', 'HEAD')
METHODS = ('GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE')
#: ``agent_runtime.EFFECT`` in increasing order; read and navigate change nothing.
EFFECT_ORDER = ('read', 'navigate', 'mutate', 'payment')
APPROVED_EFFECTS = ('mutate', 'payment')
#: The same 15 minutes ``current_context`` uses for a stale observation.
DEFAULT_MAX_AGE = 15 * 60
MAX_AGE_LIMIT = 31 * 86400
#: A reference time this far ahead of retrieval is not believed.
CLOCK_SKEW = 5 * 60
TIMEOUT = 15
MAX_RESPONSE_BYTES = 1_000_000
MAX_BODY_BYTES = 64 * 1024
MAX_CHECKS = 8
MAX_PATH_CHARS = 200
#: The owner's short description of a slot's API (endpoints, fields), shown to the AI: content, not code.
MAX_NOTE_CHARS = 400

APPROVAL_TEXT = ('이 API 호출은 상태를 바꾸는 요청이라 소유자 승인이 필요합니다. '
                 '소유자가 이 단계를 승인하면 이 요청을 한 번만 이어서 처리합니다.')
SENT_UNREADABLE_TEXT = '변경 요청은 접수됐지만 응답을 읽지 못해 실제 결과는 확인되지 않았습니다. 상대 서비스에서 확인해 주세요.'
UNKNOWN_EFFECT_TEXT = ('상태를 바꾸는 API 요청이 응답 없이 끝나 실제로 반영됐는지 알 수 없습니다. '
                       '다시 보내지 않았습니다. 상대 서비스에서 결과를 먼저 확인해 주세요.')


class ApiError(ValueError):
    """A refusal with a stable ``code``; ``agent_runtime`` turns it into a ``ToolError``."""

    def __init__(self, message, code, requires=None, effect=None):
        super().__init__(message)
        self.code, self.requires, self.effect = code, requires, effect


# -- slots ----------------------------------------------------------------------------

def _normal_hosts(hosts):
    out = []
    for host in hosts if isinstance(hosts, (list, tuple)) else ():
        host = str(host or '').strip().lower()
        if not HOST.match(host) or host.startswith(('.', '-')):
            raise ApiError(f'허용 호스트 형식이 아닙니다: {host[:60]}', 'api_slot_invalid')
        if host not in out:
            out.append(host)
    if not 1 <= len(out) <= 8:
        raise ApiError('슬롯에는 허용 호스트가 1~8개 있어야 합니다.', 'api_slot_invalid')
    return out


def slots(store):
    """The configured slots, validated; a malformed row is skipped, never repaired."""
    try:
        rows = store.config(SLOTS_KEY, {})
    except Exception:
        return {}
    out = {}
    for name, slot in (rows.items() if isinstance(rows, dict) else ()):
        if not isinstance(name, str) or not NAME.match(name) or not isinstance(slot, dict):
            continue
        try:
            hosts = _normal_hosts(slot.get('hosts'))
        except ApiError:
            continue
        header = slot.get('header') if isinstance(slot.get('header'), str) and HEADER.match(slot['header']) else 'Authorization'
        subject = slot.get('subject') if isinstance(slot.get('subject'), dict) else None
        if subject is not None and not (isinstance(subject.get('field'), str) and isinstance(subject.get('value'), str)):
            subject = None
        max_age = slot.get('max_age_seconds')
        note = ' '.join(str(slot.get('note') or '').split())[:MAX_NOTE_CHARS]
        out[name] = {'note': note, 'name': name, 'hosts': hosts, 'header': header,
                     'scheme': slot.get('scheme') if isinstance(slot.get('scheme'), str) else '',
                     'subject': subject, 'revision': int(slot.get('revision') or 1),
                     'max_age_seconds': max_age if isinstance(max_age, int) and 0 < max_age <= MAX_AGE_LIMIT else DEFAULT_MAX_AGE}
    return out


def save_slot(store, name, hosts, secret, *, header='Authorization', scheme='Bearer', subject_field=None,
              subject_value=None, max_age_seconds=None, note=''):
    """Register or replace one slot; returns its owner-readable summary (no secret)."""
    if not isinstance(name, str) or not NAME.match(name) or len(name) > 40:
        raise ApiError('슬롯 이름은 소문자·숫자·하이픈 40자 이하입니다.', 'api_slot_invalid')
    if not isinstance(secret, str) or not 8 <= len(secret.strip()) <= 4096 or any(ch in secret for ch in '\r\n'):
        raise ApiError('비밀값은 8자 이상 한 줄이어야 합니다.', 'api_slot_invalid')
    if not isinstance(header, str) or not HEADER.match(header):
        raise ApiError('헤더 이름 형식이 아닙니다.', 'api_slot_invalid')
    subject = None
    if subject_field or subject_value:
        if not (isinstance(subject_value, str) and subject_value):
            raise ApiError('대상 필드와 값은 함께 주세요.', 'api_slot_invalid')
        parse_path(subject_field)
        subject = {'field': subject_field, 'value': subject_value}
    if max_age_seconds is not None and not (isinstance(max_age_seconds, int) and 0 < max_age_seconds <= MAX_AGE_LIMIT):
        raise ApiError('최대 허용 경과 시간은 1초~31일입니다.', 'api_slot_invalid')
    rows = store.config(SLOTS_KEY, {})
    rows = rows if isinstance(rows, dict) else {}
    if name not in rows and len(rows) >= MAX_SLOTS:
        raise ApiError(f'슬롯은 {MAX_SLOTS}개까지입니다.', 'api_slot_invalid')
    previous = rows.get(name) if isinstance(rows.get(name), dict) else {}
    note = ' '.join(str(note or '').split())
    if len(note) > MAX_NOTE_CHARS or (note and secret.strip() in note):
        raise ApiError(f'API 설명은 {MAX_NOTE_CHARS}자 이하이고 비밀값을 담지 않아야 합니다.', 'api_slot_invalid')
    row = {'note': note, 'hosts': _normal_hosts(hosts), 'header': header, 'scheme': scheme or '', 'subject': subject,
           'revision': int(previous.get('revision') or 0) + 1, 'saved_at': time.time()}
    if max_age_seconds is not None:
        row['max_age_seconds'] = max_age_seconds
    store.secret(SECRET_PREFIX + name, secret.strip())
    store.put(SLOTS_KEY, {**rows, name: row})
    return describe(slots(store)[name])


def remove_slot(store, name):
    rows = store.config(SLOTS_KEY, {})
    rows = rows if isinstance(rows, dict) else {}
    existed = rows.pop(name, None) is not None
    store.put(SLOTS_KEY, rows)
    return store.remove_secret(SECRET_PREFIX + name) or existed


def secret_names(store):
    """``QuickStore.secret`` keys of every configured slot, for the stored-secret redactor."""
    try:
        rows = store.config(SLOTS_KEY, {})
    except Exception:
        return ()
    return tuple(SECRET_PREFIX + name for name in rows if isinstance(name, str) and NAME.match(name)) if isinstance(rows, dict) else ()


def describe(slot):
    """What the owner and the AI may see of a slot: never the value."""
    return {'slot': slot['name'], 'hosts': list(slot['hosts']), 'note': slot['note'], 'subject_bound': slot['subject'] is not None,
            'max_age_seconds': slot['max_age_seconds']}


#: The current-context line naming the registered slots (names and hosts only).
CONTEXT_LINE = 'API slots (api_request; AgentOS inserts the credential, never shown): '


def context_line(store):
    """One context line naming the registered slots and their hosts, or None."""
    listed = slots(store)
    if not listed:
        return None
    return CONTEXT_LINE + '; '.join(f"{name} ({', '.join(slot['hosts'])}{': ' + slot['note'] if slot['note'] else ''})"
                                    for name, slot in sorted(listed.items()))


def effective_effect(method, declared):
    """The effect AgentOS applies: the declaration, never lower than the method implies."""
    declared = declared if declared in EFFECT_ORDER else 'mutate'
    floor = 'read' if str(method or 'GET').upper() in READ_METHODS else 'mutate'
    return max(declared, floor, key=EFFECT_ORDER.index)


# -- RFC 9535 JSONPath subset -----------------------------------------------------------

MISSING = object()
WILDCARD = object()
_SEGMENT = re.compile(r'\.([A-Za-z_][A-Za-z0-9_-]*)|\[(\*|\d{1,6})\]')


def parse_path(path):
    if not isinstance(path, str) or not path.startswith('$') or len(path) > MAX_PATH_CHARS:
        raise ApiError(f'필드 경로는 $로 시작하는 JSONPath여야 합니다: {str(path)[:60]}', 'api_path_invalid')
    segments, pos, rest = [], 0, path[1:]
    while pos < len(rest):
        match = _SEGMENT.match(rest, pos)
        if not match:
            raise ApiError(f'지원하는 JSONPath는 $, .이름, [번호], [*]입니다: {path[:60]}', 'api_path_invalid')
        name, index = match.groups()
        segments.append(name if name is not None else (WILDCARD if index == '*' else int(index)))
        pos = match.end()
    return segments


def select(data, path):
    """Every value ``path`` reaches; ``MISSING`` where a branch has no such member."""
    values = [data]
    for segment in parse_path(path):
        out = []
        for value in values:
            if value is MISSING:
                out.append(MISSING)
            elif segment is WILDCARD:
                members = value if isinstance(value, list) else list(value.values()) if isinstance(value, dict) else None
                out.extend(members if members is not None else [MISSING])
            elif isinstance(segment, int):
                out.append(value[segment] if isinstance(value, list) and segment < len(value) else MISSING)
            else:
                out.append(value[segment] if isinstance(value, dict) and segment in value else MISSING)
        values = out
    return values


_NUMBER = re.compile(r'^-?\d+(\.\d+)?([eE][-+]?\d+)?$')


def decimal_of(value):
    """An exact ``Decimal`` of a JSON number or numeric string, else None (bools are not numbers)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            number = Decimal(str(value))
        except InvalidOperation:
            return None
        return number if number.is_finite() else None
    if isinstance(value, str) and _NUMBER.match(value.strip()):
        return Decimal(value.strip())
    return None


def time_of(value):
    """An aware UTC datetime of an RFC 3339 string or epoch seconds/milliseconds; None otherwise.

    A time without an offset is ambiguous and is not believed.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value > 0:
        seconds = value / 1000 if value > 1e12 else value
        try:
            return datetime.fromtimestamp(seconds, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip())
        except ValueError:
            return None
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    return None


def _iso(moment):
    return moment.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z') if moment else None


def content_digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()[:32]


def _json_list(text, label):
    if text in (None, ''):
        return []
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        raise ApiError(f'{label}는 JSON 목록이어야 합니다.', 'api_argument_invalid') from None
    if not isinstance(value, list) or len(value) > MAX_CHECKS:
        raise ApiError(f'{label}는 {MAX_CHECKS}개 이하의 JSON 목록이어야 합니다.', 'api_argument_invalid')
    return value


def provenance(data, *, status, headers, retrieved_at, as_of_field=None, max_age_seconds=DEFAULT_MAX_AGE,
               checks=(), required_fields=()):
    """Reference time, freshness, completeness and AgentOS-derived values of one response.

    ``derived`` holds only what AgentOS computed from the raw data (an exact
    decimal sum compared with a reported total); the raw data is never
    rewritten.
    """
    as_of, as_of_source = None, 'unknown'
    if as_of_field:
        values = [value for value in select(data, as_of_field) if value is not MISSING]
        as_of = time_of(values[0]) if len(values) == 1 else None
        as_of_source = f'field:{as_of_field}' if as_of else f'field-unreadable:{as_of_field}'
    if as_of is None and headers.get('last-modified'):
        try:
            modified = email.utils.parsedate_to_datetime(headers['last-modified'])
        except (TypeError, ValueError):
            modified = None
        if modified is not None and modified.tzinfo is not None:
            as_of, as_of_source = modified.astimezone(timezone.utc), 'header:last-modified'
    age = None
    if as_of is not None and (as_of - retrieved_at).total_seconds() > CLOCK_SKEW:
        as_of, as_of_source = None, 'future-time-not-believed'
    if as_of is not None:
        age = max(0, int((retrieved_at - as_of).total_seconds()))
    freshness = 'unknown' if age is None else ('fresh' if age <= max_age_seconds else 'stale')
    missing = []
    for path in required_fields:
        if not isinstance(path, str):
            raise ApiError('required_fields는 JSONPath 문자열 목록입니다.', 'api_argument_invalid')
        values = select(data, path)
        if not values or any(value is MISSING or value is None for value in values):
            missing.append(path)
    derived = []
    for check in checks:
        if not isinstance(check, dict) or set(check) != {'sum', 'equals'}:
            raise ApiError('checks 항목은 {"sum": 경로, "equals": 경로}입니다.', 'api_argument_invalid')
        parts = [decimal_of(value) for value in select(data, check['sum'])]
        reported = [decimal_of(value) for value in select(data, check['equals'])]
        row = {'expression': f"sum({check['sum']})", 'compared_to': check['equals']}
        if not parts or None in parts or len(reported) != 1 or reported[0] is None:
            row.update({'matches': None, 'reason': 'missing-or-not-a-number'})
            missing.append(check['sum'] if not parts or None in parts else check['equals'])
        else:
            total = sum(parts, Decimal(0))
            row.update({'value': str(total), 'reported': str(reported[0]), 'matches': total == reported[0],
                        'difference': str(total - reported[0])})
        derived.append(row)
    inconsistent = any(row.get('matches') is False for row in derived)
    partial = status == 206 or bool(missing)
    completeness = 'inconsistent' if inconsistent else ('partial' if partial else 'complete')
    return {'retrieved_at': _iso(retrieved_at), 'as_of': _iso(as_of), 'as_of_source': as_of_source,
            'age_seconds': age, 'max_age_seconds': max_age_seconds, 'freshness': freshness,
            'completeness': completeness, 'missing_fields': list(dict.fromkeys(missing))[:MAX_CHECKS],
            'derived': derived, 'content_digest': content_digest(data)}


# -- transport --------------------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A credential is bound to its hosts: a redirect is answered as the 3xx it is."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_request(method, url, headers, body, timeout):
    """``(status, lower-cased headers, body bytes)`` of one request, bounded; the default transport."""
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        response = urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        data = response.read(MAX_RESPONSE_BYTES + 1)
        status = getattr(response, 'status', None) or response.code
        return status, {key.lower(): value for key, value in response.headers.items()}, data


def _loopback(host):
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def scrub(value, secret):
    """``value`` with ``secret`` replaced in every string, after JSON decoding (review P1: escaped echoes)."""
    if isinstance(value, str):
        return value.replace(secret, '[redacted]')
    if isinstance(value, list):
        return [scrub(item, secret) for item in value]
    if isinstance(value, dict):
        return {scrub(key, secret): scrub(item, secret) for key, item in value.items()}
    return value


def _transient(exc):
    return isinstance(exc, (TimeoutError, ConnectionError, urllib.error.URLError)) or \
        (isinstance(exc, OSError) and not isinstance(exc, FileNotFoundError))


class ApiRequests:
    """One Work's authenticated API calls.  ``approvals`` has ``consume(binding)``/``request(binding, text)``."""

    def __init__(self, store, work_id, *, approvals=None, transport=None, clock=time.time, sleep=time.sleep):
        self.store, self.work_id, self.approvals = store, work_id, approvals
        self.transport = transport or http_request
        self.clock, self.sleep = clock, sleep

    def slots(self):
        return slots(self.store)

    def _target(self, slot, url):
        parts = urlsplit(str(url or '').strip())
        host = (parts.hostname or '').lower()
        if parts.username or parts.password or not host:
            raise ApiError('주소에 사용자 정보 없이 호스트가 있어야 합니다.', 'api_host_not_allowed')
        if parts.scheme != 'https' and not (parts.scheme == 'http' and _loopback(host)):
            raise ApiError('API 주소는 https여야 합니다(이 컴퓨터 안의 주소만 http 허용).', 'api_host_not_allowed')
        try:
            port = parts.port
        except ValueError:
            raise ApiError('주소의 포트를 확인하세요.', 'api_host_not_allowed') from None
        named = f'{host}:{port}' if port else host
        if named not in slot['hosts']:
            raise ApiError(f"슬롯 '{slot['name']}'은 {', '.join(slot['hosts'])}에만 보낼 수 있어 보내지 않았습니다.",
                           'api_host_not_allowed')
        return parts, named

    def _approve(self, slot, method, url, body, effect, named, path):
        """Consume the owner's approval of exactly this call, or request it and refuse."""
        from .browser_session import binding_digest, step_binding
        # The full URL (query included) is the target: an approval never covers another query.
        binding = step_binding(self.work_id, 'api_request', url, f"{slot['name']}|{method}|{url}", argument=body or '',
                               state=f"{slot['name']}@{slot['revision']}|{effect}")
        approvals = self.approvals
        if approvals is not None and approvals.consume(binding):
            return binding_digest(binding)[:32]
        if approvals is not None:
            # The owner approves what is sent: the query and the body come first, so a bounded label keeps them.
            query = urlsplit(url).query
            sent = ' '.join(part for part in (f'?{query}' if query else '', ' '.join(str(body or '').split())) if part)
            approvals.request(binding, f"{method} {path} {sent} → {named} ({slot['name']}, {effect})".replace('  ', ' '))
        raise ApiError(APPROVAL_TEXT, 'approval_required', requires='api-step-approval')

    def call(self, args):
        slot = self.slots().get(args.get('slot'))
        if slot is None:
            names = ', '.join(sorted(self.slots())) or '없음'
            raise ApiError(f'등록된 API 슬롯이 아닙니다. 쓸 수 있는 슬롯: {names}.', 'api_slot_unknown')
        method = str(args.get('method') or 'GET').upper()
        if method not in METHODS:
            raise ApiError('지원하는 메서드는 ' + ', '.join(METHODS) + '입니다.', 'api_argument_invalid')
        url = str(args.get('url') or '').strip()
        parts, named = self._target(slot, url)
        path = parts.path or '/'
        effect = effective_effect(method, args.get('effect'))
        body = args.get('body') or None
        if body is not None and (method in READ_METHODS or len(body.encode()) > MAX_BODY_BYTES):
            raise ApiError('본문은 GET/HEAD가 아닌 요청에만, 64KB 이하로 보낼 수 있습니다.', 'api_argument_invalid')
        checks = _json_list(args.get('checks'), 'checks')
        required = _json_list(args.get('required_fields'), 'required_fields')
        if args.get('as_of_field'):
            parse_path(args['as_of_field'])
        max_age = slot['max_age_seconds']
        if args.get('max_age_seconds'):
            text = str(args['max_age_seconds']).strip()
            if not text.isdigit() or not 0 < int(text) <= MAX_AGE_LIMIT:
                raise ApiError('max_age_seconds는 1~2678400 사이 정수입니다.', 'api_argument_invalid')
            # The AI may only tighten the slot's freshness bound, never widen it (review P1).
            max_age = min(int(text), max_age)
        idempotency = self._approve(slot, method, url, body, effect, named, path) if effect in APPROVED_EFFECTS else None
        secret = self.store.secret(SECRET_PREFIX + slot['name'])
        if not secret:
            raise ApiError(f"슬롯 '{slot['name']}'의 비밀값이 없어 호출하지 않았습니다. 먼저 등록해 주세요.", 'needs_setup',
                           requires=f"api-slot:{slot['name']}")
        headers = {slot['header']: f"{slot['scheme']} {secret}".strip() if slot['scheme'] else secret,
                   'Accept': 'application/json', 'User-Agent': 'personal-agentos'}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        if idempotency:
            headers['Idempotency-Key'] = idempotency
        tries = 2 if effect not in APPROVED_EFFECTS else 1
        attempts = 0
        while True:
            attempts += 1
            try:
                status, response_headers, raw = self.transport(method, url, headers, body.encode() if body else None, TIMEOUT)
            except Exception as exc:
                if not _transient(exc):
                    raise ApiError('API 요청을 보내지 못했습니다.', 'api_unavailable') from None
                if attempts < tries:
                    self.sleep(1)
                    continue
                if effect in APPROVED_EFFECTS:
                    raise ApiError(UNKNOWN_EFFECT_TEXT, 'effect_unknown', effect='unknown') from None
                raise ApiError(f'API가 응답하지 않았습니다({attempts}회 시도). 잠시 후 다시 시도해 주세요.', 'api_unavailable') from None
            if (status >= 500 or status == 429) and attempts < tries:
                self.sleep(1)
                continue
            break
        retrieved = datetime.fromtimestamp(self.clock(), timezone.utc)
        if 300 <= status < 400:
            raise ApiError('API가 다른 주소로 보내려 해 따라가지 않았습니다(키는 허용 호스트에만 보냅니다).', 'api_redirect_refused')
        if status in (401, 403):
            raise ApiError(f"API가 인증을 거절했습니다(HTTP {status}). 슬롯 '{slot['name']}'의 키나 권한을 확인해 주세요.",
                           'api_unauthorized', requires=f"api-slot:{slot['name']}")
        if status >= 400:
            raise ApiError(f'API가 오류로 답했습니다(HTTP {status}, {method} {path}).'
                           + (' 이 경로가 없습니다. 슬롯 설명의 경로를 확인하세요.' if status == 404 else ''), 'api_error',
                           effect='unknown' if effect in APPROVED_EFFECTS and status >= 500 else None)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ApiError('응답이 너무 커서 읽지 않았습니다.' + (' ' + SENT_UNREADABLE_TEXT if effect in APPROVED_EFFECTS else ''),
                           'api_response_too_large', effect='unknown' if effect in APPROVED_EFFECTS else None)
        # The key never comes back to the AI, even if the service echoes it.
        text = raw.decode('utf-8', 'replace').replace(secret, '[redacted]')
        try:
            data = json.loads(text) if text.strip() else None
        except ValueError:
            raise ApiError('응답이 JSON이 아니어서 쓰지 않았습니다.' + (' ' + SENT_UNREADABLE_TEXT if effect in APPROVED_EFFECTS else ''),
                           'api_not_json', effect='unknown' if effect in APPROVED_EFFECTS else None) from None
        # An escaped echo (``\"`` or ``\u`` in the JSON text) decodes back to the key: scrub the decoded values too.
        data = scrub(data, secret)
        # A read for another subject is withheld.  A sent change already happened, so it is not
        # reported as a failure; its response body is withheld instead when it is not the
        # slot's subject (review P1: another account's data must not reach the AI either way).
        subject = slot['subject']
        subject_verified = False
        if subject is not None:
            found = [value for value in select(data, subject['field']) if value is not MISSING]
            subject_verified = len(found) == 1 and str(found[0]) == subject['value']
            if not subject_verified and effect not in APPROVED_EFFECTS:
                raise ApiError(f"응답이 슬롯 '{slot['name']}'에 묶인 대상의 것인지 확인되지 않아 쓰지 않았습니다.",
                               'api_subject_mismatch')
            if not subject_verified:
                data = None
        record = provenance(data, status=status, headers=response_headers, retrieved_at=retrieved,
                            as_of_field=args.get('as_of_field') or None, max_age_seconds=max_age,
                            checks=checks, required_fields=required)
        record.update({'source': {'slot': slot['name'], 'host': named, 'path': path, 'method': method,
                                  # The owner can tell which resource was asked for (the key is never in a URL).
                                  **({'query': parts.query[:200]} if parts.query else {})},
                       'status': status, 'effect': effect, 'attempts': attempts,
                       'subject_verified': subject_verified})
        return {'data': data, 'provenance': record, 'sources': [f'{parts.scheme}://{named}{path}'],
                # Typed Evidence qualifiers (``agent_runtime.EVIDENCE_QUALIFIER_FLAGS``).
                'stale': record['freshness'] == 'stale', 'as_of_unknown': record['freshness'] == 'unknown',
                'partial': record['completeness'] == 'partial', 'inconsistent': record['completeness'] == 'inconsistent'}


def evidence(result):
    """The durable record of one call: provenance only, never the payload or the key."""
    record = result.get('provenance') if isinstance(result.get('provenance'), dict) else {}
    keep = ('source', 'status', 'effect', 'attempts', 'retrieved_at', 'as_of', 'as_of_source', 'age_seconds',
            'max_age_seconds', 'freshness', 'completeness', 'missing_fields', 'content_digest', 'subject_verified')
    out = {key: record[key] for key in keep if key in record}
    out['derived'] = [{key: row[key] for key in ('expression', 'compared_to', 'matches', 'reason') if key in row}
                      for row in record.get('derived') or ()]
    out['sources'] = list(result.get('sources') or ())[:4]
    return out
