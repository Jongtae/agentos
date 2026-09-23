import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import verify_readme_localization as verifier


class ReadmeLocalizationParityTests(unittest.TestCase):
    def test_current_public_readmes_have_semantic_structural_parity(self):
        self.assertEqual([], verifier.validate_readmes(ROOT))

    def test_missing_semantic_section_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in verifier.READMES:
                shutil.copyfile(ROOT / name, root / name)

            target = root / "README.ja.md"
            body = target.read_text(encoding="utf-8")
            body = body.replace(
                "<!-- readme-section:everyday-scene -->", "", 1
            )
            target.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any(
                    "README.ja.md" in error
                    and "readme-section:everyday-scene" in error
                    for error in errors
                ),
                errors,
            )

    def test_shared_install_fact_drift_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in verifier.READMES:
                shutil.copyfile(ROOT / name, root / name)

            target = root / "README.zh-CN.md"
            body = target.read_text(encoding="utf-8")
            body = body.replace(
                "brew install jongtae/agentos/agentos",
                "brew install some/stale/formula",
                1,
            )
            target.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any(
                    "README.zh-CN.md" in error
                    and "brew install jongtae/agentos/agentos" in error
                    for error in errors
                ),
                errors,
            )

    def test_canonical_readme_change_requires_all_locales(self):
        errors = verifier.validate_changed_paths({"README.md", "README.ko.md"})
        self.assertEqual(1, len(errors))
        self.assertIn("README.ja.md", errors[0])
        self.assertIn("README.zh-CN.md", errors[0])

    def test_canonical_readme_change_with_all_locales_passes(self):
        self.assertEqual(
            [],
            verifier.validate_changed_paths(set(verifier.READMES)),
        )

    def test_locale_only_fix_does_not_force_unrelated_locale_churn(self):
        self.assertEqual(
            [],
            verifier.validate_changed_paths({"README.ko.md"}),
        )


if __name__ == "__main__":
    unittest.main()
