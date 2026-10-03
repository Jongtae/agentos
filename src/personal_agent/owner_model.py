"""Owner-model upkeep: keep the owner in mind, asynchronously and minimised (OWNER-MODEL-03, #805 phase 1).

Bounded by docs/secretary-agency-contract.en.md ("Amendment - #805 phase 1"):

* **Trigger.** A Work a worker AI answered that ends ``succeeded`` or
  ``partial`` records one durable ``owner_model_upkeep`` row, in the same
  transaction that settles it (idempotent per Work).  Failed, cancelled and
  unknown Works, rule/command replies (no worker AI ran), preparation runs
  and location continuations record none: typed markers, never text rules.
* **Tick.** The existing service loop asks one indexed query per tick.  At
  most one pending row is claimed per tick, atomically with the check that
  no Work is queued or running, and runs off the work thread (single-flight,
  a hard deadline).  Nothing pending costs no model call.
* **Judgment (C16).** The owner's Judgment AI (``DecisionEngine.structured``)
  reads the owner's request (owner words), the final answer excerpt
  (model-stated), the profile snapshot and the clock, every fact redacted
  first, and proposes at most ``MAX_PROPOSALS`` durable owner facts.
* **Validation (AgentOS).** Out-of-enum, oversized, non-``profile.`` and
  duplicate proposals are dropped.  What is kept is saved at once as current
  Memory attributed to the source Work (#918 slice a, owner decision
  2026-09-30: the owner's own AI acts for the owner and the owner is told
  afterwards with an undo, the Work's ``memory_saved`` notice).  The per-fact
  #597 judgment and the MemoryCandidate ask are no longer on this path; C5
  is unchanged for third-party writers.
* **Minimisation.** An owner pause switch and a rolling 24-hour cap on
  every model call (``CONFIG_KEY``), checked before each call.  The newest
  pending row runs first and one older than ``MAX_PENDING_SECONDS`` expires
  without a call (#876: an ask must come while the conversation is live, not
  a day later when a backlog drains under the cap), and a claimed
  row a crash left behind expires as ``interrupted``.  Each run is one
  ``owner_model`` tool event on the source Work: counts, applied keys, kinds,
  outcomes and the deciding route - never the input texts, and a dropped
  proposal's key only as a digest.

**Self-review (SELF-REVIEW-01, #998).** The same rows, tick, cap and pause
carry a second kind of run, ``self-review``: like a secretary who notices
she fell short, the assistant reviews a Work from its own records and keeps
what it learned.  Typed markers enqueue it - a Work a worker AI answered
that ended ``failed``, a Work the next owner turn's continuity judgment
linked as a ``correction`` or ``retry``, or an owner reaction another change
observes (``enqueue_self_review``) - one row per Work.  The Judgment AI reads
the owner's request, the answer excerpt, the orchestrator's evaluation
verdicts and the owner's follow-up (or the observation), every fact redacted
first, and returns at most one **lesson** (how to serve this owner; saved as
current Memory under ``profile.working.`` by the #918 slice (a) rule, so
later briefs carry it and the owner is told with an undo) and one
**blocker** (a cause only AgentOS code can fix; kept as Evidence on the
reviewed Work, redacted, and never filed anywhere).  No text rule reads the
owner's wording; nothing names a site, task or category.

Nothing here names a site, provider, task or request category.
"""
import hashlib
import json
import time

#: The source Work's tool-event name of every upkeep run (#794 shows it).
EVENT_TOOL = 'owner_model'
#: The DecisionContext purpose of the proposal judgment.
PURPOSE = 'owner-model-upkeep'
#: #998: the two kinds of run one row may be; the row key is ``(job_id, kind)``.
KIND_UPKEEP, KIND_SELF_REVIEW = 'upkeep', 'self-review'
RUN_KINDS = (KIND_UPKEEP, KIND_SELF_REVIEW)
#: The reviewed Work's tool-event name of every self-review run.
REVIEW_EVENT_TOOL = 'self_review'
#: The DecisionContext purpose of the self-review judgment.
REVIEW_PURPOSE = 'self-review'
#: Why a self-review was enqueued (typed markers, never text rules).
REVIEW_FAILED, REVIEW_CORRECTION, REVIEW_RETRY, REVIEW_REACTION = 'failed', 'correction', 'retry', 'reaction'
REVIEW_REASONS = (REVIEW_FAILED, REVIEW_CORRECTION, REVIEW_RETRY, REVIEW_REACTION)
#: A lesson is a ``profile.`` fact under its own namespace, so it shows and is removed like other Memory.
LESSON_PREFIX = 'profile.working.'
#: Bounds of the self-review facts and of a stored observation.
EVALUATION_CHARS = 1500
FOLLOWUP_CHARS = 1500
MAX_OBSERVATION_CHARS = 500
#: A reviewed Work must have settled; a queued or running one is not reviewed.
REVIEWABLE_STATUSES = ('succeeded', 'partial', 'failed', 'unknown')
#: The owner's controls: ``{'enabled': bool, 'daily_calls': int}``.
CONFIG_KEY = 'owner_model_upkeep'
DEFAULT_DAILY_CALLS = 20
MAX_DAILY_CALLS = 200
#: The cap is a rolling window, so it needs no time zone.
WINDOW_SECONDS = 24 * 3600
#: A pending upkeep this old is dropped without a model call (#876): its ask
#: would reach the owner after the conversation it is about has moved on.
MAX_PENDING_SECONDS = 3600
#: No model call starts after a run has been going this long (each call is also
#: bounded by its adapter's own timeout).
RUN_SECONDS = 300
#: A row still ``claimed`` this long after its claim was cut off by a crash.
CLAIM_STALE_SECONDS = 3600

