"""Current-state hypotheses and their consumption (CONTEXT-STATE-01, #627).

Slice 2 of the current-context contract (docs/current-context-contract.en.md,
playbook STATE S1-S4), under the SECRETARY-01 pilot posture
(docs/secretary-agency-contract.en.md).  It adds no engine, worker or model
call of its own:

* **Hypotheses** are rows of ``current_state_claims`` in the same QuickStore
  DB as #626's observations.  The ordinary model proposes one through the
  ``propose_current_state`` tool while handling the owner's message; the host
  validates source, owner, epoch, revision, time and scope here.  A proposal
  is an interpretation (``owner_statement_interpretation``), a report
  (``source_report``, a shared position restated) or an inference
  (``inferred``) - never sensor-verified, never owner-approved, never
  canonical Memory, and it never writes ``profile.*``.
* **The snapshot** is a bounded, source-qualified view (now/timezone, source
  ages, current hypotheses, opaque refs) that both the direct-API and the CLI
  route put into ``turn_context(..., current_context=)``.
* **Location refs** (``obs:<id>``, ``profile:place.<name>``) are resolved by
  the broker at dispatch against the *current* store state, so a pause, a
  clear, an expired or re-paired source or a deleted anchor refuses every
  later call.  This is a validity check, not a disclosure judgment: under the
  pilot an admitted place label or coordinate may go into a lookup, and the
  only deterministic filter stays the lookup composition's exclusion of
  saved private values (``Capabilities._compose``) plus the stored-secret
  redaction below.

Vocabulary is mapped, not installed: OWL-Time intervals (``effective_from``/
``effective_until``), PROV-O derivation (``source_refs``), Schema.org
``homeLocation``/``workLocation`` (the ``profile.place.*`` anchors).
"""
import json
import math
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .context_observations import (CLOCK_SKEW_SECONDS, FRESHNESS_SECONDS, POSITION_KINDS, RETENTION_SECONDS,
                                   USABLE_ENTRY_LIMIT, ContextObservations)

SNAPSHOT_VERSION = 'current-context-v1'
#: The contract's new-context budget: at most 8 entries / 4096 UTF-8 bytes,
#: inside (not in addition to) the turn context budget.
SNAPSHOT_BYTES = 4096
SNAPSHOT_ENTRIES = USABLE_ENTRY_LIMIT
PREDICATES = ('current_place', 'work_mode', 'availability_hint')
WORK_MODES = ('remote', 'office', 'off', 'away', 'unknown')
KINDS = ('owner_statement_interpretation', 'source_report', 'inferred')
VALUE_CHARS = 80
ANCHOR_CHARS = 120
#: Coordinates in the snapshot and in a weather dispatch: two decimals (about
#: 1 km).  Rounding is minimization, not anonymization.
APPROX_DECIMALS = 2
OBS_PREFIX, PROFILE_PREFIX, STATE_PREFIX, REQUEST_PREFIX = 'obs:', 'profile:', 'state:', 'request:'
CURRENT_REQUEST = 'current_request'
#: ``profile.place.*`` Memory rows are the permanent place anchors (#658).
PLACE_KEY_PREFIX = 'profile.place.'
#: The one local Memory owner (``agent_runtime.MEMORY_OWNER``; a test pins it).
PROFILE_OWNER = 'local-owner'
LOCAL_OWNER_KEY = 'local:' + PROFILE_OWNER

#: Stored secrets whose literal values never reach a prompt or a lookup (#570,
#: pilot boundary 1).  ``AgentService.KNOWN_SECRET_NAMES`` is this tuple.
def _known_secret_names():
    from .search_providers import SECRET_SLOTS
    return ('model_key', 'decision_model_key', 'decision_jev_key', 'claude_code_token', 'telegram_token',
            'api_key:openai', 'api_key:anthropic', 'api_key:openrouter', *SECRET_SLOTS)


KNOWN_SECRET_NAMES = _known_secret_names()


