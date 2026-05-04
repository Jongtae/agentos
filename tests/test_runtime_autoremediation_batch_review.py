from __future__ import annotations

import unittest

from kernel.runtime.autoremediation_batch_review import build_batch_review_payload


class RuntimeAutoremediationBatchReviewTests(unittest.TestCase):
    def test_handoff_batch_has_hotspots_and_actions(self):
        payload = build_batch_review_payload(
            workspace="/tmp/workspace",
            run_id="batch-1",
            batch_governance={"decision": "handoff", "reason": "batch_error_runs_high", "eligible_run_indexes": []},
            campaign_payload={
                "run_results": [
                    {"decision": "allow", "exit_code": 5, "cycle_exit_code": 5, "reason": "runtime_error"},
                    {"decision": "handoff", "exit_code": 0, "cycle_exit_code": 0, "reason": "manual_review"},
                ]
            },
        )
        self.assertEqual(payload.get("batch_decision"), "handoff")
        self.assertEqual(len(payload.get("hotspots", [])), 2)
        self.assertIn("escalate batch execution to operator", payload.get("checklist", []))
        self.assertIn("audit unstable runs and rollback options", payload.get("checklist", []))

    def test_healthy_batch_has_eligible_runs(self):
        payload = build_batch_review_payload(
            workspace="/tmp/workspace",
            run_id="batch-2",
            batch_governance={"decision": "allow", "reason": "batch_ready", "eligible_run_indexes": [1, 2]},
            campaign_payload={
                "run_results": [
                    {"decision": "allow", "exit_code": 0, "cycle_exit_code": 0, "reason": "ok"},
                    {"decision": "allow", "exit_code": 0, "cycle_exit_code": 0, "reason": "ok"},
                ]
            },
        )
        self.assertEqual(payload.get("batch_decision"), "allow")
        self.assertEqual(payload.get("eligible_run_indexes"), [1, 2])
        self.assertEqual(payload.get("hotspots"), [])
        self.assertEqual(payload.get("checklist"), ["batch execution ready for auto-safe actions"])


if __name__ == "__main__":
    unittest.main()
