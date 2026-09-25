"""Offline spec tests, not model evaluation or product certification (#612)."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('assistant_execution_spec', ROOT / 'scripts/verify_assistant_execution.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class SpecificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = json.loads((ROOT / gate.MANIFEST).read_text())
        self.plan = json.loads((ROOT / 'delivery-plan.yaml').read_text())
        for name in [self.manifest['contract'], *{p for row in self.manifest['requirements'] for p in row['production_paths']}]:
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()

    def check(self):
        path = self.root / gate.MANIFEST
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.manifest))
        (self.root / 'delivery-plan.yaml').write_text(json.dumps(self.plan))
        return gate.check_spec(self.root)

    def test_unit_first_spec_needs_no_model_results(self):
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            result = self.check()
        self.assertNotIn('trials', result)
        self.assertNotIn('minimum_real_model_success_rate', result)
        self.assertTrue(all('unit' in row['checks'] for row in result['scenarios']))

    def test_optional_observations_can_be_unrun(self):
        for row in self.manifest['scenarios']:
            row['optional_observations'] = []
        self.check()

    def test_blanket_trial_or_score_gate_is_rejected(self):
        for key, value in [('trials', {'real_model': 3}), ('minimum_real_model_success_rate', .9)]:
            with self.subTest(key=key):
                self.manifest[key] = value
                with self.assertRaisesRegex(gate.EvidenceError, 'retired'):
                    self.check()
                self.manifest.pop(key)

    def test_routine_model_or_judge_cannot_be_enabled(self):
        for key in ['routine_model_requests', 'per_answer_judge']:
            with self.subTest(key=key):
                self.manifest['verification_policy'][key] = True
                with self.assertRaises(gate.EvidenceError):
                    self.check()
                self.manifest['verification_policy'][key] = False

    def test_optional_model_check_requires_opt_in_and_budget(self):
        original = copy.deepcopy(self.manifest['verification_policy']['model_checks'])
        for change in [{'mode': 'always'}, {'budget_required': False}]:
            self.manifest['verification_policy']['model_checks'] = {**original, **change}
            with self.assertRaises(gate.EvidenceError):
                self.check()

    def test_real_model_cannot_be_a_routine_check(self):
        self.manifest['scenarios'][0]['checks'].append('real_model')
        with self.assertRaises(gate.EvidenceError):
            self.check()

    def test_unknown_requirement_and_missing_assertions_are_rejected(self):
        row = self.manifest['scenarios'][0]
        old = copy.deepcopy(row)
        for change in [{'requirements': ['not-declared']}, {'assertions': []}]:
            row.clear(); row.update({**old, **change})
            with self.assertRaises(gate.EvidenceError):
                self.check()

    def test_lost_owner_and_production_path_are_rejected(self):
        row = self.manifest['requirements'][0]
        old = copy.deepcopy(row)
        for change in [{'owner_issue': -1}, {'production_paths': ['missing.py']}]:
            row.clear(); row.update({**old, **change})
            with self.assertRaises(gate.EvidenceError):
                self.check()

    def test_stranded_child_is_rejected(self):
        self.plan['programs']['PRESENCE-01']['ordered_substeps'].remove('AGENCY-CAP-01')
        with self.assertRaises(gate.EvidenceError):
            self.check()

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(gate.EvidenceError):
            gate.load_json(b'{"default":"unit-first","default":"always-live"}')

    def test_legacy_certificate_command_is_not_silent_success(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            gate.main(['--check-spec', '--evidence', 'old-report.json'])
        self.assertEqual(exc.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
