"""Static evaluation/readiness checks, not an agent benchmark or live run."""
import json
import unittest
from collections import Counter
from pathlib import Path

from delivery_state_invariants import assert_declared_goal_shape, closed_out_programs
from personal_agent.delivery import DeliveryPlan

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

    def test_selected_goal_readiness_does_not_enable_execution(self):
        # USE-01 remains preserved historical usefulness work. The top-level
        # goal itself moves over time and is absent after a closeout, so this
        # checks the rule in both shapes: goal-readiness never executes, and
        # a closeout never executes either.
        plan = json.loads((ROOT / "delivery-plan.yaml").read_text(encoding="utf-8"))
        shape = assert_declared_goal_shape(self, plan)
        declared = plan["next_goal"]["id"]
        documented = plan["history"]["documented_completed_iterations"]
        # The activation-governance dependency rule is a governance rule, not
        # a transient fact: without it a program can be flipped to active with
        # no governance merged. Generalised from the original
        # `== ["GOV-PA1-01"]`, which pinned the rule to whichever program
        # happened to be declared, and applied to the closed-out program too
        # so a closeout cannot erase the requirement.
        if shape == "goal-ready":
            subjects = [declared]
            self.assertNotIn(declared, documented)
        else:
            self.assertIsNone(declared)
            subjects = closed_out_programs(plan)
            self.assertTrue(subjects)
            for name in subjects:
                self.assertIn(name, documented)
        for name in subjects:
            selected = next(item for item in plan["iterations"] if item["id"] == name)
            self.assertIsInstance(selected["issue"], int)
            self.assertIn(selected["activation_status"],
                          {"owner-activated-goal-ready", "complete-on-merge"})
            if shape == "goal-ready":
                self.assertEqual(selected["activation_status"],
                                 "owner-activated-goal-ready")
            self.assertTrue(selected.get("depends_on"), selected)
            for dependency in selected["depends_on"]:
                self.assertIn(dependency, documented)
        # Goal-readiness must not execute, whichever program is declared.
        self.assertNotEqual(plan["next_goal"]["status"], "active")
        self.assertIn("GOV-PA1-01", plan["history"]["documented_completed_iterations"])
        self.assertIn("USE-01", plan["history"]["documented_completed_iterations"])
        use01 = next(item for item in plan["iterations"] if item["id"] == "USE-01")
        self.assertEqual(use01["issue"], 358)
        controller_plan = DeliveryPlan(ROOT / "delivery-plan.yaml")
        self.assertIsNone(controller_plan.select({}))
        self.assertIsNone(controller_plan.select({"active": "EPIC-PA1", "status": "running"}))
        for item in plan["iterations"]:
            if item.get("issue") in set(range(335, 347)) | {359, 360}:
                self.assertNotIn(item.get("activation_status"), {"active", "owner-activated-goal-ready"})
        for relative in (
            "docs/owner-control-contract.en.md",
            "docs/default-agent-usefulness.en.md",
            "docs/use-01-goal-readiness.en.md",
        ):
            self.assertTrue((ROOT / relative).is_file())

    def test_live_quality_is_separate_from_simulated_development(self):
        for name in ("default-agent-usefulness.en.md", "use-01-goal-readiness.en.md"):
            text = (ROOT / "docs" / name).read_text(encoding="utf-8")
            self.assertIn("pending_owner_operation", text)
            self.assertIn("20 of 24", text)
            self.assertIn("before", text)
        # This historical declaration must not gain extra claimed evidence as
        # a side effect of adding the new plan entries.
        plan = json.loads((ROOT / "delivery-plan.yaml").read_text(encoding="utf-8"))
        historical = next(item for item in plan["iterations"] if item["id"] == "MP1-I-03")
        self.assertEqual(historical["automated_evidence"], ["python3 -m pytest -q tests"])


if __name__ == "__main__":
    unittest.main()
