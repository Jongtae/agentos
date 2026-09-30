"""Drive one multi-turn scenario through a fresh sandbox; returns the run record.

Standard library only; ``task.py`` calls it from Inspect in a worker thread.
"""
import time
import uuid

from .client import AgentOSClient, ClientError, compact_events, state_diff
from .sandbox import JUDGMENT_KEYS, SandboxError
from .scenarios import owner_message

WORKERS = ('codex', 'claude-code')
USAGE_LIMIT = 'usage-limit'


class StopOnUsageLimit:
    """Inspect ``EarlyStopping`` manager: once a turn hits a subscription usage limit, start no more samples.

    The workers run on the owner's own subscriptions, which the owner's live
    AgentOS shares (#887).  Past the limit every run fails the same way, so
    going on only burns the owner's quota and fills the report with outage
    rows.  The tripping run stops at that turn and is not judged; other
    samples already running finish; the rest are skipped, and the
    skipped count lands in the log's early-stopping summary.  ``make_stop`` is
    Inspect's ``EarlyStop`` (injected so this module stays standard-library only).
    """

    def __init__(self, make_stop):
        self.make_stop = make_stop
        self.tripped = None

    async def start_task(self, task, samples, epochs):
        self.tripped = None
        return 'stop-on-usage-limit'

    async def schedule_sample(self, id, epoch):  # noqa: A002 - Inspect's protocol names
        if self.tripped:
            return self.make_stop(id=id, epoch=epoch, reason=f'usage limit hit in {self.tripped}')
        return None

    async def complete_sample(self, id, epoch, scores):  # noqa: A002
        for sample_score in (scores or {}).values():
            metadata = getattr(getattr(sample_score, 'score', None), 'metadata', None) or {}
            if USAGE_LIMIT in (metadata.get('failure_classes') or ()) and not self.tripped:
                self.tripped = f'{id} (epoch {epoch})'

    async def complete_task(self):
        return {'tripped_by': self.tripped}


def run_turns(client, scenario, turn_timeout=900, poll_interval=2.0, clock=time.monotonic):
    turns = []
    for turn in scenario['turns']:
        started = clock()
        task_id = client.send(owner_message(turn), f'eval-{scenario["id"]}-{uuid.uuid4().hex[:12]}')
        detail = client.wait(task_id, timeout=turn_timeout, interval=poll_interval)
        answer = client.answer(task_id)
        turns.append({'say': turn['say'], 'note': turn.get('note', ''), 'task_id': task_id,
                      'status': detail.get('status'), 'answer': answer.get('response') or '',
                      'answer_withheld': answer.get('answer_withheld', False),
                      'timed_out': bool(detail.get('timed_out')), 'failure_class': detail.get('failure_class'),
                      'error': (detail.get('error') or '')[:300] if isinstance(detail.get('error'), str) else None,
                      'events': compact_events(detail), 'elapsed': round(clock() - started, 1)})
        if detail.get('timed_out'):
            break  # the sandbox is still busy with this turn; later turns would queue behind it
        if detail.get('failure_class') == USAGE_LIMIT:
            break  # #887: later turns would only spend more of the owner's exhausted subscription
    return turns


def usage_limited(run):
    """Whether a run record hit a subscription usage limit (#887): then it is neither continued nor judged."""
    return any(turn.get('failure_class') == USAGE_LIMIT for turn in (run or {}).get('turns') or ())


def prepare_judgment(client, pool, box, worker, timeout=300, clock=time.monotonic):
    """Make the sandbox's Judgment AI what the owner has: qualified here, for this worker.

    A qualification is bound to the store path, so a copied seed starts
    unqualified.  A cached qualification for this slot/worker/seed was
    applied before start; only when it is missing or stale does this ask
    AgentOS to qualify again (through the owner's own routes) and cache it.
    """
    status = client.judgment()
    started = clock()
    requalified = False
    if not client.judgment_ready(status, worker):
        if getattr(box, 'cached', None):
            pool.forget_judgment(box.slot, worker)
        try:
            requested = client.requalify_judgment(worker, status)
        except ClientError as exc:
            requested, failure = None, str(exc)[:200]
        else:
            failure = None
        if requested is not None:
            requalified = True
            status = client.wait_judgment(worker, timeout=timeout)
        if failure:
            return {'ready': False, 'mode': status['mode'], 'engine': status['engine'], 'model': status['model'],
                    'requalified': True, 'cached': False, 'waited': round(clock() - started, 1), 'failure': failure}
    ready = client.judgment_ready(status, worker)
    if ready and requalified and getattr(box, 'slot', None) is not None:
        pool.store_judgment(box.slot, worker, box.read_config(JUDGMENT_KEYS))
    return {'ready': ready, 'mode': status['mode'], 'engine': status['engine'], 'model': status['model'],
            'requalified': requalified, 'cached': bool(getattr(box, 'cached', None)) and not requalified,
            'waited': round(clock() - started, 1)}


def run_scenario(scenario, worker, pool, client_factory=AgentOSClient, turn_timeout=900, poll_interval=2.0,
                 judgment_timeout=300, upkeep_timeout=90):
    """One clean-state trial: fresh sandbox, login, select worker, turns, owner-state diff."""
    if worker not in WORKERS:
        raise ValueError(f'worker must be one of {WORKERS}')
    record = {'worker': worker, 'turns': [], 'diff': {}, 'error': None, 'judgment': None, 'upkeep': None}
    try:
        with pool.sandbox(worker) as box:
            client = client_factory(box.url)
            box.wait_healthy(client)
            client.login()
            client.select_worker(worker)
            record['judgment'] = prepare_judgment(client, pool, box, worker, judgment_timeout)
            before = client.snapshot()
            record['turns'] = run_turns(client, scenario, turn_timeout, poll_interval)
            # #832: upkeep proposes Memory asynchronously after a Work (#805); let it settle first.
            record['upkeep'] = client.wait_upkeep_idle(upkeep_timeout, poll_interval)
            record['diff'] = state_diff(before, client.snapshot())
    except (SandboxError, ClientError, OSError) as exc:
        record['error'] = f'{type(exc).__name__}: {exc}'
    return record
