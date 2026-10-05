"""Bounded #1032 transition fixture plus enduring live-plan invariants."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BEFORE = ROOT / "tests" / "fixtures" / "governance" / "plan-after-upstream-activation-1029.json"
AFTER = ROOT / "tests" / "fixtures" / "governance" / "plan-after-upstream-transition-1032.json"


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
    "upstream_transition_invariants", ROOT / "tests" / "delivery_state_invariants.py"
)
assert _spec is not None and _spec.loader is not None
invariants = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(invariants)


class UpstreamTransition1032Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = read_plan(BEFORE)
        cls.after = read_plan(AFTER)

    def test_unrelated_plan_state_is_preserved(self):
        changed = {"iterations", "programs", "history", "next_goal"}
        self.assertEqual(set(self.before), set(self.after))
        for key in set(self.before) - changed:
            with self.subTest(key=key):
                self.assertEqual(self.before[key], self.after[key])

        old_history = self.before["history"]
        new_history = self.after["history"]
        self.assertEqual(set(old_history), set(new_history))
        for key, old_value in old_history.items():
            expected = old_value
            if key == "documented_completed_iterations":
                expected = old_value + ["GOV-UPSTREAM-NEXT-01"]
            with self.subTest(history=key):
                self.assertEqual(new_history[key], expected)

    def test_after_fixture_is_the_exact_reviewed_git_blob(self):
        raw = AFTER.read_bytes()
        digest = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        self.assertEqual(digest, "d1bb021a65d9cc9c40e8516bde07a1814a846b8f")

    def test_only_transition_iteration_is_appended(self):
        old_items = self.before["iterations"]
        new_items = self.after["iterations"]
        self.assertEqual(new_items[:-1], old_items)
        self.assertEqual(new_items[-1]["id"], "GOV-UPSTREAM-NEXT-01")
        self.assertEqual(new_items[-1]["issue"], 1032)
        self.assertNotIn("depends_on", new_items[-1])
        ids = [row["id"] for row in new_items]
        self.assertEqual(len(ids), len(set(ids)))

    def test_only_upstream_program_selection_changes(self):
        self.assertEqual(set(self.before["programs"]), set(self.after["programs"]))
        for name, old_program in self.before["programs"].items():
            new_program = self.after["programs"][name]
            if name != "UPSTREAM-01":
                with self.subTest(program=name):
                    self.assertEqual(new_program, old_program)
                continue

            allowed = {"active_substeps", "current_selection"}
            self.assertEqual(
                {key: value for key, value in old_program.items() if key not in allowed},
                {key: value for key, value in new_program.items() if key not in allowed},
            )
            self.assertEqual(new_program["active_substeps"], ["UPSTREAM-UPDATE-01"])
            self.assertEqual(new_program["current_selection"]["issue"], 1032)
            self.assertEqual(new_program["current_selection"]["substep"], "UPSTREAM-UPDATE-01")
            self.assertIn("fa468e6d04559b10e3d3da43fb7a1c8e6401fe3d", new_program["current_selection"]["prerequisite_evidence"])

    def test_update_child_is_the_only_declared_active_substep(self):
        goal = self.after["next_goal"]
        self.assertEqual(goal["id"], "UPSTREAM-01")
        self.assertEqual(goal["status"], "owner-activated-goal-ready")
        self.assertEqual(goal["current_substep"], "UPSTREAM-UPDATE-01")
        self.assertEqual(goal["current_issue"], 1024)
        self.assertEqual(invariants.assert_declared_goal_shape(self, plan=self.after), "goal-ready")
        self.assertEqual(
            invariants.assert_active_substeps_are_legitimate(self, self.after, "UPSTREAM-01"),
            "UPSTREAM-UPDATE-01",
        )

    def test_order_authority_and_secretary_resume_point_are_unchanged(self):
        old_upstream = self.before["programs"]["UPSTREAM-01"]
        new_upstream = self.after["programs"]["UPSTREAM-01"]
        for key in ("ordered_substeps", "concurrency", "authority", "non_goals", "completion_rule", "resume_condition"):
            with self.subTest(key=key):
                self.assertEqual(new_upstream[key], old_upstream[key])

        self.assertEqual(
            self.after["programs"]["SECRETARY-01"],
            self.before["programs"]["SECRETARY-01"],
        )
        invariants.assert_pause_survives_redeclaration(self, self.after, "SECRETARY-01")

    def test_live_plan_obeys_enduring_resting_state_invariants(self):
        current = read_plan(ROOT / "delivery-plan.yaml")
        shape = invariants.assert_declared_goal_shape(self, plan=current)
        if shape == "goal-ready":
            name = current["next_goal"]["id"]
            invariants.assert_active_substeps_are_legitimate(self, current, name)
            if name == "UPSTREAM-01":
                program = current["programs"][name]
                selection = program.get("current_selection")
                self.assertIsNotNone(selection)
                self.assertEqual(
                    current["next_goal"]["current_substep"],
                    selection["substep"],
                )
                self.assertEqual(program["active_substeps"], [selection["substep"]])
                selected = next(
                    row for row in current["iterations"] if row["id"] == selection["substep"]
                )
                self.assertEqual(current["next_goal"]["current_issue"], selected["issue"])
        else:
            self.assertIsNone(current["next_goal"]["id"])


if __name__ == "__main__":
    unittest.main()
