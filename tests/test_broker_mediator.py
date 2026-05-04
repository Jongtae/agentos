from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel.broker import (
    build_approval_broker_decision,
    build_approval_broker_request,
    mediate_managed_exec,
)
from kernel.planner.planner import Step
from kernel.policies.approval_rules import PolicyEngine


class BrokerMediatorTests(unittest.TestCase):
    def _policy(self) -> PolicyEngine:
        return PolicyEngine(require_approval=True)

    def test_allowed_managed_exec_returns_exec_request(self):
        with tempfile.TemporaryDirectory() as td:
            _ = Path(td)
            mediation = mediate_managed_exec(
                Step(tool_name="bash", description="safe", args={"command": "echo hi"}),
                self._policy(),
                step_index=2,
            )
            self.assertEqual(mediation.state, "allowed")
            self.assertEqual(mediation.request.kind, "exec")
            self.assertEqual(mediation.decision.state, "allowed")
            self.assertEqual(mediation.request.metadata["step_index"], 2)

    def test_blocked_managed_exec_returns_blocked_decision(self):
        mediation = mediate_managed_exec(
            Step(tool_name="bash", description="danger", args={"command": "sudo ls"}),
            self._policy(),
            step_index=1,
        )
        self.assertEqual(mediation.state, "blocked")
        self.assertEqual(mediation.request.kind, "exec")
        self.assertEqual(mediation.decision.state, "blocked")

    def test_approval_managed_exec_returns_approval_contract(self):
        mediation = mediate_managed_exec(
            Step(tool_name="bash", description="risky", args={"command": "rm file.txt"}),
            self._policy(),
            step_index=4,
        )
        self.assertEqual(mediation.state, "approval_required")
        self.assertEqual(mediation.request.kind, "approval")
        self.assertEqual(mediation.decision.state, "approval_required")
        self.assertIsNotNone(mediation.approval_request)
        self.assertIn("approval_id", mediation.request.correlation)

    def test_build_approval_broker_request_uses_stable_ids(self):
        step = Step(tool_name="bash", description="risky", args={"command": "rm file.txt"})
        policy = self._policy()
        approval_request = policy.build_request(step, 3)
        request = build_approval_broker_request(step, approval_request, step_index=3)
        self.assertEqual(request.kind, "approval")
        self.assertEqual(request.action, "approval_gate")
        self.assertIn("approval_id", request.correlation)

    def test_build_approval_broker_decision_tracks_allow_and_deny(self):
        step = Step(tool_name="bash", description="risky", args={"command": "rm file.txt"})
        policy = self._policy()
        approval_request = policy.build_request(step, 2)
        approved = build_approval_broker_decision(step, approval_request, approved=True, step_index=2)
        denied = build_approval_broker_decision(step, approval_request, approved=False, step_index=2)
        self.assertEqual(approved.state, "approved")
        self.assertEqual(denied.state, "denied")


if __name__ == "__main__":
    unittest.main()
