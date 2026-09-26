"""Owner-accepted preparations: reminders and prepared suggestions (SEC-ATTN-01, #659).

The anticipatory half of the secretary, bounded by
docs/secretary-agency-contract.en.md ("Attention in this program"):

* A **preparation** is one durable ``preparations`` row in the owner's
  QuickStore: a kind, a bounded goal text, a due time (UTC seconds) with the
  owner's time zone, an optional tiny recurrence and a delivery channel.
* It is ``proposed`` until the owner accepts it.  The owner's own request
  for it ("내일 9시에 알려줘") is that acceptance, but only on a
  DecisionEngine judgment (``ConversationJudgments.explicit_preparation_request``),
  never a text rule; otherwise the owner accepts it with an inline Telegram
  button or in Settings.  Only ``scheduled`` rows ever run.
* The existing service loop (``AgentService.start``) asks one indexed query
  per tick.  Nothing due costs no model and no network call.  A due row is
  claimed atomically together with its Work, keyed ``preparation:<id>:<slot>``,
  so a restart can neither run a slot twice nor lose it.
* A ``reminder`` Work carries the reminder text as its already-observed
  result and is delivered by the existing terminal delivery (``deliver_one``);
  no model runs.  A ``prepare`` Work is an ordinary queued Work whose request
  is the goal text; the normal loop (SEC-LOOP-01) runs it and its result is
  kept as the prepared answer.
* Recurrence advances after the run from *now*, so a missed window after
  downtime runs once, not once per missed slot.

Nothing here knows about calendars, sites, providers or question kinds: the
model reads the calendar with ``calendar_query`` and schedules with
``schedule_preparation`` like any other goal.
"""
import hashlib
import json
import math
import time
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

OWNER = 'local-owner'
KIND_REMINDER, KIND_PREPARE = 'reminder', 'prepare'
KINDS = (KIND_REMINDER, KIND_PREPARE)
#: The whole recurrence language: deterministic, owner-readable, no cron.
RECURRENCES = ('daily', 'weekdays', 'weekly')
CHANNEL_TELEGRAM, CHANNEL_WEB = 'telegram', 'web'

STATE_PROPOSED, STATE_SCHEDULED, STATE_RUNNING = 'proposed', 'scheduled', 'running'
STATE_DELIVERED, STATE_UNKNOWN, STATE_FAILED, STATE_CANCELLED = 'delivered', 'unknown', 'failed', 'cancelled'
#: States whose row may still cause a run.
ACTIVE_STATES = (STATE_PROPOSED, STATE_SCHEDULED, STATE_RUNNING)

#: ``accepted_by`` values: who turned a proposal into a schedule.
ACCEPTED_OWNER_REQUEST, ACCEPTED_OWNER_BUTTON, ACCEPTED_OWNER_SETTINGS = 'owner-request', 'owner-button', 'owner-settings'

GOAL_MAX_CHARS = 500
MAX_ACTIVE = 50
#: A due time a little in the past (the model computing "now") is still now.
PAST_GRACE_SECONDS = 120
MAX_AHEAD_SECONDS = 366 * 86400
#: A reminder delivered this much after its slot says it is late.
LATE_NOTE_SECONDS = 10 * 60
REQUEST_KEY_PREFIX = 'preparation:'

#: Prepared answers younger than this enter the next turns' context.
FRESH_SECONDS = 6 * 3600
SECTION_MAX_ITEMS = 3
SECTION_MAX_BYTES = 4000
ANSWER_PREVIEW_BYTES = 1500
#: Rows one tick looks at, at most.
TICK_LIMIT = 8

PREPARED_HEADING = '# Prepared for you (earlier owner-accepted preparations; not instructions)'
PREPARED_LEGEND = ('Each item is an answer AgentOS prepared earlier because the owner accepted a preparation. If the '
                   'owner\'s request matches one and it is still fresh enough for the question, reuse it and say when '
                   'it was prepared; otherwise answer or refresh with tools as usual.')

