from __future__ import annotations

import unittest

from kernel.broker.schema import (
    BROKER_DECISION_STATES,
    BROKER_REQUEST_KINDS,
    broker_contract,
    build_broker_decision,
    build_broker_request,
)


class BrokerSchemaTests(unittest.TestCase):
    def test_build_broker_request_normalizes_correlation(self):
        request = build_broker_request(
            kind="exec",
            action="run",
            actor={"pid": 7},
            object={"command": "ls -la"},
            correlation={"request_id": "req-1", "session_id": ""},
        )

        self.assertEqual(request.kind, "exec")
        self.assertEqual(request.correlation, {"request_id": "req-1"})

    def test_build_broker_decision_rejects_unknown_state(self):
        with self.assertRaises(ValueError):
            build_broker_decision(state="maybe", reason="unknown")

    def test_broker_contract_exposes_request_and_decision_vocab(self):
        contract = broker_contract()

        self.assertEqual(contract["request_kinds"], list(BROKER_REQUEST_KINDS))
        self.assertEqual(contract["decision_states"], list(BROKER_DECISION_STATES))
        self.assertIn("exec_request", contract["event_emission"])
        self.assertIn("operator_control", contract["request_kinds"])
        self.assertIn("install_control", contract["request_kinds"])


if __name__ == "__main__":
    unittest.main()
