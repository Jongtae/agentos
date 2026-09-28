"""Owner-model upkeep: keep the owner in mind, asynchronously and minimised (OWNER-MODEL-03, #805 phase 1).

Bounded by docs/secretary-agency-contract.en.md ("Amendment - #805 phase 1"):

* **Trigger.** A Work a worker AI answered that ends ``succeeded`` or
  ``partial`` records one durable ``owner_model_upkeep`` row, in the same
  transaction that settles it (idempotent per Work).  Failed, cancelled and
  unknown Works, rule/command replies (no worker AI ran), preparation runs
  and location continuations record none: typed markers, never text rules.
* **Tick.** The existing service loop asks one indexed query per tick.  At
  most one pending row runs per tick, only while no Work is queued or
  running, never on a request path.  Nothing pending costs no model call.
* **Judgment (C16).** The owner's Judgment AI (``DecisionEngine.structured``)
  reads the owner's request (owner words), the final answer excerpt
  (model-stated), the profile snapshot and the clock, every fact redacted
  first, and proposes at most ``MAX_PROPOSALS`` durable owner facts.
* **Validation (AgentOS).** Out-of-enum, oversized, non-``profile.`` and
  duplicate proposals are dropped.  ``stated`` passes the #597
  ``explicit_memory_request`` judgment and value-coverage rule to become
  canonical Memory through the candidate -> accept path; otherwise, and
  always for ``inferred``, it stays a pending MemoryCandidate (C5).  Both are
  attributed to the source Work.
* **Minimisation.** An owner pause switch and a rolling 24-hour call cap
  (``CONFIG_KEY``); a pending row older than ``MAX_PENDING_SECONDS`` expires
  without a call.  Each run is one ``owner_model`` tool event on the source
  Work: counts, keys, kinds, outcomes and the deciding route - never the
  input texts.

Nothing here names a site, provider, task or request category.
"""
import json
import time

#: The source Work's tool-event name of every upkeep run (#794 shows it).
EVENT_TOOL = 'owner_model'
#: The DecisionContext purpose of the proposal judgment.
PURPOSE = 'owner-model-upkeep'
#: The owner's controls: ``{'enabled': bool, 'daily_calls': int}``.
CONFIG_KEY = 'owner_model_upkeep'
DEFAULT_DAILY_CALLS = 20
MAX_DAILY_CALLS = 200
#: The cap is a rolling window, so it needs no time zone.
WINDOW_SECONDS = 24 * 3600
#: A pending upkeep this old is dropped without a model call.
MAX_PENDING_SECONDS = 7 * 24 * 3600

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
REFUSED_INFERRED = 'inferred-stays-candidate'

TABLE_SQL = '''
CREATE TABLE IF NOT EXISTS owner_model_upkeep(job_id TEXT PRIMARY KEY, state TEXT NOT NULL, created REAL NOT NULL,
    claimed REAL, calls INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS owner_model_upkeep_state ON owner_model_upkeep(state, created);
CREATE INDEX IF NOT EXISTS owner_model_upkeep_claimed ON owner_model_upkeep(claimed);
'''