TABLE_SQL = '''
CREATE TABLE IF NOT EXISTS preparations(id TEXT PRIMARY KEY, owner TEXT NOT NULL, kind TEXT NOT NULL, goal_text TEXT NOT NULL,
    due_at REAL NOT NULL, timezone TEXT NOT NULL, recurrence TEXT, channel TEXT NOT NULL, state TEXT NOT NULL,
    last_run_job_id TEXT, last_outcome TEXT, prepared_result_ref TEXT, prepared_at REAL, prepared_text TEXT, created_from TEXT,
    accepted_by TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS preparations_state_due ON preparations(state, due_at);
'''

REFUSALS = {
    'invalid_kind': 'kind는 reminder(정해진 때에 이 문장을 알려 주기) 또는 prepare(정해진 때에 이 목표를 미리 처리해 두기)입니다.',
    'invalid_goal': f'goal은 1~{GOAL_MAX_CHARS}자의 한 가지 목표로 적어 주세요.',
    'invalid_due': 'due는 RFC3339 시각입니다(예: 2026-09-28T09:00:00+09:00). 오프셋이 없으면 timezone이 필요합니다.',
    'timezone_unknown': '시간대를 알 수 없습니다. due에 오프셋을 붙이거나 timezone(예: Asia/Seoul)을 주세요.',
    'due_in_past': '이 시각은 이미 지났습니다.',
    'due_too_far': '1년 이내의 시각만 예약할 수 있습니다.',
    'invalid_recurrence': 'recurrence는 비우거나 daily, weekdays, weekly 중 하나입니다.',
    'too_many': f'진행 중인 준비가 {MAX_ACTIVE}개를 넘어 더 만들지 않았습니다. 설정에서 필요 없는 준비를 정리해 주세요.',
    'not_found': '이 준비를 찾지 못했습니다.',
    'not_proposed': '이미 처리된 준비입니다.',
    'running': '지금 실행 중인 준비는 지울 수 없습니다. 먼저 취소하세요.',
}


class PreparationRefusal(ValueError):
    """A typed refusal the broker turns into a ``ToolError``."""

    def __init__(self, code, detail=''):
        super().__init__(REFUSALS[code] + (' ' + detail if detail else ''))
        self.code = code


# --- pure helpers (fake-clock unit tests) -----------------------------------

