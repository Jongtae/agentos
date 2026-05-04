import unittest

from scripts import backfill_historical_phase_issues as backfill


class BackfillHistoricalPhaseIssuesTests(unittest.TestCase):
    def test_targets_cover_phase_118_through_171(self):
        phases = [item["phase"] for item in backfill.BACKFILL_TARGETS]
        self.assertEqual(phases[0], 118)
        self.assertEqual(phases[-1], 171)
        self.assertEqual(len(phases), len(set(phases)))

    def test_start_entry_marks_historical_backfill(self):
        target = {"stage": 21, "phase": 154, "title": "Base Image and Remaster Contract"}
        entry = backfill.start_entry("Jongtae/agentos", target, 999, "git.com:Jongtae/agentos.git/issues/999")
        self.assertTrue(entry["historical_backfill"])
        self.assertIsNone(entry["branch"])
        self.assertEqual(entry["planned_branch"], "codex/stage21-phase154-base-image-and-remaster-contract")

    def test_close_entry_carries_commit_provenance(self):
        target = {"stage": 26, "phase": 171, "title": "Stage 26 Closeout / Boot Target Baseline"}
        entry = backfill.close_entry("Jongtae/agentos", target, 1000, "abc1234")
        self.assertTrue(entry["historical_backfill"])
        self.assertEqual(entry["commit"], "abc1234")
        self.assertIsNone(entry["merge_target"])


if __name__ == "__main__":
    unittest.main()
