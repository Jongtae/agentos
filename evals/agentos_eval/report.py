"""Trend report per sweep: JSON plus a short markdown summary, grouped by root cause.

Reports are written to ``<eval home>/reports`` (outside the repository).
Failures are clustered by ``kind:name`` (a rubric dimension, a deterministic
check or an infrastructure failure), and each report is compared with the
previous one so a regression or a new cluster stands out.
"""
import hashlib
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

SCORER = 'secretary'
#: A drop of at least this much in a pass rate or rubric mean is a regression.
REGRESSION_DROP = 0.10


def records_from_samples(samples, scorer=SCORER):
    """Per-run records from Inspect eval-log samples (duck-typed: ``id``, ``epoch``, ``scores``).

    A sample that errored before it was scored stays in the denominator as an
    ``infra:sample_error`` failure, so an outage never improves a pass rate.
    """
    records = []
    for sample in samples or []:
        score = (getattr(sample, 'scores', None) or {}).get(scorer)
        if score is None:
            meta = getattr(sample, 'metadata', None) or {}
            scenario = meta.get('scenario') if isinstance(meta.get('scenario'), dict) else {}
            error = getattr(sample, 'error', None)
            reason = str(getattr(error, 'message', None) or error or 'not scored')[:200]
            records.append({'scenario': scenario.get('id') or str(getattr(sample, 'id', '')).split('@')[0],
                            'source': scenario.get('source'), 'split': scenario.get('split'),
                            'worker': meta.get('worker'), 'checks': {}, 'judge_status': 'not_scored',
                            'failures': [{'kind': 'infra', 'name': 'sample_error', 'reason': reason}],
                            'sample_id': str(getattr(sample, 'id', '')), 'epoch': getattr(sample, 'epoch', 1),
                            'value': {'passed': 0.0}})
            continue
        meta = dict(getattr(score, 'metadata', None) or {})
        records.append({**meta, 'sample_id': str(getattr(sample, 'id', '')), 'epoch': getattr(sample, 'epoch', 1),
                        'value': dict(getattr(score, 'value', None) or {})})
    return records


def _rate(values):
    values = list(values)
    return round(sum(values) / len(values), 4) if values else None


def _group(records):
    runs = len(records)
    passed = sum(1 for record in records if record['value'].get('passed'))
    checks = defaultdict(list)
    rubric = defaultdict(list)
    for record in records:
        for name, ok in (record.get('checks') or {}).items():
            checks[name].append(1.0 if ok else 0.0)
        for key, value in record['value'].items():
            if key.startswith('rubric_') and key != 'rubric_mean' and value == value:
                rubric[key[len('rubric_'):]].append(value)
    return {'runs': runs, 'passed': passed, 'pass_rate': _rate([record['value'].get('passed', 0) for record in records]),
            'checks': {name: {'n': len(values), 'pass_rate': _rate(values)} for name, values in sorted(checks.items())},
            'rubric': {dim: {'n': len(values), 'mean': _rate(values),
                             'zero_rate': _rate([1.0 if value == 0 else 0.0 for value in values])}
                       for dim, values in sorted(rubric.items())}}


def clusters(records):
    grouped = {}
    for record in records:
        for failure in record.get('failures') or []:
            key = f"{failure['kind']}:{failure['name']}"
            row = grouped.setdefault(key, {'key': key, 'kind': failure['kind'], 'name': failure['name'], 'count': 0,
                                           'scenarios': Counter(), 'workers': Counter(), 'examples': []})
            row['count'] += 1
            row['scenarios'][record.get('scenario')] += 1
            row['workers'][record.get('worker') or 'unknown'] += 1
            if len(row['examples']) < 3 and failure.get('reason'):
                row['examples'].append(f"{record.get('scenario')}: {failure['reason']}")
    result = []
    for row in grouped.values():
        result.append({**row, 'scenarios': dict(row['scenarios'].most_common()), 'workers': dict(row['workers'])})
    return sorted(result, key=lambda row: (-row['count'], row['key']))


def cohort(records):
    """Which population a report measured: its (scenario, worker) pairs and epochs.

    Trends compare only reports of the same cohort, so a targeted re-run of
    one scenario is never compared with a full sweep.
    """
    pairs = sorted({(str(record.get('scenario')), str(record.get('worker'))) for record in records})
    epochs = max((record.get('epoch') or 1 for record in records), default=0)
    return hashlib.sha256(json.dumps([pairs, epochs]).encode()).hexdigest()[:12]


def aggregate(records, run=None):
    by_worker = defaultdict(list)
    by_scenario = defaultdict(list)
    for record in records:
        by_worker[record.get('worker') or 'unknown'].append(record)
        by_scenario[record.get('scenario')].append(record)
    judge = Counter(record.get('judge_status') or 'unknown' for record in records)
    return {'run': dict(run or {}), 'cohort': cohort(records), 'generated_at': time.time(), 'totals': _group(records),
            'by_worker': {worker: _group(rows) for worker, rows in sorted(by_worker.items())},
            'scenarios': {scenario: {'runs': len(rows), 'pass_rate': _rate([row['value'].get('passed', 0) for row in rows]),
                                     'source': rows[0].get('source'), 'split': rows[0].get('split')}
                          for scenario, rows in sorted(by_scenario.items())},
            'clusters': clusters(records), 'judge': dict(judge)}


