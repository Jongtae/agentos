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
        for rel in ("docs/release-manifest.json", *verifier.STATUS_DOCS):
            shutil.copyfile(ROOT / rel, root / rel)

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
                "<!-- readme-section:scenes-today -->", "", 1
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
                "<!-- readme-section:more -->",
                insertion + "<!-- readme-section:more -->",
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
                "<!-- readme-section:more -->",
                "## Pricing\n\nA new user-facing section.\n\n"
                "<!-- readme-section:more -->",
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
                "That is all of it.",
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
            target = root / "docs" / "product-status.ko.md"
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
                    "product-status.ko.md" in error
                    and "not-shipped capability disclaimer" in error
                    for error in errors
                ),
                errors,
            )

    def test_product_direction_disclaimer_inversion_is_detected(self):
        tmp, root = self.temp_root()
        with tmp:
            target = root / "docs" / "product-status.ko.md"
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
                    "product-status.ko.md" in error
                    and "not-shipped capability disclaimer" in error
                    for error in errors
                ),
                errors,
            )

    def test_product_direction_label_deletion_is_detected(self):
        tmp, root = self.temp_root()
        with tmp:
            target = root / "docs" / "product-status.ko.md"
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
                    "product-status.ko.md" in error
                    and "missing its visible product-direction label" in error
                    for error in errors
                ),
                errors,
            )

    def test_product_direction_label_must_stay_before_scene(self):
        tmp, root = self.temp_root()
        with tmp:
            target = root / "docs" / "product-status.en.md"
            body = target.read_text(encoding="utf-8")
            label = verifier.PRODUCT_DIRECTION_LABELS["README.md"]
            body = body.replace(label + "\n\n", "", 1)
            scene_end = (
                "> **Personal AgentOS:** gathers the allowed context, researches the options, "
                "separates what is known from what still needs verification, prepares the next "
                "step, and stops at the approval boundary."
            )
            self.assertIn(scene_end, body)
            body = body.replace(scene_end, scene_end + "\n\n" + label, 1)
            target.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any(
                    "product-status.en.md" in error
                    and "label must appear before" in error
                    for error in errors
                ),
                errors,
            )

    def test_status_live_evidence_inversion_is_detected(self):
        tmp, root = self.temp_root()
        with tmp:
            target = root / "docs" / "product-status.en.md"
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
                    "product-status.en.md" in error
                    and "synthetic-vs-live evidence boundary" in error
                    for error in errors
                ),
                errors,
            )

    def test_status_row_evidence_class_inversion_is_detected(self):
        for rel, replacement, expected in (
            ("docs/product-status.en.md", "**Live provider verified**",
             "docs/product-status.en.md: status section lost every synthetic pass-with-friction row"),
            ("docs/product-status.ko.md", "**실제 제공자 검증 완료**",
             "docs/product-status.ko.md: status evidence-class count differs"),
        ):
            with self.subTest(doc=rel):
                tmp, root = self.temp_root()
                with tmp:
                    target = root / rel
                    body = target.read_text(encoding="utf-8")
                    target.write_text(
                        body.replace(verifier.STATUS_ROW_EVIDENCE_TOKEN, replacement),
                        encoding="utf-8",
                    )
                    errors = verifier.validate_readmes(root)
                    self.assertTrue(
                        any(error.startswith(expected) for error in errors), errors
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
        anchor = "<!-- readme-section:more -->"
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
            hero = "## Your own AI assistant, on your own machine."
            heading = "## The settings you will need"
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

    def test_scenes_evidence_sentence_deletion_is_detected(self):
        tmp, root = self.temp_root()
        with tmp:
            target = root / "README.md"
            body = target.read_text(encoding="utf-8")
            scenes = verifier.section_slice(body, "scenes-today", "settings")
            token = verifier.SCENES_EVIDENCE_LABELS["README.md"]
            self.assertIn(token, scenes)
            # Moving the sentence into image alt text must not satisfy the check.
            body = body.replace(
                scenes,
                scenes.replace(token, "live accounts", 1).replace(
                    "![", f"![{token} ", 1
                ),
                1,
            )
            target.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any(
                    "README.md" in error
                    and "scenes-today is missing its visible evidence-class sentence" in error
                    for error in errors
                ),
                errors,
            )

    def test_hero_local_first_sentence_deletion_is_detected(self):
        tmp, root = self.temp_root()
        with tmp:
            target = root / "README.ko.md"
            body = target.read_text(encoding="utf-8")
            body = body.replace(
                verifier.HERO_LOCAL_FIRST_LABELS["README.ko.md"], "완전히 로컬에서만 처리됩니다", 1
            )
            target.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any(
                    "README.ko.md" in error
                    and "local-first != local-only" in error
                    for error in errors
                ),
                errors,
            )

    def test_locale_scene_panel_mismatch_is_detected(self):
        tmp, root = self.temp_root()
        with tmp:
            target = root / "README.ja.md"
            body = target.read_text(encoding="utf-8")
            body = body.replace(
                verifier.LOCALE_SCENE_VISUALS["README.ja.md"],
                verifier.LOCALE_SCENE_VISUALS["README.md"],
                1,
            )
            target.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any(
                    "README.ja.md" in error and "another locale's scene panel" in error
                    for error in errors
                ),
                errors,
            )
            self.assertTrue(
                any(
                    "README.ja.md" in error and "scenes.ja.png" in error
                    for error in errors
                ),
                errors,
            )

    def test_license_fact_drift_is_detected(self):
        tmp, root = self.temp_root()
        with tmp:
            target = root / "README.zh-CN.md"
            body = target.read_text(encoding="utf-8")
            body = body.replace("AGPL-3.0-only", "MIT", 1)
            target.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any(
                    "README.zh-CN.md" in error and "'AGPL-3.0-only'" in error
                    for error in errors
                ),
                errors,
            )

    def test_committed_visuals_match_generator(self):
        """docs/assets/readme/*.html are the generated sources of the PNG
        panels; a hand edit or a stale regeneration would let the four
        locales' panels drift apart. PNGs are rendered from them by Chrome
        (not reproducible in CI), so only their presence is checked."""
        import build_readme_visuals as visuals

        expected = {}
        for locale in visuals.SCENES:
            expected[f"hero.{locale}.html"] = visuals.build_hero(locale)
            expected[f"scenes.{locale}.html"] = visuals.build_scenes(locale)
        for name, content in expected.items():
            with self.subTest(asset=name):
                self.assertEqual(
                    content, (visuals.OUT / name).read_text(encoding="utf-8")
                )
                self.assertTrue((visuals.OUT / name.replace(".html", ".png")).is_file(), name)
        committed = sorted(path.name for path in visuals.OUT.glob("*.html"))
        self.assertEqual(sorted(expected), committed)

    def test_scene_panel_requests_appear_in_their_readme(self):
        """The request wording in each locale's panel is the wording the
        README quotes, so the picture and the prose cannot disagree."""
        import build_readme_visuals as visuals

        for name, visual in verifier.LOCALE_SCENE_VISUALS.items():
            locale = visual.split("scenes.")[1].removesuffix(".png")
            body = (ROOT / name).read_text(encoding="utf-8")
            scenes = verifier.section_slice(body, "scenes-today", "settings")
            for ask, _reply, _chip in visuals.SCENES[locale]:
                with self.subTest(readme=name, ask=ask):
                    self.assertIn(ask.replace("\n", " "), scenes)

    def test_scene_panel_requests_route_deterministically(self):
        """Every mail scene routes only after the fixture clears its declared
        unsupported-capability boundary; no model guess supplies an intent."""
        import build_readme_visuals as visuals

        src = ROOT / "src"
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
        from personal_agent import conversation_handoff as handoff
        from personal_agent import quickstart_service as service
        from personal_agent.decision import OUTCOME_DECIDED, FixtureDecisionEngine, SelectionDecision, fixture_confidence

        classifier = handoff.IntentClassifier(
            workspace_search=service.workspace_search_request,
            judge=handoff.ConversationJudgments(FixtureDecisionEngine(choose=lambda context,candidates,question:
                SelectionDecision(OUTCOME_DECIDED,'none-of-these',candidates,fixture_confidence())
                if context.purpose == 'unsupported-capability' else None)),
        )
        expected = ("workspace-summary", "mail-search", "calendar-create",
                    "memory", "research", "workspace-search")
        for locale in ("en", "ko"):
            for index, (ask, _reply, _chip) in enumerate(visuals.SCENES[locale]):
                text = ask.replace("\n", " ")
                with self.subTest(locale=locale, ask=text):
                    want = expected[index]
                    if want == "workspace-summary":
                        self.assertIsNotNone(service.workspace_summary_request(text))
                    elif want == "memory":
                        self.assertTrue(service.AgentService.memory_followup_prefilter(text))
                    else:
                        self.assertEqual(want, classifier.classify(text).intent)

    def test_shared_install_fact_drift_is_detected(self):
        tmp, root = self.temp_root()
        with tmp:
            target = root / "README.zh-CN.md"
            body = target.read_text(encoding="utf-8")
            body = body.replace(
                "git clone https://github.com/Jongtae/agentos.git",
                "git clone https://example.com/some/fork.git",
                1,
            )
            target.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any(
                    "README.zh-CN.md" in error
                    and "git clone https://github.com/Jongtae/agentos.git" in error
                    for error in errors
                ),
                errors,
            )

    def test_published_release_fact_comes_from_manifest(self):
        tmp, root = self.temp_root()
        with tmp:
            manifest = root / "docs" / "release-manifest.json"
            body = manifest.read_text(encoding="utf-8")
            body = body.replace('"version": "1.1.0"', '"version": "9.9.9"', 1)
            manifest.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any("expected exactly one 'v9.9.9'" in error for error in errors),
                errors,
            )

    def test_product_direction_scene_may_not_return_to_the_readme(self):
        tmp, root = self.temp_root()
        with tmp:
            target = root / "README.md"
            body = target.read_text(encoding="utf-8")
            body = body.replace("<!-- readme-section:more -->", verifier.CAPABILITY_MARKERS[0] + "\n\n<!-- readme-section:more -->", 1)
            target.write_text(body, encoding="utf-8")
            errors = verifier.validate_readmes(root)
            self.assertTrue(any("belongs on the status page" in e for e in errors), errors)

    def test_status_page_change_requires_korean_mirror(self):
        errors = verifier.validate_changed_paths({"docs/product-status.en.md"})
        self.assertEqual(1, len(errors))
        self.assertIn("product-status.ko.md", errors[0])

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
