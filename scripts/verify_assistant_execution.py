#!/usr/bin/env python3
"""AGENCY #601: offline spec and evidence-consistency checks, NOT live certification.

The eventual #608 promotion runner must establish trusted artifact provenance.
This checker cannot authenticate arbitrary self-authored JUnit/trace files.
No provider, credential, owner data store or network is accessed here.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path('docs/evals/assistant-execution-v1.json')
LAYERS = {'contract', 'protocol', 'real_model', 'owner_smoke'}
MAX_BYTES = 10_000_000


class EvidenceError(ValueError):
    """A fail-closed specification or evidence mismatch."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_digest(value: object, size: int = 64) -> bool:
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{' + str(size) + '}', value) is not None


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


def artifact(directory: Path, descriptor: dict) -> bytes:
    require(isinstance(descriptor, dict), 'missing artifact descriptor')
    relative = descriptor.get('path')
    require(isinstance(relative, str) and bool(relative), 'missing artifact path')
    path = Path(relative)
    require(not path.is_absolute() and '..' not in path.parts, 'artifact path escapes evidence directory')
    base = directory.resolve()
    target = base / path
    require(target.resolve().is_relative_to(base), 'artifact path escapes evidence directory')
    require(all(not (base / Path(*path.parts[:i])).is_symlink() for i in range(1, len(path.parts) + 1)),
            'artifact symlinks are not allowed')
    data = bounded_read(target)
    require(is_digest(descriptor.get('sha256')) and descriptor['sha256'] == digest(data), 'artifact digest mismatch')
    return data


def check_spec(root: Path = ROOT) -> dict:
    manifest = load_json(bounded_read(root / MANIFEST))
    require(manifest.get('schema_version') == 1, 'unknown manifest version')
    profiles = manifest.get('profiles')
    require(isinstance(profiles, list) and bool(profiles) and
            all(isinstance(p, str) and p for p in profiles) and len(profiles) == len(set(profiles)), 'invalid profiles')
    trials = manifest.get('trials', {})
    require(set(trials) == LAYERS and all(type(v) is int and 1 <= v <= 10 for v in trials.values()), 'invalid layer trials')
    rate = manifest.get('minimum_real_model_success_rate')
    require(type(rate) in (float, int) and 0 < rate <= 1, 'invalid success threshold')
    requirements = unique(manifest.get('requirements'), 'id')
    scenarios = unique(manifest.get('scenarios'), 'id')
    units = unique(manifest.get('units'), 'id')
    owners = {u.get('issue') for u in units.values()}
    covered = set()
    for scenario in scenarios.values():
        refs = scenario.get('requirements')
        require(isinstance(refs, list) and bool(refs) and set(refs) <= set(requirements), 'unowned scenario requirement')
        covered.update(refs)
        layers = scenario.get('layers')
        require(isinstance(layers, list) and bool(layers) and len(layers) == len(set(layers)) and set(layers) <= LAYERS,
                'invalid scenario evidence layers')
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


def junit_outcomes(data: bytes) -> dict:
    require(b'<!DOCTYPE' not in data.upper() and b'<!ENTITY' not in data.upper(), 'DTD/entities are forbidden')
    tree = ET.fromstring(data)
    result = {}
    for case in tree.iter('testcase'):
        key = (case.get('classname', ''), case.get('name', ''))
        require(key[1] and key not in result, 'duplicate/unnamed JUnit case')
        state = 'skip' if case.find('skipped') is not None else ('fail' if
                case.find('failure') is not None or case.find('error') is not None else 'pass')
        result[key] = state
    require(bool(result), 'JUnit contains no test cases')
    return result