def zone(name):
    """An IANA zone or a fixed ``+HH:MM`` offset, or None."""
    if not isinstance(name, str) or not name:
        return None
    if name[0] in '+-' and len(name) == 6 and name[3] == ':':
        try:
            hours, minutes = int(name[1:3]), int(name[4:6])
        except ValueError:
            return None
        if hours > 18 or minutes > 59:
            return None
        sign = 1 if name[0] == '+' else -1
        return dt_timezone(sign * timedelta(hours=hours, minutes=minutes))
    if len(name) > 64 or name.startswith(('/', '.')) or '..' in name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def offset_name(parsed):
    """``+HH:MM`` for a timezone-aware datetime's offset."""
    total = int(parsed.utcoffset().total_seconds() // 60)
    sign = '+' if total >= 0 else '-'
    total = abs(total)
    return f'{sign}{total // 60:02d}:{total % 60:02d}'


def local_text(ts, timezone_name):
    """``2026-09-28 09:00 (Mon, Asia/Seoul)`` for a stored UTC time."""
    tz = zone(timezone_name) or dt_timezone.utc
    local = datetime.fromtimestamp(ts, tz)
    return local.strftime('%Y-%m-%d %H:%M') + f" ({local.strftime('%a')}, {timezone_name or 'UTC'})"


def iso(ts, timezone_name=None):
    tz = zone(timezone_name) or dt_timezone.utc
    return datetime.fromtimestamp(ts, tz).isoformat(timespec='minutes')


def parse_due(due, timezone_name, default_timezone, now):
    """``(due_at, timezone)`` for one proposal, or a typed refusal.

    ``due`` is RFC3339; with no offset it is wall-clock time in ``timezone``
    (or the owner's zone).  The stored zone is the named IANA zone when one
    is known, otherwise the explicit offset, so a recurrence keeps the
    owner's wall-clock time.
    """
    if not isinstance(due, str) or not due.strip() or len(due) > 40:
        raise PreparationRefusal('invalid_due')
    try:
        parsed = datetime.fromisoformat(due.strip().replace('Z', '+00:00'))
    except ValueError:
        raise PreparationRefusal('invalid_due') from None
    named = timezone_name if zone(timezone_name) is not None else None
    if timezone_name and named is None:
        raise PreparationRefusal('timezone_unknown')
    if named is None and zone(default_timezone) is not None:
        named = default_timezone
    if parsed.tzinfo is None:
        if named is None:
            raise PreparationRefusal('timezone_unknown')
        parsed = parsed.replace(tzinfo=zone(named))
    stored = named or offset_name(parsed)
    due_at = parsed.timestamp()
    if not math.isfinite(due_at):
        raise PreparationRefusal('invalid_due')
    if due_at < now - PAST_GRACE_SECONDS:
        raise PreparationRefusal('due_in_past', f'지금은 {local_text(now, stored)}입니다.')
    if due_at > now + MAX_AHEAD_SECONDS:
        raise PreparationRefusal('due_too_far')
    return max(due_at, now), stored


def normalize_recurrence(value):
    if value in (None, '', 'none'):
        return None
    if value not in RECURRENCES:
        raise PreparationRefusal('invalid_recurrence')
    return value


def normalize_goal(goal):
    goal = ' '.join(str(goal or '').split())
    if not goal or len(goal) > GOAL_MAX_CHARS:
        raise PreparationRefusal('invalid_goal')
    return goal


def next_due(due_at, timezone_name, recurrence, now):
    """The first slot of ``recurrence`` strictly after ``now`` (and ``due_at``), or None.

    Computed on the owner's wall clock, so a daily 11:30 stays 11:30 across a
    DST change.  Slots missed during downtime are skipped, never replayed.
    """
    if not recurrence:
        return None
    tz = zone(timezone_name) or dt_timezone.utc
    first = datetime.fromtimestamp(due_at, tz)
    day = max(first.date(), datetime.fromtimestamp(now, tz).date()) - timedelta(days=1)
    for _ in range(16):
        day += timedelta(days=1)
        if recurrence == 'weekdays' and day.weekday() >= 5:
            continue
        if recurrence == 'weekly' and day.weekday() != first.weekday():
            continue
        slot = datetime(day.year, day.month, day.day, first.hour, first.minute, first.second, tzinfo=tz).timestamp()
        if slot > now and slot > due_at:
            return slot
    raise AssertionError('recurrence has no slot within 16 days')  # pragma: no cover - unreachable


def request_key(preparation_id, due_at):
    """The Work request key of one slot: the idempotency key of a run."""
    return f'{REQUEST_KEY_PREFIX}{preparation_id}:{int(due_at)}'


def preparation_of(work_request_key):
    """The preparation id a Work was started for, or None."""
    key = str(work_request_key or '')
    if not key.startswith(REQUEST_KEY_PREFIX):
        return None
    return key[len(REQUEST_KEY_PREFIX):].rsplit(':', 1)[0] or None


def run_outcome(kind, job):
    """What one run's Work shows: ``delivered``, ``unknown`` or ``failed``.

    ``delivered`` means the Work's result reached its channel (Telegram
    ``sent``) or was kept in AgentOS (no chat, ``none``).  An uncertain
    Telegram send is ``unknown``, never re-sent and never called delivered.
    """
    if not job:
        return STATE_FAILED
    delivery = job.get('delivery')
    if delivery == 'unknown':
        return STATE_UNKNOWN
    if delivery not in ('sent', 'none'):
        return STATE_FAILED
    if kind == KIND_REMINDER:
        return STATE_DELIVERED
    return STATE_DELIVERED if job.get('status') in ('succeeded', 'partial') else STATE_FAILED


def reminder_text(goal, due_at, timezone_name, now):
    text = '알림: ' + goal
    if now - due_at > LATE_NOTE_SECONDS:
        text += f'\n(예정 시각 {local_text(due_at, timezone_name)}보다 늦게 전달했습니다.)'
    return text


def proposal_summary(row):
    """One owner-readable line for a proposal (Telegram, judgment context)."""
    kind = '알림' if row['kind'] == KIND_REMINDER else '미리 준비'
    repeat = {'daily': ' · 매일', 'weekdays': ' · 평일마다', 'weekly': ' · 매주'}.get(row.get('recurrence') or '', '')
    return f"[{kind}] {local_text(row['due_at'], row['timezone'])}{repeat} — {row['goal_text']}"


def digest(rows):
    """The exact set of proposals one Telegram message offers."""
    material = json.dumps(sorted((row['id'], row['kind'], row['goal_text'], row['due_at'], row.get('recurrence'))
                                 for row in rows), ensure_ascii=False)
    return hashlib.sha256(material.encode()).hexdigest()[:32]


# --- the owner's preparations -------------------------------------------------

class Preparations:
    """The ``preparations`` rows of one owner store.  No model, no network."""

    def __init__(self, store, clock=time.time):
        self.store, self.clock = store, clock

    def get(self, preparation_id):
        with self.store.db() as db:
            row = db.execute('SELECT * FROM preparations WHERE id=?', (str(preparation_id or ''),)).fetchone()
            return dict(row) if row else None

    def create(self, *, kind, goal, due_at, timezone, recurrence, channel, created_from, state,
               accepted_by=None, owner=OWNER):
        """One new row (idempotent for the same Work, kind, goal and slot)."""
        if kind not in KINDS:
            raise PreparationRefusal('invalid_kind')
        if state not in (STATE_PROPOSED, STATE_SCHEDULED):
            raise ValueError('a preparation starts proposed or scheduled')
        now = self.clock()
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            same = db.execute('SELECT * FROM preparations WHERE created_from=? AND kind=? AND goal_text=? AND due_at=? '
                              'AND state IN (?,?,?)', (created_from, kind, goal, due_at, *ACTIVE_STATES)).fetchone()
            if same:
                return dict(same)
            active = db.execute('SELECT count(*) FROM preparations WHERE state IN (?,?,?)', ACTIVE_STATES).fetchone()[0]
            if active >= MAX_ACTIVE:
                raise PreparationRefusal('too_many')
            row = {'id': uuid.uuid4().hex[:16], 'owner': owner, 'kind': kind, 'goal_text': goal, 'due_at': due_at,
                   'timezone': timezone, 'recurrence': recurrence, 'channel': channel, 'state': state,
                   'last_run_job_id': None, 'last_outcome': None, 'prepared_result_ref': None, 'prepared_at': None, 'prepared_text': None,
                   'created_from': created_from, 'accepted_by': accepted_by, 'created_at': now, 'updated_at': now}
            db.execute(f"INSERT INTO preparations({','.join(row)}) VALUES ({','.join('?' * len(row))})", tuple(row.values()))
            return row

    def accept(self, preparation_id, accepted_by):
        """``proposed`` → ``scheduled``: the owner's explicit yes."""
        now = self.clock()
        with self.store.db() as db:
            changed = db.execute("UPDATE preparations SET state='scheduled',accepted_by=?,updated_at=? WHERE id=? AND state='proposed'",
                                 (accepted_by, now, preparation_id)).rowcount
        if not changed:
            raise PreparationRefusal('not_found' if not self.get(preparation_id) else 'not_proposed')
        return self.get(preparation_id)

    def cancel(self, preparation_id):
        """Stop every future run.  A Work already running finishes as its own Work."""
        now = self.clock()
        with self.store.db() as db:
            changed = db.execute('UPDATE preparations SET state=?,updated_at=? WHERE id=? AND state IN (?,?,?)',
                                 (STATE_CANCELLED, now, preparation_id, *ACTIVE_STATES)).rowcount
        row = self.get(preparation_id)
        if row is None:
            raise PreparationRefusal('not_found')
        return {**row, 'changed': bool(changed)}

    def delete(self, preparation_id):
        """Remove the row.  Its past Works and their Evidence stay."""
        with self.store.db() as db:
            row = db.execute('SELECT state FROM preparations WHERE id=?', (preparation_id,)).fetchone()
            if row is None:
                raise PreparationRefusal('not_found')
            if row['state'] == STATE_RUNNING:
                raise PreparationRefusal('running')
            db.execute('DELETE FROM preparations WHERE id=?', (preparation_id,))
        return {'deleted': True, 'id': preparation_id}

    def proposed_from(self, work_id):
        with self.store.db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM preparations WHERE created_from=? AND state='proposed' "
                                                    'ORDER BY created_at', (work_id,))]

    def rows(self, limit=100):
        """Every row with its last run's Work status and delivery, active first."""
        with self.store.db() as db:
            return [dict(row) for row in db.execute(
                'SELECT p.*, j.status AS last_status, j.delivery AS last_delivery, j.response AS last_response '
                'FROM preparations p LEFT JOIN jobs j ON j.id=p.last_run_job_id '
                "ORDER BY CASE p.state WHEN 'proposed' THEN 0 WHEN 'running' THEN 1 WHEN 'scheduled' THEN 2 ELSE 3 END, "
                'p.due_at LIMIT ?', (int(limit),))]

    # -- the tick ----------------------------------------------------------

    def due(self, now):
        """The tick's one indexed query: due slots and runs ready to settle.

        A ``scheduled`` row is due at ``due_at``; a ``running`` row is ready
        once its Work is no longer queued or running and its delivery is no
        longer pending or in flight.  Nothing else is read.
        """
        with self.store.db() as db:
            return [dict(row) for row in db.execute(
                'SELECT p.*, j.status AS job_status, j.delivery AS job_delivery FROM preparations p '
                'LEFT JOIN jobs j ON j.id=p.last_run_job_id '
                "WHERE p.state IN ('scheduled','running') AND p.due_at<=? "
                "AND (p.state='scheduled' OR j.id IS NULL OR (j.status NOT IN ('queued','running') "
                "AND j.delivery NOT IN ('pending','sending'))) ORDER BY p.due_at LIMIT ?", (now, TICK_LIMIT))]

    def start(self, row, *, channel, chat_id, now):
        """Claim one due slot and create its Work in ONE transaction.

        Returns the Work id, or None when the slot is no longer due (another
        claim, a cancel) or the queue refused it (the row stays scheduled and
        is tried again on a later tick).  The Work's request key names the
        slot, so a replayed claim finds the same Work instead of a second.
        """
        key = request_key(row['id'], row['due_at'])
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT * FROM preparations WHERE id=?', (row['id'],)).fetchone()
            if not current or current['state'] != STATE_SCHEDULED or current['due_at'] != row['due_at']:
                return None
            current = dict(current)
            existing = db.execute('SELECT id FROM jobs WHERE request_key=?', (key,)).fetchone()
            if existing:
                job_id = existing['id']
            elif current['kind'] == KIND_REMINDER:
                # The reminder text is the Work's observed result ('builtin':
                # no AI ran, as for notes); the existing terminal delivery
                # sends it once (mark-before-send).
                job_id = str(uuid.uuid4())
                text = reminder_text(current['goal_text'], current['due_at'], current['timezone'], now)
                db.execute('INSERT INTO jobs(id,request_key,message,channel,chat_id,status,response,error,delivery,provider,model,created) '
                           'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                           (job_id, key, current['goal_text'], channel, chat_id, 'succeeded', text, None,
                            'pending' if chat_id else 'none', 'builtin', 'preparation', now))
                db.execute('INSERT INTO messages(role,content,channel,created,job_id) VALUES (?,?,?,?,?)',
                           ('assistant', text, channel, now, job_id))
            else:
                try:
                    job_id = self.store.enqueue(current['goal_text'], key, channel, chat_id, db=db)
                except ValueError:
                    return None
            db.execute('UPDATE preparations SET state=?,last_run_job_id=?,updated_at=? WHERE id=?',
                       (STATE_RUNNING, job_id, now, current['id']))
            # Evidence: preparation id -> Work id; the Work's delivery is the receipt.
            db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                       (job_id, 'preparation', 'succeeded', json.dumps(
                           {'preparation_id': current['id'], 'kind': current['kind'], 'slot': iso(current['due_at']),
                            'recurrence': current['recurrence'], 'accepted_by': current['accepted_by'],
                            'channel': channel.split(':', 1)[0]}), now))
            return job_id

    def settle(self, row, now, scrub=None):
        """Record one finished run and schedule the next slot, if any.

        A prepared answer is kept as ``scrub(job)`` - the service removes the
        Work's saved private values and stored secrets - never raw.
        """
        answer = None
        if row['kind'] == KIND_PREPARE:
            finished = self.store.job(row['last_run_job_id']) if row.get('last_run_job_id') else None
            if finished and finished['status'] in ('succeeded', 'partial'):
                answer = scrub(finished) if scrub is not None else str(finished.get('response') or '')
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT * FROM preparations WHERE id=?', (row['id'],)).fetchone()
            if not current or current['state'] != STATE_RUNNING:
                return None
            current = dict(current)
            job = db.execute('SELECT * FROM jobs WHERE id=?', (current['last_run_job_id'],)).fetchone()
            job = dict(job) if job else None
            if job and job['status'] in ('queued', 'running') or job and job['delivery'] in ('pending', 'sending'):
                return None
            outcome = run_outcome(current['kind'], job)
            updates = {'last_outcome': outcome, 'updated_at': now}
            if current['kind'] == KIND_PREPARE and job and job['status'] in ('succeeded', 'partial') and answer is not None:
                updates.update(prepared_result_ref=job['id'], prepared_at=now, prepared_text=answer)
            following = next_due(current['due_at'], current['timezone'], current['recurrence'], now)
            if following is None:
                updates['state'] = outcome
            else:
                updates.update(state=STATE_SCHEDULED, due_at=following)
            db.execute(f"UPDATE preparations SET {','.join(k + '=?' for k in updates)} WHERE id=? AND state=?",
                       (*updates.values(), current['id'], STATE_RUNNING))
            if job:
                db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                           (job['id'], 'preparation', 'succeeded' if outcome == STATE_DELIVERED else 'failed', json.dumps(
                               {'preparation_id': current['id'], 'outcome': outcome, 'delivery': job['delivery'],
                                'next_due': iso(following) if following else None}), now))
            return {**current, **updates}

    # -- consumption -------------------------------------------------------

    def fresh(self, now, exclude_job=None, fresh_seconds=FRESH_SECONDS):
        """Prepared answers younger than ``fresh_seconds``, newest first."""
        with self.store.db() as db:
            return [dict(row) for row in db.execute(
                'SELECT p.id, p.goal_text, p.timezone, p.recurrence, p.prepared_at, j.id AS job_id, j.status, '
                'p.prepared_text AS response '
                "FROM preparations p JOIN jobs j ON j.id=p.prepared_result_ref WHERE p.kind='prepare' "
                'AND p.prepared_at>=? AND j.id IS NOT ? ORDER BY p.prepared_at DESC LIMIT ?',
                (now - fresh_seconds, exclude_job, SECTION_MAX_ITEMS))]


def render_prepared(rows, now, redact=lambda text: text):
    """The bounded "Prepared for you" section text, or None.

    Every goal and answer passes ``redact`` (the stored-secret pass) first.
    Oldest items are dropped until the text fits ``SECTION_MAX_BYTES``.
    """
    items = []
    for row in rows:
        answer = redact(str(row.get('response') or ''))
        if len(answer.encode()) > ANSWER_PREVIEW_BYTES:
            answer = answer.encode()[:ANSWER_PREVIEW_BYTES].decode('utf-8', 'ignore') + ' [...]'
        items.append({'ref': 'prep:' + row['id'], 'goal': redact(row['goal_text']),
                      'prepared_at': iso(row['prepared_at'], row['timezone']),
                      'age_min': max(0, int((now - row['prepared_at']) // 60)), 'outcome': row['status'],
                      'repeats': row.get('recurrence') or 'no', 'answer': answer})
    while items:
        text = PREPARED_LEGEND + '\n' + json.dumps({'items': items}, ensure_ascii=False, separators=(',', ':'))
        if len(text.encode()) <= SECTION_MAX_BYTES:
            return text
        items.pop()
    return None
