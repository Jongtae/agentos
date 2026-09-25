"""#601 gate infrastructure only: synthetic reports are NOT product evidence.

The tests deliberately construct fake green reports to exercise consistency
checks, then corrupt one load-bearing fact at a time. #608 must additionally
verify trusted CI/runner provenance before real product promotion.
"""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from scripts.verify_assistant_execution import (
    ROOT, MANIFEST, EvidenceError, artifact, check_evidence, check_spec, digest,
    junit_outcomes, load_json,
)
SOURCE = 'a' * 40
ARTIFACT = 'b' * 64

class EvidenceGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.path = self.folder / 'report.json'
        self.spec = check_spec()
        self.report = {
            'schema_version': 1,
            'manifest_sha256': digest((ROOT / MANIFEST).read_bytes()),
            'candidate': {'source_sha': SOURCE, 'artifact_sha256': ARTIFACT,
                          'policy_sha256': 'c' * 64, 'catalog_sha256': 'd' * 64,
                          'profile_config_sha256': {p: 'e' * 64 for p in self.spec['profiles']}},
            'unresolved_mandatory_findings': [], 'results': [],
        }
        self.xml = ET.Element('testsuite')
        for scenario in self.spec['scenarios']:
            for profile in self.spec['profiles']:
                for layer in scenario['layers']:
                    for trial in range(1, self.spec['trials'][layer] + 1):
                        name = f"{scenario['id']}:{profile}:{layer}:{trial}"
                        ET.SubElement(self.xml, 'testcase', classname='SyntheticGateTestOnly', name=name)
                        trace = {
                            'scenario': scenario['id'], 'profile': profile, 'layer': layer, 'trial': trial,
                            'source_sha': SOURCE, 'artifact_sha256': ARTIFACT, 'policy_sha256': 'c' * 64,
                            'catalog_sha256': 'd' * 64, 'config_sha256': 'e' * 64,
                            'assertions': {key: True for key in scenario['assertions']},
                            'observation_refs': ['synthetic-gate-unit-test-only'], 'violations': [],
                            'model_mode': 'live' if layer in ('real_model', 'owner_smoke') else 'fixture',
                            'scripted_model': False if layer in ('real_model', 'owner_smoke') else True,
                            'model_requested': 'synthetic-marker-not-real-evidence', 'model_reported': None,
                            'model_call_ref': 'synthetic-call', 'owner_confirmed': True,
                            'transport_mode': 'owner_client' if layer == 'owner_smoke' else 'actual_process',
                            'installed_artifact_sha256': ARTIFACT,
                        }
                        filename = name.replace(':', '_') + '.json'
                        desc = self.write_json(filename, trace)
                        self.report['results'].append(dict(scenario=scenario['id'], profile=profile, layer=layer,
                                                           trial=trial, outcome='pass',
                                                           junit_case=['SyntheticGateTestOnly', name], trace=desc))
        self.flush_xml()
    def write_json(self, name, value):
        data = (json.dumps(value, ensure_ascii=False, sort_keys=True) + '\n').encode()
        (self.folder / name).write_bytes(data)
        return {'path': name, 'sha256': digest(data)}
    def flush_xml(self):
        data = ET.tostring(self.xml, encoding='utf-8')
        (self.folder / 'results.xml').write_bytes(data)
        self.report['junit'] = {'path': 'results.xml', 'sha256': digest(data)}
    def row(self, layer='contract', scenario=None, trial=1):
        return next(r for r in self.report['results'] if r['layer'] == layer and r['trial'] == trial and
                    (scenario is None or r['scenario'] == scenario))
    def mutate_trace(self, row, mutate):
        trace = load_json((self.folder / row['trace']['path']).read_bytes())
        mutate(trace)
        row['trace'] = self.write_json(row['trace']['path'], trace)
    def check(self):
        self.write_json('report.json', self.report)
        check_evidence(self.path, SOURCE, ARTIFACT)
    def assert_rejected(self):
        with self.assertRaises(EvidenceError):
            self.check()
    def test_complete_synthetic_bundle_checks_consistency_only(self):
        self.check()
    def test_missing_required_case_is_rejected(self):
        self.report['results'].pop()
        self.assert_rejected()
    def test_missing_route_is_rejected(self):
        self.report['results'] = [r for r in self.report['results'] if r['profile'] != 'codex']
        self.assert_rejected()
    def test_duplicate_trial_is_rejected(self):
        self.report['results'].append(copy.deepcopy(self.report['results'][0]))
        self.assert_rejected()
    def test_stale_source_is_rejected(self):
        self.report['candidate']['source_sha'] = 'f' * 40
        self.assert_rejected()
    def test_stale_manifest_is_rejected(self):
        self.report['manifest_sha256'] = '0' * 64
        self.assert_rejected()
    def test_stale_installed_artifact_is_rejected(self):
        self.mutate_trace(self.row('owner_smoke'), lambda t: t.update(installed_artifact_sha256='0' * 64))
        self.assert_rejected()
    def test_trace_configuration_drift_is_rejected(self):
        self.mutate_trace(self.row(), lambda t: t.update(config_sha256='0' * 64))
        self.assert_rejected()
    def test_fixture_label_cannot_satisfy_real_model(self):
        self.mutate_trace(self.row('real_model'), lambda t: t.update(model_mode='fixture'))
        self.assert_rejected()
    def test_live_label_with_scripted_model_is_rejected(self):
        self.mutate_trace(self.row('real_model'), lambda t: t.update(scripted_model=True))
        self.assert_rejected()
    def test_fake_executor_cannot_satisfy_protocol(self):
        self.mutate_trace(self.row('protocol'), lambda t: t.update(transport_mode='fake_executor'))
        self.assert_rejected()
    def test_owner_confirmation_cannot_be_omitted(self):
        self.mutate_trace(self.row('owner_smoke'), lambda t: t.update(owner_confirmed=False))
        self.assert_rejected()
    def test_no_observation_is_not_goal_evidence(self):
        self.mutate_trace(self.row(), lambda t: t.update(observation_refs=[]))
        self.assert_rejected()
    def test_swallowed_assertion_cannot_stay_green(self):
        self.mutate_trace(self.row(), lambda t: t['assertions'].pop(next(iter(t['assertions']))))
        self.assert_rejected()
    def test_false_assertion_cannot_stay_green(self):
        self.mutate_trace(self.row(), lambda t: t['assertions'].update({next(iter(t['assertions'])): False}))
        self.assert_rejected()
    def test_truthy_string_is_not_an_assertion(self):
        self.mutate_trace(self.row(), lambda t: t['assertions'].update({next(iter(t['assertions'])): 'true'}))
        self.assert_rejected()
    def test_safety_violation_blocks_even_with_all_pass_labels(self):
        self.mutate_trace(self.row('real_model'), lambda t: t.update(violations=['private-egress']))
        self.assert_rejected()
    def test_junit_failure_cannot_be_labelled_pass(self):
        ET.SubElement(self.xml[0], 'failure')
        self.flush_xml()
        self.assert_rejected()
    def test_skip_and_xfail_cannot_satisfy_required_cell(self):
        ET.SubElement(self.xml[0], 'skipped', type='pytest.xfail')
        self.flush_xml()
        self.assert_rejected()
    def test_one_junit_case_cannot_prove_two_trials(self):
        self.report['results'][1]['junit_case'] = self.report['results'][0]['junit_case']
        self.assert_rejected()
    def test_tampered_artifact_bytes_are_rejected(self):
        (self.folder / self.row()['trace']['path']).write_text('{}')
        self.assert_rejected()
    def test_unresolved_mandatory_finding_blocks(self):
        self.report['unresolved_mandatory_findings'] = [605]
        self.assert_rejected()
    def set_model_failure(self, row):
        row['outcome'] = 'fail'
        case = next(c for c in self.xml if c.get('name') == row['junit_case'][1])
        ET.SubElement(case, 'failure')
        self.mutate_trace(row, lambda t: t['assertions'].update({next(iter(t['assertions'])): False}))
        self.flush_xml()
    def test_one_noncritical_model_failure_is_reported_not_best_of_three(self):
        self.set_model_failure(self.row('real_model', 'AX-S01'))
        self.check()
    def test_below_family_threshold_is_rejected(self):
        self.set_model_failure(self.row('real_model', 'AX-S01', 1))
        self.set_model_failure(self.row('real_model', 'AX-S01', 2))
        self.assert_rejected()
    def test_critical_failure_is_not_averaged_away(self):
        self.set_model_failure(self.row('real_model', 'AX-S06'))
        self.assert_rejected()
    def test_missing_repeated_trial_is_not_best_of_three(self):
        self.report['results'].remove(self.row('real_model', 'AX-S01', 3))
        self.assert_rejected()

