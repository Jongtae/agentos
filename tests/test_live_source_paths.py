from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.live_source_paths import resolve_live_source_paths


class LiveSourcePathsTests(unittest.TestCase):
    def test_resolves_layered_paths_from_install_sources_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            iso_root = Path(td)
            (iso_root / "casper").mkdir(parents=True, exist_ok=True)
            (iso_root / "casper" / "install-sources.yaml").write_text(
                "- default: true\n"
                "  path: minimal.squashfs\n"
                "  variations:\n"
                "    minimal:\n"
                "      path: minimal.squashfs\n"
                "- default: false\n"
                "  path: minimal.standard.squashfs\n"
                "  variations:\n"
                "    standard:\n"
                "      path: minimal.standard.squashfs\n"
                "    enhanced-secureboot:\n"
                "      path: minimal.standard.enhanced-secureboot.squashfs\n",
                encoding="utf-8",
            )
            for name in ("minimal.squashfs", "minimal.standard.squashfs", "minimal.standard.live.squashfs"):
                (iso_root / "casper" / name).write_text("stub\n", encoding="utf-8")

            paths = [str(path.relative_to(iso_root)) for path in resolve_live_source_paths(iso_root)]

            self.assertEqual(
                paths,
                [
                    "casper/minimal.squashfs",
                    "casper/minimal.standard.squashfs",
                    "casper/minimal.standard.live.squashfs",
                ],
            )

    def test_falls_back_to_single_squashfs_when_install_sources_absent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            iso_root = Path(td)
            (iso_root / "casper").mkdir(parents=True, exist_ok=True)
            (iso_root / "casper" / "filesystem.squashfs").write_text("stub\n", encoding="utf-8")

            paths = [str(path.relative_to(iso_root)) for path in resolve_live_source_paths(iso_root)]
            self.assertEqual(paths, ["casper/filesystem.squashfs"])


if __name__ == "__main__":
    unittest.main()
