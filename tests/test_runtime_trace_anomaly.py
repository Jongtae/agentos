from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from kernel.runtime.trace import approval_anomaly_from_counters


class RuntimeTraceAnomalyTests(unittest.TestCase):
    def test_high_denied_rate_detected(self):
        counters = {"requested": 10, "approved": 2, "denied": 8, "blocked": 0}
        r = approval_anomaly_from_counters(counters)
        self.assertTrue(r["anomaly_detected"])
        self.assertEqual(r["reason"], "high_denied_rate")

    def test_blocked_spike_detected(self):
        counters = {"requested": 1, "approved": 1, "denied": 0, "blocked": 10}
        r = approval_anomaly_from_counters(counters)
        self.assertTrue(r["anomaly_detected"])
        self.assertEqual(r["reason"], "blocked_spike")

    def test_normal_counters_not_flagged(self):
        counters = {"requested": 4, "approved": 3, "denied": 1, "blocked": 1}
        r = approval_anomaly_from_counters(counters)
        self.assertFalse(r["anomaly_detected"])

    def test_thresholds_can_be_overridden(self):
        counters = {"requested": 4, "approved": 1, "denied": 3, "blocked": 0}
        with patch.dict(
            os.environ,
            {
                "AGENTOS_APPROVAL_DENY_MIN_REQUESTED": "3",
                "AGENTOS_APPROVAL_DENY_RATE_WARN": "0.7",
            },
            clear=True,
        ):
            r = approval_anomaly_from_counters(counters)
        self.assertTrue(r["anomaly_detected"])
        self.assertEqual(r["reason"], "high_denied_rate")


if __name__ == "__main__":
    unittest.main()