CATEGORIES = ('identity', 'place', 'routine', 'schedule', 'preference')
KIND_STATED, KIND_INFERRED = 'stated', 'inferred'
KINDS = (KIND_STATED, KIND_INFERRED)
PROFILE_PREFIX = 'profile.'
MAX_PROPOSALS = 5
MAX_TEXT_CHARS = 200
MAX_KEY_CHARS = 160
#: Bounds of the facts one judgment reads (the owner's request is never cut).
ANSWER_CHARS = 1500
PROFILE_CHARS = 1200
CLOCK_CHARS = 300

STATE_PENDING, STATE_CLAIMED = 'pending', 'claimed'
STATE_DONE, STATE_UNAVAILABLE, STATE_EXPIRED, STATE_GONE = 'done', 'unavailable', 'expired', 'gone'
#: Tool-event statuses: never ``succeeded``/``failed``, so an upkeep row is not a Work step.
EVENT_RECORDED, EVENT_UNAVAILABLE, EVENT_EXPIRED = 'recorded', 'unavailable', 'expired'
#: Outcomes of one applied proposal.
APPLIED_MEMORY, APPLIED_CANDIDATE = 'memory', 'candidate'
#: Historical refusal reasons of the #597 per-fact gate (Evidence rows written before #918 slice a).
REFUSED_INFERRED = 'inferred-stays-candidate'
REFUSED_BUDGET = 'no-call-budget'
REFUSED_DEADLINE = 'deadline'
#: Why a run stopped before its last proposal (recorded as ``stopped``).
STOPPED_PAUSED, STOPPED_CAP, STOPPED_DEADLINE = 'paused', 'cap', 'deadline'


def call_sent(decision):
    """Whether one decision reached its engine's transport (#805 review).

    An adapter reports ``sent``; an answer given before any transport (no
    route configured, invalid configuration, cancelled, too large, a
    structured-unsupported route) is not a call.  An engine that does not
    report it is counted, so the cap never undercounts.
    """
    confidence = decision.confidence
    return confidence.sent is not False and confidence.engine != STRUCTURED_UNSUPPORTED_ENGINE

#: ``decision.STRUCTURED_UNSUPPORTED`` (kept stdlib-only here; a test pins the two equal).
STRUCTURED_UNSUPPORTED_ENGINE = 'structured-unsupported'

TABLE_SQL = '''
CREATE TABLE IF NOT EXISTS owner_model_upkeep(job_id TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'upkeep',
    state TEXT NOT NULL, created REAL NOT NULL, claimed REAL, calls INTEGER NOT NULL DEFAULT 0,
    reason TEXT, observation TEXT, PRIMARY KEY(job_id, kind));
CREATE INDEX IF NOT EXISTS owner_model_upkeep_state ON owner_model_upkeep(state, created);
CREATE INDEX IF NOT EXISTS owner_model_upkeep_claimed ON owner_model_upkeep(claimed);
'''


def migrate(db):
    """Give a pre-#998 ``owner_model_upkeep`` table its ``kind`` key; returns whether it was rebuilt.

    SQLite cannot widen a primary key in place, so the old rows (all upkeep)
    are copied into the new shape once.  Idempotent: a table that already has
    ``kind`` is left alone.
    """
    columns = {row['name'] for row in db.execute('PRAGMA table_info(owner_model_upkeep)')}
    if not columns or 'kind' in columns:
        return False
    db.executescript('''
DROP INDEX IF EXISTS owner_model_upkeep_state;
DROP INDEX IF EXISTS owner_model_upkeep_claimed;
ALTER TABLE owner_model_upkeep RENAME TO owner_model_upkeep_v1;
''' + TABLE_SQL + '''
INSERT INTO owner_model_upkeep(job_id,kind,state,created,claimed,calls)
    SELECT job_id,'upkeep',state,created,claimed,calls FROM owner_model_upkeep_v1;
DROP TABLE owner_model_upkeep_v1;
''')
    return True