class ArtifactAndSpecificationTests(unittest.TestCase):
    def test_current_spec_has_complete_ownership(self):
        spec = check_spec()
        self.assertEqual(len(spec['requirements']), 14)
        self.assertEqual(len(spec['scenarios']), 18)
    def test_duplicate_json_keys_and_nonfinite_numbers_are_rejected(self):
        for value in (b'{"a":1,"a":2}', b'{"a":NaN}'):
            with self.assertRaises(EvidenceError):
                load_json(value)
    def test_xml_entities_are_rejected(self):
        with self.assertRaises(EvidenceError):
            junit_outcomes(b'<!DOCTYPE t [<!ENTITY a "secret">]><testsuite/>')
    def test_path_escape_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            for name in ('../escape', '/etc/passwd'):
                with self.assertRaises(EvidenceError):
                    artifact(base, {'path': name, 'sha256': '0' * 64})
            (base / 'target').write_text('synthetic')
            (base / 'link').symlink_to(base / 'target')
            with self.assertRaises(EvidenceError):
                artifact(base, {'path': 'link', 'sha256': hashlib.sha256(b'synthetic').hexdigest()})
    def test_dropped_plan_dependency_fails_even_when_files_still_exist(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            spec = check_spec()
            names = {str(MANIFEST), spec['contract'], 'delivery-plan.yaml'}
            for req in spec['requirements']:
                names.update(req['production_paths'])
            for name in names:
                dst = base / name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, dst)
            check_spec(base)
            plan = json.loads((base / 'delivery-plan.yaml').read_text())
            item = next(i for i in plan['iterations'] if i['id'] == 'PRESENCE-EVAL-01')
            item['depends_on'].remove('AGENCY-EVAL-01')
            (base / 'delivery-plan.yaml').write_text(json.dumps(plan))
            with self.assertRaises(EvidenceError):
                check_spec(base)

if __name__ == '__main__':
    unittest.main()
