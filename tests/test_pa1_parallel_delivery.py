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
        self.assertEqual(self.plan["next_goal"]["id"], "EPIC-PA1")
        self.assertEqual(self.plan["next_goal"]["status"], "owner-activated-goal-ready")
        epic = self.items["EPIC-PA1"]
        self.assertEqual(epic["issue"], 386)
        self.assertEqual(epic["depends_on"], ["GOV-PA1-01"])
        self.assertEqual(epic["activation_status"], "owner-activated-goal-ready")
        completed = self.plan["history"]["documented_completed_iterations"]
        self.assertIn("GOV-PA1-01", completed)
        self.assertIn("USE-01", completed)
        self.assertNotIn("EPIC-PA1", completed)
        self.assertEqual(self.program["active_substeps"], [])
        tasks = (ROOT / "TASKS.md").read_text(encoding="utf-8")
        self.assertIn("selects EPIC-PA1 as goal-ready only", tasks)
        self.assertNotIn("selects USE-01 as goal-ready", tasks)
        self.assertIn("#358 did not select a successor; EPIC-PA1 is separately prepared by #385", tasks)

    def test_epic_is_the_only_nonterminal_program_authority(self):
        nonterminal = [
            name for name, program in self.plan["programs"].items()
            if program.get("status") != "complete"
        ]
        self.assertEqual(nonterminal, ["EPIC-PA1"])
        self.assertEqual(self.program["status"], "owner-activated-goal-ready")
        self.assertEqual(self.program["issue"], 386)

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


if __name__ == "__main__":
    unittest.main()
