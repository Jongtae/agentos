import importlib.util
from pathlib import Path
import unittest

import personal_agent.connector_contract as connector_contract


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pa1_delegation_record.py"
SPEC = importlib.util.spec_from_file_location("pa1_delegation_record", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
WorktreeDelegationRecord = MODULE.WorktreeDelegationRecord


class Pa1DelegationRecordTests(unittest.TestCase):
    def test_record_is_deterministic_and_does_not_grant_runtime_authority(self):
        record = WorktreeDelegationRecord(
            issue=387,
            branch="codex/387-pa1-connector-foundation",
            base_sha="a09f6c3bcc00170a50531ba9b1da265dd559d2e2",
            owned_files=("tests/test_connector_contract.py", "src/personal_agent/connector_contract.py"),
            requested_profile="critical",
            tool_accepted_setting="gpt-5.6-sol/high",
        )
        value = record.as_dict()
        self.assertEqual(value["observed_execution_setting"], "unknown")
        self.assertEqual(value["owned_files"], sorted(value["owned_files"]))
        self.assertNotIn("grant", value)
        self.assertNotIn("personal_agent", MODULE.__name__)
        self.assertFalse(hasattr(connector_contract, "WorktreeDelegationRecord"))
        self.assertEqual(SCRIPT.parent.name, "scripts")


if __name__ == "__main__":
    unittest.main()
