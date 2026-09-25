#!/usr/bin/env python3
"""Offline requirement/ownership check only; never a product-result certificate.

#612 retires the unused exhaustive-trial/JUnit/trace certification path.
Use existing unit/integration test reports. No model, network or owner data.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path('docs/evals/assistant-execution-v1.json')
MAX_BYTES = 10_000_000


class EvidenceError(ValueError):
    """A fail-closed specification or evidence mismatch."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def unique(rows: list, field: str) -> dict:
    require(isinstance(rows, list) and bool(rows), f'{field}: expected nonempty list')
    result = {}
    for row in rows:
        require(isinstance(row, dict), f'{field}: expected object')
        key = row.get(field)
        require(isinstance(key, str) and bool(key) and key not in result, f'{field}: missing/duplicate identifier')
        result[key] = row
    return result


def bounded_read(path: Path) -> bytes:
    with path.open('rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    require(len(data) <= MAX_BYTES, 'artifact exceeds size limit')
    return data


def no_duplicate_keys(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, 'duplicate JSON key')
        obj[key] = value
    return obj


def load_json(data: bytes):
    return json.loads(data, object_pairs_hook=no_duplicate_keys,
                      parse_constant=lambda _: (_ for _ in ()).throw(EvidenceError('non-finite JSON number')))


def check_spec(root: Path = ROOT) -> dict:
    manifest = load_json(bounded_read(root / MANIFEST))
    require(manifest.get('schema_version') == 2, 'unknown manifest version')
    profiles = manifest.get('profiles')
    require(isinstance(profiles, list) and bool(profiles) and
            all(isinstance(p, str) and p for p in profiles) and len(profiles) == len(set(profiles)), 'invalid profiles')
    policy = manifest.get('verification_policy', {})
    require(isinstance(policy, dict) and policy.get('default') == 'unit-first', 'unit-first policy required')
    require(policy.get('routine_model_requests') is False and policy.get('per_answer_judge') is False,
            'routine model requests and per-answer judges must remain disabled')
    require('trials' not in manifest and 'minimum_real_model_success_rate' not in manifest,
            'blanket trial/score gate is retired')
    model = policy.get('model_checks', {})
    require(isinstance(model, dict) and model.get('mode') == 'opt-in' and model.get('budget_required') is True,
            'model checks require explicit opt-in and budget')
    require(policy.get('integration') == 'changed-boundary' and policy.get('mutation') == 'risk-targeted',
            'verification must be change/risk proportionate')
    requirements = unique(manifest.get('requirements'), 'id')
    scenarios = unique(manifest.get('scenarios'), 'id')
    units = unique(manifest.get('units'), 'id')
    owners = {u.get('issue') for u in units.values()}
    covered = set()
    for scenario in scenarios.values():
        refs = scenario.get('requirements')
        require(isinstance(refs, list) and bool(refs) and set(refs) <= set(requirements), 'unowned scenario requirement')
        covered.update(refs)
        layers = scenario.get('checks')
        require(isinstance(layers, list) and bool(layers) and len(layers) == len(set(layers)) and set(layers) <= {'unit', 'integration'} and 'unit' in layers,
                'invalid unit/integration checks')
        optional = scenario.get('optional_observations', [])
        require(isinstance(optional, list) and all(isinstance(v, str) for v in optional) and
                len(optional) == len(set(optional)) and set(optional) <= {'real_model', 'owner_smoke'},
                'invalid optional observations')
        checks = scenario.get('assertions')
        require(isinstance(checks, list) and bool(checks) and all(isinstance(v, str) and v for v in checks) and
                len(checks) == len(set(checks)), 'missing/duplicate scenario assertions')
        require(isinstance(scenario.get('expected'), str) and bool(scenario['expected']), 'missing outcome rubric')
        require(isinstance(scenario.get('family'), str) and bool(scenario['family']), 'missing goal family')
        require(type(scenario.get('critical')) is bool, 'critical must be a boolean')
    require(covered == set(requirements), 'requirement without a scenario')
    for req in requirements.values():
        require(type(req.get('owner_issue')) is int and req['owner_issue'] in owners, 'requirement has no declared owner')
        paths = req.get('production_paths')
        require(isinstance(paths, list) and bool(paths), 'requirement lacks production path')
        for rel in paths:
            require(isinstance(rel, str) and not Path(rel).is_absolute() and '..' not in Path(rel).parts,
                    'invalid production path')
            require((root / rel).is_file(), f'missing production path: {rel}')
    require((root / manifest['contract']).is_file(), 'missing canonical execution contract')
    root_plan = bounded_read(root / 'delivery-plan.yaml')
    require(not (root / 'src/personal_agent/delivery-plan.yaml').exists(), 'retired runtime plan mirror recreated')
    plan = load_json(root_plan)
    items = unique(plan['iterations'], 'id')
    order = plan['programs']['PRESENCE-01']['ordered_substeps']
    require(len(order) == len(set(order)), 'duplicate program substep')
    for ident, unit in units.items():
        require(ident in items and items[ident].get('issue') == unit['issue'], f'plan missing/wrong owning issue: {ident}')
        require(ident in order and items[ident].get('program') == 'PRESENCE-01', f'unreachable program child: {ident}')
        require(items[ident].get('activation_status') == 'parent-controlled', 'child must remain parent-controlled')
        require(order.index(ident) < order.index('PRESENCE-EVAL-01'), 'execution child stranded after final evaluation')
        for dependency in items[ident].get('depends_on', []):
            require(dependency in items, f'unknown dependency: {dependency}')
            if dependency in order:
                require(order.index(dependency) < order.index(ident), 'dependency order/cycle error')
    require('AGENCY-EVAL-01' in items['PRESENCE-EVAL-01'].get('depends_on', []), 'final Presence evaluation lacks agency dependency')
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-spec', action='store_true', required=True,
                        help='Check offline requirements and plan ownership, not outcomes')
    parser.parse_args(argv)
    try:
        check_spec()
    except (EvidenceError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f'Assistant execution specification failed: {exc}', file=sys.stderr)
        return 1
    print('Assistant execution specification valid; no product outcomes evaluated.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
