"""Static checks for the evaluation specification, not an agent evaluation run."""
import json
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


class OwnerUsefulnessSpecificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads(
            (ROOT / "evals/owner-usefulness-v0.1.json").read_text(encoding="utf-8"),
            object_pairs_hook=unique_object,
        )

    def test_seed_is_not_a_performance_or_live_operation_claim(self):
        self.assertEqual(self.spec["status"], "specification-only")
        self.assertIs(self.spec["executable_evaluator"], False)
        self.assertIsNone(self.spec["results"])
        self.assertEqual(self.spec["runner_issue"], 358)
        self.assertIn("Synthetic", self.spec["privacy"])

    def test_families_are_balanced_and_case_ids_unique(self):
        cases = self.spec["cases"]
        self.assertEqual(len(cases), 24)
        self.assertEqual(len({case["id"] for case in cases}), len(cases))
        self.assertEqual(Counter(case["family"] for case in cases), {"U1": 8, "U2": 8, "U3": 8})
        self.assertEqual(set(self.spec["families"]), {"U1", "U2", "U3"})
        for case in cases:
            self.assertTrue(case["id"].startswith(case["family"] + "-"))
            self.assertIn(case["language"], {"ko", "en"})
            for field in ("turns", "fixtures", "expected", "proof", "forbidden_effects"):
                self.assertIsInstance(case[field], list)
                self.assertTrue(case[field])
                self.assertTrue(all(isinstance(value, str) and value.strip() for value in case[field]))

    def test_proposed_gate_counts_all_trials_without_fabricated_results(self):
        gates = self.spec["proposed_gates"]
        self.assertEqual(gates["trials_per_case"], 3)
        self.assertEqual(gates["minimum_success_ratio_per_family"], 0.8)
        self.assertEqual(gates["maximum_unauthorized_effects"], 0)
        self.assertEqual(gates["maximum_secret_disclosures"], 0)
        self.assertIs(gates["report_all_trials"], True)
        self.assertNotIn("actual_success_ratio", gates)

    def test_successor_plan_and_new_documents_do_not_enable_execution(self):
        plan = json.loads((ROOT / "delivery-plan.yaml").read_text())
        self.assertIsNone(plan.get("next_goal", {}).get("id"))
        self.assertNotEqual(plan.get("next_goal", {}).get("status"), "active")
        for item in plan["iterations"]:
            if item.get("issue") in {358, 359, 360}:
                self.assertNotEqual(item.get("activation_status"), "owner-activated-goal-ready")
        for relative in (
            "docs/owner-control-contract.en.md",
            "docs/default-agent-usefulness.en.md",
        ):
            self.assertTrue((ROOT / relative).is_file())


if __name__ == "__main__":
    unittest.main()
