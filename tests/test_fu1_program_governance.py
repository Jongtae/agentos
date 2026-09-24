"""Governance regressions for the EPIC-FU1 / #501 program record.

These tests prove only repository orchestration metadata recorded by
GOV-FU1-01 / #502. They do not activate a heartbeat, run a substep, use
credentials or exercise providers. The generic top-level invariants live in
``delivery_state_invariants``; this file pins what is specific to EPIC-FU1 so
the program block does not ship without regression coverage.
"""
import json
import unittest

from personal_agent.delivery import DeliveryPlan

from delivery_state_invariants import (
    CLOSED_ON_MERGE,
    CLOSED_OUT,
    GOAL_READY,
    PAUSED,
    assert_activation_record,
    assert_active_substeps_are_legitimate,
    assert_declared_goal_shape,
    load_plan,
    plan_file,
)

PROGRAM = "EPIC-FU1"
ORDER = ["FU1-474", "FU1-473", "FU1-DEC-01", "FU1-475", "FU1-482"]
ISSUES = {"FU1-474": 474, "FU1-473": 473, "FU1-DEC-01": 521, "FU1-475": 475, "FU1-482": 482}


class Fu1ProgramGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.plan = load_plan()
        self.items = {item["id"]: item for item in self.plan["iterations"]}
        self.program = self.plan["programs"][PROGRAM]

    def test_program_is_finite_ordered_and_sequential(self):
        self.assertEqual(self.program["issue"], 501)
        self.assertEqual(self.items[PROGRAM]["issue"], 501)
        self.assertEqual(self.items[PROGRAM]["kind"], "program-governance")
        self.assertEqual(self.items[PROGRAM]["depends_on"], ["GOV-FU1-01"])
        self.assertEqual(self.items["GOV-FU1-01"]["issue"], 502)
        self.assertEqual(self.items["GOV-FU1-01"]["activation_status"], CLOSED_ON_MERGE)
        self.assertEqual(self.program["ordered_substeps"], ORDER)
        self.assertEqual(self.program["concurrency"]["max_open_children"], 1)
        previous = "GOV-FU1-01"
        for substep in ORDER:
            with self.subTest(substep=substep):
                item = self.items[substep]
                self.assertEqual(item["issue"], ISSUES[substep])
                self.assertEqual(item["program"], PROGRAM)
                # A child can never self-activate.
                self.assertEqual(item["activation_status"], "parent-controlled")
                # Strictly sequential: each substep depends on exactly its
                # predecessor, because they share conversation routing.
                self.assertEqual(item["depends_on"], [previous])
                self.assertTrue(item["owns"])
                self.assertTrue(all(path.startswith(("src/personal_agent/", "tests/"))
                                    for path in item["owns"]), item["owns"])
                previous = substep
        assert_active_substeps_are_legitimate(self, self.plan, PROGRAM)

    def test_program_role_is_backed_by_an_owner_activation_record(self):
        status = self.program["status"]
        self.assertIn(status, {GOAL_READY, CLOSED_OUT, PAUSED})
        record = self.program.get("activated_by")
        assert_activation_record(self, f"{PROGRAM} activated_by", record)
        self.assertEqual(record["issue"], 502)
        completed = self.plan["history"]["documented_completed_iterations"]
        self.assertIn("GOV-FU1-01", completed)
        shape = assert_declared_goal_shape(self, self.plan)
        if status == GOAL_READY:
            self.assertEqual(shape, "goal-ready")
            self.assertEqual(self.plan["next_goal"]["id"], PROGRAM)
            self.assertEqual(self.items[PROGRAM]["activation_status"], GOAL_READY)
            self.assertNotIn(PROGRAM, completed)
            # The declared action names the first substep and forbids
            # successor selection and live operation.
            action = self.plan["next_goal"]["action"]
            self.assertIn("FU1-474", action)
            self.assertIn("one substep at a time", action)
            self.assertIn("Do not select any unlisted successor", action)
            self.assertIn("live credentials", action)
        elif status == CLOSED_OUT:
            self.assertNotEqual(self.plan["next_goal"]["id"], PROGRAM)
            self.assertIn(PROGRAM, completed)
        else:
            self.assertEqual(status, PAUSED)
            self.assertNotEqual(self.plan["next_goal"]["id"], PROGRAM)
            self.assertNotIn(PROGRAM, completed)
            self.assertEqual(self.program["paused_by"]["issue"], 523)
            self.assertTrue(self.program["resume_condition"])

    def test_selection_requires_active_transition_and_governance_dependency(self):
        if self.program["status"] != GOAL_READY:
            self.skipTest("EPIC-FU1 is closed out; completion selectability is covered generically")
        with plan_file(self.plan) as path:
            self.assertIsNone(DeliveryPlan(path).select({}))
        altered = json.loads(json.dumps(self.plan))
        altered["next_goal"]["status"] = "active"  # Test fixture only, never repository activation.
        with plan_file(altered) as path:
            self.assertEqual(DeliveryPlan(path).select({})["id"], PROGRAM)
        withheld = json.loads(json.dumps(altered))
        withheld["history"]["documented_completed_iterations"].remove("GOV-FU1-01")
        with plan_file(withheld) as path:
            self.assertIsNone(DeliveryPlan(path).select({}))

    def test_authority_non_goals_and_review_are_recorded(self):
        authority = self.program["authority"]
        for phrase in ("may not add connectors, OAuth scopes, endpoints or external destinations",
                       "live credentials", "weaken approval semantics",
                       "create another heartbeat", "select a successor"):
            self.assertIn(phrase, authority)
        non_goals = " ".join(self.program["non_goals"])
        for phrase in ("#477-#481", "#483", "#489", "#490", "#493", "#494",
                       "live credential", "Calendar write authority"):
            self.assertIn(phrase, non_goals)
        self.assertTrue(self.program["evidence_classes"])
        self.assertIn("No live", self.program["completion_claim"])
        review = self.program["independent_review"]["required_for"]
        self.assertEqual(sorted(review), sorted(["FU1-473", "FU1-DEC-01", "FU1-482", "program-closeout"]))
        self.assertIn("does not select a successor", self.program["completion_rule"])


if __name__ == "__main__":
    unittest.main()
