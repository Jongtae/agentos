from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.kernel_operator_review_bundle_history import build_review_bundle_history


class KernelOperatorReviewBundleHistoryTests(unittest.TestCase):
    def test_build_review_bundle_history_summarizes_drift(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bundle1 = root / "review-bundle-a"
            bundle2 = root / "review-bundle-b"
            bundle1.mkdir(parents=True, exist_ok=True)
            bundle2.mkdir(parents=True, exist_ok=True)

            (bundle1 / "bundle-manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": "agentos-operator-review-bundle.v1",
                        "generated_at_utc": "2026-04-13T00:00:00Z",
                        "workspace": "/tmp/ws",
                        "snapshot_label": "a",
                        "summary": {
                            "session_phase": "setup_session",
                            "approval_forensic_status": "pending",
                            "validation_stable": False,
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (bundle1 / "review-pack.json").write_text("{}\n", encoding="utf-8")
            (bundle1 / "review-packet.md").write_text("# a\n", encoding="utf-8")

            (bundle2 / "bundle-manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": "agentos-operator-review-bundle.v1",
                        "generated_at_utc": "2026-04-14T00:00:00Z",
                        "workspace": "/tmp/ws",
                        "snapshot_label": "b",
                        "summary": {
                            "session_phase": "ai_shell",
                            "approval_forensic_status": "quiet",
                            "validation_stable": True,
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (bundle2 / "review-pack.json").write_text("{}\n", encoding="utf-8")
            (bundle2 / "review-packet.md").write_text("# b\n", encoding="utf-8")

            payload = build_review_bundle_history(history_dir=str(root), limit=10)
            self.assertEqual(payload["schema_version"], "agentos-operator-review-bundle-history.v1")
            self.assertEqual(payload["summary"]["review_bundle_count"], 2)
            self.assertFalse(payload["summary"]["stable"])
            self.assertIn("session_phase", payload["summary"]["changed_fields"])
            self.assertIn("snapshot_label", payload["summary"]["changed_fields"])
            self.assertEqual(payload["summary"]["latest_snapshot_label"], "b")

    def test_build_review_bundle_history_uses_nested_review_bundles_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            nested = root / "review-bundles"
            bundle = nested / "review-bundle-a"
            bundle.mkdir(parents=True, exist_ok=True)

            (bundle / "bundle-manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": "agentos-operator-review-bundle.v1",
                        "generated_at_utc": "2026-04-14T00:00:00Z",
                        "workspace": "/tmp/ws",
                        "snapshot_label": "a",
                        "summary": {
                            "session_phase": "ai_shell",
                            "approval_forensic_status": "quiet",
                            "validation_stable": True,
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (bundle / "review-pack.json").write_text("{}\n", encoding="utf-8")
            (bundle / "review-packet.md").write_text("# a\n", encoding="utf-8")

            payload = build_review_bundle_history(history_dir=str(root), limit=10)
            self.assertEqual(payload["summary"]["review_bundle_count"], 1)
            self.assertEqual(Path(payload["history_dir"]), nested.resolve())


if __name__ == "__main__":
    unittest.main()
