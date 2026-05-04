from __future__ import annotations

import unittest

from kernel.policies.approval_rules import ApprovalRequest
from kernel.runtime.approval_adapter import ApprovalInterruptAdapter


class ApprovalAdapterTests(unittest.TestCase):
    def test_build_interrupt_payload(self):
        adapter = ApprovalInterruptAdapter()
        req = ApprovalRequest(
            step_index=2,
            tool_name="bash",
            description="remove files",
            command_or_path="rm -rf tmp",
            risk_reason="destructive",
        )
        payload = adapter.build_interrupt_payload(req, run_id="run-1")
        self.assertEqual(payload["kind"], "approval_interrupt")
        self.assertEqual(payload["run_id"], "run-1")
        self.assertEqual(payload["step_index"], 2)
        self.assertEqual(payload["tool_name"], "bash")

    def test_resolve_resume_approve(self):
        adapter = ApprovalInterruptAdapter()
        out = adapter.resolve_resume("approve")
        self.assertTrue(out.approved)
        self.assertEqual(out.reason, "approved")

    def test_resolve_resume_deny(self):
        adapter = ApprovalInterruptAdapter()
        out = adapter.resolve_resume("deny")
        self.assertFalse(out.approved)
        self.assertEqual(out.reason, "denied")

    def test_resolve_resume_timeout(self):
        adapter = ApprovalInterruptAdapter()
        out = adapter.resolve_resume("timeout")
        self.assertFalse(out.approved)
        self.assertEqual(out.reason, "timeout")

    def test_resolve_resume_unknown_raises(self):
        adapter = ApprovalInterruptAdapter()
        with self.assertRaises(ValueError):
            adapter.resolve_resume("maybe")


if __name__ == "__main__":
    unittest.main()
