import importlib.util
from pathlib import Path
import shlex
import stat
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("prepare_smoke", Path(__file__).resolve().parents[1] / "scripts/prepare_owner_smoke.py")
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


class SmokeSetupTests(unittest.TestCase):
    def test_creates_only_synthetic_state_and_quoted_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "new root"
            result = smoke.prepare(root, 8788, {})
            self.assertEqual((root / "reference/launch.md").read_text(), smoke.NOTE)
            self.assertEqual(list((root / "state").iterdir()), [])
            self.assertEqual(list((root / "workspace").iterdir()), [])
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((root / "reference/launch.md").stat().st_mode), 0o600)
            self.assertEqual(shlex.split(result["start_command"])[-2:], ["--data", str(root / "state")])
            self.assertFalse(result["service_started"])
            self.assertFalse(result["private_data_copied"])
            self.assertEqual(result["provider_calls"], 0)

    def test_existing_root_not_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "keep").write_text("original")
            with self.assertRaises(FileExistsError): smoke.prepare(root, 8788, {})
            self.assertEqual(list(root.iterdir()), [root / "keep"])
            self.assertEqual((root / "keep").read_text(), "original")

    def test_inherited_state_and_integration_refused_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            for key in ("AGENTOS_DATA", "AGENTOS_DRIVE_LOCAL_ONLY", "AGENTOS_ISOLATED_ENGINE_URL", "AGENTOS_PUBLIC_ACCESS_TOKEN"):
                with self.subTest(key=key):
                    root = Path(tmp) / key
                    with self.assertRaises(ValueError) as caught:
                        smoke.prepare(root, 8788, {key: "SECRET_CANARY"})
                    self.assertNotIn("SECRET_CANARY", str(caught.exception))
                    self.assertFalse(root.exists())

    def test_bad_port_no_side_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            for port in (0, 80, 65536):
                with self.subTest(port=port):
                    root = Path(tmp) / str(port)
                    with self.assertRaises(ValueError): smoke.prepare(root, port, {})
                    self.assertFalse(root.exists())

    def test_symlink_root_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"; target.mkdir()
            root = Path(tmp) / "link"; root.symlink_to(target, target_is_directory=True)
            with self.assertRaises(FileExistsError): smoke.prepare(root, 8788, {})
            self.assertEqual(list(target.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
