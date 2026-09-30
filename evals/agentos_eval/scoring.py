"""Scoring one scenario run: deterministic checks plus the secretary-rubric judge.

A *run record* is what the solver collected from one sandbox::

    {'worker': 'codex', 'error': None,
     'turns': [{'say', 'note', 'task_id', 'status', 'answer', 'answer_withheld',
                'timed_out', 'failure_class', 'error', 'events', 'elapsed'}],
     'diff': {'memories', 'candidates', 'preparations', 'settings_changed', 'owner_model_changed'}}

Every failure is a ``{'kind', 'name', 'reason'}`` row.  ``kind`` and ``name``
form the root-cause cluster key the report groups by (a rubric dimension, a
deterministic check or an infrastructure failure), so twenty scenarios that
fail for one reason show up as one cluster, not twenty cases.
"""
import json
import math
import re

from .scenarios import RUBRIC

#: Terminal statuses that are not a failed outcome.
OK_STATUSES = frozenset({'succeeded', 'partial'})
ANSWER_CHARS = 6000
JUDGE_MAX_TOKENS = 1500


def _texts(rows, *keys):
    for row in rows:
        for key in keys:
            value = row.get(key)
            if isinstance(value, str) and value:
                yield value


def _normalized(text):
    return ' '.join(str(text or '').split()).casefold()


def deterministic_checks(scenario, run):
    """``(checks, failures)``: check name -> bool, and the failure rows."""
    failures = []
    if run.get('error'):
        failures.append({'kind': 'infra', 'name': 'harness', 'reason': str(run['error'])[:200]})
        return {'harness': False}, failures
    checks = {}
    judgment = run.get('judgment') or {}
    if judgment.get('requalified') and not judgment.get('ready'):
        # The sandbox could not get the owner's Judgment AI qualified: the run
        # measured the fallback path, not what the owner gets.
        failures.append({'kind': 'infra', 'name': 'judgment_ai',
                         'reason': judgment.get('failure') or f"not ready after {judgment.get('waited')}s"})
    turns = run.get('turns') or []
    undelivered = [index for index, turn in enumerate(turns)
                   if turn.get('answer_withheld') or not (turn.get('answer') or '').strip()]
    checks['delivered'] = bool(turns) and not undelivered
    for index in undelivered:
        reason = 'withheld' if turns[index].get('answer_withheld') else 'empty'
        failures.append({'kind': 'check', 'name': 'delivered', 'reason': f'turn {index + 1}: {reason}'})
    allowed = OK_STATUSES | set(scenario['expect'].get('allow_status') or ())
    bad = []
    for index, turn in enumerate(turns):
        if turn.get('timed_out'):
            bad.append((index, 'timeout'))
        elif turn.get('status') not in allowed:
            detail = turn.get('failure_class') or turn.get('status') or 'unknown'
            bad.append((index, f"{turn.get('status')}/{detail}" if detail != turn.get('status') else detail))
    checks['not_failed'] = bool(turns) and not bad
    for index, reason in bad:
        failures.append({'kind': 'check', 'name': 'not_failed', 'reason': f'turn {index + 1}: {reason}'})
    diff = run.get('diff') or {}
    groups = scenario['expect'].get('memory_any') or []
    if groups:
        stored = ' \n'.join(_texts([*diff.get('memories', []), *diff.get('candidates', [])],
                                   'content', 'value', 'memory_key')).casefold()
        missing = [group for group in groups if not any(item.casefold() in stored for item in group)]
        checks['memory'] = not missing
        for group in missing:
            failures.append({'kind': 'check', 'name': 'memory', 'reason': 'no new memory/candidate mentions '
                             + ' | '.join(group)})
    if scenario['expect'].get('preparation'):
        checks['preparation'] = bool(diff.get('preparations'))
        if not checks['preparation']:
            failures.append({'kind': 'check', 'name': 'preparation', 'reason': 'no reminder/preparation was created'})
    if scenario['expect'].get('no_memory_of_request'):
        # #846: a standing wish is a watch, not a memory; the request sentence must not become a value.
        said = {_normalized(turn.get('say')) for turn in turns if (turn.get('say') or '').strip()}
        said |= {_normalized(turn['say']) for turn in scenario.get('turns') or [] if turn.get('say')}
        stored = [_normalized(text) for text in _texts([*diff.get('memories', []), *diff.get('candidates', [])],
                                                       'content', 'value')]
        echoed = [text for text in stored if text in said]
        checks['no_memory_of_request'] = not echoed
        for text in echoed:
            failures.append({'kind': 'check', 'name': 'no_memory_of_request',
                             'reason': f'a new memory/candidate is the owner\'s request sentence: {text[:80]}'})
    return checks, failures


# -- judge --------------------------------------------------------------------
JUDGE_SYSTEM = (
    'You evaluate a personal AI secretary called AgentOS. You see an owner scenario, the owner turns, '
    'the answers AgentOS delivered and the owner-state changes it recorded. Judge only what is shown; '
    'do not assume a tool ran, a place exists or a price is right unless the answer shows its source. '
    'Score each listed dimension 2 (meets), 1 (partly) or 0 (fails), or null when the conversation gives '
    'no occasion to show it. Reply with JSON only.')


