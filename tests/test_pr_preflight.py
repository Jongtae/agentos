"""Hermetic tests for the informational merge handoff, not a new merge gate."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("pr_preflight", Path(__file__).resolve().parents[1] / "scripts/pr_preflight.py")
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


def sample():
    return {"pr": {"number": 1, "state": "OPEN", "headRefOid": "a" * 40,
                   "isDraft": False, "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN",
                   "reviewDecision": "APPROVED", "mergedAt": None},
            "head_stable": True, "required_checks_known": True,
            "required_checks": [{"name": "validate", "bucket": "pass"}],
            "allow_auto_merge": False}


class PreflightTests(unittest.TestCase):
    def test_auto_merge_disabled_does_not_block_normal_merge(self):
        result = preflight.classify(sample())
        self.assertEqual(result["outcome"], "normal_merge_candidate")
        self.assertTrue(result["read_only"])
        self.assertFalse(result["automatic_retry"])

    def test_required_checks(self):
        for bucket, outcome in [("pending", "ci_pending"), ("fail", "validation_failed"),
                                ("cancel", "validation_failed"), ("skipping", "checks_need_inspection"),
                                ("mystery", "checks_need_inspection")]:
            with self.subTest(bucket=bucket):
                s = sample(); s["required_checks"][0]["bucket"] = bucket
                self.assertEqual(preflight.classify(s)["outcome"], outcome)

    def test_failed_check_discovery_is_not_pass(self):
        s = sample(); s.update(required_checks=[], required_checks_known=False)
        self.assertEqual(preflight.classify(s)["outcome"], "checks_unknown")

    def test_no_required_checks_only_with_verified_discovery(self):
        s = sample(); s["required_checks"] = []
        self.assertEqual(preflight.classify(s)["outcome"], "normal_merge_candidate")

    def test_pr_states(self):
        for key, value, expected in [
            ("isDraft", True, "draft"), ("mergeable", "CONFLICTING", "conflict"),
            ("mergeStateStatus", "BEHIND", "base_update_needed"),
            ("mergeStateStatus", "BLOCKED", "integration_pending"),
            ("mergeStateStatus", "UNKNOWN", "integration_pending"),
            ("reviewDecision", "CHANGES_REQUESTED", "changes_requested"),
            ("reviewDecision", "REVIEW_REQUIRED", "review_pending"),
            ("state", "CLOSED", "closed_unmerged"), ("state", "MERGED", "merged")]:
            with self.subTest(key=key, value=value):
                s = sample(); s["pr"][key] = value
                self.assertEqual(preflight.classify(s)["outcome"], expected)

    def test_head_pin_and_race(self):
        self.assertEqual(preflight.classify(sample(), "b" * 40)["outcome"], "head_changed")
        s = sample(); s["head_stable"] = False
        self.assertEqual(preflight.classify(s)["outcome"], "head_changed")

    def test_check_failure_precedes_review_wait(self):
        s = sample(); s["pr"]["reviewDecision"] = "REVIEW_REQUIRED"
        s["required_checks"][0]["bucket"] = "fail"
        self.assertEqual(preflight.classify(s)["outcome"], "validation_failed")

    def test_invalid_payloads(self):
        for s in [{}, {"pr": {}}, {**sample(), "required_checks": ["bad"]}]:
            with self.subTest(snapshot=s):
                with self.assertRaises(ValueError): preflight.classify(s)

    def test_read_only_collection_and_moving_head(self):
        s = sample()
        with patch.object(preflight, "gh_json", side_effect=[
            (s["pr"], 0), (s["required_checks"], 0), ({"allow_auto_merge": False}, 0),
            ({"headRefOid": "b" * 40}, 0)]) as run:
            collected = preflight.collect("owner/repo", 1)
        self.assertEqual(preflight.classify(collected)["outcome"], "head_changed")
        commands = [call.args[0][:2] for call in run.call_args_list]
        self.assertEqual(commands, [["pr", "view"], ["pr", "checks"], ["api", "repos/owner/repo"], ["pr", "view"]])

    def test_failed_or_missing_head_reread_is_unknown(self):
        for after, code in [(None, -1), ({}, 0), ({"headRefOid": None}, 0)]:
            with self.subTest(after=after, code=code):
                s = sample()
                with patch.object(preflight, "gh_json", side_effect=[
                    (s["pr"], 0), (s["required_checks"], 0), ({"allow_auto_merge": False}, 0),
                    (after, code)]):
                    collected = preflight.collect("owner/repo", 1)
                self.assertIsNone(collected["head_stable"])
                self.assertEqual(preflight.classify(collected)["outcome"], "head_unknown")
        s = sample(); s.pop("head_stable")
        self.assertEqual(preflight.classify(s)["outcome"], "head_unknown")

    def test_merged_head_mismatch_requires_delivered_revision_review(self):
        for state in ("MERGED", "CLOSED"):
            with self.subTest(state=state):
                s = sample(); s["pr"].update(state=state, mergedAt="2030-01-01T00:00:00Z")
                result = preflight.classify(s, "b" * 40)
                self.assertEqual(result["outcome"], "merged_head_mismatch")
                self.assertIn("delivered revision", result["next_action"])
                self.assertEqual(preflight.classify(s, "a" * 40)["outcome"], "merged")
                self.assertEqual(preflight.classify(s)["outcome"], "merged")

    def test_head_pin_is_case_insensitive(self):
        for state in ("OPEN", "MERGED"):
            for observed, expected in [("a" * 40, "A" * 40), ("A" * 40, "a" * 40)]:
                with self.subTest(state=state, observed=observed):
                    s = sample(); s["pr"].update(state=state, headRefOid=observed)
                    outcome = "merged" if state == "MERGED" else "normal_merge_candidate"
                    self.assertEqual(preflight.classify(s, expected)["outcome"], outcome)

    def test_failed_collection_does_not_expose_error_payload(self):
        with patch.object(preflight, "gh_json", return_value=(None, -1)):
            with self.assertRaises(ValueError): preflight.collect("owner/repo", 1)


if __name__ == "__main__":
    unittest.main()
