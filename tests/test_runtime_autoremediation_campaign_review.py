from __future__ import annotations

import unittest

from kernel.runtime.autoremediation_campaign_review import build_campaign_review_payload


class RuntimeAutoremediationCampaignReviewTests(unittest.TestCase):
    def test_handoff_campaign_has_hotspots_and_actions(self):
        payload = build_campaign_review_payload(
            workspace="/tmp/ws",
            run_id="campaign-1",
            campaign_governance={"decision": "handoff", "reason": "campaign_error_rate_high"},
            run_results=[
                {"decision": "allow", "exit_code": 0, "reason": "ok"},
                {"decision": "handoff", "exit_code": 5, "reason": "operator_handoff_required"},
            ],
        )
        self.assertEqual(payload.get("campaign_decision"), "handoff")
        self.assertGreaterEqual(len(payload.get("hotspots", [])), 1)
        self.assertGreaterEqual(len(payload.get("checklist", [])), 3)

    def test_healthy_campaign_has_no_hotspots(self):
        payload = build_campaign_review_payload(
            workspace="/tmp/ws",
            run_id="campaign-2",
            campaign_governance={"decision": "allow", "reason": "campaign_healthy"},
            run_results=[
                {"decision": "allow", "exit_code": 0, "reason": "ok"},
                {"decision": "allow", "exit_code": 0, "reason": "ok"},
            ],
        )
        self.assertEqual(payload.get("campaign_decision"), "allow")
        self.assertEqual(payload.get("hotspots"), [])
        self.assertEqual(payload.get("checklist"), ["no immediate campaign action required"])


if __name__ == "__main__":
    unittest.main()