REVIEW_QUESTION = (
    'The assistant fell short on this one finished request, or the owner reacted to it: review_reason says '
    'which (failed: the request ended failed; correction: the owner\'s next message corrected it; retry: the '
    'owner asked for it again; reaction: the owner reacted to the answer, see owner_followup). From the '
    'assistant\'s own records - owner_request (the owner\'s own words), final_answer_excerpt (what the '
    'assistant answered, model-stated), work_outcome, evaluation (the orchestrator\'s verdicts on each '
    'attempt) and owner_followup (the owner\'s next message, or the observation) - work out why, as a '
    'careful secretary would. Return at most two notes. lesson: one short durable note about how to serve '
    'this owner better next time, for example how they refer to things, what they take for granted, what '
    'they expect done without being asked, or what they do not want; written as a reusable rule for later '
    'requests, never as the story of this one, and never repeating what owner_profile already says. '
    'lesson_key names the lesson, not the request, and starts with "' + LESSON_PREFIX + '" '
    '(' + LESSON_PREFIX + '<topic>); reuse an owner_profile key under that prefix when the lesson refines it. '
    'blocker: one short note only when the cause is something the assistant\'s software must change - '
    'context it was not given, a tool or capability it lacked, a wrong routing - said generally, so a '
    'developer can act on it; empty when the cause was the assistant\'s own judgment or the request itself. '
    'Each note is at most 200 characters. Never include health, finances, relationships, beliefs, '
    'credentials or other people, and never a secret. Use an empty string for a note you do not have; '
    'when nothing durable can be learned, return both empty. This judgment writes nothing.')

REVIEW_SCHEMA = {'type': 'object', 'additionalProperties': False,
                 'properties': {'lesson_key': {'type': 'string'}, 'lesson': {'type': 'string'},
                                'blocker': {'type': 'string'}},
                 'required': ['lesson_key', 'lesson', 'blocker']}


def review_shape(data):
    """Types only; each note's meaning is ``validate_review``'s."""
    return all(isinstance(data.get(name), str) for name in ('lesson_key', 'lesson', 'blocker'))


def lesson_key(key):
    """Whether ``key`` is a well-formed lesson key (a ``profile.working.`` Memory key)."""
    return profile_key(key) and key.startswith(LESSON_PREFIX) and len(key) > len(LESSON_PREFIX)


def validate_review(data, known, request=''):
    """``(lesson, blocker, dropped)``: what AgentOS may keep of one self-review answer (deterministic).

    ``lesson`` is ``{'memory_key', 'content'}`` or None; ``blocker`` a short
    text or None.  ``known`` and ``request`` are as in ``validate``: a lesson
    that repeats a current ``profile.`` value, or is the request sentence
    itself, is dropped.  ``dropped`` lists each refused note with its reason
    (a model-chosen key only as a digest).
    """
    data = data if isinstance(data, dict) else {}
    dropped, lesson, blocker = [], None, None
    key, content = data.get('lesson_key'), data.get('lesson')
    content = content.strip() if isinstance(content, str) else ''
    key = key.strip() if isinstance(key, str) else ''
    if content or key:
        reason = None
        if not content:
            reason = 'content'
        elif len(content) > MAX_TEXT_CHARS:
            reason = 'content'
        elif not lesson_key(key):
            reason = 'key'
        elif normalized(request) and normalized(content) == normalized(request):
            reason = 'request'
        elif normalized(content) in known:
            reason = 'duplicate'
        if reason is None:
            lesson = {'memory_key': key, 'content': content}
        else:
            dropped.append({'note': 'lesson', 'reason': reason, **({'key_digest': key_digest(key)} if key else {})})
    note = data.get('blocker')
    note = ' '.join(note.split()) if isinstance(note, str) else ''
    if note:
        if len(note) > MAX_TEXT_CHARS:
            dropped.append({'note': 'blocker', 'reason': 'content'})
        else:
            blocker = note
    return lesson, blocker, dropped

QUESTION = ('From this one finished request, propose durable facts about the owner that would help the assistant '
            'serve them in later requests. owner_request holds the owner\'s own words; final_answer_excerpt is '
            'what the assistant answered (model-stated) and is never by itself a fact about the owner. Use kind '
            '"stated" only for what the owner said about themselves in owner_request, and write its content in the '
            'owner\'s own words. Use kind "inferred" for a reasonable inference from what the owner said (for '
            'example a routine); it is remembered like a stated fact and the owner is told with an undo (#918: the owner asked for exactly this, for example "배우자가 있음"). category is'
            'one of: ' + ', '.join(CATEGORIES) + '. memory_key starts with "profile." and names the fact, not '
            'the request (profile.<category>.<name>); when the fact updates a key already in owner_profile, use '
            'that key and set supersedes_key to it, otherwise supersedes_key is an empty string. content and '
            'evidence are at most 200 characters each; evidence is a short quote or paraphrase of what the owner '
            'said. already_noted lists what was already noted from this same request; never propose a fact it '
            'already covers, even in other words or under another key. Never propose health, finances, '
            'relationships, beliefs, credentials or anything about other '
            'people unless the owner stated it about themselves for a purpose (then kind "stated"). Keep the strength '
            'of what the owner said: a passing reaction to one occasion (it was fine, it was good) is about that '
            'occasion, not a durable preference, unless the owner says it lasts or contrasts it with what they '
            'usually think. Do not repeat '
            'what owner_profile already says. A fact is never the request: what the owner asked for, wished for or wanted watched in owner_request is the task of that request, not a durable fact about the owner, so never turn the request sentence into content. Use clock only to turn relative time into an absolute date, or to '
            'leave out what is only about today. Propose at most 5, and an empty list when nothing durable and '
            'new was said. This judgment writes nothing.')

