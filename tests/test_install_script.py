"""INSTALL-XPLAT-01 #1167: the one-line installer pins what it installs.

The script itself is model-free shell. These tests run it with fake `curl`,
`uv` and `uname` on PATH so no network or real install happens; the real
download/install path is exercised by .github/workflows/install-smoke.yml.
"""
import hashlib
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install.sh"


def pin(name, text=None):
    text = SCRIPT.read_text(encoding="utf-8") if text is None else text
    match = re.search(rf'^{name}="([^"]+)"$', text, re.M)
    assert match, name
    return match.group(1)


FAKE_CURL = """#!/bin/sh
# fake curl: record the URL, write fixed bytes to the -o destination
echo "$@" >> "$FAKE_LOG"
while [ $# -gt 0 ]; do [ "$1" = "-o" ] && { printf 'agentos-archive' > "$2"; exit 0; }; shift; done
"""
FAKE_UV = """#!/bin/sh
if [ "$1" = "--version" ]; then echo "uv ${FAKE_UV_VERSION:-0.12.23}"; exit 0; fi
echo "uv $*" >> "$FAKE_LOG"
if [ "$2 $3" = "tool dir" ]; then echo "$FAKE_BIN"; fi
"""
FAKE_AGENTOS = """#!/bin/sh
echo "agentos $*" >> "$FAKE_LOG"
"""


class InstallScriptTests(unittest.TestCase):
    def run_script(self, script_text, uname="Darwin", env=None):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            bin_dir = folder / "bin"
            tool_bin = folder / "tool-bin"
            bin_dir.mkdir()
            tool_bin.mkdir()
            fakes = [(bin_dir / "curl", FAKE_CURL), (bin_dir / "uname", f"#!/bin/sh\necho {uname}\n"),
                     (tool_bin / "agentos", FAKE_AGENTOS)]
            if not (env or {}).get("NO_FAKE_UV"):
                fakes.append((bin_dir / "uv", FAKE_UV))
            for path, body in fakes:
                path.write_text(body, encoding="utf-8")
                path.chmod(0o755)
            script = folder / "install.sh"
            script.write_text(script_text, encoding="utf-8")
            log = folder / "log"
            run_env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(folder),
                       "FAKE_LOG": str(log), "FAKE_BIN": str(tool_bin), **(env or {})}
            result = subprocess.run(["sh", str(script)], env=run_env, capture_output=True,
                                    text=True, timeout=30)
            calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
            return result, calls

    def with_archive_checksum(self, digest):
        return re.sub(r'^AGENTOS_ARCHIVE_SHA256="[^"]+"$', f'AGENTOS_ARCHIVE_SHA256="{digest}"',
                      SCRIPT.read_text(encoding="utf-8"), flags=re.M)

    def test_pins_match_the_newest_published_release(self):
        manifest = json.loads((ROOT / "docs" / "release-manifest.json").read_text(encoding="utf-8"))
        newest = manifest["published"][-1]
        self.assertEqual(pin("AGENTOS_VERSION"), newest["version"])
        self.assertEqual(pin("AGENTOS_ARCHIVE_SHA256"), newest["archive_sha256"])
        self.assertRegex(pin("UV_VERSION"), r"^\d+\.\d+\.\d+$")
        self.assertRegex(pin("UV_INSTALLER_SHA256"), r"^[0-9a-f]{64}$")
        self.assertIn("https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-installer.sh",
                      SCRIPT.read_text(encoding="utf-8"))

    def test_script_is_valid_posix_shell(self):
        subprocess.run(["sh", "-n", str(SCRIPT)], check=True)

    def test_verified_archive_is_installed_with_the_homebrew_extra_and_started(self):
        digest = hashlib.sha256(b"agentos-archive").hexdigest()
        result, calls = self.run_script(self.with_archive_checksum(digest))
        self.assertEqual(result.returncode, 0, result.stderr)
        version = pin("AGENTOS_VERSION")
        self.assertTrue(any(f"archive/refs/tags/v{version}.tar.gz" in call for call in calls))
        install = next(call for call in calls if call.startswith("uv --no-config tool install"))
        self.assertIn("--python 3.13", install)
        self.assertFalse(any("uv-installer.sh" in call for call in calls), "a current uv is reused")
        self.assertRegex(install, rf"personal-agentos\[mcp-host\] @ \S+agentos-{re.escape(version)}\.tar\.gz$")
        self.assertEqual(calls[-1], "agentos start")

    def test_no_start_flag_installs_without_starting(self):
        digest = hashlib.sha256(b"agentos-archive").hexdigest()
        result, calls = self.run_script(self.with_archive_checksum(digest), env={"AGENTOS_NO_START": "1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(call.startswith("uv --no-config tool install") for call in calls))
        self.assertNotIn("agentos start", calls)

    def test_checksum_mismatch_installs_nothing(self):
        for env in ({}, {"NO_FAKE_UV": "1"}):
            with self.subTest(env=env):
                result, calls = self.run_script(SCRIPT.read_text(encoding="utf-8"), env=env)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("checksum mismatch for v", result.stderr)
                # The archive is verified before uv is fetched or used.
                self.assertFalse(any("uv-installer.sh" in call for call in calls))
                self.assertFalse(any(call.startswith("uv ") for call in calls))
                self.assertNotIn("agentos start", calls)

    def test_unverified_uv_installer_is_never_run(self):
        digest = hashlib.sha256(b"agentos-archive").hexdigest()
        for env in ({"NO_FAKE_UV": "1"}, {"FAKE_UV_VERSION": "0.1.45"}):
            with self.subTest(env=env):
                # No uv, or one too old for `uv tool`: the pinned installer is
                # fetched, and the fake bytes do not match its checksum.
                result, calls = self.run_script(self.with_archive_checksum(digest), env=env)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("uv 0", result.stderr)
                self.assertTrue(any("uv-installer.sh" in call for call in calls))
                self.assertFalse(any("tool install" in call for call in calls))

    def test_windows_shells_are_sent_to_wsl_before_any_download(self):
        for uname in ("MINGW64_NT-10.0", "MSYS_NT-10.0", "CYGWIN_NT-10.0"):
            with self.subTest(uname=uname):
                result, calls = self.run_script(SCRIPT.read_text(encoding="utf-8"), uname=uname)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("wsl --install", result.stderr)
                self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
