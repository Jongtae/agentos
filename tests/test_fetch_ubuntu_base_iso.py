from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPT = ROOT_DIR / "scripts" / "fetch_ubuntu_base_iso.sh"


class FetchUbuntuBaseIsoTests(unittest.TestCase):
    def _sha256(self, path: Path) -> str:
        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()

    def test_fetches_from_manifest_and_reuses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            source = tmp / "source.iso"
            source.write_bytes(b"agentos-test-base-iso")
            manifest = tmp / "base-image.json"
            output_dir = tmp / "cache"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": "agentos-ubuntu-base-image.v1",
                        "ubuntu_version": "24.04.4",
                        "release_codename": "noble",
                        "artifact_type": "desktop-live-iso",
                        "arch": "amd64",
                        "filename": "ubuntu-24.04.4-desktop-amd64.iso",
                        "download_url": source.as_uri(),
                        "sha256": self._sha256(source),
                    }
                ),
                encoding="utf-8",
            )

            first = subprocess.run(
                [str(SCRIPT), "--manifest", str(manifest), "--output-dir", str(output_dir), "--print-path"],
                check=True,
                capture_output=True,
                text=True,
            )
            resolved = Path(first.stdout.strip())
            self.assertTrue(resolved.exists())
            self.assertEqual(resolved.read_bytes(), source.read_bytes())

            second = subprocess.run(
                [str(SCRIPT), "--manifest", str(manifest), "--output-dir", str(output_dir), "--print-path"],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(second.stdout.strip(), str(resolved))

    def test_rejects_bad_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            source = tmp / "source.iso"
            source.write_bytes(b"agentos-test-base-iso")
            manifest = tmp / "base-image.json"
            output_dir = tmp / "cache"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": "agentos-ubuntu-base-image.v1",
                        "ubuntu_version": "24.04.4",
                        "release_codename": "noble",
                        "artifact_type": "desktop-live-iso",
                        "arch": "amd64",
                        "filename": "ubuntu-24.04.4-desktop-amd64.iso",
                        "download_url": source.as_uri(),
                        "sha256": "0" * 64,
                    }
                ),
                encoding="utf-8",
            )

            proc = subprocess.run(
                [str(SCRIPT), "--manifest", str(manifest), "--output-dir", str(output_dir), "--print-path"],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("checksum mismatch", proc.stderr.lower())


if __name__ == "__main__":
    unittest.main()
