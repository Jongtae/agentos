from __future__ import annotations

import unittest

from scripts.kernel_operator_review_packet import build_review_packet_markdown


class KernelOperatorReviewPacketTests(unittest.TestCase):
    def test_build_review_packet_markdown_renders_human_summary(self) -> None:
        markdown = build_review_packet_markdown(
            {
                "workspace": "/tmp/ws",
                "summary": {
                    "session_phase": "ai_shell",
                    "session_origin": "local_managed_tty1",
                    "approval_forensic_status": "quiet",
                    "validation_stable": True,
                    "control_event_count": 4,
                },
                "case_export": {
                    "summary": {
                        "approval_requested": 1,
                        "approval_denied": 0,
                        "broker_override_count": 0,
                        "milestone_count": 3,
                    }
                },
                "validation_window": {
                    "summary": {
                        "stable": True,
                        "changed_fields": [],
                        "current_overall_state": "stable",
                    }
                },
                "control_history": {
                    "summary": {
                        "categories": ["bridge", "operator_control"],
                        "latest_bridge_state": "reloaded",
                        "latest_enforce_policy_target": "network_allowlist",
                    }
                },
                "references": {
                    "primary_commands": ["scripts/agentos-kernelctl review-pack --json"],
                },
            }
        )
        self.assertIn("# AgentOS Operator Review Packet", markdown)
        self.assertIn("Session phase: `ai_shell`", markdown)
        self.assertIn("Latest enforce target: `network_allowlist`", markdown)


if __name__ == "__main__":
    unittest.main()
