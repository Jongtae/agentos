import json
import os
import subprocess
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path
import importlib.util
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cleanup_temp_artifacts.py"
SPEC = importlib.util.spec_from_file_location("cleanup_temp_artifacts", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["cleanup_temp_artifacts"] = MODULE
SPEC.loader.exec_module(MODULE)


class CleanupTempArtifactsTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.private_tmp = self.root / "private-tmp"
        self.var_folders = self.root / "var-folders"
        self.private_tmp.mkdir(parents=True)
        self.var_folders.mkdir(parents=True)

    def tearDown(self):
        self.tempdir.cleanup()

    def _run(self, *args):
        return subprocess.run(
            ["python3", str(SCRIPT), *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def _olden(self, path: Path):
        old_time = time.time() - (48 * 3600)
        os.utime(path, (old_time, old_time))

    def test_detects_old_private_tmp_remaster_artifact(self):
        image = self.private_tmp / "agentos-remaster-7.sparseimage"
        image.write_bytes(b"stub")
        self._olden(image)

        result = self._run(
            "--json",
            "--private-tmp-root",
            str(self.private_tmp),
            "--var-folders-root",
            str(self.var_folders),
        )
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["stale_candidate_count"], 1)
        self.assertEqual(payload["candidates"][0]["kind"], "private_tmp_remaster_artifact")

    def test_detects_old_var_folders_remaster_dir_with_markers(self):
        path = self.var_folders / "fd" / "token" / "T" / "tmp.abc123"
        (path / "casper").mkdir(parents=True)
        big_file = path / "casper" / "filesystem.squashfs"
        big_file.write_bytes(b"0" * (1024 * 1024))
        self._olden(path)
        self._olden(path / "casper")
        self._olden(big_file)

        result = self._run(
            "--json",
            "--min-tmp-dir-size-mb",
            "0",
            "--private-tmp-root",
            str(self.private_tmp),
            "--var-folders-root",
            str(self.var_folders),
        )
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["stale_candidate_count"], 1)
        self.assertEqual(payload["candidates"][0]["kind"], "var_folders_remaster_tmpdir")
        self.assertIn("casper", payload["candidates"][0]["markers"])

    def test_delete_removes_stale_candidates(self):
        image = self.private_tmp / "agentos-remaster-4.sparseimage"
        image.write_bytes(b"stub")
        self._olden(image)

        result = self._run(
            "--delete",
            "--json",
            "--private-tmp-root",
            str(self.private_tmp),
            "--var-folders-root",
            str(self.var_folders),
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["deleted_count"], 1)
        self.assertFalse(image.exists())

    def test_in_use_candidates_are_not_stale_failures(self):
        image = self.private_tmp / "agentos-remaster-8.sparseimage"
        image.write_bytes(b"stub")
        self._olden(image)
        with mock.patch.object(MODULE, "_path_in_use", return_value=True):
            candidates = MODULE._collect_candidates(
                private_tmp_root=self.private_tmp,
                var_folders_root=self.var_folders,
                older_than_hours=24.0,
                min_tmp_dir_size_mb=512,
            )
        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0].in_use)


if __name__ == "__main__":
    unittest.main()