SCHEMA = {'type': 'object', 'additionalProperties': False,
          'properties': {'proposals': {'type': 'array', 'items': {
              'type': 'object', 'additionalProperties': False,
              'properties': {'category': {'type': 'string', 'enum': list(CATEGORIES)},
                             'kind': {'type': 'string', 'enum': list(KINDS)},
                             'memory_key': {'type': 'string'},
                             'content': {'type': 'string'},
                             'evidence': {'type': 'string'},
                             'supersedes_key': {'type': 'string'}},
              'required': ['category', 'kind', 'memory_key', 'content', 'evidence', 'supersedes_key']}}},
          'required': ['proposals']}


def shape(data):
    """Types only; each proposal's meaning is ``validate``'s."""
    return isinstance(data.get('proposals'), list)


def normalized(text):
    return ' '.join(str(text or '').split()).casefold()


def profile_key(key):
    """Whether ``key`` is a well-formed ``profile.`` Memory key."""
    return (isinstance(key, str) and key.startswith(PROFILE_PREFIX) and len(PROFILE_PREFIX) < len(key) <= MAX_KEY_CHARS
            and not any(character.isspace() for character in key))


def _refusal(item):
    """Why one proposal is out of shape or bounds, or None."""
    if not isinstance(item, dict):
        return 'shape'
    if any(not isinstance(item.get(name), str) for name in ('category', 'kind', 'memory_key', 'content', 'evidence')):
        return 'shape'
    if item['category'] not in CATEGORIES:
        return 'category'
    if item['kind'] not in KINDS:
        return 'kind'
    if not profile_key(item['memory_key']):
        return 'key'
    if not item['content'].strip() or len(item['content'].strip()) > MAX_TEXT_CHARS:
        return 'content'
    if not item['evidence'].strip() or len(item['evidence'].strip()) > MAX_TEXT_CHARS:
        return 'evidence'
    supersedes = item.get('supersedes_key') or ''
    # #805 review: a proposal may supersede only its own key (a different key is never retired here).
    if not isinstance(supersedes, str) or (supersedes.strip() and supersedes.strip() != item['memory_key']):
        return 'supersedes'
    return None


def key_digest(key):
    """A model-chosen key as Evidence keeps it for a dropped proposal: a short digest."""
    return hashlib.sha256(str(key).encode()).hexdigest()[:12]


def validate(proposals, known, pending, noted_keys=(), request=''):
    """``(kept, dropped)`` of the proposals AgentOS may apply (deterministic).

    ``known`` is the normalized content of every current ``profile.`` Memory
    value and of everything the source Work already wrote (Memory or
    candidate), under any key: the same content under another key is a
    duplicate.  ``pending`` is ``{(memory_key, normalized content)}`` of the
    pending candidates.  ``noted_keys`` are the keys the source Work already
    wrote or proposed (#836: one ask per owner message, so upkeep never adds
    a second fact under a key that Work already covers).  ``request`` is the
    owner's request text: content that is that sentence is the request, not a
    fact about the owner (#846; an equality check on the value's shape, no
    intent detection).  ``dropped`` keeps a key only as a digest.
    """
    request_text = normalized(request)
    kept, dropped, keys, contents = [], [], set(), set()
    for index, item in enumerate(proposals if isinstance(proposals, list) else ()):
        reason = 'over-limit' if index >= MAX_PROPOSALS else _refusal(item)
        key = item.get('memory_key') if isinstance(item, dict) and isinstance(item.get('memory_key'), str) else None
        if reason is None:
            content = normalized(item['content'])
            if request_text and content == request_text:
                reason = 'request'
            elif (key in keys or key in noted_keys or content in contents or content in known
                    or (key, content) in pending):
                reason = 'duplicate'
        if reason is not None:
            dropped.append({'key_digest': key_digest(key), 'reason': reason} if key else {'reason': reason})
            continue
        keys.add(key)
        contents.add(content)
        kept.append({'category': item['category'], 'kind': item['kind'], 'memory_key': key,
                     'content': item['content'].strip(), 'supersedes_key': (item.get('supersedes_key') or '').strip()})
    return kept, dropped


