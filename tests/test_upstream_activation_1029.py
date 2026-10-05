"""Bounded #1029 preservation fixture plus enduring live-plan invariants."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tests" / "fixtures" / "governance" / "plan-after-delivery-refresh-1021.json"
AFTER = ROOT / "tests" / "fixtures" / "governance" / "plan-after-upstream-activation-1029.json"


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_plan(path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


_spec = importlib.util.spec_from_file_location(
    "upstream_activation_invariants", ROOT / "tests" / "delivery_state_invariants.py"
)
assert _spec is not None and _spec.loader is not None
invariants = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(invariants)


class UpstreamActivation1029Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = read_plan(BASELINE)
        cls.after = read_plan(AFTER)
        cls.before_items = {row["id"]: row for row in cls.before["iterations"]}
        cls.items = {row["id"]: row for row in cls.after["iterations"]}

    def test_unrelated_root_and_history_state_is_preserved(self):
        changed = {"iterations", "programs", "history", "next_goal"}
        self.assertEqual(set(self.before), set(self.after))
        for key in set(self.before) - changed:
            with self.subTest(key=key):
                self.assertEqual(self.before[key], self.after[key])

        old_history = self.before["history"]
        new_history = self.after["history"]
        self.assertEqual(set(old_history), set(new_history))
        for key in old_history:
            expected = old_history[key]
            if key == "documented_completed_iterations":
                expected = expected + ["GOV-UPSTREAM-ACT-01"]
            with self.subTest(history=key):
                self.assertEqual(new_history[key], expected)

    def test_after_fixture_is_the_exact_reviewed_git_blob(self):
        import hashlib

        raw = AFTER.read_bytes()
        digest = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        self.assertEqual(digest, "0cdf0f9674349d9a9e810ec3d8627ba73691b046")

    def test_only_secretary_changes_and_upstream_iterations_are_appended(self):
        appended = [
            "GOV-UPSTREAM-ACT-01",
            "UPSTREAM-01",
            "UPSTREAM-MAP-01",
            "UPSTREAM-UPDATE-01",
            "UPSTREAM-RUNTIME-01",
            "UPSTREAM-KNOWLEDGE-01",
            "UPSTREAM-CONTRIB-01",
        ]
        old_ids = [row["id"] for row in self.before["iterations"]]
        new_ids = [row["id"] for row in self.after["iterations"]]
        self.assertEqual(new_ids, old_ids + appended)
        self.assertEqual(len(new_ids), len(set(new_ids)))

        for old in self.before["iterations"]:
            new = self.items[old["id"]]
            allowed = {"activation_status", "summary"} if old["id"] == "SECRETARY-01" else set()
            with self.subTest(iteration=old["id"]):
                self.assertEqual(
                    {key: value for key, value in old.items() if key not in allowed},
                    {key: value for key, value in new.items() if key not in allowed},
                )

        self.assertEqual(self.items["SECRETARY-01"]["activation_status"], "owner-paused")
        self.assertEqual(self.items["UPSTREAM-01"]["activation_status"], "owner-activated-goal-ready")

    def test_prior_programs_are_preserved_except_the_interrupted_secretary(self):
        self.assertEqual(set(self.after["programs"]), set(self.before["programs"]) | {"UPSTREAM-01"})
        allowed = {
            "status",
            "active_substeps",
            "paused_by",
            "owner_amendments",
            "resume_condition",
            "current_delivery",
            "pause_history",
            "reactivated_by",
            "reactivation_history",
        }
        for name, old in self.before["programs"].items():
            new = self.after["programs"][name]
            if name != "SECRETARY-01":
                with self.subTest(program=name):
                    self.assertEqual(new, old)
                continue
            self.assertEqual(
                {key: value for key, value in old.items() if key not in allowed},
                {key: value for key, value in new.items() if key not in allowed},
            )
            self.assertEqual(new["owner_amendments"][:-1], old["owner_amendments"])
            self.assertEqual(new["owner_amendments"][-1]["issue"], 1029)
            self.assertEqual(new["pause_history"], [old["paused_by"]])
            self.assertEqual(new["reactivation_history"], [old["reactivated_by"]])
            self.assertNotIn("reactivated_by", new)

    def test_upstream_is_the_only_declared_and_armed_program(self):
        goal = self.after["next_goal"]
        self.assertEqual(goal["id"], "UPSTREAM-01")
        self.assertEqual(goal["status"], "owner-activated-goal-ready")
        self.assertEqual(goal["current_substep"], "UPSTREAM-MAP-01")
        self.assertEqual(goal["current_issue"], 1023)
        self.assertEqual(invariants.assert_declared_goal_shape(self, plan=self.after), "goal-ready")
        self.assertEqual(
            invariants.assert_active_substeps_are_legitimate(self, self.after, "UPSTREAM-01"),
            "UPSTREAM-MAP-01",
        )

    def test_child_order_and_issue_declared_prerequisites_are_explicit(self):
        order = [
            "UPSTREAM-MAP-01",
            "UPSTREAM-UPDATE-01",
            "UPSTREAM-RUNTIME-01",
            "UPSTREAM-KNOWLEDGE-01",
            "UPSTREAM-CONTRIB-01",
        ]
        parent = self.after["programs"]["UPSTREAM-01"]
        self.assertEqual(parent["ordered_substeps"], order)
        self.assertEqual(parent["concurrency"]["max_open_children"], 1)
        self.assertEqual(self.items["UPSTREAM-MAP-01"]["depends_on"], ["GOV-UPSTREAM-ACT-01"])
        for child in order[1:]:
            with self.subTest(child=child):
                self.assertEqual(self.items[child]["depends_on"], ["UPSTREAM-MAP-01"])
                self.assertEqual(self.items[child]["activation_status"], "parent-controlled")
        self.assertIn("#1024", self.items["UPSTREAM-RUNTIME-01"]["coordination"])
        self.assertIn("#1024", self.items["UPSTREAM-KNOWLEDGE-01"]["coordination"])
        self.assertIn("#1024, #1025, #1026", self.items["UPSTREAM-CONTRIB-01"]["finding_gate"])

    def test_secretary_resume_point_is_preserved_without_completion(self):
        old = self.before["programs"]["SECRETARY-01"]
        new = self.after["programs"]["SECRETARY-01"]
        self.assertEqual(new["status"], "owner-paused")
        self.assertEqual(new["active_substeps"], [])
        self.assertEqual(new["paused_by"]["issue"], 1029)
        for key in ("governance_issue", "implementation_issue", "phase", "delivery_contract", "remaining_order"):
            with self.subTest(key=key):
                self.assertEqual(new["current_delivery"][key], old["current_delivery"][key])
        for item in new["current_delivery"]["remaining_order"]:
            self.assertNotIn(item, self.after["history"]["documented_completed_iterations"])
        invariants.assert_pause_survives_redeclaration(self, self.after, "SECRETARY-01")

    def test_live_plan_obeys_enduring_resting_state_invariants(self):
        current = read_plan(ROOT / "delivery-plan.yaml")
        shape = invariants.assert_declared_goal_shape(self, plan=current)
        if shape == "goal-ready":
            name = current["next_goal"]["id"]
            invariants.assert_active_substeps_are_legitimate(self, current, name)
        else:
            self.assertIsNone(current["next_goal"]["id"])


if __name__ == "__main__":
    unittest.main()
