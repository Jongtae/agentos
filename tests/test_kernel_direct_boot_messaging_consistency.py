from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kernel_direct_boot_messaging_consistency import (
    build_direct_boot_messaging_consistency,
    validate_direct_boot_messaging_consistency,
)


class KernelDirectBootMessagingConsistencyTests(unittest.TestCase):
    def test_build_direct_boot_messaging_consistency_writes_expected_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            artifacts = workspace / "artifacts"
            artifacts.mkdir(parents=True)
            docs_root = Path(tmpdir) / "docs-root"
            (docs_root / "docs/runbooks").mkdir(parents=True)
            (docs_root / "README.md").write_text(
                "brew install --cask utm\nAgentOS Setup -> AgentOS Managed Session -> ai>\nAgentOS Recovery\nAgentOS Recovery -> Return to AgentOS -> ai>\n",
                encoding="utf-8",
            )
            (docs_root / "docs/runbooks/vm-install-quickstart.md").write_text(
                "Continue to AgentOS\nInstall AgentOS\nmake this appliance persistent\nAgentOS Recovery\nAgentOS Recovery -> Return to AgentOS -> ai>\nAgentOS Setup -> AgentOS Managed Session -> ai>\n",
                encoding="utf-8",
            )
            (docs_root / "docs/runbooks/vm-install-guide.md").write_text(
                "Continue to AgentOS\nInstall AgentOS\nmake this appliance persistent\nAgentOS Recovery\nAgentOS Recovery -> Return to AgentOS -> ai>\nAgentOS Setup -> AgentOS Managed Session -> ai>\n",
                encoding="utf-8",
            )
            (docs_root / "docs/runbooks/agentos-operations-runbook.md").write_text(
                "Continue to AgentOS\nmake this appliance persistent\nAgentOS Recovery\nAgentOS Recovery -> Return to AgentOS -> ai>\nboot AgentOS -> tiny setup -> ai>\n",
                encoding="utf-8",
            )
            (docs_root / "docs/runbooks/distribution-packaging-runbook.md").write_text(
                "AgentOS Setup -> AgentOS Managed Session -> ai>\nAgentOS Recovery\nadvanced/fallback reference\n",
                encoding="utf-8",
            )

            payload = build_direct_boot_messaging_consistency(
                workspace=str(workspace),
                report_dir=str(artifacts),
                docs_root=str(docs_root),
                snapshot_label="consistency",
            )

            self.assertEqual(payload["schema_version"], "agentos-direct-boot-messaging-consistency.v1")
            self.assertTrue(Path(payload["artifacts"]["direct_boot_messaging_consistency_manifest_json"]).exists())
            self.assertEqual(payload["summary"]["overall_state"], "ready")
            self.assertEqual(payload["summary"]["install_later_messaging"], "ready")
            self.assertEqual(payload["summary"]["recovery_messaging"], "ready")
            self.assertEqual(validate_direct_boot_messaging_consistency(payload), [])


if __name__ == "__main__":
    unittest.main()