QUESTION = ('From this one finished request, propose durable facts about the owner that would help the assistant '
            'serve them in later requests. owner_request holds the owner\'s own words; final_answer_excerpt is '
            'what the assistant answered (model-stated) and is never by itself a fact about the owner. Use kind '
            '"stated" only for what the owner said about themselves in owner_request, and write its content in the '
            'owner\'s own words. Use kind "inferred" for a reasonable inference from what the owner said (for '
            'example a routine); it is only a proposal the owner confirms, never asserted as fact. category is '
            'one of: ' + ', '.join(CATEGORIES) + '. memory_key starts with "profile." and names the fact, not '
            'the request (profile.<category>.<name>); when the fact updates a key already in owner_profile, use '
            'that key and set supersedes_key to it, otherwise supersedes_key is an empty string. content and '
            'evidence are at most 200 characters each; evidence is a short quote or paraphrase of what the owner '
            'said. Never propose health, finances, relationships, beliefs, credentials or anything about other '
            'people unless the owner stated it about themselves for a purpose (then kind "stated"). Do not repeat '
            'what owner_profile already says. Use clock only to turn relative time into an absolute date, or to '
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
    if not isinstance(supersedes, str) or (supersedes and not profile_key(supersedes)):
        return 'supersedes'
    return None


def validate(proposals, current, pending):
    """``(kept, dropped)`` of the proposals AgentOS may apply (deterministic).

    ``current`` / ``pending`` are ``{(memory_key, normalized content)}`` of the
    current Memory and the pending MemoryCandidates: a proposal equal to one
    is a duplicate.  ``dropped`` names a key only when it is well formed.
    """
    kept, dropped, keys = [], [], set()
    for index, item in enumerate(proposals if isinstance(proposals, list) else ()):
        reason = 'over-limit' if index >= MAX_PROPOSALS else _refusal(item)
        key = item.get('memory_key') if isinstance(item, dict) and profile_key(item.get('memory_key')) else None
        if reason is None:
            value = (key, normalized(item['content']))
            if key in keys or value in current or value in pending:
                reason = 'duplicate'
        if reason is not None:
            dropped.append({'memory_key': key, 'reason': reason} if key else {'reason': reason})
            continue
        keys.add(key)
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
        if db is None:
            with self.store.db() as conn:
                return self.calls_used(now, conn)
        row = db.execute('SELECT COALESCE(SUM(calls),0) FROM owner_model_upkeep WHERE claimed>=?',
                         (now - WINDOW_SECONDS,)).fetchone()
        return int(row[0] or 0)

    def status(self, now=None):
        now = self.clock() if now is None else now
        with self.store.db() as db:
            pending = db.execute('SELECT COUNT(*) FROM owner_model_upkeep WHERE state=?', (STATE_PENDING,)).fetchone()[0]
            used = self.calls_used(now, db)
        return {**self.settings(), 'pending': int(pending), 'calls_last_24h': used}

    # -- the queue ----------------------------------------------------------
    def enqueue(self, db, job_id, now=None):
        """One pending upkeep for ``job_id`` inside the caller's transaction; idempotent per Work."""
        if not self.settings(db)['enabled']:
            return False
        return db.execute('INSERT OR IGNORE INTO owner_model_upkeep(job_id,state,created) VALUES (?,?,?)',
                          (job_id, STATE_PENDING, self.clock() if now is None else now)).rowcount == 1

    def due(self, now):
        """The oldest pending row this tick may run, or None (one indexed query when nothing is pending)."""
        with self.store.db() as db:
            row = db.execute('SELECT job_id,created FROM owner_model_upkeep WHERE state=? ORDER BY created LIMIT 1',
                             (STATE_PENDING,)).fetchone()
            if row is None:
                return None
            if not self.settings(db)['enabled']:
                return None
            if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running') LIMIT 1").fetchone():
                return None
            if now - row['created'] > MAX_PENDING_SECONDS:
                return dict(row)
            if self.calls_used(now, db) >= self.settings(db)['daily_calls']:
                return None
            return dict(row)

    def claim(self, job_id, now):
        """Claim once: a claimed row is never run again, even after a restart.

        It counts one call until ``finish`` records the real number, so a run
        cut off mid-call still counts against the cap.
        """
        with self.store.db() as db:
            return db.execute('UPDATE owner_model_upkeep SET state=?,claimed=?,calls=1 WHERE job_id=? AND state=?',
                              (STATE_CLAIMED, now, job_id, STATE_PENDING)).rowcount == 1

    def finish(self, job_id, state, calls, event_status, detail, now):
        """Settle a claimed row and record its one tool event on the source Work."""
        with self.store.db() as db:
            db.execute('UPDATE owner_model_upkeep SET state=?,calls=? WHERE job_id=?', (state, int(calls), job_id))
            db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                       (job_id, EVENT_TOOL, event_status, json.dumps(detail, ensure_ascii=False), now))

    # -- known values -------------------------------------------------------
    def known_values(self, owner):
        """``(current, pending)`` ``{(memory_key, normalized content)}`` of ``profile.`` Memory and candidates."""
        current, offset = set(), 0
        while True:
            page = self.store.memories(owner, limit=101, offset=offset, key_prefix=PROFILE_PREFIX)
            current |= {(row['memory_key'], normalized(row['content'])) for row in page}
            if len(page) < 101:
                break
            offset += 101
        with self.store.db() as db:
            pending = {(row['memory_key'], normalized(row['content'])) for row in db.execute(
                "SELECT memory_key,content FROM memory_candidates WHERE state='pending' AND memory_key LIKE 'profile.%'")}
        return current, pending

    # -- one run ------------------------------------------------------------
    def run(self, job, judgments, *, answer, profile, clock, now):
        """Ask, validate and apply for one finished Work; returns ``(state, calls, event_status, detail)``.

        ``judgments`` is a ``ConversationJudgments`` whose redactor is scoped
        to this Work.  Only a confident structured answer is applied.
        """
        from .agent_runtime import MEMORY_OWNER, memory_write_refusal
        from .conversation_handoff import JUDGMENT_YES
        from .decision import STRUCTURED_UNSUPPORTED
        request = str(job.get('message') or '')
        data, decision = judgments.owner_model_proposals(request, answer, profile, clock, work_id=job['id'])
        confidence = decision.confidence
        calls = 0 if confidence.engine == STRUCTURED_UNSUPPORTED else 1
        detail = {'decision': decision.outcome, 'route': confidence.route or None, 'provider': confidence.provider or None,
                  'model': confidence.model or None, 'observed_model': confidence.observed_model or None,
                  'confidence': confidence.probability,
                  'inputs': {'owner_request_chars': len(request), 'answer_chars': len(answer or ''),
                             'profile_chars': len(profile or ''), 'clock': bool(clock)}}
        if data is None:
            return STATE_UNAVAILABLE, calls, EVENT_UNAVAILABLE, detail
        current, pending = self.known_values(MEMORY_OWNER)
        kept, dropped = validate(data.get('proposals'), current, pending)
        applied, verdict = [], None
        for item in kept:
            key, content = item['memory_key'], item['content']
            refusal = REFUSED_INFERRED
            if item['kind'] == KIND_STATED:
                if verdict is None:
                    # #597: the owner's own request is what may make a stated fact canonical.
                    verdict = judgments.explicit_memory_request(request).outcome
                    calls += 1
                approval = (self.store.issue_memory_approval(job['id'], request) if verdict == JUDGMENT_YES
                            and request.strip() else None)
                refusal = memory_write_refusal(self.store, job['id'], approval, key, content)
            row = {'memory_key': key, 'category': item['category'], 'kind': item['kind'],
                   'content_chars': len(content), 'supersedes_key': item['supersedes_key'] or None}
            try:
                # Attributed to the source Work, so its provenance links back (#794).
                candidate = self.store.save_memory_candidate(job['id'], key, content)
            except ValueError:
                dropped.append({'memory_key': key, 'reason': 'store-refused'})
                continue
            row['candidate_id'] = candidate['id']
            if refusal is None:
                # The same candidate -> exact approval -> accept path as save_memory (#597).
                try:
                    token = self.store.issue_candidate_memory_approval(MEMORY_OWNER, job['id'], candidate['id'],
                                                                       candidate['content_digest'])
                    memory = self.store.accept_memory_candidate(MEMORY_OWNER, job['id'], candidate['id'],
                                                                candidate['content_digest'], token['approval_token'])
                    row.update(outcome=APPLIED_MEMORY, memory_id=memory['id'])
                except ValueError:
                    refusal = 'accept-refused'
            if refusal is not None:
                row.update(outcome=APPLIED_CANDIDATE, refused_because=refusal)
            applied.append(row)
        detail.update(proposed=len(data.get('proposals') or []), applied=applied, dropped=dropped,
                      memory_request=verdict)
        return STATE_DONE, calls, EVENT_RECORDED, detail
