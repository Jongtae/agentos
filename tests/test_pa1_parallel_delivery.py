"""Governance regressions for the prepared EPIC-PA1 parallel delivery graph.

These tests prove only repository orchestration metadata. They do not activate
a delivery heartbeat, create worktrees, use credentials, or exercise providers.
"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Pa1ParallelDeliveryTests(unittest.TestCase):
    def setUp(self):
        root = (ROOT / "delivery-plan.yaml").read_bytes()
        self.assertEqual(root, (ROOT / "src/personal_agent/delivery-plan.yaml").read_bytes())
        self.plan = json.loads(root)
        self.items = {item["id"]: item for item in self.plan["iterations"]}
        self.program = self.plan["programs"]["EPIC-PA1"]

    def test_epic_is_goal_ready_but_not_active(self):
        # EPIC-PA1 is owner-paused by #419 so a non-overlapping EPIC-REUSE-01
        # tranche can run first. What must hold is that goal-readiness alone
        # never executes, and that a paused program is not the declared goal.
        self.assertNotEqual(self.plan["next_goal"]["id"], "EPIC-PA1")
        self.assertNotEqual(self.plan["next_goal"]["status"], "active")
        self.assertEqual(self.program["status"], "owner-paused")
        self.assertIn("resume_condition", self.program)
        epic = self.items["EPIC-PA1"]
        self.assertEqual(epic["issue"], 386)
        self.assertEqual(epic["depends_on"], ["GOV-PA1-01"])
        self.assertEqual(epic["activation_status"], "owner-paused")
        completed = self.plan["history"]["documented_completed_iterations"]
        self.assertIn("GOV-PA1-01", completed)
        self.assertIn("USE-01", completed)
        self.assertNotIn("EPIC-PA1", completed)
        self.assertEqual(self.program["active_substeps"], [])
        tasks = (ROOT / "TASKS.md").read_text(encoding="utf-8")
        self.assertIn("selects EPIC-PA1 as goal-ready only", tasks)
        self.assertNotIn("selects USE-01 as goal-ready", tasks)
        self.assertIn("#358 did not select a successor; EPIC-PA1 is separately prepared by #385", tasks)

    def test_exactly_one_program_holds_execution_authority(self):
        """Governance allows one active top-level program, not one program.

        The earlier form asserted EPIC-PA1 was the only non-complete program,
        which pinned a transient fact rather than the rule. A paused program
        still exists and still owns its substeps; it simply cannot execute.
        """
        terminal = {"complete", "owner-paused"}
        executing = [
            name for name, program in self.plan["programs"].items()
            if program.get("status") not in terminal
        ]
        self.assertEqual(len(executing), 1, executing)
        self.assertEqual(self.plan["next_goal"]["id"], executing[0])
        self.assertEqual(self.program["status"], "owner-paused")
        self.assertEqual(self.program["issue"], 386)

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
        import json
        import tempfile
        from personal_agent.delivery import DeliveryPlan

        plan = json.loads((ROOT / "delivery-plan.yaml").read_text(encoding="utf-8"))
        paused = [
            name for name, program in plan["programs"].items()
            if program.get("status") == "owner-paused"
        ]
        self.assertTrue(paused)
        for name in paused:
            with self.subTest(program=name):
                altered = json.loads(json.dumps(plan))
                # Redeclare the paused program as the active goal - the exact
                # mistake the pause has to survive.
                altered["next_goal"] = {"id": name, "status": "active"}
                with tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / "delivery-plan.yaml"
                    path.write_text(json.dumps(altered), encoding="utf-8")
                    self.assertIsNone(DeliveryPlan(path).select({}))

    def test_a_paused_program_holds_no_running_work(self):
        """A paused program must not keep substeps in flight.

        Treating `owner-paused` as terminal for the one-active-program rule is
        only safe if paused means stopped. Without this, any number of programs
        could sit `owner-paused` with populated `active_substeps` and the
        one-program assertion would not notice.
        """
        for name, program in self.plan["programs"].items():
            if program.get("status") != "owner-paused":
                continue
            with self.subTest(program=name):
                self.assertEqual(program.get("active_substeps"), [])
                self.assertTrue(program.get("resume_condition"))
                self.assertTrue(program.get("paused_by"))
                iteration = self.items[name]
                self.assertNotEqual(iteration["activation_status"], "owner-activated-goal-ready")

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
        self.assertEqual(program["status"], "owner-activated-goal-ready")

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
        self.assertEqual(self.program["active_substeps"], [])

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
        self.assertEqual(self.program["active_substeps"], [])
        self.assertEqual(self.plan["next_goal"]["status"], "owner-activated-goal-ready")

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
        self.assertEqual(self.program["active_substeps"], [])
        self.assertEqual(self.plan["next_goal"]["status"], "owner-activated-goal-ready")

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
