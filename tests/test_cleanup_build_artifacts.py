import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cleanup_build_artifacts.py"


class CleanupBuildArtifactsTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.build_root = Path(self.tempdir.name) / "build-output"
        (self.build_root / "release").mkdir(parents=True)
        (self.build_root / "iso-assets").mkdir(parents=True)

    def tearDown(self):
        self.tempdir.cleanup()

    def _run(self, *args):
        return subprocess.run(
            ["python3", str(SCRIPT), "--build-root", str(self.build_root), *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_missing_build_root_passes_with_no_candidates(self):
        missing_root = Path(self.tempdir.name) / "missing-build-output"
        result = subprocess.run(
            ["python3", str(SCRIPT), "--build-root", str(missing_root), "--json"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["policy_status"], "pass")
        self.assertEqual(payload["stale_candidate_count"], 0)
        self.assertEqual(payload["build_root"], str(missing_root.resolve()))

    def test_detects_old_releases_and_smoke_artifacts(self):
        for version in ("0.36.60", "0.36.61", "0.36.62"):
            (self.build_root / "release" / f"agentos-v{version}-amd64.iso").write_bytes(b"x" * 8)
            (self.build_root / f"manifest-v{version}.txt").write_text("manifest\n", encoding="utf-8")
            (self.build_root / "iso-assets" / f"v{version}").mkdir(parents=True, exist_ok=True)
            (self.build_root / f"remaster-v{version}").mkdir(parents=True, exist_ok=True)
        (self.build_root / "release" / "agentos-v0.36.62-boot-test.iso").write_bytes(b"x")
        (self.build_root / "manifest-vsmoke-iso-123.txt").write_text("tmp\n", encoding="utf-8")
        (self.build_root / "remaster-vsmoke-iso-123").mkdir()
        (self.build_root / "iso-assets" / "vsmoke-iso-123").mkdir()

        result = self._run("--json", "--keep-release-count", "2")
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        kinds = {candidate["kind"] for candidate in payload["candidates"]}
        self.assertIn("release_iso", kinds)
        self.assertIn("release_boot_test", kinds)
        self.assertIn("manifest_ephemeral", kinds)
        self.assertIn("remaster_smoke_dir", kinds)
        self.assertIn("iso_assets_smoke_dir", kinds)

    def test_detects_old_arm64_releases(self):
        for version in ("0.36.60", "0.36.61", "0.36.62"):
            (self.build_root / "release" / f"agentos-v{version}-arm64.iso").write_bytes(b"x" * 8)
            (self.build_root / f"manifest-v{version}.txt").write_text("manifest\n", encoding="utf-8")

        result = self._run("--json", "--keep-release-count", "1")
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        release_candidates = [candidate["path"] for candidate in payload["candidates"] if candidate["kind"] == "release_iso"]
        self.assertTrue(any(path.endswith("agentos-v0.36.60-arm64.iso") for path in release_candidates))
        self.assertTrue(any(path.endswith("agentos-v0.36.61-arm64.iso") for path in release_candidates))

    def test_delete_keeps_only_latest_regular_releases(self):
        for version in ("0.36.60", "0.36.61", "0.36.62", "0.36.63"):
            (self.build_root / "release" / f"agentos-v{version}-amd64.iso").write_bytes(b"x")
            (self.build_root / f"manifest-v{version}.txt").write_text("manifest\n", encoding="utf-8")
            (self.build_root / "iso-assets" / f"v{version}").mkdir(parents=True, exist_ok=True)
            (self.build_root / f"remaster-v{version}").mkdir(parents=True, exist_ok=True)

        result = self._run("--delete", "--json", "--keep-release-count", "2")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["stale_candidate_count"], 0)
        self.assertTrue((self.build_root / "release" / "agentos-v0.36.62-amd64.iso").exists())
        self.assertTrue((self.build_root / "release" / "agentos-v0.36.63-amd64.iso").exists())
        self.assertFalse((self.build_root / "release" / "agentos-v0.36.60-amd64.iso").exists())
        self.assertFalse((self.build_root / "release" / "agentos-v0.36.61-amd64.iso").exists())


if __name__ == "__main__":
    unittest.main()
