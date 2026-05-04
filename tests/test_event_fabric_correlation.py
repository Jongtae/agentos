from __future__ import annotations

import unittest

from kernel.event_fabric.correlation import (
    CORRELATION_KEYS,
    build_correlation_context,
    correlation_contract,
    normalize_correlation_context,
)
from kernel.event_fabric.schema import build_os_event_record


class EventFabricCorrelationTests(unittest.TestCase):
    def test_build_correlation_context_prefers_stable_keys(self):
        context = build_correlation_context(
            session_id="session-1",
            run_id="run-1",
            request_id="req-1",
            trace_id="trace-1",
            boot_id="boot-1",
            custom_key="custom",
            approval_id="",
        )

        self.assertEqual(context["session_id"], "session-1")
        self.assertEqual(context["request_id"], "req-1")
        self.assertEqual(context["boot_id"], "boot-1")
        self.assertEqual(context["custom_key"], "custom")
        self.assertNotIn("approval_id", context)

    def test_normalize_correlation_context_drops_empty_values(self):
        normalized = normalize_correlation_context(
            {
                "request_id": "req-1",
                "session_id": "",
                "trace_id": None,
                "custom": "value",
            }
        )

        self.assertEqual(normalized, {"request_id": "req-1", "custom": "value"})

    def test_build_os_event_record_normalizes_correlation_payload(self):
        event = build_os_event_record(
            source="runtime",
            kind="broker.exec_request",
            action="request",
            correlation={
                "request_id": "req-1",
                "session_id": "",
                "trace_id": "trace-1",
            },
        )

        self.assertEqual(event.correlation, {"request_id": "req-1", "trace_id": "trace-1"})

    def test_correlation_contract_exposes_stable_keys(self):
        contract = correlation_contract()

        self.assertEqual(contract["stable_keys"], list(CORRELATION_KEYS))
        self.assertIn("request_id", contract["linkage_priority"])
        self.assertIn("boot_id", contract["stable_keys"])
        self.assertIn("session_id", contract["session_join_keys"])


if __name__ == "__main__":
    unittest.main()