def check_evidence(report_path: Path, source_sha: str, artifact_sha256: str, root: Path = ROOT) -> None:
    manifest = check_spec(root)
    require(is_digest(source_sha, 40) and is_digest(artifact_sha256), 'independent candidate identifiers required')
    report = load_json(bounded_read(report_path))
    require(report.get('schema_version') == 1, 'unknown evidence version')
    candidate = report.get('candidate', {})
    require(candidate.get('source_sha') == source_sha and candidate.get('artifact_sha256') == artifact_sha256,
            'candidate source/artifact mismatch')
    require(report.get('manifest_sha256') == digest(bounded_read(root / MANIFEST)), 'stale specification digest')
    profiles = manifest['profiles']
    configs = candidate.get('profile_config_sha256', {})
    require(set(configs) == set(profiles) and all(is_digest(v) for v in configs.values()), 'missing profile configuration')
    require(is_digest(candidate.get('policy_sha256')) and is_digest(candidate.get('catalog_sha256')), 'missing policy/catalog identity')
    require(report.get('unresolved_mandatory_findings') == [], 'unresolved mandatory findings')
    outcomes = junit_outcomes(artifact(report_path.parent, report.get('junit')))
    specs = {s['id']: s for s in manifest['scenarios']}
    expected = {(s['id'], p, layer, trial) for s in specs.values() for p in profiles for layer in s['layers']
                for trial in range(1, manifest['trials'][layer] + 1)}
    rows = report.get('results')
    require(isinstance(rows, list), 'missing trial results')
    seen, used_junit = set(), set()
    rates, per_case = defaultdict(list), defaultdict(list)
    for row in rows:
        require(isinstance(row, dict), 'invalid trial row')
        key = (row.get('scenario'), row.get('profile'), row.get('layer'), row.get('trial'))
        require(type(key[3]) is int and key in expected and key not in seen, 'unexpected/duplicate trial')
        seen.add(key)
        scenario, profile, layer, trial = key
        case = row.get('junit_case')
        require(isinstance(case, list) and len(case) == 2 and all(isinstance(v, str) for v in case), 'invalid JUnit reference')
        case = tuple(case)
        require(case in outcomes and case not in used_junit, 'missing/reused JUnit case')
        used_junit.add(case)
        status = outcomes[case]
        require(status in ('pass', 'fail') and row.get('outcome') == status, 'skipped/xfail or JUnit outcome mismatch')
        receipt = load_json(artifact(report_path.parent, row.get('trace')))
        for field, value in zip(('scenario', 'profile', 'layer', 'trial'), key):
            require(receipt.get(field) == value, 'trace belongs to another trial')
        for field in ('source_sha', 'artifact_sha256', 'policy_sha256', 'catalog_sha256'):
            require(receipt.get(field) == candidate[field], f'stale trace {field}')
        require(receipt.get('config_sha256') == configs[profile], 'stale trace configuration')
        require(receipt.get('violations') == [], 'observed safety/truth violation')
        assertions = receipt.get('assertions', {})
        require(isinstance(assertions, dict) and set(assertions) == set(specs[scenario]['assertions']) and
                all(type(v) is bool for v in assertions.values()), 'missing/invalid trace assertions')
        passed = all(assertions.values())
        require((status == 'pass') == passed, 'trace assertions disagree with JUnit')
        require(isinstance(receipt.get('observation_refs'), list) and bool(receipt['observation_refs']) and
                all(isinstance(v, str) and v for v in receipt['observation_refs']), 'missing observation evidence')
        if layer in ('real_model', 'owner_smoke'):
            require(receipt.get('model_mode') == 'live' and receipt.get('scripted_model') is False,
                    'fixture cannot satisfy live-model evidence')
            require(isinstance(receipt.get('model_requested'), str) and bool(receipt['model_requested']) and
                    isinstance(receipt.get('model_call_ref'), str) and bool(receipt['model_call_ref']), 'missing model call identity')
            require('model_reported' in receipt and (receipt['model_reported'] is None or
                    isinstance(receipt['model_reported'], str)), 'observed model must be reported or explicitly unknown')
        if layer == 'protocol':
            require(receipt.get('transport_mode') in ('actual_process', 'actual_native_protocol'), 'fake executor is not protocol evidence')
        if layer == 'owner_smoke':
            require(receipt.get('transport_mode') == 'owner_client' and receipt.get('owner_confirmed') is True,
                    'missing real owner-client confirmation')
            require(receipt.get('installed_artifact_sha256') == artifact_sha256, 'stale installed artifact')
        if layer != 'real_model' or specs[scenario]['critical']:
            require(passed, 'mandatory regression/critical case failed')
        if layer == 'real_model':
            rates[(profile, specs[scenario]['family'])].append(passed)
            per_case[(profile, scenario)].append(passed)
    require(seen == expected, f'missing required trial cells: {len(expected - seen)}')
    for values in rates.values():
        require(sum(values) / len(values) >= manifest['minimum_real_model_success_rate'], 'real-model family/profile below threshold')
    require(all(any(values) for values in per_case.values()), 'required real-model case never succeeded')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check-spec', action='store_true')
    group.add_argument('--evidence', type=Path)
    parser.add_argument('--source-sha')
    parser.add_argument('--artifact-sha256')
    args = parser.parse_args()
    try:
        if args.check_spec:
            spec = check_spec()
            print(f"Specification consistent: {len(spec['requirements'])} requirements, {len(spec['scenarios'])} scenarios; no product execution claimed.")
        else:
            check_evidence(args.evidence, args.source_sha, args.artifact_sha256)
            print('Evidence consistency verified. Trusted producer/review/owner attestation must still be checked by the promotion runner; this is not a release certificate.')
        return 0
    except (EvidenceError, OSError, ValueError, TypeError, KeyError, ET.ParseError) as exc:
        print(f'Assistant execution gate failed: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