class Upkeep:
    """The durable upkeep queue and the owner's controls, in the owner's QuickStore."""

    def __init__(self, store, clock=time.time):
        self.store, self.clock = store, clock

    # -- controls -----------------------------------------------------------
    @staticmethod
    def _controls(value):
        value = value if isinstance(value, dict) else {}
        cap = value.get('daily_calls', DEFAULT_DAILY_CALLS)
        if isinstance(cap, bool) or not isinstance(cap, int):
            cap = DEFAULT_DAILY_CALLS
        return {'enabled': value.get('enabled', True) is not False, 'daily_calls': max(0, min(MAX_DAILY_CALLS, cap))}

    def settings(self, db=None):
        """``{'enabled', 'daily_calls'}``: enabled by default (#805)."""
        if db is None:
            return self._controls(self.store.config(CONFIG_KEY))
        row = db.execute('SELECT value FROM config WHERE key=?', (CONFIG_KEY,)).fetchone()
        try:
            return self._controls(json.loads(row['value']) if row else None)
        except (TypeError, ValueError):
            return self._controls(None)

    def set_controls(self, body):
        """The owner's pause switch and call cap; nothing else."""
        body = body if isinstance(body, dict) else {}
        current = self.settings()
        if 'enabled' in body:
            if not isinstance(body['enabled'], bool):
                raise ValueError('알아 두기 사용 여부를 확인하세요.')
            current['enabled'] = body['enabled']
        if 'daily_calls' in body:
            cap = body['daily_calls']
            if isinstance(cap, bool) or not isinstance(cap, int) or not 0 <= cap <= MAX_DAILY_CALLS:
                raise ValueError(f'하루 판단 횟수는 0~{MAX_DAILY_CALLS} 사이로 입력하세요.')
            current['daily_calls'] = cap
        self.store.put(CONFIG_KEY, current)
        return self.status()

    def calls_used(self, now, db=None):
        """Every model call counted in the rolling window (proposal and per-fact judgments)."""
        if db is None:
            with self.store.db() as conn:
                return self.calls_used(now, conn)
        row = db.execute('SELECT COALESCE(SUM(calls),0) FROM owner_model_upkeep WHERE claimed>=?',
                         (now - WINDOW_SECONDS,)).fetchone()
        return int(row[0] or 0)

    def allowance(self, now):
        """``(calls the owner's current settings allow now, why none)``: re-read before every call.

        ``why`` is ``paused`` when the owner paused upkeep, ``cap`` when the
        rolling cap is spent (this run's calls so far included), else None.
        """
        with self.store.db() as db:
            settings = self.settings(db)
            if not settings['enabled']:
                return 0, STOPPED_PAUSED
            left = max(0, settings['daily_calls'] - self.calls_used(now, db))
        return left, (None if left else STOPPED_CAP)

    def status(self, now=None):
        now = self.clock() if now is None else now
        with self.store.db() as db:
            pending = db.execute('SELECT COUNT(*) FROM owner_model_upkeep WHERE state=?', (STATE_PENDING,)).fetchone()[0]
            # #832: a claimed row is an upkeep run in flight; read-only, so a caller can tell the queue is idle.
            running = db.execute('SELECT COUNT(*) FROM owner_model_upkeep WHERE state=?', (STATE_CLAIMED,)).fetchone()[0]
            used = self.calls_used(now, db)
        return {**self.settings(), 'pending': int(pending), 'running': int(running), 'calls_last_24h': used}

    # -- the queue ----------------------------------------------------------
    def enqueue(self, db, job_id, now=None, *, kind=KIND_UPKEEP, reason=None, observation=None):
        """One pending run of ``kind`` for ``job_id``; idempotent per ``(Work, kind)``.

        Inside the caller's transaction when ``db`` is given, else its own.
        ``reason`` and ``observation`` belong to a self-review row (#998);
        the observation is a short typed note (an owner reaction) that the
        judgment reads redacted, bounded here.
        """
        if kind not in RUN_KINDS:
            raise ValueError('upkeep kind')
        if db is None:
            with self.store.db() as conn:
                conn.execute('BEGIN IMMEDIATE')
                return self.enqueue(conn, job_id, now, kind=kind, reason=reason, observation=observation)
        if not self.settings(db)['enabled']:
            return False
        if observation is not None:
            observation = ' '.join(str(observation).split())[:MAX_OBSERVATION_CHARS] or None
        return db.execute('INSERT OR IGNORE INTO owner_model_upkeep(job_id,kind,state,created,reason,observation) '
                          'VALUES (?,?,?,?,?,?)',
                          (job_id, kind, STATE_PENDING, self.clock() if now is None else now, reason, observation)).rowcount == 1

    def expire_interrupted(self, now):
        """Claimed rows a crash left behind: expired with an ``interrupted`` event (call only with no run in flight)."""
        with self.store.db() as db:
            rows = [(row['job_id'], row['kind']) for row in db.execute(
                'SELECT job_id,kind FROM owner_model_upkeep WHERE state=? AND claimed<?',
                (STATE_CLAIMED, now - CLAIM_STALE_SECONDS))]
        for job_id, kind in rows:
            self.finish(job_id, STATE_EXPIRED, None, EVENT_EXPIRED, {'reason': 'interrupted'}, now, kind=kind)
        return len(rows)

    def claim_due(self, now):
        """Claim the newest pending row this tick may run, or None (#876: the live conversation first).

        One immediate transaction: the check that no Work is queued or
        running and the claim are atomic with ``run_one``'s own claim, so an
        upkeep never starts beside a Work that was already claimed.  A
        claimed row is never run again, even after a restart; it counts one
        call until the run records its real number.  ``remaining`` is the
        budget at claim time, for the record: the run re-reads it before each
        later call (``allowance``).
        """
        select = ('SELECT job_id,kind,created,reason,observation FROM owner_model_upkeep WHERE state=? '
                  'ORDER BY created DESC LIMIT 1')
        with self.store.db() as db:
            row = db.execute(select, (STATE_PENDING,)).fetchone()
            if row is None:
                return None
            db.execute('BEGIN IMMEDIATE')
            row = db.execute(select, (STATE_PENDING,)).fetchone()
            settings = self.settings(db)
            if row is None or not settings['enabled']:
                return None
            if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running') LIMIT 1").fetchone():
                return None
            expired = now - row['created'] > MAX_PENDING_SECONDS
            remaining = settings['daily_calls'] - self.calls_used(now, db)
            if not expired and remaining < 1:
                return None
            db.execute('UPDATE owner_model_upkeep SET state=?,claimed=?,calls=? WHERE job_id=? AND kind=?',
                       (STATE_CLAIMED, now, 0 if expired else 1, row['job_id'], row['kind']))
            return {'job_id': row['job_id'], 'kind': row['kind'], 'created': row['created'], 'expired': expired,
                    'remaining': remaining, 'reason': row['reason'], 'observation': row['observation']}

    def count(self, job_id, calls, kind=KIND_UPKEEP):
        """Record the calls a run has made so far (the cap sees them at once)."""
        with self.store.db() as db:
            db.execute('UPDATE owner_model_upkeep SET calls=? WHERE job_id=? AND kind=?', (int(calls), job_id, kind))

    def finish(self, job_id, state, calls, event_status, detail, now, kind=KIND_UPKEEP):
        """Settle a claimed row and record its one tool event on the source Work (``self_review`` for a review)."""
        tool = REVIEW_EVENT_TOOL if kind == KIND_SELF_REVIEW else EVENT_TOOL
        with self.store.db() as db:
            if calls is None:
                db.execute('UPDATE owner_model_upkeep SET state=? WHERE job_id=? AND kind=?', (state, job_id, kind))
            else:
                db.execute('UPDATE owner_model_upkeep SET state=?,calls=? WHERE job_id=? AND kind=?',
                           (state, int(calls), job_id, kind))
            db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                       (job_id, tool, event_status, json.dumps(detail, ensure_ascii=False), now))

    def followups(self, job_id, limit=3):
        """The owner's later messages the continuity judgment linked to ``job_id`` as a correction or retry (#998).

        Read, not judged: only the stored ``relation_kind`` / ``related_job_id``
        link is used, oldest first.
        """
        with self.store.db() as db:
            rows = db.execute("SELECT message FROM jobs WHERE related_job_id=? AND relation_kind IN (?,?) AND id!=? "
                              'ORDER BY created LIMIT ?', (job_id, REVIEW_CORRECTION, REVIEW_RETRY, job_id, limit)).fetchall()
        return [str(row['message'] or '') for row in rows if row['message']]

    def evaluations(self, job_id, limit=6):
        """The orchestrator's recorded verdict texts on ``job_id``'s attempts, oldest first (#710 Evidence)."""
        with self.store.db() as db:
            rows = db.execute("SELECT detail FROM tool_events WHERE job_id=? AND tool='orchestrator' AND status='evaluated' "
                              'ORDER BY id LIMIT ?', (job_id, limit)).fetchall()
        texts = []
        for row in rows:
            try:
                trace = json.loads(row['detail'])
            except (TypeError, ValueError):
                continue
            if isinstance(trace, dict) and isinstance(trace.get('text'), str) and trace['text'].strip():
                texts.append(trace['text'].strip())
        return texts

    # -- known values -------------------------------------------------------
    def known_values(self, owner, job_id):
        """``(known, pending)`` for ``validate``: see there."""
        known, offset = set(), 0
        while True:
            page = self.store.memories(owner, limit=101, offset=offset, key_prefix=PROFILE_PREFIX)
            known |= {normalized(row['content']) for row in page}
            if len(page) < 101:
                break
            offset += 101
        work_key = self.store._work_binding(job_id)
        with self.store.db() as db:
            # #805 review: what this Work already wrote (the worker's own save_memory), any key or state.
            known |= {normalized(row['content']) for row in db.execute(
                "SELECT content FROM memories WHERE work_key=? AND state='current'", (work_key,))}
            known |= {normalized(row['content']) for row in db.execute(
                'SELECT content FROM memory_candidates WHERE work_key=?', (work_key,))}
            pending = {(row['memory_key'], normalized(row['content'])) for row in db.execute(
                "SELECT memory_key,content FROM memory_candidates WHERE state='pending' AND memory_key LIKE 'profile.%'")}
        return known, pending

    def work_noted(self, job_id):
        """``(keys, contents)`` the source Work already wrote or proposed, any state (#836).

        A rejected candidate keeps neither (the reject erases them).  The
        contents go to the proposal judgment as ``already_noted``; the keys to
        ``validate``.
        """
        work_key = self.store._work_binding(job_id)
        with self.store.db() as db:
            rows = [tuple(row) for row in db.execute(
                "SELECT memory_key,content FROM memory_candidates WHERE work_key=? AND memory_key!='' ORDER BY created,id",
                (work_key,))]
            rows += [tuple(row) for row in db.execute(
                "SELECT memory_key,content FROM memories WHERE work_key=? AND state='current' ORDER BY created,id",
                (work_key,))]
        return {key for key, _content in rows}, list(dict.fromkeys(content for _key, content in rows if content))

    # -- one run ------------------------------------------------------------
    def run(self, job, judgments, *, answer, profile, clock, cancelled=None):
        """Ask, validate and apply for one finished Work; returns ``(state, calls, event_status, detail)``.

        ``judgments`` is a ``ConversationJudgments`` whose redactor is scoped
        to this Work.  Only a confident structured answer is applied.  Only a
        call that reached a transport is counted.  Before every later call,
        and before each write, the owner's pause switch and the rolling cap
        are read again; a pause stops the run, a spent cap or the deadline
        (``cancelled()``) stops further calls, and ``stopped`` says which.
        """
        from .agent_runtime import MEMORY_OWNER, SECRET_SHAPED_VALUE, memory_value_has_secret
        stop = cancelled or (lambda: False)
        request = str(job.get('message') or '')
        noted_keys, noted = self.work_noted(job['id'])
        data, decision = judgments.owner_model_proposals(request, answer, profile, clock, work_id=job['id'],
                                                         cancelled=cancelled, noted=noted)
        confidence = decision.confidence
        calls = 1 if call_sent(decision) else 0
        self.count(job['id'], calls)
        detail = {'decision': decision.outcome, 'route': confidence.route or None, 'provider': confidence.provider or None,
                  'model': confidence.model or None, 'observed_model': confidence.observed_model or None,
                  'confidence': confidence.probability, 'sent': bool(calls),
                  'inputs': {'owner_request_chars': len(request), 'answer_chars': len(answer or ''),
                             'profile_chars': len(profile or ''), 'clock': bool(clock)}}
        if data is None:
            return STATE_UNAVAILABLE, calls, EVENT_UNAVAILABLE, detail
        known, pending = self.known_values(MEMORY_OWNER, job['id'])
        kept, dropped = validate(data.get('proposals'), known, pending, noted_keys, request=request)
        applied, stopped = [], None
        for index, item in enumerate(kept):
            key, content = item['memory_key'], item['content']
            _left, why = self.allowance(self.clock())
            if why == STOPPED_PAUSED:
                # The owner paused learning: nothing more is written for this run.
                stopped = STOPPED_PAUSED
                dropped.extend({'key_digest': key_digest(rest['memory_key']), 'reason': STOPPED_PAUSED}
                               for rest in kept[index:])
                break
            if memory_value_has_secret(self.store, key, content):
                # #918 review P1: a stored secret or a credential-shaped value never enters Memory; only a key digest is kept.
                dropped.append({'key_digest': key_digest(key), 'reason': SECRET_SHAPED_VALUE})
                continue
            row = {'memory_key': key, 'category': item['category'], 'kind': item['kind'],
                   'content_chars': len(content), 'supersedes_key': item['supersedes_key'] or None}
            # #918 slice (a), owner decision 2026-09-30: the owner's own Judgment AI saves at once as
            # current Memory, attributed to the source Work (#794); the owner is told afterwards with
            # an undo (the Work's memory_saved notice) instead of a per-fact #597 judgment and an ask.
            # A write is not a model call, so the cap and the deadline do not stop it; the pause does.
            try:
                # Review: the owner notice is held in the same transaction as the row, so a save is never untold.
                memory = self.store.save_memory(key, content, MEMORY_OWNER, work_id=job['id'], notice=True)
            except ValueError:
                dropped.append({'key_digest': key_digest(key), 'reason': 'store-refused'})
                continue
            row.update(outcome=APPLIED_MEMORY, memory_id=memory['id'], superseded=bool(memory.get('supersedes')),
                       auto_saved=True)
            applied.append(row)
        detail.update(proposed=len(data.get('proposals') or []), applied=applied, dropped=dropped, stopped=stopped)
        return STATE_DONE, calls, EVENT_RECORDED, detail

    # -- one self-review (#998) ---------------------------------------------
    def run_review(self, job, row, judgments, *, answer, profile, clock, cancelled=None):
        """Review one settled Work from its own records; returns ``(state, calls, event_status, detail)``.

        One ``structured`` judgment (``ConversationJudgments.self_review``)
        over the owner's request, the answer excerpt, the Work's outcome, the
        orchestrator's verdicts, and the owner's follow-up (or the row's
        observation), all redacted by ``judgments``.  The kept lesson is
        saved at once as current ``profile.working.`` Memory attributed to
        the reviewed Work (#918 slice a: the owner's own AI writes, the owner
        is told with an undo); the blocker is kept in the event detail,
        redacted, and nowhere else.  The pause switch is read again before
        the write; a write is not a call.
        """
        from .agent_runtime import MEMORY_OWNER, SECRET_SHAPED_VALUE, memory_value_has_secret
        request = str(job.get('message') or '')
        reason = row.get('reason') or ''
        followups = self.followups(job['id'])
        followup = '\n'.join(followups) if followups else (row.get('observation') or '')
        evaluation = '\n'.join(self.evaluations(job['id']))
        data, decision = judgments.self_review(request, answer, str(job.get('status') or ''), evaluation, followup,
                                               profile, reason, work_id=job['id'], cancelled=cancelled)
        confidence = decision.confidence
        calls = 1 if call_sent(decision) else 0
        self.count(job['id'], calls, KIND_SELF_REVIEW)
        detail = {'reason': reason, 'decision': decision.outcome, 'route': confidence.route or None,
                  'provider': confidence.provider or None, 'model': confidence.model or None,
                  'observed_model': confidence.observed_model or None, 'confidence': confidence.probability,
                  'sent': bool(calls),
                  'inputs': {'owner_request_chars': len(request), 'answer_chars': len(answer or ''),
                             'evaluations': len(self.evaluations(job['id'])), 'followups': len(followups),
                             'observation': bool(row.get('observation')), 'profile_chars': len(profile or ''),
                             'clock': bool(clock)}}
        if data is None:
            return STATE_UNAVAILABLE, calls, EVENT_UNAVAILABLE, detail
        known, _pending = self.known_values(MEMORY_OWNER, job['id'])
        lesson, blocker, dropped = validate_review(data, known, request=request)
        detail.update(lesson=None, blocker=None, dropped=dropped, stopped=None)
        if blocker:
            # Evidence on the reviewed Work only: redacted like every fact, never filed anywhere.
            detail['blocker'] = judgments.redact(blocker)[:MAX_TEXT_CHARS]
        if lesson:
            key, content = lesson['memory_key'], lesson['content']
            _left, why = self.allowance(self.clock())
            if why == STOPPED_PAUSED:
                detail['stopped'] = STOPPED_PAUSED
                dropped.append({'note': 'lesson', 'key_digest': key_digest(key), 'reason': STOPPED_PAUSED})
            elif memory_value_has_secret(self.store, key, content):
                dropped.append({'note': 'lesson', 'key_digest': key_digest(key), 'reason': SECRET_SHAPED_VALUE})
            else:
                try:
                    memory = self.store.save_memory(key, content, MEMORY_OWNER, work_id=job['id'], notice=True)
                except ValueError:
                    dropped.append({'note': 'lesson', 'key_digest': key_digest(key), 'reason': 'store-refused'})
                else:
                    detail['lesson'] = {'memory_key': key, 'content_chars': len(content), 'outcome': APPLIED_MEMORY,
                                        'memory_id': memory['id'], 'superseded': bool(memory.get('supersedes')),
                                        'auto_saved': True}
        return STATE_DONE, calls, EVENT_RECORDED, detail


def enqueue_self_review(store, work_id, reason, observation=None, *, db=None, now=None, clock=time.time):
    """One pending self-review of ``work_id`` (#998); returns whether a row was added.

    The API another trigger uses (for example an owner reaction, #996):
    ``reason`` is one of ``REVIEW_REASONS``; ``observation`` is an optional
    short typed note the judgment reads as the owner's follow-up when no
    later message is linked to the Work.  Idempotent per Work: a second
    self-review of the same Work is not added.  Nothing runs here; the
    existing idle tick claims the row under the owner's pause switch and
    the rolling call cap.  With ``db`` it joins the caller's transaction.
    """
    if reason not in REVIEW_REASONS:
        raise ValueError('self-review reason')
    if not isinstance(work_id, str) or not work_id:
        raise ValueError('self-review work')
    return Upkeep(store, clock).enqueue(db, work_id, now, kind=KIND_SELF_REVIEW, reason=reason, observation=observation)
