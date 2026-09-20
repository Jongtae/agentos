"""Non-executing WEB-ADMIN-01 readiness regressions (issue #379)."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WebManagementReadinessTests(unittest.TestCase):
    def test_mirrored_contract_is_ready_but_not_selected_or_completed(self):
        source = (ROOT / 'delivery-plan.yaml').read_bytes()
        self.assertEqual(source, (ROOT / 'src/personal_agent/delivery-plan.yaml').read_bytes())
        plan = json.loads(source)
        entries = [item for item in plan['iterations'] if item['id'] == 'WEB-ADMIN-01']
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry['issue'], 382)
        self.assertEqual(entry['activation_status'], 'parent-controlled')
        self.assertEqual(entry['contract'], 'web-management-contract.en.md')
        self.assertEqual(set(entry['depends_on']), {'GOV-USE-01', 'DOGFOOD-01', 'PA1-FDN-01'})
        self.assertEqual(entry['program'], 'EPIC-PA1')
        self.assertEqual(entry['parallel_group'], 'pa1-wave-1')
        completed = plan['history']['documented_completed_iterations']
        self.assertTrue({'GOV-USE-01', 'DOGFOOD-01'}.issubset(completed))
        self.assertNotIn('PA1-FDN-01', completed)
        self.assertNotIn('WEB-ADMIN-01', completed)
        self.assertNotEqual(plan['next_goal']['status'], 'active')
        self.assertEqual(plan['next_goal']['id'], 'EPIC-PA1')
        self.assertNotEqual(plan['next_goal']['id'], 'WEB-ADMIN-01')
        self.assertTrue((ROOT / 'docs' / entry['contract']).is_file())

    def test_historical_top02_validation_is_not_weakened(self):
        plan = json.loads((ROOT / 'delivery-plan.yaml').read_text())
        entry = next(item for item in plan['iterations'] if item['id'] == 'TOP-02')
        self.assertEqual(entry['tests'], [
            'python3 -m pytest -q tests',
            'python3 -m unittest discover -s tests -q',
        ])

    def test_prompt_checks_existing_readiness_before_activation(self):
        prompt = (ROOT / 'docs/design/utility-v1/CODEX_PROMPT.txt').read_text()
        self.assertIn('READINESS AND ACTIVATION GATE', prompt)
        self.assertIn('dependency-satisfied goal-ready record in both', prompt)
        self.assertIn('Do not infer activation from this document', prompt)
        self.assertIn('Do not continue into W1-W3 in that same preparation invocation', prompt)
        self.assertIn('Do not execute #381 or other successor goals', prompt)


if __name__ == '__main__':
    unittest.main()
