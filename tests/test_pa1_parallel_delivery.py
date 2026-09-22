"""Governance regressions for the prepared EPIC-PA1 parallel delivery graph.

These tests prove only repository orchestration metadata. They do not activate
a delivery heartbeat, create worktrees, use credentials, or exercise providers.
"""
import json
from pathlib import Path
import unittest

from personal_agent.delivery import DeliveryPlan

from delivery_state_invariants import (
    GOAL_READY,
    PAUSED,
    assert_activation_record,
    assert_closed_out_record,
    assert_declared_goal_shape,
    assert_no_unauthorised_execution_authority,
    assert_active_substeps_are_legitimate,
    assert_pause_survives_redeclaration,
    closed_out_programs,
    executing_programs,
    is_resumed,
    paused_programs,
    plan_file,
    synthetic_paused_program,
)

ROOT = Path(__file__).resolve().parents[1]


class Pa1ParallelDeliveryTests(unittest.TestCase):
    def setUp(self):
        root = (ROOT / "delivery-plan.yaml").read_bytes()
        self.assertEqual(root, (ROOT / "src/personal_agent/delivery-plan.yaml").read_bytes())
        self.plan = json.loads(root)
        self.items = {item["id"]: item for item in self.plan["iterations"]}
        self.program = self.plan["programs"]["EPIC-PA1"]

    def test_epic_is_goal_ready_but_not_active(self):
        """Goal-readiness alone never executes, in whichever role PA1 sits.

        The earlier form spelled this as "EPIC-PA1 is owner-paused by #419".
        That was true while a non-overlapping EPIC-REUSE-01 tranche ran
        first, but it pinned the cast rather than the rule, so it broke the
        moment the owner legitimately swapped the roles back. EPIC-PA1 has
        exactly two legitimate roles -- the armed declared goal, or paused --
        and the invariant is the same in both: nothing is selectable and the
        heartbeat stays down. The role is now read from the plan and the
        *full* set of pins for whichever role holds is asserted, so neither
        role is a free pass.
        """
        self.assertNotEqual(self.plan["next_goal"]["status"], "active")
        epic = self.items["EPIC-PA1"]
        self.assertEqual(epic["issue"], 386)
        self.assertEqual(epic["depends_on"], ["GOV-PA1-01"])
        completed = self.plan["history"]["documented_completed_iterations"]
        self.assertIn("GOV-PA1-01", completed)
        self.assertIn("USE-01", completed)
        self.assertNotIn("EPIC-PA1", completed)
        assert_active_substeps_are_legitimate(self, self.plan, "EPIC-PA1")
        # The pause history is never erased by a resumption: #419's record
        # and its resume condition stay on the program either way.
        self.assertIn("resume_condition", self.program)
        self.assertTrue(self.program["resume_condition"])
        assert_activation_record(self, "EPIC-PA1 paused_by", self.program.get("paused_by"))

        status = self.program["status"]
        self.assertIn(status, {GOAL_READY, PAUSED}, status)
        if status == GOAL_READY:
            # Armed: the declaration must agree across all three layers and
            # must be backed by an explicit owner reactivation record, so a
            # resumption cannot happen as a side effect of anything else.
            self.assertEqual(self.plan["next_goal"]["id"], "EPIC-PA1")
            self.assertEqual(epic["activation_status"], GOAL_READY)
            assert_activation_record(self, "EPIC-PA1 reactivated_by",
                                     self.program.get("reactivated_by"))
            self.assertTrue(is_resumed(self.program))
        else:
            # Paused: not declared, not armed where selection reads, and the
            # pause record has no matching reactivation.
            self.assertNotEqual(self.plan["next_goal"]["id"], "EPIC-PA1")
            self.assertEqual(epic["activation_status"], PAUSED)
            self.assertFalse(is_resumed(self.program))
        # Either role: goal-readiness selects nothing and starts nothing.
        # This is new strength -- the earlier form asserted plan fields back
        # at themselves and never ran the selection code.
        shape = assert_declared_goal_shape(self, self.plan)
        if status == GOAL_READY:
            self.assertEqual(shape, "goal-ready")
        assert_no_unauthorised_execution_authority(self, self.plan)

        tasks = (ROOT / "TASKS.md").read_text(encoding="utf-8")
        self.assertIn("selects EPIC-PA1 as goal-ready only", tasks)
        self.assertNotIn("selects USE-01 as goal-ready", tasks)
        self.assertIn("#358 did not select a successor; EPIC-PA1 is separately prepared by #385", tasks)

    def test_exactly_one_program_holds_execution_authority(self):
        """Governance allows at most one active top-level program.

        The earlier form asserted EPIC-PA1 was the only non-complete program,
        which pinned a transient fact rather than the rule. A paused program
        still exists and still owns its substeps; it simply cannot execute.

        The failure mode this exists to catch is *two* programs holding
        execution authority at once. Zero is the safer direction, not a
        violation: AGENTS.md keeps the heartbeat paused "when no top-level
        goal is active or after top-level closeout". So the count relaxes to
        `<= 1`, and the zero case pays for that relaxation with positive
        quiescence assertions -- nothing declared, nothing armed, nothing
        selectable, heartbeat paused -- rather than merely being tolerated.
        """
        executing = executing_programs(self.plan)
        self.assertLessEqual(len(executing), 1, executing)
        shape = assert_declared_goal_shape(self, self.plan)
        if executing:
            self.assertEqual(shape, "goal-ready")
            self.assertEqual(self.plan["next_goal"]["id"], executing[0])
            self.assertIsNotNone(self.plan["next_goal"]["id"])
        else:
            self.assertEqual(shape, "terminal")
            self.assertIsNone(self.plan["next_goal"]["id"])
        self.assertEqual(self.program["issue"], 386)
        # The dropped pins here were `EPIC-PA1 not in executing` and
        # `next_goal.id != "EPIC-PA1"`. Their concern -- a program that has
        # been closed out or paused silently regaining authority as a side
        # effect of something else -- is kept, but derived from the plan
        # instead of from that one name, so it now guards every program and
        # survives the roles swapping in either direction.
        assert_no_unauthorised_execution_authority(self, self.plan)

    def test_a_paused_program_cannot_be_selected_even_if_redeclared_active(self):
        """Pausing must remove execution authority, not merely relabel it.

        An earlier form of this test asserted `select({}) is None` against the
        real plan and claimed that proved pausing worked. It did not: selection
        reads the iterations layer and never `programs[*]["status"]`, so the
        assertion passed for an unrelated reason and the test asserted coverage
        it did not have. The pause is now carried by the paused program's own
        iteration `activation_status`, which is the value selection actually
        reads, and this test forces that path.
        """
        plan = json.loads((ROOT / "delivery-plan.yaml").read_text(encoding="utf-8"))
        recorded = paused_programs(plan)

        # The subject set is fixed, not drawn from the current cast. The
        # earlier form iterated the live plan's paused programs, which is how
        # its sibling test evaporated when the owner resumed the only one.
        # This test had a guard and failed loudly instead -- but a guard only
        # turns an evaporated test into a broken one. A synthetic pause is
        # therefore always constructed and always checked, and the real paused
        # programs are checked *in addition*.
        synthetic, name = synthetic_paused_program(plan)
        with self.subTest(scenario="synthetic-pause"):
            self.assertEqual(paused_programs(synthetic), sorted(recorded + [name]))
            assert_pause_survives_redeclaration(self, synthetic, name)

        with self.subTest(scenario="synthetic-pause-two-layer-consistency"):
            # The pause only holds because it is recorded at the iterations
            # layer too. Arming that layer while leaving the program record
            # paused makes the program selectable again, so the consistency
            # assertion inside assert_pause_survives_redeclaration is doing
            # real work rather than restating the program record.
            armed = json.loads(json.dumps(synthetic))
            entry = next(item for item in armed["iterations"] if item["id"] == name)
            entry["activation_status"] = "owner-activated-goal-ready"
            armed["next_goal"] = {"id": name, "status": "active"}
            with plan_file(armed) as path:
                self.assertEqual(DeliveryPlan(path).select({})["id"], name)
            with self.assertRaises(AssertionError):
                assert_pause_survives_redeclaration(self, armed, name)

        with self.subTest(scenario="recorded-paused-programs"):
            # Aggregated into one subTest so the case count does not move
            # with the cast; every assertion carries the program name.
            for recorded_name in recorded:
                assert_pause_survives_redeclaration(self, plan, recorded_name)

    def test_a_paused_program_holds_no_running_work(self):
        """A paused program must not keep substeps in flight.

        Treating `owner-paused` as terminal for the one-active-program rule is
        only safe if paused means stopped. Without this, any number of programs
        could sit `owner-paused` with populated `active_substeps` and the
        one-program assertion would not notice.
        """
        # Keyed on the pause *record*, not the current status. Keying on
        # status meant that resuming the only paused program emptied this
        # loop and the test passed vacuously. A program that was ever paused
        # keeps its record, so the subject survives a role swap either way.
        subjects = sorted(
            name for name, program in self.plan["programs"].items()
            if program.get("paused_by")
        )
        self.assertTrue(subjects, "no program carries a pause record to check")
        for name in subjects:
            program = self.plan["programs"][name]
            with self.subTest(program=name):
                if is_resumed(program):
                    # The record survives resumption on purpose, so the
                    # subject set cannot evaporate -- but "holds no running
                    # work" is a claim about being paused *now*. A resumed
                    # program is allowed work in flight, bounded instead by
                    # the legitimacy rule.
                    assert_active_substeps_are_legitimate(self, self.plan, name)
                else:
                    self.assertEqual(program.get("active_substeps"), [])
                self.assertTrue(program.get("resume_condition"))
                assert_activation_record(self, f"{name} paused_by", program.get("paused_by"))
                iteration = self.items[name]
                if is_resumed(program):
                    # Resumed: the program record and the layer selection
                    # actually reads must agree, and the resumption must be
                    # an explicit owner record rather than a drifted field.
                    self.assertEqual(program.get("status"), "owner-activated-goal-ready")
                    self.assertEqual(iteration["activation_status"],
                                     "owner-activated-goal-ready")
                    assert_activation_record(self, f"{name} reactivated_by",
                                             program.get("reactivated_by"))
                else:
                    self.assertEqual(program.get("status"), "owner-paused")
                    self.assertNotEqual(iteration["activation_status"],
                                        "owner-activated-goal-ready")

    def test_reuse_concurrency_policy_is_bounded_and_disjointness_required(self):
        """The parallel exception must stay bounded and conditional.

        #418 forbade parallel children because several substeps share
        quickstart_service.py, quickstart.py, provider contracts and
        packaging. Those substeps were split to #420, so the reason no longer
        covers the activated tranche - but the exception replacing it has to
        keep both halves: a hard ceiling, and a disjointness precondition.
        Dropping either turns a bounded exception back into the unlimited
        parallelism the original rule refused.

        The ceiling is set by review capacity, not file conflict, so it counts
        children in any state before merge rather than only those being
        implemented.
        """
        policy = self.plan["programs"]["EPIC-REUSE-01"]["concurrency"]
        self.assertIsInstance(policy["max_open_children"], int)
        self.assertLessEqual(policy["max_open_children"], 2)
        self.assertGreaterEqual(policy["max_open_children"], 1)
        # Disjointness is the precondition, not advice.
        self.assertTrue(policy["requires"])
        self.assertIn("disjoint", policy["requires"].lower())
        # R1's own children share gmail.py and must never run together.
        self.assertIn(["R1a", "R1b", "R1c"], policy["mutually_exclusive"])
        self.assertTrue(policy["mutually_exclusive_reason"])
        # The limit counts review and remediation, which is where the cost is.
        self.assertIn("remediation", policy["counts"].lower())
        # Per-child gates are untouched by this exception.
        unchanged = policy["unchanged"].lower()
        for gate in ("existing solutions review", "independent review"):
            self.assertIn(gate, unchanged)

    def test_activated_reuse_program_matches_its_declared_scope(self):
        """The program holding the declared goal needs its own regression pins.

        EPIC-PA1 has a dedicated suite; when authority moved, the new holder
        shipped with none, so its substep scope, deferral and governance
        dependency were unprotected.
        """
        program = self.plan["programs"]["EPIC-REUSE-01"]
        self.assertEqual(program["issue"], 418)
        self.assertEqual(program["ordered_substeps"], ["R1", "R2", "R4", "R7", "R8"])
        deferred = program["deferred_substeps"]
        self.assertEqual(deferred["successor_issue"], 420)
        self.assertEqual(deferred["substeps"], ["R3", "R5", "R6"])
        # A deferred substep must never appear in the activated tranche.
        self.assertFalse(set(deferred["substeps"]) & set(program["ordered_substeps"]))
        # The authority text must keep the prohibitions #418 declares.
        authority = program["authority"].lower()
        for prohibition in ("may not", "credential", "authority", "fail-closed"):
            self.assertIn(prohibition, authority)
        self.assertTrue(program["non_goals"])
        # R1 was split and R1c never ran. The split and its disposition are
        # pinned here unconditionally: a completed program's record must not
        # be quietly edited to make the gap disappear.
        self.assertEqual(program["declared_substep_children"], {"R1": ["R1a", "R1b", "R1c"]})
        self.assertEqual(program["substep_children"], {"R1": ["R1a", "R1b"]})
        self.assertIn("R1c", program["unexecuted_substeps"],
                      "R1c's unexecuted disposition was removed from the closed-out record")
        self.assertEqual(program["unexecuted_substeps"]["R1c"]["successor_issue"], 440)
        self.assertTrue(program["unexecuted_substeps"]["R1c"]["reason"])
        self.assertNotIn("R1c", program.get("completed_substeps", []))

        # The scope pins above hold whichever role #418 holds. Its status
        # does not: it may be the armed declared goal, or closed out. The
        # role is read from the program record rather than from the plan
        # shape, because a program can now be closed out while a *different*
        # program holds the declared goal -- which is exactly the state the
        # earlier shape-keyed form stopped checking.
        assert_declared_goal_shape(self, self.plan)
        assert_active_substeps_are_legitimate(self, self.plan, "EPIC-PA1")
        status = program["status"]
        self.assertIn(status, {"owner-activated-goal-ready", "complete"}, status)
        if status == "owner-activated-goal-ready":
            self.assertEqual(self.plan["next_goal"]["id"], "EPIC-REUSE-01")
            self.assertEqual(self.items["EPIC-REUSE-01"]["activation_status"],
                             "owner-activated-goal-ready")
            self.assertNotIn("EPIC-REUSE-01",
                             self.plan["history"]["documented_completed_iterations"])
        else:
            # Closed out: the full closeout contract, including per-substep
            # evidence, completion history, and the requirement that it is
            # neither declared nor executing.
            assert_closed_out_record(self, self.plan, "EPIC-REUSE-01")
            done = program["completed_substeps"]
            # Closeout may never claim a substep that was deferred to #420.
            self.assertFalse(set(deferred["substeps"]) & set(done))
            # Every activated substep needs recorded evidence, directly or
            # through every child it was split into.  Matching by prefix is
            # what let R1a alone stand in for R1, so the structural check in
            # delivery_state_invariants owns this and is asserted above.
            for substep in program["ordered_substeps"]:
                children = program.get("substep_children", {}).get(substep, [])
                self.assertTrue(substep in done or (children and set(children) <= set(done)), substep)
        # Closing #418 must not select or resume a successor. The earlier
        # form spelled that as "EPIC-PA1 is still owner-paused", which is a
        # cast pin: it could only ever notice one successor, and it forbade
        # the owner's own legitimate resumption. The rule it stood for is
        # that authority is never inherited -- so any program that was ever
        # paused must carry an explicit owner reactivation record before it
        # may execute, and nothing barred may be declared or executing.
        assert_no_unauthorised_execution_authority(self, self.plan)
        for name, other in self.plan["programs"].items():
            if name == "EPIC-REUSE-01" or not other.get("paused_by"):
                continue
            with self.subTest(successor=name):
                if other["status"] not in {"owner-paused", "complete"}:
                    assert_activation_record(self, f"{name} reactivated_by",
                                             other.get("reactivated_by"))
                    # Generic, not pinned to this program: no closed-out
                    # program may resume a successor by its own closeout
                    # issue. Comparing only against EPIC-REUSE-01 would
                    # reintroduce the cast-pinning this module removes.
                    closing_issues = {self.plan["programs"][closed].get("issue")
                                      for closed in closed_out_programs(self.plan)}
                    self.assertNotIn(other["reactivated_by"]["issue"], closing_issues,
                                     f"{name} was resumed by a closed-out program's own issue")

    def test_children_are_parent_controlled_and_cannot_self_activate(self):
        child_ids = set(self.program["ordered_substeps"])
        self.assertTrue(child_ids)
        for child_id in child_ids:
            child = self.items[child_id]
            self.assertEqual(child["program"], "EPIC-PA1")
            self.assertEqual(child["activation_status"], "parent-controlled")
            self.assertNotIn(child.get("activation_status"), {
                "active", "owner-activated-goal-ready"
            })
        assert_active_substeps_are_legitimate(self, self.plan, "EPIC-PA1")

    def test_finite_wave_graph_and_issue_mapping(self):
        self.assertEqual(self.program["ordered_substeps"], [
            "PA1-FDN-01",
            "PA1-INSTALL-01",
            "PA1-GMAIL-01",
            "PA1-CALENDAR-01",
            "PA1-RESEARCH-01",
            "PA1-MEMORY-01",
            "WEB-ADMIN-01",
            "PA1-CONV-01",
            "PA1-INT-01",
        ])
        self.assertEqual(self.program["parallel_groups"], {
            "wave-0": ["PA1-FDN-01"],
            "wave-1": [
                "PA1-INSTALL-01", "PA1-GMAIL-01", "PA1-CALENDAR-01",
                "PA1-RESEARCH-01", "PA1-MEMORY-01", "WEB-ADMIN-01",
            ],
            "wave-2": ["PA1-CONV-01"],
            "wave-3": ["PA1-INT-01"],
        })
        expected_issues = {
            "PA1-FDN-01": 387, "PA1-INSTALL-01": 388, "PA1-GMAIL-01": 389,
            "PA1-CALENDAR-01": 390, "PA1-RESEARCH-01": 391,
            "PA1-MEMORY-01": 392, "WEB-ADMIN-01": 382,
            "PA1-CONV-01": 393, "PA1-INT-01": 394,
        }
        self.assertEqual({key: self.items[key]["issue"] for key in expected_issues}, expected_issues)
        for key in expected_issues:
            self.assertEqual(self.items[key]["activation_status"], "parent-controlled")

    def test_wave_one_has_exclusive_primary_ownership(self):
        wave = self.program["parallel_groups"]["wave-1"]
        seen = {}
        collisions = []
        for child in wave:
            owned = self.items[child].get("owns", [])
            self.assertTrue(owned, child)
            for path in owned:
                if path in seen:
                    collisions.append((path, seen[path], child))
                seen[path] = child
        self.assertEqual(collisions, [])

        shared = set(self.program["shared_files"])
        for child in wave:
            overlap = set(self.items[child].get("owns", [])) & shared
            if child == "WEB-ADMIN-01":
                self.assertEqual(overlap, {
                    "src/personal_agent/web/index.html",
                    "src/personal_agent/web/app.js",
                    "src/personal_agent/web/style.css",
                })
            else:
                self.assertEqual(overlap, set(), child)

    def test_shared_wiring_stays_with_convergence_owners(self):
        shared = set(self.program["shared_files"])
        self.assertEqual(
            set(self.items["PA1-INT-01"]["owns"]),
            shared,
        )
        self.assertIn(
            "src/personal_agent/quickstart_service.py",
            self.items["PA1-CONV-01"]["owns"],
        )
        for child_id in self.program["parallel_groups"]["wave-1"]:
            owned_shared = set(self.items[child_id].get("owns", [])) & shared
            if child_id == "WEB-ADMIN-01":
                self.assertEqual(owned_shared, {
                    "src/personal_agent/web/index.html",
                    "src/personal_agent/web/app.js",
                    "src/personal_agent/web/style.css",
                })
            else:
                self.assertEqual(owned_shared, set())

    def test_dependencies_force_foundation_conversation_then_integration(self):
        for child in ("PA1-INSTALL-01", "PA1-GMAIL-01", "PA1-CALENDAR-01",
                      "PA1-RESEARCH-01", "PA1-MEMORY-01"):
            self.assertEqual(self.items[child]["depends_on"], ["PA1-FDN-01"])
        self.assertIn("PA1-FDN-01", self.items["WEB-ADMIN-01"]["depends_on"])
        self.assertEqual(set(self.items["PA1-CONV-01"]["depends_on"]), {
            "PA1-FDN-01", "PA1-GMAIL-01", "PA1-CALENDAR-01",
            "PA1-RESEARCH-01", "PA1-MEMORY-01",
        })
        self.assertEqual(set(self.items["PA1-INT-01"]["depends_on"]), {
            "PA1-INSTALL-01", "PA1-GMAIL-01", "PA1-CALENDAR-01",
            "PA1-RESEARCH-01", "PA1-MEMORY-01", "PA1-CONV-01",
            "WEB-ADMIN-01",
        })

    def test_parallel_contract_exists_and_preserves_single_program_boundary(self):
        path = ROOT / self.program["contract"]
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("## One-thread execution behavior", text)
        self.assertIn("## Ownership rule", text)
        self.assertIn("## Owner activation prompt", text)
        self.assertIn("second heartbeat", text)
        self.assertIn("live credentials", text)
        self.assertIn("purchases", text)
        self.assertIn("booking", text)
        self.assertIn("payment", text)


    def test_dynamic_execution_profiles_are_machine_readable_and_inactive(self):
        profiles = self.program["execution_profiles"]
        self.assertEqual(set(profiles), {"economy", "standard", "critical"})
        self.assertEqual((profiles["economy"]["preferred_model"], profiles["economy"]["preferred_reasoning"]), ("Luna", "Medium"))
        self.assertEqual((profiles["standard"]["preferred_model"], profiles["standard"]["preferred_reasoning"]), ("Sol", "Medium"))
        self.assertEqual((profiles["critical"]["preferred_model"], profiles["critical"]["preferred_reasoning"]), ("Sol", "High"))
        self.assertEqual(self.program["routing_policy"]["default"], "standard")
        assert_active_substeps_are_legitimate(self, self.plan, "EPIC-PA1")
        # "Inactive" is the point of this test. It used to be spelled as the
        # single declared-goal status that happened to hold, then as
        # `EPIC-PA1 not in executing` -- both cast pins. What "inactive"
        # means for routing metadata is that it starts nothing: nothing is
        # selectable, the heartbeat stays down, no program holds authority
        # it is barred from, and no substep has armed itself off the back of
        # a profile entry. That last check is new, and matters more now that
        # PA1 may legitimately be the declared goal.
        assert_declared_goal_shape(self, self.plan)
        assert_no_unauthorised_execution_authority(self, self.plan)
        self.assertLessEqual(len(executing_programs(self.plan)), 1)
        for child in self.program["ordered_substeps"]:
            self.assertEqual(self.items[child]["activation_status"], "parent-controlled", child)

    def test_child_initial_profiles_match_pa1_risk_routing(self):
        expected = {
            "PA1-FDN-01": "critical",
            "PA1-INSTALL-01": "standard",
            "PA1-GMAIL-01": "standard",
            "PA1-CALENDAR-01": "standard",
            "PA1-RESEARCH-01": "standard",
            "PA1-MEMORY-01": "standard",
            "WEB-ADMIN-01": "standard",
            "PA1-CONV-01": "critical",
            "PA1-INT-01": "critical",
        }
        self.assertEqual({key: self.items[key]["execution_profile"] for key in expected}, expected)

    def test_dynamic_routing_contract_has_escalation_and_truthfulness_rules(self):
        path = ROOT / self.program["contract"]
        text = path.read_text(encoding="utf-8")
        self.assertIn("## Dynamic worker capability routing", text)
        self.assertIn("### Mandatory escalation", text)
        self.assertIn("Escalation does not widen issue authority", text)
        self.assertIn("`requested`, `tool_accepted`, and `observed_execution`", text)
        self.assertIn("`observed_execution: unknown`", text)
        self.assertIn("Tool acceptance is not proof of execution", self.program["routing_policy"]["truthfulness"])


    def test_owner_only_operating_gates_do_not_stop_safe_development(self):
        policy = self.program["owner_operating_gate_policy"]
        self.assertEqual(policy["treatment"], "operating-validation-not-implementation-blocker")
        self.assertEqual(policy["pending_state"], "owner_validation_pending")
        self.assertIs(policy["continue_safe_work"], True)
        self.assertEqual(policy["batch_at"], "PA1-INT-01")
        self.assertEqual(policy["final_checklist_owner"], "PA1-INT-01")
        self.assertIn("all remaining safe", policy["stop_program_only_when"])
        self.assertIn("development_complete and operating_validated remain separate", policy["evidence_boundary"])
        assert_active_substeps_are_legitimate(self, self.plan, "EPIC-PA1")
        # The gate policy is metadata. It may not start work or start the
        # heartbeat in *any* role -- the earlier form said "on a paused
        # program", which stopped being true when the owner resumed PA1 and
        # would have left the gate policy unguarded in the role where it
        # actually matters.
        assert_declared_goal_shape(self, self.plan)
        assert_no_unauthorised_execution_authority(self, self.plan)
        self.assertLessEqual(len(executing_programs(self.plan)), 1)
        for child in self.program["ordered_substeps"]:
            self.assertEqual(self.items[child]["activation_status"], "parent-controlled", child)

    def test_owner_gate_contract_batches_live_checks_without_fabricating_success(self):
        text = (ROOT / self.program["contract"]).read_text(encoding="utf-8")
        self.assertIn("## Owner-only operating gates", text)
        self.assertIn("owner_validation_pending", text)
        self.assertIn("Continue-before-stopping rule", text)
        self.assertIn("Batched owner validation", text)
        self.assertIn("PA1-INT-01 / #394 owns the consolidated owner-validation checklist", text)
        self.assertIn("Unknown/unrun live operation is never converted into success", text)


if __name__ == "__main__":
    unittest.main()
