"""Current-context input: attributable Telegram observations and source time (#626).

Slice 1 of the current-context contract (`docs/current-context-contract.en.md`,
playbook INPUT I1-I4).  It records what the paired owner *volunteered* - a
shared point, a live-location share, an edited text - with its own source
identity and source time, in the same QuickStore database and inside the
caller's Telegram-ingress transaction.  It never starts a location fetch,
geocoder, model call, Work or reply: a location tick is data, not a request.

Truth vocabulary kept here, never widened:

* ``current_position_report`` - a static point sent in answer to an
  outstanding owner-bound location request.  Sender-reported, not verified
  GPS.
* ``live_position_report`` - a live share the owner started.  Each point ages
  on its own (15-minute freshness) even when the share window is long.
* ``place_reference`` - an unsolicited pin, a venue or a forwarded location.
  It names a place; it is never the owner's present position by inference.
* ``text_edit`` - the owner edited an earlier text.  It invalidates context
  derived from the old wording (#627 reads the revision); it never replays
  the original Work.

Consumption (a model snapshot, weather/search location refs) is #627; this
module only exposes :meth:`ContextObservations.usable` for it.  Precise
coordinates are never logged and never returned by :meth:`status`.
"""
import json
import math
import time
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .conversation_handoff import RESUME_TTL_SECONDS

CONFIG_KEY = 'current_context'
POLICY_VERSION = 1
#: Engineering defaults from the contract, not measured accuracy guarantees.
RETENTION_SECONDS = 24 * 60 * 60
FRESHNESS_SECONDS = 15 * 60
CLOCK_SKEW_SECONDS = 5 * 60
USABLE_ENTRY_LIMIT = 8
#: Telegram's documented horizontal accuracy range.
MAX_ACCURACY_M = 1500
#: Telegram's "live until stopped" live_period sentinel.
INDEFINITE_LIVE_PERIOD = 0x7FFFFFFF
#: An outstanding location prompt lives as long as a handoff resume.
LOCATION_REQUEST_TTL_SECONDS = RESUME_TTL_SECONDS
MAX_MESSAGE_ID = 2 ** 53
LABEL_CHARS = 200
EDITED_TEXT_CHARS = 4000
POSITION_KINDS = ('current_position_report', 'live_position_report')
#: Someone else's place (a forward or an inline bot's result), never the
#: owner's present position.
FORWARD_FIELDS = ('forward_origin', 'forward_date', 'forward_from', 'forward_from_chat',
                  'forward_sender_name', 'forward_from_message_id', 'via_bot')

DEFAULT_SETTINGS = {'version': POLICY_VERSION, 'enabled': False, 'epoch': 0, 'cutoff': 0.0, 'timezone': ''}


def _number(value):
    """A finite real number; bool, NaN and Infinity are not coordinates."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _source_time(value):
    """A Telegram Unix date, or None when it is absent or not a real date."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return float(value)


def valid_timezone(name):
    """An IANA zone name the stdlib resolves, or '' for "not chosen"."""
    if name == '':
        return ''
    if not isinstance(name, str) or len(name) > 64 or name.startswith(('/', '.')) or '..' in name:
        raise ValueError('시간대는 Asia/Seoul 같은 IANA 이름으로 입력하세요.')
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError('알 수 없는 시간대입니다. Asia/Seoul 같은 IANA 이름으로 입력하세요.') from None
    return name


def normalize_point(location):
    """Keep only the scoped fields of a Telegram ``Location``; None if invalid."""
    if not isinstance(location, dict):
        return None
    latitude, longitude = _number(location.get('latitude')), _number(location.get('longitude'))
    if latitude is None or longitude is None or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    point = {'latitude': latitude, 'longitude': longitude, 'accuracy_m': None}
    if 'horizontal_accuracy' in location:
        accuracy = _number(location.get('horizontal_accuracy'))
        if accuracy is None or not 0 <= accuracy <= MAX_ACCURACY_M:
            return None
        point['accuracy_m'] = accuracy
    return point


def _live_period(location):
    value = location.get('live_period') if isinstance(location, dict) else None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def owner_key(owner_id):
    return f'telegram:{owner_id}'


