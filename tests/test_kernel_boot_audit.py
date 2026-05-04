from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.kernel_boot_audit import audit_report


class KernelBootAuditTests(unittest.TestCase):
    def test_audit_includes_shadow_summary(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        install_root = root / "install"
        workspace = root / "workspace"

        (install_root / "etc/systemd/system/getty@tty1.service.d").mkdir(parents=True, exist_ok=True)
        (install_root / "etc/profile.d").mkdir(parents=True, exist_ok=True)
        (install_root / "usr/local/bin").mkdir(parents=True, exist_ok=True)
        (install_root / "etc/systemd/system").mkdir(parents=True, exist_ok=True)
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "artifacts").mkdir(parents=True, exist_ok=True)

        (install_root / "etc/systemd/system/agentos-kernel.service").write_text(
            "ExecStart=/usr/local/bin/agentos-shell --kernel-mode --doctor --preflight\n",
            encoding="utf-8",
        )
        (install_root / "etc/systemd/system/getty@tty1.service.d/override.conf").write_text(
            "--autologin agentos\n",
            encoding="utf-8",
        )
        (install_root / "etc/profile.d/agentos-kernel-autostart.sh").write_text(
            "exec agentos-shell --kernel-mode\n",
            encoding="utf-8",
        )
        (install_root / "usr/local/bin/agentos-shell").write_text("#!/bin/sh\n", encoding="utf-8")
        (install_root / "usr/local/bin/agentos-kernelctl").write_text("#!/bin/sh\n", encoding="utf-8")
        (workspace / "artifacts" / "runtime_trace.jsonl").write_text(
            "\n".join(
                [
                    '{"timestamp_utc":"2026-04-14T00:00:01+00:00","event":"step_blocked","payload":{"reason":"workspace_boundary","detail":"../outside.txt"}}',
                    '{"timestamp_utc":"2026-04-14T00:00:02+00:00","event":"step_blocked","payload":{"reason":"network_allowlist","detail":"blocked.example"}}',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (workspace / "artifacts" / "os_events.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "timestamp_utc": "2026-04-14T00:00:01+00:00",
                            "source": "journald",
                            "kind": "session.login",
                            "actor": {"pid": 7},
                            "object": {"session_id": "8", "user_name": "agentos"},
                            "action": "login",
                            "decision": {"state": "observed"},
                            "correlation": {"session_id": "8", "boot_id": "boot-1", "session_origin": "local_managed_tty1"},
                            "raw_ref": {"collector": "journald_systemd_logind"},
                        }
                    ),
                    json.dumps(
                        {
                            "timestamp_utc": "2026-04-14T00:00:02+00:00",
                            "source": "kernel",
                            "kind": "file.outside_workspace_candidate",
                            "actor": {"pid": 7},
                            "object": {"path": "/tmp/outside.txt", "workspace_root": str(workspace)},
                            "action": "read",
                            "decision": {"state": "candidate", "policy_target": "fs_workspace_boundary"},
                            "correlation": {"session_id": "8", "boot_id": "boot-1", "request_id": "req-boot"},
                            "raw_ref": {"collector": "file_access_candidate"},
                        }
                    ),
                    json.dumps(
                        {
                            "timestamp_utc": "2026-04-14T00:00:03+00:00",
                            "source": "journald",
                            "kind": "systemd.unit_state",
                            "actor": {"pid": 7},
                            "object": {"unit": "agentos-kernel.service", "state": "started", "state_family": "active", "session_id": "8"},
                            "action": "state_change",
                            "decision": {"state": "observed"},
                            "correlation": {"session_id": "8", "boot_id": "boot-1", "next_managed_entry": "ai_shell"},
                            "raw_ref": {"collector": "journald_systemd_logind"},
                        }
                    ),
                    json.dumps(
                        {
                            "timestamp_utc": "2026-04-14T00:00:04+00:00",
                            "source": "kernel",
                            "kind": "network.connect_candidate",
                            "actor": {"pid": 7},
                            "object": {"host": "blocked.example", "port": 443, "allowlist": ["openai.com"]},
                            "action": "connect",
                            "decision": {"state": "candidate", "policy_target": "network_allowlist"},
                            "correlation": {"session_id": "8", "boot_id": "boot-1", "request_id": "req-boot"},
                            "raw_ref": {"collector": "network_connect_candidate"},
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        shadow_cmd = root / "fake-shadow.py"
        shadow_cmd.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env python3",
                    "import json",
                    "print(json.dumps({",
                    "  'policy_target': 'fs_workspace_boundary',",
                    "  'comparison': {'aligned': True, 'delta': 0},",
                    "  'user_space_blocked_count': 1,",
                    "  'shadow_detected_count': 1,",
                    "  'coverage_summary': {'policy_target_count': 2, 'aligned_count': 2, 'divergent_count': 0},",
                    "  'policy_targets': [",
                    "    {'policy_target': 'fs_workspace_boundary', 'comparison': {'status': 'aligned', 'delta': 0}},",
                    "    {'policy_target': 'network_allowlist', 'comparison': {'status': 'aligned', 'delta': 0}}",
                    "  ]",
                    "}))",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        shadow_cmd.chmod(0o755)

        payload = audit_report(
            install_root=str(install_root),
            workspace=str(workspace),
            shadow_cmd=str(shadow_cmd),
        )
        self.assertTrue(payload["ok"])
        self.assertIn("shadow_mode", payload)
        self.assertTrue(payload["shadow_mode"]["available"])
        self.assertTrue(payload["shadow_mode"]["aligned"])
        self.assertEqual(payload["shadow_mode"]["delta"], 0)
        self.assertEqual(payload["shadow_mode"]["coverage_summary"]["policy_target_count"], 2)
        self.assertEqual(len(payload["shadow_mode"]["policy_targets"]), 2)
        self.assertEqual(payload["event_fabric"]["next_policy_target"], "destructive_action_approval")
        self.assertIn("event_fabric", payload)
        self.assertTrue(payload["event_fabric"]["available"])
        self.assertTrue(payload["event_fabric"]["event_file_exists"])
        self.assertEqual(payload["event_fabric"]["total_events"], 4)
        self.assertIn("file.outside_workspace_candidate", payload["event_fabric"]["recent_kinds"])
        self.assertEqual(payload["event_fabric"]["session_ownership"]["session_phase"], "ai_shell")
        self.assertEqual(payload["event_fabric"]["session_correlation"]["boot_ids"], ["boot-1"])
        coverage = payload["event_fabric"].get("collector_coverage", {})
        self.assertIn("observed_sources", coverage)
        self.assertIn("kind_counts", coverage)
        self.assertIn("gaps", coverage)


if __name__ == "__main__":
    unittest.main()
