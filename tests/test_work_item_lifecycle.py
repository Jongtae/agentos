import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import work_item_lifecycle


class WorkItemLifecycleTests(unittest.TestCase):
    def test_phase_titles_and_branch_names(self):
        self.assertEqual(
            work_item_lifecycle.phase_issue_title(27, 172, "Remastered VM Boot Checklist"),
            "EPIC: Stage 27 / Phase 172 Remastered VM Boot Checklist",
        )
        self.assertEqual(
            work_item_lifecycle.phase_branch_name(27, 172, "Remastered VM Boot Checklist"),
            "codex/stage27-phase172-remastered-vm-boot-checklist",
        )

    def test_task_titles_and_branch_names(self):
        self.assertEqual(
            work_item_lifecycle.task_issue_title("P172-01", "Add checklist artifact"),
            "[P172-01] Add checklist artifact",
        )
        self.assertEqual(
            work_item_lifecycle.task_branch_name("P172-01", "Add checklist artifact"),
            "codex/p172-01-add-checklist-artifact",
        )

    def test_append_ledger_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = Path(tmpdir) / "ledger.jsonl"
            entry = {"action": "start", "issue_number": 12}
            with mock.patch.object(work_item_lifecycle, "LEDGER_PATH", ledger):
                work_item_lifecycle.append_ledger(entry)
            payload = json.loads(ledger.read_text().strip())
            self.assertEqual(payload["issue_number"], 12)


if __name__ == "__main__":
    unittest.main()