class ContextObservations:
    """Owner-scoped observation store inside the existing QuickStore DB."""

    def __init__(self, store, clock=time.time):
        self.store = store
        self.clock = clock
        with store.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS context_observations(
              id TEXT PRIMARY KEY, owner_key TEXT NOT NULL, generation TEXT NOT NULL,
              context_epoch INTEGER NOT NULL, source_key TEXT NOT NULL, source_revision INTEGER NOT NULL,
              revision_at REAL NOT NULL, revision_update_id INTEGER NOT NULL, source_kind TEXT NOT NULL,
              source_job_id TEXT, observed_at REAL NOT NULL, received_at REAL NOT NULL, valid_until REAL,
              expires_at REAL NOT NULL, payload_json TEXT NOT NULL, state TEXT NOT NULL,
              UNIQUE(owner_key, generation, context_epoch, source_key));
            CREATE INDEX IF NOT EXISTS context_observations_use
              ON context_observations(owner_key, context_epoch, state, expires_at);
            CREATE INDEX IF NOT EXISTS context_observations_source ON context_observations(source_key);
            CREATE INDEX IF NOT EXISTS context_observations_job ON context_observations(source_job_id);
            CREATE TABLE IF NOT EXISTS context_location_requests(
              id TEXT PRIMARY KEY, job_id TEXT NOT NULL, chat_id INTEGER NOT NULL, generation TEXT NOT NULL,
              context_epoch INTEGER NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, state TEXT NOT NULL);
            ''')

    # --- settings ---------------------------------------------------------

    @staticmethod
    def _normalize(raw):
        """Stored settings, falling back to the safe default for bad values."""
        settings = dict(DEFAULT_SETTINGS)
        if not isinstance(raw, dict):
            return settings
        if isinstance(raw.get('enabled'), bool):
            settings['enabled'] = raw['enabled']
        epoch = raw.get('epoch')
        if isinstance(epoch, int) and not isinstance(epoch, bool) and 0 <= epoch < 2 ** 62:
            settings['epoch'] = epoch
        cutoff = _number(raw.get('cutoff'))
        if cutoff is not None and cutoff >= 0:
            settings['cutoff'] = cutoff
        try:
            settings['timezone'] = valid_timezone(raw.get('timezone', ''))
        except ValueError:
            settings['timezone'] = ''
        return settings

    def settings(self, db=None):
        if db is None:
            return self._normalize(self.store.config(CONFIG_KEY))
        row = db.execute('SELECT value FROM config WHERE key=?', (CONFIG_KEY,)).fetchone()
        try:
            return self._normalize(json.loads(row['value']) if row else None)
        except (TypeError, ValueError):
            return dict(DEFAULT_SETTINGS)

    @staticmethod
    def _put(db, settings):
        db.execute('INSERT INTO config VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                   (CONFIG_KEY, json.dumps(settings)))

    def set_controls(self, body):
        """Owner control: exactly ``enabled`` / ``timezone`` / ``clear``.

        Starts no GPS, geocoder, model call or background job.  Enabling sets
        an ingestion cutoff so updates sent while paused are not backfilled;
        clearing removes the temporary values and bumps the context epoch so
        late updates and old sources cannot resurrect them.
        """
        if not isinstance(body, dict) or not body or set(body) - {'enabled', 'timezone', 'clear'}:
            raise ValueError('현재 맥락 설정은 사용 여부, 시간대, 지우기만 바꿀 수 있습니다.')
        if 'enabled' in body and not isinstance(body['enabled'], bool):
            raise ValueError('사용 여부는 켜기 또는 끄기로 선택하세요.')
        if 'clear' in body and body['clear'] is not True:
            raise ValueError('지우기 요청이 올바르지 않습니다.')
        timezone = valid_timezone(body['timezone']) if 'timezone' in body else None
        now = self.clock()
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            settings = self.settings(db)
            if body.get('enabled') is True and not settings['enabled']:
                settings['cutoff'] = max(settings['cutoff'], now)
            if 'enabled' in body:
                settings['enabled'] = body['enabled']
            if timezone is not None:
                settings['timezone'] = timezone
            if body.get('clear'):
                settings['epoch'] += 1
                settings['cutoff'] = max(settings['cutoff'], now)
                db.execute('DELETE FROM context_observations')
                db.execute("UPDATE context_location_requests SET state='cleared' WHERE state='pending'")
            self._put(db, settings)
        return self.status()

    # --- reads ------------------------------------------------------------

    @staticmethod
    def _active_identity(db):
        """The currently paired Telegram owner and generation, or None.

        Reads are scoped to it so a disconnect or re-pair never exposes the
        previous account's observations, even inside the retention window.
        """
        row = db.execute("SELECT value FROM config WHERE key='telegram'").fetchone()
        try:
            cfg = json.loads(row['value']) if row else {}
        except (TypeError, ValueError):
            return None
        user_id, generation = cfg.get('user_id'), cfg.get('generation')
        if not cfg.get('enabled') or not isinstance(user_id, int) or isinstance(user_id, bool) or not generation:
            return None
        return owner_key(user_id), generation

    def prune(self, db, now):
        db.execute('DELETE FROM context_observations WHERE expires_at<=?', (now,))
        db.execute("UPDATE context_location_requests SET state='expired' WHERE state='pending' AND expires<=?", (now,))

    @staticmethod
    def _entry(row, now):
        payload = json.loads(row['payload_json'])
        if row['source_kind'] in POSITION_KINDS:
            fresh = row['valid_until'] is not None and now <= row['valid_until']
            freshness = 'fresh' if fresh else 'stale'
        else:
            freshness = 'reference' if row['source_kind'] == 'place_reference' else 'source'
        return {'id': row['id'], 'kind': row['source_kind'], 'source_key': row['source_key'],
                'revision': row['source_revision'], 'observed_at': row['observed_at'],
                'received_at': row['received_at'], 'valid_until': row['valid_until'],
                'expires_at': row['expires_at'], 'state': row['state'], 'freshness': freshness,
                'job_id': row['source_job_id'], 'payload': payload}

    def usable(self, now=None, job_id=None):
        """Current-epoch, unexpired observations for #627 to consume.

        With context use off only a location explicitly requested for
        ``job_id`` is returned (task scope); nothing else is reused.
        """
        now = self.clock() if now is None else now
        with self.store.db() as db:
            settings = self.settings(db)
            identity = self._active_identity(db)
            rows = [] if identity is None else db.execute(
                'SELECT * FROM context_observations WHERE owner_key=? AND generation=? AND context_epoch=? '
                "AND expires_at>? AND state!='invalidated' ORDER BY observed_at DESC",
                (*identity, settings['epoch'], now)).fetchall()
        entries = [self._entry(row, now) for row in rows]
        if not settings['enabled']:
            entries = [entry for entry in entries if job_id is not None and entry['job_id'] == job_id
                       and entry['payload'].get('scope') == 'task']
        return entries[:USABLE_ENTRY_LIMIT]

    def status(self, now=None):
        """Owner-visible, redacted status: kind/source/age, never coordinates."""
        now = self.clock() if now is None else now
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self.prune(db, now)
            settings = self.settings(db)
            identity = self._active_identity(db)
            rows = [] if identity is None else db.execute(
                'SELECT * FROM context_observations WHERE owner_key=? AND generation=? AND context_epoch=? '
                'ORDER BY observed_at DESC LIMIT ?', (*identity, settings['epoch'], USABLE_ENTRY_LIMIT)).fetchall()
            pending = db.execute("SELECT count(*) FROM context_location_requests WHERE state='pending' AND expires>?",
                                 (now,)).fetchone()[0]
        items = []
        for row in rows:
            entry = self._entry(row, now)
            items.append({'kind': entry['kind'], 'source': 'telegram', 'state': entry['state'],
                          'freshness': entry['freshness'], 'age_seconds': max(0, int(now - entry['observed_at'])),
                          'expires_at': entry['expires_at'], 'label': entry['payload'].get('label') or '',
                          'time_uncertain': bool(entry['payload'].get('time_uncertain'))})
        return {'enabled': settings['enabled'], 'timezone': settings['timezone'],
                # Truthful boundary: #626 stores; answers do not read it yet (#627).
                'used_in_answers': False,
                'retention_hours': RETENTION_SECONDS // 3600, 'freshness_minutes': FRESHNESS_SECONDS // 60,
                'observations': [item for item in items if item['kind'] != 'text_edit'],
                'edited_sources': sum(1 for item in items if item['kind'] == 'text_edit'),
                'pending_location_request': bool(pending)}

    # --- location request binding (I3) ------------------------------------

    def open_location_request(self, job_id, chat_id, generation, now=None):
        """Bind one outstanding current-location prompt to one Work."""
        now = self.clock() if now is None else now
        request_id = str(uuid.uuid4())
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            epoch = self.settings(db)['epoch']
            db.execute("UPDATE context_location_requests SET state='superseded' WHERE state='pending' AND chat_id=? "
                       'AND generation=?', (chat_id, generation))
            db.execute('INSERT INTO context_location_requests VALUES (?,?,?,?,?,?,?,?)',
                       (request_id, job_id, chat_id, generation, epoch, now, now + LOCATION_REQUEST_TTL_SECONDS,
                        'pending'))
        return request_id

    def cancel_location_request(self, request_id):
        with self.store.db() as db:
            db.execute("UPDATE context_location_requests SET state='cancelled' WHERE id=? AND state='pending'",
                       (request_id,))

    @staticmethod
    def _consume_request(db, chat_id, generation, epoch, sent_at, now):
        row = db.execute("SELECT * FROM context_location_requests WHERE state='pending' AND chat_id=? AND generation=? "
                         'AND context_epoch=? AND expires>? AND created<? ORDER BY created DESC LIMIT 1',
                         # A point sent before the prompt existed is not its
                         # answer (Telegram dates are whole seconds).
                         (chat_id, generation, epoch, now, sent_at + 1)).fetchone()
        if not row:
            return None
        db.execute("UPDATE context_location_requests SET state='consumed' WHERE id=?", (row['id'],))
        return row['job_id']

    # --- ingress (I2), always inside the caller's BEGIN IMMEDIATE ----------

    def note_text_source(self, db, job_id, message, generation):
        """Stamp a new text Work with its own source time and identity.

        A missing or future-skewed date stays unknown (NULL); the worker start
        time or receipt time is never substituted.
        """
        chat_id = (message.get('chat') or {}).get('id')
        message_id = message.get('message_id')
        if not isinstance(chat_id, int) or not self._valid_message_id(message_id):
            return
        source_at = _source_time(message.get('date'))
        if source_at is not None and source_at > self.clock() + CLOCK_SKEW_SECONDS:
            source_at = None
        db.execute('UPDATE jobs SET source_at=?,source_message_key=? WHERE id=? AND source_message_key IS NULL',
                   (source_at, self.source_key(generation, chat_id, message_id), job_id))

    @staticmethod
    def source_key(generation, chat_id, message_id):
        return f'telegram:{generation}:{chat_id}:{message_id}'

    @staticmethod
    def _valid_message_id(value):
        return isinstance(value, int) and not isinstance(value, bool) and 0 < value < MAX_MESSAGE_ID

    def ingest_telegram(self, db, update, generation, owner_id):
        """Record one already-authorized owner update; return a short outcome.

        The caller has checked generation, private chat and the paired owner
        and holds ``BEGIN IMMEDIATE``; its cursor advance commits with this
        write or rolls back with it.  Outcomes are content-free diagnostics.
        """
        now = self.clock()
        self.prune(db, now)
        edited = not isinstance(update.get('message'), dict) and isinstance(update.get('edited_message'), dict)
        message = update['edited_message'] if edited else update.get('message')
        if not isinstance(message, dict):
            return 'ignored:unsupported'
        chat_id, message_id = (message.get('chat') or {}).get('id'), message.get('message_id')
        if not isinstance(chat_id, int) or not self._valid_message_id(message_id):
            return 'rejected:identity'
        settings = self.settings(db)
        key = self.source_key(generation, chat_id, message_id)
        sent_at = _source_time(message.get('date'))
        if sent_at is None:
            return 'rejected:unknown_time'
        edit_at = _source_time(message.get('edit_date')) if edited else None
        observed_at = edit_at or sent_at
        uncertain = edited and edit_at is None
        if observed_at > now + CLOCK_SKEW_SECONDS:
            return 'rejected:future_time'
        if edited and isinstance(message.get('text'), str):
            return self._text_edit(db, settings, key, message, owner_id, generation, observed_at, uncertain,
                                   update['update_id'], now)
        venue = message.get('venue') if isinstance(message.get('venue'), dict) else None
        location = venue.get('location') if venue else message.get('location')
        if not isinstance(location, dict):
            return 'ignored:unsupported'
        point = normalize_point(location)
        if point is None:
            return 'rejected:invalid_location'
        owner = owner_key(owner_id)
        existing = db.execute('SELECT * FROM context_observations WHERE owner_key=? AND generation=? '
                              'AND context_epoch=? AND source_key=?',
                              (owner, generation, settings['epoch'], key)).fetchone()
        # A source first seen now must postdate the cutoff; a share already
        # recorded in this epoch (so not cleared) may continue after a resume.
        if (observed_at if existing else sent_at) < settings['cutoff']:
            return 'rejected:before_cutoff'
        if observed_at + RETENTION_SECONDS <= now:
            return 'rejected:expired'
        if existing and (observed_at, update['update_id']) <= (existing['revision_at'], existing['revision_update_id']):
            return 'ignored:stale_revision'
        live_period = _live_period(location)
        payload = {**point, 'live': False, 'time_uncertain': uncertain}
        if venue:
            label = venue.get('title')
            payload['label'] = label[:LABEL_CHARS] if isinstance(label, str) else ''
        job_id = existing['source_job_id'] if existing else None
        if existing:
            kind = existing['source_kind']
        elif venue or any(field in message for field in FORWARD_FIELDS):
            kind = 'place_reference'
        elif live_period:
            kind = 'live_position_report'
        else:
            job_id = self._consume_request(db, chat_id, generation, settings['epoch'], sent_at, now)
            kind = 'current_position_report' if job_id else 'place_reference'
        if job_id and not existing:
            # Requested for one task: usable for it even with reuse off.
            payload['scope'] = 'task'
        elif existing:
            payload['scope'] = json.loads(existing['payload_json']).get('scope', 'context')
        else:
            payload['scope'] = 'context'
        if payload['scope'] != 'task' and not settings['enabled']:
            return 'ignored:context_off'
        state, valid_until = 'current', None
        if kind == 'current_position_report':
            valid_until = observed_at + FRESHNESS_SECONDS
        elif kind == 'live_position_report':
            if not existing:
                period = live_period
            else:
                period = json.loads(existing['payload_json']).get('live_period')
                if edited and live_period is None:
                    # Telegram's edit without live_period is the observed end
                    # of the share; the last point is kept, not "moved".
                    period = None
            live_end = (sent_at + period) if period and period != INDEFINITE_LIVE_PERIOD else None
            payload['live_period'] = period
            payload['live'] = bool(period) and (live_end is None or observed_at < live_end)
            if payload['live']:
                valid_until = observed_at + FRESHNESS_SECONDS
                if live_end is not None:
                    valid_until = min(valid_until, live_end)
            else:
                state = 'ended'
                if existing and period is None:
                    # End of share: keep the prior point, never a new position.
                    prior = json.loads(existing['payload_json'])
                    payload.update({name: prior.get(name) for name in ('latitude', 'longitude', 'accuracy_m')})
                    observed_at = existing['observed_at']
        expires_at = observed_at + RETENTION_SECONDS
        if existing:
            db.execute('UPDATE context_observations SET source_revision=source_revision+1,revision_at=?,'
                       'revision_update_id=?,observed_at=?,received_at=?,valid_until=?,expires_at=?,payload_json=?,'
                       'state=? WHERE id=?',
                       (edit_at or sent_at, update['update_id'], observed_at, now, valid_until, expires_at,
                        json.dumps(payload), state, existing['id']))
            return 'updated:' + kind
        db.execute('INSERT INTO context_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (str(uuid.uuid4()), owner, generation, settings['epoch'], key, 1, observed_at, update['update_id'],
                    kind, job_id, observed_at, now, valid_until, expires_at, json.dumps(payload), state))
        return 'recorded:' + kind

    def _text_edit(self, db, settings, key, message, owner_id, generation, observed_at, uncertain, update_id, now):
        """An edited earlier text: new revision, never a replayed request."""
        job = db.execute('SELECT id,source_edited_at FROM jobs WHERE source_message_key=?', (key,)).fetchone()
        if not job:
            return 'ignored:unknown_source'
        if observed_at < settings['cutoff']:
            # A late replay of an edit made before pause/clear stays out.
            return 'rejected:before_cutoff'
        if job['source_edited_at'] is None or observed_at > job['source_edited_at']:
            db.execute('UPDATE jobs SET source_edited_at=? WHERE id=?', (observed_at, job['id']))
        if observed_at + RETENTION_SECONDS <= now:
            return 'rejected:expired'
        owner = owner_key(owner_id)
        existing = db.execute('SELECT * FROM context_observations WHERE owner_key=? AND generation=? '
                              'AND context_epoch=? AND source_key=?',
                              (owner, generation, settings['epoch'], key)).fetchone()
        if existing and (observed_at, update_id) <= (existing['revision_at'], existing['revision_update_id']):
            return 'ignored:stale_revision'
        # With context use off the revision is still recorded (so anything
        # derived from the old wording is invalidated) but no text is kept.
        payload = {'time_uncertain': uncertain,
                   'text': message['text'][:EDITED_TEXT_CHARS] if settings['enabled'] else None}
        expires_at = observed_at + RETENTION_SECONDS
        if existing:
            db.execute('UPDATE context_observations SET source_revision=source_revision+1,revision_at=?,'
                       'revision_update_id=?,observed_at=?,received_at=?,expires_at=?,payload_json=? WHERE id=?',
                       (observed_at, update_id, observed_at, now, expires_at, json.dumps(payload), existing['id']))
            return 'updated:text_edit'
        db.execute('INSERT INTO context_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (str(uuid.uuid4()), owner, generation, settings['epoch'], key, 1, observed_at, update_id,
                    'text_edit', job['id'], observed_at, now, None, expires_at, json.dumps(payload), 'current'))
        return 'recorded:text_edit'
