from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
BOOTSTRAP = ROOT_DIR / "image-assets" / "live" / "bin" / "agentos-live-session-bootstrap"


class AgentOSLiveSessionBootstrapTests(unittest.TestCase):
    def test_bootstrap_records_started_and_spawned_states(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_dir = root / "state"
            launcher = root / "launcher.sh"
            marker = root / "launcher-invoked"
            launcher.write_text(
                "#!/usr/bin/env bash\n"
                "printf 'launcher:%s\\n' \"$1\" > \"" + str(marker) + "\"\n"
                "cat > \"" + str(state_dir / "welcome-status.json") + "\" <<'EOF'\n"
                '{"component":"agentos-welcome-shell","state":"continue_selected"}\n'
                "EOF\n"
                "sleep 1\n",
                encoding="utf-8",
            )
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
            env = dict(os.environ)
            env["AGENTOS_LIVE_BOOTSTRAP_STATE_DIR"] = str(state_dir)
            env["AGENTOS_SKIP_GUEST_AGENT_BOOTSTRAP"] = "1"
            env["AGENTOS_WELCOME_LAUNCHER"] = str(launcher)
            env["AGENTOS_WELCOME_ACTION"] = "continue"
            proc = subprocess.run(
                ["bash", str(BOOTSTRAP)],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            self.assertEqual(proc.returncode, 0)
            status = json.loads((state_dir / "live-session-status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["state"], "welcome_launch_succeeded")
            self.assertEqual(status["launch_method"], "custom_launcher")
            self.assertTrue(marker.exists())

    def test_bootstrap_records_failed_launcher_when_no_welcome_status_appears(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_dir = root / "state"
            launcher = root / "launcher.sh"
            launcher.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' 'launcher failed' >&2\n"
                "exit 1\n",
                encoding="utf-8",
            )
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
            env = dict(os.environ)
            env["AGENTOS_LIVE_BOOTSTRAP_STATE_DIR"] = str(state_dir)
            env["AGENTOS_SKIP_GUEST_AGENT_BOOTSTRAP"] = "1"
            env["AGENTOS_WELCOME_LAUNCHER"] = str(launcher)
            env["AGENTOS_WELCOME_BIN"] = str(root / "missing-welcome-shell")
            proc = subprocess.run(
                ["bash", str(BOOTSTRAP)],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            self.assertEqual(proc.returncode, 41)
            status = json.loads((state_dir / "live-session-status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["state"], "live_session_takeover_failure")


if __name__ == "__main__":
    unittest.main()
