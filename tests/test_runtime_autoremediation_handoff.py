from __future__ import annotations

import unittest

from kernel.runtime.autoremediation_handoff import build_operator_handoff_payload


class RuntimeAutoremediationHandoffTests(unittest.TestCase):
    def test_handoff_payload_for_operator_handoff(self):
        payload = build_operator_handoff_payload(
            workspace="/tmp/ws",
            run_id="run-123",
            governance={
                "decision": "handoff",
                "reason": "operator_handoff_required",
                "inputs": {
                    "scheduler_status": "apply",
                    "scheduler_reason": "eligible",
                    "cadence_status": "allow",
                    "cadence_reason": "eligible",
                    "escalation_reason": "execution_errors_detected",
                    "hold_streak": 2,
                    "failure_streak": 2,
                },
            },
            cycle_payload={
                "escalation": {
                    "event": {
                        "title": "Execution errors",
                        "failure_streak": 2,
                    }
                }
            },
        )

        self.assertTrue(bool(payload.get("handoff_required", False)))
        self.assertEqual(payload.get("summary", {}).get("reason"), "operator_handoff_required")
        self.assertGreaterEqual(len(payload.get("recommended_actions", [])), 2)

    def test_non_handoff_payload_has_no_immediate_action(self):
        payload = build_operator_handoff_payload(
            workspace="/tmp/ws",
            run_id="run-456",
            governance={
                "decision": "allow",
                "reason": "cycle_apply_executed",
                "inputs": {},
            },
            cycle_payload={
                "escalation": {
                    "reason": "no_escalation",
                    "event": {},
                },
                "scheduler": {"decision": {"status": "apply", "reason": "eligible"}},
                "cadence": {"status": "allow", "reason": "eligible"},
            },
        )

        self.assertFalse(bool(payload.get("handoff_required", True)))
        self.assertEqual(payload.get("recommended_actions"), ["no immediate operator action required"])


if __name__ == "__main__":
    unittest.main()