def compare(current, previous):
    """Trend against the previous report: deltas, regressions, new and resolved clusters."""
    if not previous:
        return {'previous_run': None, 'regressions': [], 'new_clusters': [c['key'] for c in current['clusters']],
                'resolved_clusters': []}
    regressions = []

    def check(label, now, before):
        if now is not None and before is not None and before - now >= REGRESSION_DROP:
            regressions.append({'metric': label, 'before': before, 'now': now})
    check('pass_rate', current['totals']['pass_rate'], previous['totals'].get('pass_rate'))
    for name, row in current['totals']['checks'].items():
        check(f'check:{name}', row['pass_rate'], previous['totals'].get('checks', {}).get(name, {}).get('pass_rate'))
    for dim, row in current['totals']['rubric'].items():
        check(f'rubric:{dim}', row['mean'], previous['totals'].get('rubric', {}).get(dim, {}).get('mean'))
    now_keys = {row['key'] for row in current['clusters']}
    before_keys = {row['key'] for row in previous.get('clusters', [])}
    before_rate, now_rate = previous['totals'].get('pass_rate'), current['totals']['pass_rate']
    return {'previous_run': previous.get('run', {}).get('id'),
            'pass_rate_delta': None if before_rate is None or now_rate is None else round(now_rate - before_rate, 4),
            'regressions': regressions, 'new_clusters': sorted(now_keys - before_keys),
            'resolved_clusters': sorted(before_keys - now_keys)}


def _pct(value):
    return 'n/a' if value is None else f'{value * 100:.0f}%'


def render_markdown(report):
    run, totals, trend = report.get('run', {}), report['totals'], report.get('trend') or {}
    lines = [f"# AgentOS eval sweep {run.get('id', '')}", '',
             f"- runs: {totals['runs']}, passed: {totals['passed']} ({_pct(totals['pass_rate'])})",
             f"- workers: {', '.join(f'{name} {_pct(row['pass_rate'])} of {row['runs']}' for name, row in report['by_worker'].items())}",
             f"- judge: {', '.join(f'{k} {v}' for k, v in sorted(report['judge'].items()))}"]
    if run.get('git_head'):
        lines.append(f"- code: {run['git_head']}")
    if run.get('stopped'):
        lines.append(f"- STOPPED on a usage limit in {run['stopped'].get('tripped_by')}: "
                     f"{run['stopped'].get('skipped')} runs not started; not used as a trend baseline")
    if trend.get('previous_run'):
        lines.append(f"- vs {trend['previous_run']}: pass rate delta {trend.get('pass_rate_delta')}")
    if trend.get('regressions'):
        lines += ['', '## Regressions']
        lines += [f"- {row['metric']}: {_pct(row['before'])} -> {_pct(row['now'])}" for row in trend['regressions']]
    lines += ['', '## Failure clusters (root cause first)']
    if not report['clusters']:
        lines.append('- none')
    new = set(trend.get('new_clusters') or [])
    for row in report['clusters'][:15]:
        marker = ' (new)' if row['key'] in new else ''
        lines.append(f"- **{row['key']}**{marker}: {row['count']} runs across {len(row['scenarios'])} scenarios; "
                     f"workers {row['workers']}")
        lines += [f'  - {example}' for example in row['examples']]
    lines += ['', '## Checks and rubric', '', '| item | codex | claude-code | all |', '| --- | --- | --- | --- |']
    items = [('check', name) for name in totals['checks']] + [('rubric', dim) for dim in totals['rubric']]
    for kind, name in items:
        def cell(group):
            row = group.get('checks' if kind == 'check' else 'rubric', {}).get(name)
            return 'n/a' if not row else _pct(row['pass_rate'] if kind == 'check' else row['mean'])
        lines.append(f"| {kind}:{name} | {cell(report['by_worker'].get('codex', {}))} | "
                     f"{cell(report['by_worker'].get('claude-code', {}))} | {cell(totals)} |")
    if trend.get('resolved_clusters'):
        lines += ['', 'Resolved since the previous sweep: ' + ', '.join(trend['resolved_clusters'])]
    return '\n'.join(lines) + '\n'


def latest_report(folder, of_cohort=None):
    """The newest complete report in ``folder``, of ``of_cohort`` when given."""
    folder = Path(folder)
    reports = sorted(folder.glob('*.json')) if folder.is_dir() else []
    for path in reversed(reports):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if (data.get('run') or {}).get('stopped'):
            continue  # #887: stopped on a usage limit, so incomplete; never a baseline
        if of_cohort is None or data.get('cohort') == of_cohort:
            return data
    return None


def write_report(records, folder, run):
    """Aggregate, compare with the previous report, write ``<run id>.json`` and ``.md``; returns the paths."""
    folder = Path(folder)
    report = aggregate(records, run)
    previous = latest_report(folder, report['cohort'])
    report['trend'] = compare(report, previous)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    json_path = folder / f"{run['id']}.json"
    md_path = folder / f"{run['id']}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    md_path.write_text(render_markdown(report), encoding='utf-8')
    return json_path, md_path, report
