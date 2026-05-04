from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import yaml

from scripts.kernel_operator_evidence import build_evidence_report


class KernelOperatorEvidenceTests(unittest.TestCase):
    def test_build_evidence_report_aggregates_runtime_broker_and_policy(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "artifacts").mkdir(parents=True, exist_ok=True)
            (workspace / "spec.yaml").write_text(
                yaml.dump(
                    {
                        "name": "evidence-test",
                        "kernel_engine": {"provider": "none", "mode": "single"},
                        "runtime": {"workspace_root": "./"},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            (workspace / "artifacts" / "runtime_trace.jsonl").write_text(
                "\n".join(
                    [
                        '{"timestamp_utc":"2026-04-14T00:00:00+00:00","event":"approval_requested","payload":{"tool_name":"bash"}}',
                        '{"timestamp_utc":"2026-04-14T00:00:01+00:00","event":"step_blocked","payload":{"reason":"workspace_boundary","detail":"../outside.txt"}}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (workspace / "artifacts" / "os_events.jsonl").write_text(
                "\n".join(
                    [
                        '{"timestamp_utc":"2026-04-14T00:00:00+00:00","source":"broker","kind":"broker.approval_request","actor":{"component":"agentos-runtime"},"object":{"policy_target":"destructive_action_approval","tool_name":"bash"},"action":"approval_gate","decision":{"state":"requested","request_kind":"approval"},"correlation":{"approval_id":"approval:test"},"raw_ref":{"component":"broker"}}',
                        '{"timestamp_utc":"2026-04-14T00:00:02+00:00","source":"kernel","kind":"file.outside_workspace_candidate","actor":{"pid":7},"object":{"path":"../outside.txt","workspace_root":"./"},"action":"read","decision":{"state":"candidate","policy_target":"fs_workspace_boundary"},"correlation":{"session_id":"agentos:tty1"},"raw_ref":{"collector":"file_access_candidate"}}',
                        '{"timestamp_utc":"2026-04-14T00:00:03+00:00","source":"journald","kind":"session.login","actor":{"uid":1000},"object":{"session_id":"agentos:tty1"},"action":"login","decision":{"state":"observed"},"correlation":{"session_id":"agentos:tty1","boot_id":"boot-1"},"raw_ref":{"collector":"journald"}}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with patch("status._resolve_tty_path", return_value=""):
                report = build_evidence_report(workspace=str(workspace))
            self.assertTrue(report["ok"])
            self.assertEqual(report["summary"]["session_origin"], "noninteractive")
            self.assertEqual(report["summary"]["runtime_session_origin"], "noninteractive")
            self.assertEqual(report["summary"]["session_path_family"], "fallback_or_unmanaged")
            targets = {item["policy_target"]: item["status"] for item in report["summary"]["policy_targets"]}
            self.assertIn("destructive_action_approval", targets)
            self.assertIn("approval_forensics", report)
            self.assertEqual(report["summary"]["approval_forensics"]["approval_requested"], 1)
            self.assertEqual(report["summary"]["recommended_handoff_artifact"], "review_bundle")
            self.assertEqual(report["handoff"]["default_artifact"], "review_bundle")
            self.assertIn("review-bundle", report["handoff"]["recommended_command"])
            self.assertEqual(report["install_validation"]["available"], False)
            self.assertEqual(report["audit_summary"]["available"], False)

    def test_build_evidence_report_surfaces_legacy_compatibility_origin(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "artifacts").mkdir(parents=True, exist_ok=True)
            (workspace / "spec.yaml").write_text(
                yaml.dump(
                    {
                        "name": "evidence-legacy-origin-test",
                        "kernel_engine": {"provider": "none", "mode": "single"},
                        "runtime": {"workspace_root": "./"},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            old_managed = os.environ.get("AGENTOS_SESSION_MANAGED")
            old_entry = os.environ.get("AGENTOS_SESSION_ENTRY")
            os.environ["AGENTOS_SESSION_MANAGED"] = "1"
            os.environ["AGENTOS_SESSION_ENTRY"] = "local_tty1"
            try:
                report = build_evidence_report(workspace=str(workspace))
            finally:
                if old_managed is None:
                    os.environ.pop("AGENTOS_SESSION_MANAGED", None)
                else:
                    os.environ["AGENTOS_SESSION_MANAGED"] = old_managed
                if old_entry is None:
                    os.environ.pop("AGENTOS_SESSION_ENTRY", None)
                else:
                    os.environ["AGENTOS_SESSION_ENTRY"] = old_entry

            self.assertEqual(report["summary"]["runtime_session_origin"], "local_managed_tty1")
            self.assertEqual(report["summary"]["session_path_family"], "legacy_compatibility")
            self.assertEqual(report["summary"]["session_compatibility_label"], "legacy_tty1_installed")

    def test_build_evidence_report_surfaces_installed_appliance_origin(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "artifacts").mkdir(parents=True, exist_ok=True)
            (workspace / "spec.yaml").write_text(
                yaml.dump(
                    {
                        "name": "evidence-installed-origin-test",
                        "kernel_engine": {"provider": "none", "mode": "single"},
                        "runtime": {"workspace_root": "./"},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            old_managed = os.environ.get("AGENTOS_SESSION_MANAGED")
            old_entry = os.environ.get("AGENTOS_SESSION_ENTRY")
            old_installed = os.environ.get("AGENTOS_INSTALLED_APPLIANCE")
            os.environ["AGENTOS_SESSION_MANAGED"] = "1"
            os.environ["AGENTOS_SESSION_ENTRY"] = "installed_appliance"
            os.environ["AGENTOS_INSTALLED_APPLIANCE"] = "1"
            try:
                report = build_evidence_report(workspace=str(workspace))
            finally:
                if old_managed is None:
                    os.environ.pop("AGENTOS_SESSION_MANAGED", None)
                else:
                    os.environ["AGENTOS_SESSION_MANAGED"] = old_managed
                if old_entry is None:
                    os.environ.pop("AGENTOS_SESSION_ENTRY", None)
                else:
                    os.environ["AGENTOS_SESSION_ENTRY"] = old_entry
                if old_installed is None:
                    os.environ.pop("AGENTOS_INSTALLED_APPLIANCE", None)
                else:
                    os.environ["AGENTOS_INSTALLED_APPLIANCE"] = old_installed

            self.assertEqual(report["summary"]["runtime_session_origin"], "installed_appliance_boot")
            self.assertEqual(report["summary"]["session_path_family"], "appliance_first")
            self.assertEqual(report["summary"]["session_compatibility_label"], "installed_appliance")


if __name__ == "__main__":
    unittest.main()