def redact_known_secrets(store, text):
    """The stored secrets' literal values and credential shapes, replaced.

    The deterministic pass provenance records and the #658 profile snapshot
    already use, callable from any process holding the store (the CLI's MCP
    bridge resolves profile anchors without the service).
    """
    from .bounded_execution import SECRET_PATTERN
    text = str(text or '')
    for name in KNOWN_SECRET_NAMES:
        try:
            value = store.secret(name)
        except Exception:
            value = None
        if isinstance(value, str) and len(value) >= 8:
            text = text.replace(value, '[redacted]')
    return SECRET_PATTERN.sub('[redacted]', text)


class ContextRefusal(ValueError):
    """A typed refusal (``code``) the broker turns into a ``ToolError``."""
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


REFUSALS = {
    'context_paused': '소유자가 현재 맥락 사용을 멈춰 두어 이 정보를 쓰지 않았습니다. 필요하면 소유자에게 지역을 한 번 물어보세요.',
    'location_ref_unknown': '이 위치 참조는 현재 맥락에 없거나 더 이상 쓸 수 없습니다(지웠거나 만료됐거나 다른 계정의 것). 소유자에게 현재 위치나 지역을 한 번 물어보세요.',
    'location_stale': '이 위치는 15분 넘게 지난 마지막 위치라 현재 위치로 쓰지 않았습니다. 소유자에게 지금 위치나 지역을 한 번 물어보세요.',
    'location_ref_delegated': '위임된 전문 에이전트는 소유자의 현재 위치 참조를 쓸 수 없습니다. 필요한 지역을 작업에 직접 적어 주세요.',
    'unsupported_predicate': '지원하는 현재 상황 종류는 current_place, work_mode, availability_hint입니다.',
    'invalid_value': '값이 비어 있거나 너무 깁니다. work_mode는 remote, office, off, away, unknown 중 하나입니다.',
    'unsupported_source': '근거는 current_request 또는 현재 맥락의 obs: 위치 참조만 쓸 수 있습니다. 요약이나 이전 가설은 새 근거가 아닙니다.',
    'source_unavailable': '근거로 든 메시지나 위치를 지금 쓸 수 없습니다(수정, 만료, 지우기 또는 멈춤 이후).',
    'source_time_unknown': '근거 메시지의 보낸 시각을 알 수 없어 기간을 정하지 않았습니다.',
    'timezone_unknown': '소유자 시간대가 설정되지 않아 "오늘"의 끝을 정할 수 없습니다. 끝나는 시각을 오프셋과 함께 주거나 소유자에게 시간대를 물어보세요.',
    'invalid_interval': 'until은 today, now 또는 오프셋이 있는 RFC3339 시각이어야 하며, 지금 이후이고 근거로부터 24시간 이내여야 합니다.',
    'invalid_place_ref': 'place_ref는 현재 맥락의 obs: 위치 참조 또는 저장된 profile:place. 장소여야 합니다.',
    'invalid_supersedes': '고칠 가설(state:)을 찾지 못했거나, 소유자 메시지 근거 없이 다른 가설을 대체하려 했습니다.',
}


def refusal(code):
    return ContextRefusal(REFUSALS[code], code)


# --- pure helpers (fake-clock unit tests) -----------------------------------

