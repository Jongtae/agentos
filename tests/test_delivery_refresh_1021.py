"""Bounded #1021 governance regression; historical fixtures are not a scheduler.

The before/after pair pins this amendment's preservation evidence without
freezing every future delivery-plan change to the 2026-10-06 work queue.
The live root still passes the repository's existing state/heartbeat contract.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "governance"


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_plan(path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


# Use the shared real-controller assertions, not a second selector model.
_spec = importlib.util.spec_from_file_location(
    "delivery_refresh_invariants", ROOT / "tests" / "delivery_state_invariants.py"
)
assert _spec is not None and _spec.loader is not None
invariants = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(invariants)


class DeliveryRefresh1021Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before_path = FIXTURES / "plan-before-delivery-refresh-1021.json"
        cls.after_path = FIXTURES / "plan-after-delivery-refresh-1021.json"
        cls.before = read_plan(cls.before_path)
        cls.after = read_plan(cls.after_path)
        cls.items = {row["id"]: row for row in cls.after["iterations"]}

    def test_baseline_is_the_exact_reviewed_git_blob(self):
        raw = self.before_path.read_bytes()
        digest = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        self.assertEqual(digest, "c5b0b3aa03896796083aa4c9973d3e591aafac5f")

    def test_root_metadata_and_all_unrelated_history_are_preserved(self):
        changed = {"iterations", "programs", "history", "next_goal"}
        self.assertEqual(set(self.before), set(self.after))
        for key in set(self.before) - changed:
            with self.subTest(key=key):
                self.assertEqual(self.before[key], self.after[key])
        old_history = self.before["history"]
        new_history = self.after["history"]
        for key in old_history:
            with self.subTest(history=key):
                expected = old_history[key]
                if key == "documented_completed_iterations":
                    expected = expected + ["GOV-DELIVERY-06"]
                self.assertEqual(new_history[key], expected)
        self.assertEqual(set(new_history), set(old_history))

    def test_only_four_existing_iterations_change_and_two_are_appended(self):
        allowed = {
            "SECRETARY-01": {"summary"},
            "SEC-EVAL-01": {"summary", "depends_on"},
            "SEC-A2A-01": {"summary", "depends_on"},
            "OWNER-MODEL-01": {
                "milestone", "activation_status", "program", "depends_on",
                "delivery_contract", "selected_phase", "selected_by",
                "reuse_pull_requests", "tests", "owns",
                "independent_review_required", "summary",
            },
        }
        old_ids = [i["id"] for i in self.before["iterations"]]
        new_ids = [i["id"] for i in self.after["iterations"]]
        self.assertEqual(new_ids, old_ids + ["GOV-DELIVERY-06", "OSS-MEMORY-01"])
        self.assertEqual(len(new_ids), len(set(new_ids)))
        for old in self.before["iterations"]:
            new = self.items[old["id"]]
            permitted = allowed.get(old["id"], set())
            with self.subTest(iteration=old["id"]):
                self.assertEqual(
                    {k: v for k, v in old.items() if k not in permitted},
                    {k: v for k, v in new.items() if k not in permitted},
                )

    def test_prior_program_records_are_not_rewritten(self):
        self.assertEqual(set(self.before["programs"]), set(self.after["programs"]))
        for name, old in self.before["programs"].items():
            new = self.after["programs"][name]
            if name != "SECRETARY-01":
                with self.subTest(program=name):
                    self.assertEqual(new, old)
                continue
            changed = {
                "ordered_substeps", "active_substeps", "owner_amendments",
                "owner_directed_followups_rule", "current_delivery",
            }
            self.assertEqual(
                {k: v for k, v in old.items() if k not in changed},
                {k: v for k, v in new.items() if k not in changed},
            )
            self.assertEqual(new["owner_amendments"][:-1], old["owner_amendments"])
            self.assertEqual(new["owner_amendments"][-1]["issue"], 1021)
            self.assertTrue(new["owner_directed_followups_rule"].startswith(old["owner_directed_followups_rule"]))

    def test_amendment_selects_only_remaining_phase_three_under_its_parent(self):
        goal = self.after["next_goal"]
        self.assertEqual(goal["id"], "SECRETARY-01")
        self.assertEqual(goal["status"], "owner-activated-goal-ready")
        self.assertEqual(goal["current_substep"], "OWNER-MODEL-01")
        self.assertEqual(goal["current_issue"], 794)
        selected = self.items[goal["current_substep"]]
        self.assertEqual(selected["issue"], 794)
        self.assertEqual(selected["program"], goal["id"])
        self.assertEqual(selected["activation_status"], "parent-controlled")
        self.assertEqual(selected["selected_phase"], 3)
        self.assertEqual(selected["selected_by"]["issue"], 1021)
        self.assertEqual(selected["reuse_pull_requests"], [886, 896, 972])
        self.assertTrue(selected["independent_review_required"])
        self.assertEqual(
            invariants.assert_active_substeps_are_legitimate(self, self.after, goal["id"]),
            "OWNER-MODEL-01",
        )
        self.assertTrue((ROOT / selected["delivery_contract"]).is_file())

    def test_operating_closeout_and_track_a_cannot_be_skipped(self):
        parent = self.after["programs"]["SECRETARY-01"]
        order = ["OWNER-MODEL-01", "SEC-EVAL-01", "OSS-MEMORY-01", "SEC-A2A-01"]
        self.assertEqual(parent["ordered_substeps"][-4:], order)
        self.assertEqual(parent["current_delivery"]["remaining_order"], order)
        self.assertIn("OWNER-MODEL-01", self.items["SEC-EVAL-01"]["depends_on"])
        gate = self.items["OSS-MEMORY-01"]
        self.assertEqual(gate["activation_status"], "reserved")
        self.assertIsNone(gate.get("issue"))
        self.assertEqual(gate["depends_on"], ["OWNER-MODEL-01", "SEC-EVAL-01"])
        self.assertEqual(
            set(self.items["SEC-A2A-01"]["depends_on"]),
            {"SEC-EVAL-01", "OWNER-MODEL-01", "OSS-MEMORY-01"},
        )
        completed = self.after["history"]["documented_completed_iterations"]
        for name in order:
            self.assertNotIn(name, completed)
        self.assertEqual(parent["completion_rule"], self.before["programs"]["SECRETARY-01"]["completion_rule"])
        self.assertEqual(parent["probes"], self.before["programs"]["SECRETARY-01"]["probes"])

    def test_amendment_keeps_the_actual_heartbeat_paused(self):
        self.assertEqual(invariants.assert_declared_goal_shape(self, plan=self.after), "goal-ready")
        # The shared assertion runs the real DeliveryController and checks
        # that no external command is issued, not merely a string status.

    def test_live_plan_still_obeys_the_shared_resting_state_contract(self):
        current = read_plan(ROOT / "delivery-plan.yaml")
        shape = invariants.assert_declared_goal_shape(self, plan=current)
        if shape == "goal-ready":
            name = current["next_goal"]["id"]
            invariants.assert_active_substeps_are_legitimate(self, current, name)
        else:
            self.assertIsNone(current["next_goal"]["id"])


if __name__ == "__main__":
    unittest.main()
