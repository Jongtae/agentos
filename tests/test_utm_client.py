from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from utm_client import UTMError, _UtmctlBackend, _http, _strip_event_noise, _vm_is_running


class UtmClientParsingTests(unittest.TestCase):
    def test_strip_event_noise_removes_apple_event_warnings(self) -> None:
        raw = (
            "Error from event: The operation couldn’t be completed. (OSStatus error -10004.)\n"
            "NOTE: utmctl does not work from SSH sessions or before logging in.\n"
            "started\n"
        )
        self.assertEqual(_strip_event_noise(raw), "started")

    def test_vm_is_running_accepts_started_and_suspended(self) -> None:
        self.assertTrue(_vm_is_running("started"))
        self.assertTrue(_vm_is_running("Status: suspended"))
        self.assertFalse(_vm_is_running("stopped"))

    def test_http_wraps_timeout_as_utm_error(self) -> None:
        with patch("utm_client.urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaises(UTMError) as exc:
                _http("GET", "http://127.0.0.1:1/health", timeout=1)
        self.assertIn("timed out", str(exc.exception))

    def test_utmctl_backend_run_wraps_timeout(self) -> None:
        backend = _UtmctlBackend()
        with patch("utm_client.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["utmctl", "list"], timeout=30)):
            with self.assertRaises(UTMError) as exc:
                backend._run("list")
        self.assertIn("timed out", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