def judge_prompt(scenario, run):
    dims = scenario['rubric']
    lines = [f'Scenario: {scenario["title"]}', '']
    if scenario.get('good_secretary'):
        lines += ['What a good secretary would do:', scenario['good_secretary'], '']
    lines.append('Conversation:')
    for index, turn in enumerate(run.get('turns') or [], 1):
        if turn.get('note'):
            lines.append(f'[situation before turn {index}: {turn["note"]}]')
        lines.append(f'OWNER {index}: {turn.get("say", "")}')
        answer = (turn.get('answer') or '').strip()
        if turn.get('answer_withheld'):
            answer = '(answer withheld by AgentOS)'
        if len(answer) > ANSWER_CHARS:
            answer = answer[:ANSWER_CHARS] + ' [...]'
        lines.append(f'AGENTOS {index} (status {turn.get("status")}): {answer or "(no answer delivered)"}')
    diff = run.get('diff') or {}
    lines += ['', 'Owner-state changes recorded during the conversation:']
    for label, rows, keys in (('new memory', diff.get('memories', []), ('content',)),
                              ('new memory candidate (awaiting owner confirmation)', diff.get('candidates', []),
                               ('content', 'value')),
                              ('new reminder/preparation', diff.get('preparations', []),
                               ('kind', 'goal', 'due_local', 'every_minutes', 'until_local', 'delivery', 'state'))):
        for row in rows[:10]:
            lines.append(f'- {label}: ' + ' / '.join(str(row.get(key)) for key in keys if row.get(key)))
    if not any(diff.get(key) for key in ('memories', 'candidates', 'preparations')):
        lines.append('- none')
    if diff.get('settings_changed'):
        lines.append('- settings changed')
    lines += ['', 'Dimensions:']
    lines += [f'- {dim}: {RUBRIC[dim]}' for dim in dims]
    lines += ['', 'Reply as JSON: {"dimensions": {"<dimension>": {"score": 0|1|2|null, "reason": "<one sentence>"}}, '
              '"summary": "<one sentence>"}']
    return '\n'.join(lines)


def parse_judgment(text, dims):
    """Parse the judge reply into ``{dim: {'score': 0..1 or None, 'reason'}}``; raises ValueError."""
    match = re.search(r'\{.*\}', text or '', re.S)
    if not match:
        raise ValueError('judge reply has no JSON object')
    data = json.loads(match.group(0))
    rows = data.get('dimensions') if isinstance(data, dict) else None
    if not isinstance(rows, dict):
        raise ValueError('judge reply has no dimensions')
    result = {}
    for dim in dims:
        row = rows.get(dim)
        if not isinstance(row, dict) or 'score' not in row:
            raise ValueError(f'judge reply misses {dim}')
        score = row['score']
        if score is not None and (isinstance(score, bool) or score not in (0, 1, 2)):
            raise ValueError(f'judge score for {dim} is not 0, 1, 2 or null')
        result[dim] = {'score': None if score is None else score / 2, 'reason': str(row.get('reason') or '')[:300]}
    return {'dimensions': result, 'summary': str(data.get('summary') or '')[:400]}


def rubric_failures(judgment):
    """A dimension scored 0 is a failure; 1 (partly) is a weakness, reported but not a failure."""
    rows = []
    for dim, row in (judgment or {}).get('dimensions', {}).items():
        if row['score'] == 0:
            rows.append({'kind': 'rubric', 'name': dim, 'reason': row['reason']})
    return rows


CHECK_NAMES = ('harness', 'delivered', 'not_failed', 'memory', 'preparation', 'no_memory_of_request')


def combine(scenario, run, checks, failures, judgment=None, judge_status='skipped'):
    """The score value (all floats, for Inspect) and the metadata the report reads."""
    value = {f'check_{name}': 1.0 if ok else 0.0 for name, ok in checks.items()}
    if judgment:
        for dim, row in judgment['dimensions'].items():
            if row['score'] is not None:
                value[f'rubric_{dim}'] = float(row['score'])
        failures = [*failures, *rubric_failures(judgment)]
    rubric_scores = [value[key] for key in value if key.startswith('rubric_')]
    value['checks_pass'] = 1.0 if checks and all(checks.values()) else 0.0
    value['rubric_mean'] = sum(rubric_scores) / len(rubric_scores) if rubric_scores else math.nan
    # Inspect's per-key metrics need every score to carry the same keys; a key that
    # does not apply to this scenario is NaN, which Inspect counts as unscored.
    for key in [f'check_{name}' for name in CHECK_NAMES] + [f'rubric_{dim}' for dim in RUBRIC]:
        value.setdefault(key, math.nan)
    value['passed'] = 1.0 if value['checks_pass'] and not failures else 0.0
    metadata = {'scenario': scenario['id'], 'source': scenario.get('source', 'bundled'), 'split': scenario['split'],
                'worker': run.get('worker'), 'checks': checks, 'failures': failures, 'judge_status': judge_status,
                'judgment': judgment, 'judgment_ai': run.get('judgment'), 'statuses': [turn.get('status') for turn in run.get('turns') or []],
                'failure_classes': [turn.get('failure_class') for turn in run.get('turns') or []],
                'elapsed': [turn.get('elapsed') for turn in run.get('turns') or []]}
    return value, metadata
