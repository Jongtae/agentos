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
    def copy_public_readmes(self, root):
        for name in verifier.READMES:
            shutil.copyfile(ROOT / name, root / name)
        shutil.copyfile(
            ROOT / "docs" / "release-manifest.json",
            root / "docs" / "release-manifest.json",
        )

    def temp_root(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        (root / "docs").mkdir()
        self.copy_public_readmes(root)
        return tmp, root

    def test_current_public_readmes_have_semantic_structural_parity(self):
        self.assertEqual([], verifier.validate_readmes(ROOT))

    def test_missing_semantic_section_is_detected(self):
        tmp, root = self.temp_root()
        with tmp:
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
                    and (
                        "section sequence differs" in error
                        or "missing a readme-section marker" in error
                    )
                    for error in errors
                ),
                errors,
            )

    def test_new_canonical_section_cannot_be_english_only(self):
        tmp, root = self.temp_root()
        with tmp:
            target = root / "README.md"
            body = target.read_text(encoding="utf-8")
            insertion = (
                "<!-- readme-section:pricing -->\n\n"
                "## Pricing\n\n"
                "Includes autonomous checkout.\n\n"
            )
            body = body.replace(
                "<!-- readme-section:development -->",
                insertion + "<!-- readme-section:development -->",
                1,
            )
            target.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any(
                    "README.ko.md" in error
                    and "section sequence differs" in error
                    and "pricing" in error
                    for error in errors
                ),
                errors,
            )

    def test_new_unmarked_canonical_h2_is_rejected(self):
        tmp, root = self.temp_root()
        with tmp:
            target = root / "README.md"
            body = target.read_text(encoding="utf-8")
            body = body.replace(
                "<!-- readme-section:development -->",
                "## Pricing\n\nA new user-facing section.\n\n"
                "<!-- readme-section:development -->",
                1,
            )
            target.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any(
                    "README.md" in error
                    and "H2 '## Pricing'" in error
                    and "missing a readme-section marker" in error
                    for error in errors
                ),
                errors,
            )

    def test_new_unmarked_setext_h2_is_rejected(self):
        tmp, root = self.temp_root()
        with tmp:
            target = root / "README.md"
            body = target.read_text(encoding="utf-8")
            body = body.replace(
                "Personal AgentOS is not trying to make every action autonomous.",
                "Pricing\n-------\n\nPro tier includes autonomous checkout.\n\n"
                "Personal AgentOS is not trying to make every action autonomous.",
                1,
            )
            target.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any(
                    "README.md" in error
                    and "H2 'Pricing'" in error
                    and "missing a readme-section marker" in error
                    for error in errors
                ),
                errors,
            )

    def test_product_direction_disclaimer_deletion_is_detected(self):
        tmp, root = self.temp_root()
        with tmp:
            target = root / "README.ko.md"
            body = target.read_text(encoding="utf-8")
            body = body.replace(
                verifier.PRODUCT_DIRECTION_DISCLAIMERS["README.ko.md"],
                "",
                1,
            )
            target.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any(
                    "README.ko.md" in error
                    and "not-shipped capability disclaimer" in error
                    for error in errors
                ),
                errors,
            )

    def test_product_direction_disclaimer_inversion_is_detected(self):
        tmp, root = self.temp_root()
        with tmp:
            target = root / "README.ko.md"
            body = target.read_text(encoding="utf-8")
            body = body.replace(
                verifier.PRODUCT_DIRECTION_DISCLAIMERS["README.ko.md"],
                "**이 장면처럼 자율 구매와 결제를 지금 사용할 수 있습니다.**",
                1,
            )
            target.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any(
                    "README.ko.md" in error
                    and "not-shipped capability disclaimer" in error
                    for error in errors
                ),
                errors,
            )

    def test_product_direction_label_deletion_is_detected(self):
        tmp, root = self.temp_root()
        with tmp:
            target = root / "README.ko.md"
            body = target.read_text(encoding="utf-8")
            body = body.replace(
                verifier.PRODUCT_DIRECTION_LABELS["README.ko.md"],
                "",
                1,
            )
            target.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any(
                    "README.ko.md" in error
                    and "missing its visible product-direction label" in error
                    for error in errors
                ),
                errors,
            )

    def test_product_direction_label_must_stay_before_scene(self):
        tmp, root = self.temp_root()
        with tmp:
            target = root / "README.zh-CN.md"
            body = target.read_text(encoding="utf-8")
            label = verifier.PRODUCT_DIRECTION_LABELS["README.zh-CN.md"]
            body = body.replace(label + "\n\n", "", 1)
            scene_end = (
                "> **Personal AgentOS：**收集被允许的上下文，调查选项，"
                "把已确认的信息和仍需核实的内容分开，准备下一步，并在需要批准的边界停下。"
            )
            body = body.replace(scene_end, scene_end + "\n\n" + label, 1)
            target.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any(
                    "README.zh-CN.md" in error
                    and "label must appear before" in error
                    for error in errors
                ),
                errors,
            )

    def test_status_live_evidence_inversion_is_detected(self):
        tmp, root = self.temp_root()
        with tmp:
            target = root / "README.md"
            body = target.read_text(encoding="utf-8")
            body = body.replace(
                verifier.STATUS_EVIDENCE_BOUNDARIES["README.md"],
                "**live provider operation was run**",
                1,
            )
            target.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any(
                    "README.md" in error
                    and "synthetic-vs-live evidence boundary" in error
                    for error in errors
                ),
                errors,
            )

    def test_status_row_evidence_class_inversion_is_detected(self):
        for name, replacement in (
            ("README.md", "**Live provider verified**"),
            ("README.ko.md", "**실제 제공자 검증 완료**"),
        ):
            with self.subTest(readme=name):
                tmp, root = self.temp_root()
                with tmp:
                    target = root / name
                    body = target.read_text(encoding="utf-8")
                    body = body.replace(
                        verifier.STATUS_ROW_EVIDENCE_TOKEN,
                        replacement,
                    )
                    target.write_text(body, encoding="utf-8")

                    errors = verifier.validate_readmes(root)
                    if name == "README.md":
                        expected = (
                            "README.md: status section lost every synthetic "
                            "pass-with-friction row"
                        )
                    else:
                        expected = f"{name}: status evidence-class count differs"
                    self.assertTrue(
                        any(error.startswith(expected) for error in errors),
                        errors,
                    )

    def test_canonical_status_cannot_drop_every_synthetic_row(self):
        """The zero-row guard is the fail-closed backstop for #472 evidence."""
        tmp, root = self.temp_root()
        with tmp:
            target = root / "README.md"
            body = target.read_text(encoding="utf-8")
            body = body.replace(
                verifier.STATUS_ROW_EVIDENCE_TOKEN, "**Live provider verified**"
            )
            target.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any(
                    error.startswith(
                        "README.md: status section lost every synthetic "
                        "pass-with-friction row"
                    )
                    for error in errors
                ),
                errors,
            )

    def test_heading_like_text_inside_a_fenced_block_is_not_a_section(self):
        """Fenced samples may contain heading-like text without breaking parity.

        A fence must also not silence the public H2 checks that follow it, so
        both fence styles are opened and closed here.
        """
        fixtures = (
            "```\nPricing\n---\n```",
            "```text\nPricing\n---\n```",
            "~~~\nPricing\n---\n~~~",
            "```text\nfence styles:\n~~~\n```",
        )
        anchor = "<!-- readme-section:architecture -->"
        for fence in fixtures:
            with self.subTest(fence=fence.splitlines()[0]):
                tmp, root = self.temp_root()
                with tmp:
                    target = root / "README.md"
                    body = target.read_text(encoding="utf-8")
                    self.assertIn(anchor, body)
                    target.write_text(
                        body.replace(anchor, fence + "\n\n" + anchor, 1),
                        encoding="utf-8",
                    )
                    self.assertEqual([], verifier.validate_readmes(root))

    def test_a_fenced_block_cannot_silence_later_public_headings(self):
        """An unmatched fence style inside a sample must not disable parity."""
        tmp, root = self.temp_root()
        with tmp:
            target = root / "README.md"
            clean = target.read_text(encoding="utf-8")
            hero = "## Delegate the work. Keep the control."
            heading = "## Owner control by design"
            self.assertIn(hero, clean)
            self.assertIn(heading, clean)

            fenced = clean.replace(
                hero, hero + "\n\n```text\nfence styles:\n~~~\n```", 1
            )
            # The fenced sample itself is legitimate content.
            self.assertEqual(
                len(verifier.public_h2_indexes(clean)),
                len(verifier.public_h2_indexes(fenced)),
            )

            smuggled = fenced.replace(
                heading, "## Pricing\n\nUnannounced.\n\n" + heading, 1
            )
            self.assertEqual(
                len(verifier.public_h2_indexes(clean)) + 1,
                len(verifier.public_h2_indexes(smuggled)),
            )

            target.write_text(smuggled, encoding="utf-8")
            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any(
                    error.startswith("README.md: H2 ")
                    and "missing a readme-section marker" in error
                    for error in errors
                ),
                errors,
            )

    def test_shared_install_fact_drift_is_detected(self):
        tmp, root = self.temp_root()
        with tmp:
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

    def test_published_release_fact_comes_from_manifest(self):
        tmp, root = self.temp_root()
        with tmp:
            manifest = root / "docs" / "release-manifest.json"
            body = manifest.read_text(encoding="utf-8")
            body = body.replace('"version": "1.0.4"', '"version": "9.9.9"', 1)
            manifest.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any("expected exactly one 'v9.9.9'" in error for error in errors),
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
