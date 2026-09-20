"""Read-only preservation checks for GOV-USE-01; not product/live evidence."""
import hashlib
import json
import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
BASELINE_SHA = "873ef6dab6cd9fdef02c7150decc5432e229680c"
LEDGER_SHA = "21fe8b6c90a493ff31f38aca7285935bd660cdfd"
ROADMAP_SHA = "25d87bbcc3c7667da640815f1f6d2c559d2a6a12"


def blob_sha(content):
    return hashlib.sha1(b"blob " + str(len(content)).encode("ascii") + b"\0" + content).hexdigest()


class GovUsePreservationTests(unittest.TestCase):
    def test_old_delivery_contracts_are_semantically_unchanged(self):
        original = (ROOT / "tests/fixtures/governance/plan-before-gov-use.json").read_bytes()
        self.assertEqual(blob_sha(original), BASELINE_SHA)
        baseline = json.loads(original)
        current = json.loads((ROOT / "delivery-plan.yaml").read_bytes())
        old_items = {item["id"]: item for item in baseline["iterations"]}
        new_items = {item["id"]: item for item in current["iterations"]}
        for identifier, original_item in old_items.items():
            with self.subTest(iteration=identifier):
                self.assertEqual(new_items[identifier], original_item)
        self.assertTrue({"GOV-USE-01", "USE-01"}.issubset(new_items))
        for field in ("repository", "retry", "completion_claims"):
            with self.subTest(field=field):
                self.assertEqual(current[field], baseline[field])
        for name, value in baseline["programs"].items():
            with self.subTest(program=name):
                self.assertEqual(current["programs"][name], value)
        self.assertIn("EPIC-PA1", current["programs"])
        for field, value in baseline["history"].items():
            with self.subTest(history=field):
                if field == "documented_completed_iterations":
                    self.assertEqual(current["history"][field][:len(value)], value)
                else:
                    self.assertEqual(current["history"][field], value)
        for name, value in baseline["milestones"].items():
            self.assertEqual(current["milestones"][name], value)

    def test_ledger_only_appends_to_the_immutable_preparation_baseline(self):
        content = (ROOT / "docs/issue-branch-ledger.jsonl").read_bytes()
        marker = b'\n{"record_type":"governance_closeout","iteration":"GOV-USE-01"'
        self.assertEqual(content.count(marker), 1)
        prefix, _ = content.split(marker, 1)
        # The separator before an appended record may also have been the old
        # terminal newline; either representation must match the ORIGINAL blob.
        self.assertIn(LEDGER_SHA, {blob_sha(prefix), blob_sha(prefix + b"\n")})
        rows = [json.loads(line) for line in content.splitlines() if line.strip()]
        preparation = [row for row in rows if row.get("record_type") == "goal_preparation"
                       and row.get("iteration") == "USE-01"]
        self.assertEqual(len(preparation), 1)
        self.assertIs(preparation[0]["execution_started"], False)
        self.assertIs(preparation[0]["heartbeat_active"], False)
        self.assertIs(preparation[0]["implementation_branch_created"], False)

    def test_original_roadmap_is_preserved_byte_for_byte(self):
        content = (ROOT / "docs/roadmap.history-2026-09-14.md").read_bytes()
        self.assertEqual(blob_sha(content), ROADMAP_SHA)

    def test_current_alignment_documents_have_existing_local_link_targets(self):
        paths = ["README.md", "README.ko.md", "README.ja.md", "README.zh-CN.md",
                 "PRD.md", "PRODUCT_VISION.ko.md", "AGENTS.md", "QUICKSTART.md", "TASKS.md",
                 "docs/roadmap.md", "docs/personal-agentos-architecture.en.md",
                 "docs/agent-distribution-platform-foundation.en.md",
                 "docs/owner-control-contract.en.md", "docs/default-agent-usefulness.en.md",
                 "docs/use-01-goal-readiness.en.md", "docs/reviews/gov-use-01-audit.en.md"]
        for relative in paths:
            source = ROOT / relative
            text = source.read_text(encoding="utf-8")
            for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
                parsed = urlsplit(link)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                target = source.parent / unquote(parsed.path)
                with self.subTest(source=relative, target=link):
                    self.assertTrue(target.exists(), f"Missing local link: {relative} -> {link}")


if __name__ == "__main__":
    unittest.main()