def iso(ts):
    """UTC ISO-8601 for a stored timestamp; UTC is representation, not the owner's zone."""
    return datetime.fromtimestamp(ts, dt_timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def zone(name):
    """The owner's chosen IANA zone, or None.  Never the server's local zone."""
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def local_day_end(source_at, timezone_name):
    """Unix time of the local midnight that ends the source utterance's day.

    Uses the owner-selected IANA zone (DST-aware through ``zoneinfo``); with
    no zone chosen it refuses rather than guessing from the server clock.
    """
    tz = zone(timezone_name)
    if tz is None:
        raise refusal('timezone_unknown')
    day = datetime.fromtimestamp(source_at, tz).date() + timedelta(days=1)
    return datetime(day.year, day.month, day.day, tzinfo=tz).timestamp()


def parse_until(until, predicate, kind, source_at, timezone_name, now):
    """``effective_until`` for one proposal, or a typed refusal.

    ``today`` ends at the source day's local midnight; ``now`` and an
    omitted value for a place or availability are one freshness interval.
    An explicit RFC3339 time needs an explicit offset.  Everything is capped
    at the temporary retention from the source time, and an ``inferred``
    hypothesis never outlives the implicit-place freshness.
    """
    if until in (None, ''):
        until = 'today' if predicate == 'work_mode' else 'now'
    if until == 'today':
        end = local_day_end(source_at, timezone_name)
    elif until == 'now':
        end = now + FRESHNESS_SECONDS
    else:
        try:
            parsed = datetime.fromisoformat(str(until).replace('Z', '+00:00'))
        except ValueError:
            raise refusal('invalid_interval') from None
        if parsed.tzinfo is None:
            raise refusal('invalid_interval')
        end = parsed.timestamp()
    if kind == 'inferred':
        end = min(end, now + FRESHNESS_SECONDS)
    end = min(end, source_at + RETENTION_SECONDS)
    if not math.isfinite(end) or end <= now:
        raise refusal('invalid_interval')
    return end


def overlaps(a, b):
    return a['effective_from'] < b['end'] and b['effective_from'] < a['end']


def mark_conflicts(claims):
    """``state`` per claim: ``conflicting`` when another live claim of the same
    predicate says something different over an overlapping interval.

    Contradictory evidence stays visible; no global newest-wins rule decides it.
    """
    for claim in claims:
        claim['state'] = 'supported'
    for index, a in enumerate(claims):
        for b in claims[index + 1:]:
            if a['predicate'] == b['predicate'] and overlaps(a, b) and \
                    (a['value'], a.get('place_ref')) != (b['value'], b.get('place_ref')):
                a['state'] = b['state'] = 'conflicting'
    return claims


def approx(value):
    return round(float(value), APPROX_DECIMALS)


def _owner_scope(db):
    """The paired Telegram owner and generation, or the one local owner."""
    identity = ContextObservations._active_identity(db)
    return identity if identity is not None else (LOCAL_OWNER_KEY, '')


class CurrentContext:
    """Hypotheses, snapshot and ref resolution over one QuickStore.

    ``observations`` shares #626's settings, clock and tables; the CLI's MCP
    bridge builds its own over the same store and gets the same answers.
    """

    def __init__(self, store, observations=None):
        self.store = store
        self.observations = observations or ContextObservations(store)

    def now(self):
        return self.observations.clock()

    def enabled(self):
        try:
            return bool(self.observations.settings()['enabled'])
        except Exception:
            return False

    # --- sources ----------------------------------------------------------

    def _request_source(self, db, job_id, settings):
        """This Work's own owner message as a source: time and edit revision."""
        job = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone() if job_id else None
        if not job:
            raise refusal('source_unavailable')
        job = dict(job)
        telegram = str(job.get('channel') or '').startswith('telegram:')
        # A Telegram message keeps its own date (#626); a local message was
        # typed where it was stored.  A missing Telegram date stays unknown.
        at = job.get('source_at') if telegram else (job.get('source_at') or job.get('created'))
        if at is None:
            raise refusal('source_time_unknown')
        if at < settings['cutoff']:
            # Sent before the last clear/resume: it cannot recreate context.
            raise refusal('source_unavailable')
        return {'ref': REQUEST_PREFIX + job['id'], 'revision': job.get('source_edited_at') or 0, 'at': float(at)}

    def _observation(self, db, scope, epoch, obs_id, now):
        row = db.execute('SELECT * FROM context_observations WHERE id=? AND owner_key=? AND generation=? '
                         "AND context_epoch=? AND expires_at>? AND state!='invalidated'",
                         (obs_id, *scope, epoch, now)).fetchone()
        if row is None or row['source_kind'] == 'text_edit':
            return None
        return row

    def _source_live(self, db, scope, epoch, source, now):
        """Is a stored source ref still exactly what the claim was derived from?"""
        ref = source.get('ref', '')
        if ref.startswith(REQUEST_PREFIX):
            job = db.execute('SELECT source_edited_at FROM jobs WHERE id=?', (ref[len(REQUEST_PREFIX):],)).fetchone()
            return job is not None and (job['source_edited_at'] or 0) == source.get('revision')
        if ref.startswith(OBS_PREFIX):
            row = self._observation(db, scope, epoch, ref[len(OBS_PREFIX):], now)
            return row is not None and row['source_revision'] == source.get('revision')
        return False

    def _place_anchor(self, key):
        """A current ``profile.place.*`` Memory row, redacted, or None."""
        if not isinstance(key, str) or not key.startswith(PLACE_KEY_PREFIX):
            return None
        for row in self.store.memories(PROFILE_OWNER, limit=101, key_prefix=PLACE_KEY_PREFIX):
            if row.get('memory_key') == key:
                label = ' '.join(redact_known_secrets(self.store, row.get('content')).split())[:ANCHOR_CHARS]
                return {'memory_key': key, 'label': label, 'memory_id': row.get('id')}
        return None

    def anchors(self):
        rows = self.store.memories(PROFILE_OWNER, limit=101, key_prefix=PLACE_KEY_PREFIX)
        out = []
        for row in sorted(rows, key=lambda row: row.get('memory_key') or ''):
            key = row.get('memory_key') or ''
            if key.startswith(PLACE_KEY_PREFIX):
                out.append({'ref': PROFILE_PREFIX + key[len('profile.'):],
                            'label': ' '.join(redact_known_secrets(self.store, row.get('content')).split())[:ANCHOR_CHARS]})
        return out

    # --- hypotheses (S1, S4) ----------------------------------------------

    def _live_claims(self, db, scope, settings, now):
        rows = db.execute("SELECT * FROM current_state_claims WHERE owner_key=? AND generation=? AND context_epoch=? "
                          "AND state='current' AND expires_at>? AND effective_until>? ORDER BY effective_from",
                          (*scope, settings['epoch'], now, now)).fetchall()
        claims = []
        for row in rows:
            sources = json.loads(row['source_refs_json'])
            if not all(self._source_live(db, scope, settings['epoch'], source, now) for source in sources):
                # A corrected, edited, cleared or expired source invalidates
                # exactly the hypotheses derived from it.
                db.execute("UPDATE current_state_claims SET state='invalidated' WHERE id=?", (row['id'],))
                continue
            value = json.loads(row['value_json'])
            claims.append({'id': row['id'], 'predicate': row['predicate'], 'value': value.get('value', ''),
                           'place_ref': value.get('place_ref'), 'kind': row['kind'], 'sources': sources,
                           'effective_from': row['effective_from'], 'effective_until': row['effective_until'],
                           'end': min(row['effective_until'], row['expires_at']), 'expires_at': row['expires_at']})
        return mark_conflicts(claims)

    def hypotheses(self, now=None):
        """Live hypotheses of the current owner and epoch (empty while paused)."""
        now = self.now() if now is None else now
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            settings = self.observations.settings(db)
            if not settings['enabled']:
                return []
            return self._live_claims(db, _owner_scope(db), settings, now)

    def propose(self, job_id, args, now=None):
        """Validate and record one model-proposed hypothesis for this Work.

        Returns a plain result either way: a refused proposal is reported to
        the model (``recorded: False`` with a typed reason) and never blocks
        the rest of the turn or fabricates a remembered fact.
        """
        now = self.now() if now is None else now
        try:
            return self._propose(job_id, args, now)
        except ContextRefusal as exc:
            return {'recorded': False, 'reason': exc.code, 'message': str(exc)}

    def _propose(self, job_id, args, now):
        predicate = args.get('predicate')
        if predicate not in PREDICATES:
            raise refusal('unsupported_predicate')
        value = ' '.join(str(args.get('value') or '').split())
        if predicate == 'work_mode' and value not in WORK_MODES:
            raise refusal('invalid_value')
        if len(value) > VALUE_CHARS or (not value and not args.get('place_ref')):
            raise refusal('invalid_value')
        source_arg = args.get('source') or CURRENT_REQUEST
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            settings = self.observations.settings(db)
            if not settings['enabled']:
                raise refusal('context_paused')
            scope = _owner_scope(db)
            epoch = settings['epoch']
            if source_arg == CURRENT_REQUEST:
                source = self._request_source(db, job_id, settings)
                kind = 'owner_statement_interpretation'
            elif isinstance(source_arg, str) and source_arg.startswith(OBS_PREFIX):
                row = self._observation(db, scope, epoch, source_arg[len(OBS_PREFIX):], now)
                if row is None:
                    raise refusal('source_unavailable')
                source = {'ref': source_arg, 'revision': row['source_revision'], 'at': row['observed_at']}
                kind = 'source_report' if predicate == 'current_place' and args.get('place_ref') == source_arg \
                    and row['source_kind'] in POSITION_KINDS else 'inferred'
            else:
                # A state:, an assistant summary or any other text is not new
                # independent evidence (CT-11).
                raise refusal('unsupported_source')
            if source['at'] > now + CLOCK_SKEW_SECONDS:
                raise refusal('source_unavailable')
            place_ref = args.get('place_ref') or None
            if place_ref is not None:
                if place_ref.startswith(OBS_PREFIX):
                    if self._observation(db, scope, epoch, place_ref[len(OBS_PREFIX):], now) is None:
                        raise refusal('invalid_place_ref')
                elif not (place_ref.startswith(PROFILE_PREFIX)
                          and self._place_anchor('profile.' + place_ref[len(PROFILE_PREFIX):])):
                    raise refusal('invalid_place_ref')
            until = parse_until(args.get('until'), predicate, kind, source['at'], settings['timezone'], now)
            if kind == 'source_report':
                row = self._observation(db, scope, epoch, source_arg[len(OBS_PREFIX):], now)
                if row['valid_until'] is None or row['valid_until'] <= now:
                    raise refusal('source_unavailable')
                until = min(until, row['valid_until'])
            effective_from = min(source['at'], now)
            new = {'predicate': predicate, 'value': value, 'place_ref': place_ref, 'effective_from': effective_from,
                   'end': until}
            live = self._live_claims(db, scope, settings, now)
            for claim in live:
                if claim['predicate'] == predicate and (claim['value'], claim['place_ref']) == (value, place_ref) \
                        and any(s['ref'] == source['ref'] for s in claim['sources']):
                    # The same proposition from the same source: no second row,
                    # no double evidence.
                    return self._result(claim, duplicate=True)
            superseded = []
            wanted = args.get('supersedes') or None
            if wanted is not None:
                target = next((c for c in live if STATE_PREFIX + c['id'] == wanted), None)
                if target is None or target['predicate'] != predicate or kind != 'owner_statement_interpretation':
                    raise refusal('invalid_supersedes')
                superseded.append(target['id'])
            if kind == 'owner_statement_interpretation':
                # The owner's later statement of the same proposition over an
                # overlapping interval corrects their earlier one; a report or
                # an inference never overrides the owner (it stays a conflict).
                superseded += [c['id'] for c in live if c['predicate'] == predicate and c['id'] not in superseded
                               and c['kind'] == 'owner_statement_interpretation' and overlaps(c, new)
                               and c['sources'][0].get('at', 0) <= source['at']]
            for claim_id in superseded:
                db.execute("UPDATE current_state_claims SET state='superseded' WHERE id=?", (claim_id,))
            claim_id = str(uuid.uuid4())
            expires_at = source['at'] + RETENTION_SECONDS
            db.execute('INSERT INTO current_state_claims VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (claim_id, *scope, epoch, predicate, json.dumps({'value': value, 'place_ref': place_ref}),
                        kind, json.dumps([source]), effective_from, until, expires_at, 1,
                        STATE_PREFIX + superseded[0] if superseded else None, 'current', job_id, now))
        return self._result({'id': claim_id, 'predicate': predicate, 'value': value, 'place_ref': place_ref,
                             'kind': kind, 'effective_from': effective_from, 'effective_until': until,
                             'end': min(until, expires_at), 'sources': [source]},
                            superseded=[STATE_PREFIX + item for item in superseded])

    @staticmethod
    def _result(claim, duplicate=False, superseded=()):
        result = {'recorded': True, 'ref': STATE_PREFIX + claim['id'], 'predicate': claim['predicate'],
                  'value': claim['value'], 'kind': claim['kind'], 'until': iso(claim['end']),
                  'note': 'A revisable, source-qualified hypothesis for the stated interval. It is not Memory, '
                          'not a profile fact and not verified GPS.'}
        if claim.get('place_ref'):
            result['place_ref'] = claim['place_ref']
        if duplicate:
            result['duplicate'] = True
        if superseded:
            result['superseded'] = list(superseded)
        return result

    # --- location refs at dispatch (S3 under the pilot) --------------------

    def resolve_location(self, job_id, ref, now=None):
        """The admitted source behind one opaque location ref, checked now.

        ``obs:<id>``: a #626 observation of the current owner, epoch and
        generation, usable for this Work (context on, or requested for this
        task), unexpired; a position must still be fresh.  Returns rounded
        coordinates.  ``profile:place.<name>``: a current ``profile.place.*``
        Memory anchor, redacted; returns its label.  Anything else refuses.
        """
        now = self.now() if now is None else now
        if not isinstance(ref, str):
            raise refusal('location_ref_unknown')
        if ref.startswith(PROFILE_PREFIX):
            anchor = self._place_anchor('profile.' + ref[len(PROFILE_PREFIX):])
            if anchor is None or not anchor['label'].strip() or anchor['label'] == '[redacted]':
                raise refusal('location_ref_unknown')
            return {'label': anchor['label'],
                    'source': {'ref': ref, 'kind': 'profile_place_anchor',
                               'basis': 'owner-saved place (canonical Memory), not a measured position'}}
        if not ref.startswith(OBS_PREFIX):
            raise refusal('location_ref_unknown')
        obs_id = ref[len(OBS_PREFIX):]
        entry = next((e for e in self.observations.usable(now=now, job_id=job_id) if e['id'] == obs_id), None)
        if entry is None or entry['kind'] == 'text_edit':
            raise refusal('location_ref_unknown' if self.enabled() else 'context_paused')
        payload = entry['payload']
        if entry['kind'] in POSITION_KINDS and entry['freshness'] != 'fresh':
            raise refusal('location_stale')
        basis = ('sender-reported position, not verified GPS' if entry['kind'] in POSITION_KINDS
                 else 'a place the owner shared, not their measured position')
        return {'latitude': approx(payload['latitude']), 'longitude': approx(payload['longitude']),
                'label': payload.get('label') or '',
                'source': {'ref': ref, 'kind': entry['kind'], 'freshness': entry['freshness'],
                           'age_seconds': max(0, int(now - entry['observed_at'])), 'basis': basis}}

    # --- snapshot (S2) -----------------------------------------------------

    def snapshot(self, job_id=None, now=None):
        """The bounded current-context snapshot for one Work, or None.

        With context use off only a location explicitly requested for this
        Work (task scope) is shown; otherwise nothing is sent and the turn is
        exactly the old text flow (CT-18).
        """
        now = self.now() if now is None else now
        settings = self.observations.settings()
        observations = [e for e in self.observations.usable(now=now, job_id=job_id) if e['kind'] != 'text_edit']
        enabled = settings['enabled']
        if not enabled and not observations:
            return None
        snap = {'version': SNAPSHOT_VERSION, 'as_of': iso(now), 'timezone': settings['timezone'] or 'unknown'}
        tz = zone(settings['timezone'])
        if tz is not None:
            local = datetime.fromtimestamp(now, tz)
            snap['local_time'] = local.isoformat(timespec='minutes') + ' ' + local.strftime('%a')
        job = self.store.job(job_id) if job_id else None
        if job:
            telegram = str(job.get('channel') or '').startswith('telegram:')
            sent = job.get('source_at') if telegram else (job.get('source_at') or job.get('created'))
            snap['request_sent_at'] = iso(sent) if sent else 'unknown'
        hypotheses = []
        if enabled:
            for claim in self.hypotheses(now):
                item = {'ref': STATE_PREFIX + claim['id'], 'predicate': claim['predicate'], 'value': claim['value'],
                        'kind': claim['kind'], 'state': claim['state'], 'since': iso(claim['effective_from']),
                        'until': iso(claim['end']), 'sources': [s['ref'] for s in claim['sources']]}
                if claim.get('place_ref'):
                    item['place_ref'] = claim['place_ref']
                hypotheses.append(item)
        locations = []
        for entry in observations:
            payload = entry['payload']
            status = entry['freshness'] if entry['state'] != 'ended' else 'stale'
            item = {'ref': OBS_PREFIX + entry['id'], 'kind': entry['kind'], 'status': status,
                    'age_min': max(0, int((now - entry['observed_at']) // 60)),
                    'approx': f"{approx(payload['latitude'])},{approx(payload['longitude'])}"}
            if payload.get('accuracy_m') is not None:
                item['accuracy_m'] = int(payload['accuracy_m'])
            if payload.get('label'):
                item['label'] = payload['label']
            if entry['state'] == 'ended':
                item['live'] = 'ended'
            if payload.get('time_uncertain'):
                item['time_uncertain'] = True
            locations.append(item)
        anchors = self.anchors() if enabled else []
        # Priority when the budget binds: hypotheses, fresh/reference places,
        # anchors, then stale last-known positions.
        fresh = [item for item in locations if item['status'] != 'stale']
        stale = [item for item in locations if item['status'] == 'stale']
        ranked = [('hypotheses', item) for item in hypotheses] + [('locations', item) for item in fresh] + \
                 [('anchors', item) for item in anchors] + [('locations', item) for item in stale]
        ranked = ranked[:SNAPSHOT_ENTRIES]
        while True:
            body = dict(snap)
            for section in ('hypotheses', 'locations', 'anchors'):
                items = [item for name, item in ranked if name == section]
                if items:
                    body[section] = items
            text = render(body)
            if len(text.encode()) <= SNAPSHOT_BYTES or not ranked:
                return body if len(text.encode()) <= SNAPSHOT_BYTES else None
            ranked.pop()

    def render(self, job_id=None, now=None):
        body = self.snapshot(job_id, now)
        return render(body) if body else None

    def status(self, now=None):
        """#626 status plus the live hypotheses the owner can inspect."""
        status = self.observations.status(now)
        status['hypotheses'] = [{'ref': STATE_PREFIX + claim['id'], 'predicate': claim['predicate'],
                                 'value': claim['value'], 'place_ref': claim.get('place_ref'), 'kind': claim['kind'],
                                 'state': claim['state'], 'until': claim['end']}
                                for claim in self.hypotheses(now)]
        return status


LEGEND = ('Refs are opaque. Pass a location ref to weather(location_ref) instead of asking again; a profile: ref is '
          'a saved place. status fresh = a recent sender-reported position (not verified GPS); stale = last known, '
          'not current; reference = a place that was shared, not where the owner is. hypotheses are revisable '
          'interpretations for their interval, not Memory; record or correct today\'s situation with '
          'propose_current_state.')


def render(body):
    """The section text: one legend line and the compact JSON snapshot."""
    return LEGEND + '\n' + json.dumps(body, ensure_ascii=False, separators=(',', ':'))
