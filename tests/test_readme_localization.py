import importlib.util
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import verify_readme_localization as verifier


class ReadmeLocalizationParityTests(unittest.TestCase):
    def copy_public_readmes(self, root):
        for name in verifier.READMES:
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, root / name)
        assets = tuple(
            path
            for section_id, locales in verifier.SECTION_VISUALS.items()
            for desktop in locales.values()
            for path in ((desktop,) if section_id == "conversation"
                         else (desktop, desktop.removesuffix(".svg") + ".narrow.svg"))
        )
        for rel in set(("docs/release-manifest.json", *verifier.STATUS_DOCS, *assets)):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
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
            target = root / "docs/i18n/README.ja.md"
            body = target.read_text(encoding="utf-8")
            body = body.replace(
                "<!-- readme-section:presence -->", "", 1
            )
            target.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any(
                    "docs/i18n/README.ja.md" in error
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
                    "docs/i18n/README.ko.md" in error
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
                "<!-- readme-section:more -->",
                "Pricing\n-------\n\nPro tier includes autonomous checkout.\n\n"
                "<!-- readme-section:more -->",
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
                verifier.PRODUCT_DIRECTION_DISCLAIMERS["docs/i18n/README.ko.md"],
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
                verifier.PRODUCT_DIRECTION_DISCLAIMERS["docs/i18n/README.ko.md"],
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
                verifier.PRODUCT_DIRECTION_LABELS["docs/i18n/README.ko.md"],
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
            headings = verifier.public_h2_indexes(clean)
            hero = headings[0][1]
            heading = headings[-1][1]
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

    def test_conversation_direction_boundary_must_be_visible(self):
        for name, token in verifier.README_DIRECTION_DISCLAIMERS.items():
            for hidden in ("", f"<!-- {token} -->", f"![{token}](example.png)",
                           f'<img src="example.png" alt="{token}">'):
                with self.subTest(readme=name, hidden=hidden[:20]):
                    tmp, root = self.temp_root()
                    with tmp:
                        target = root / name
                        body = target.read_text(encoding="utf-8")
                        self.assertIn(token, body)
                        target.write_text(body.replace(token, hidden, 1), encoding="utf-8")
                        errors = verifier.validate_readmes(root)
                        self.assertTrue(any(
                            name in error and "visible illustrative product-direction boundary" in error
                            for error in errors
                        ), errors)

    def test_ownership_local_first_sentence_deletion_is_detected(self):
        tmp, root = self.temp_root()
        with tmp:
            target = root / "docs/i18n/README.ko.md"
            body = target.read_text(encoding="utf-8")
            body = body.replace(
                verifier.HERO_LOCAL_FIRST_LABELS["docs/i18n/README.ko.md"], "완전히 로컬에서만 처리됩니다", 1
            )
            target.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any(
                    "docs/i18n/README.ko.md" in error
                    and "local-first != local-only" in error
                    for error in errors
                ),
                errors,
            )

    def test_localized_picture_sources_cannot_use_another_locale(self):
        for section_id, locales in verifier.SECTION_VISUALS.items():
            for suffix in ((".png",) if section_id == "conversation"
                           else (".svg", ".narrow.svg")):
                with self.subTest(section=section_id, source=suffix):
                    tmp, root = self.temp_root()
                    with tmp:
                        target = root / "docs/i18n/README.ja.md"
                        body = target.read_text(encoding="utf-8")
                        wrong = locales["README.md"] if section_id == "conversation" else locales["README.md"].removesuffix(".svg") + suffix
                        expected = locales["docs/i18n/README.ja.md"] if section_id == "conversation" else locales["docs/i18n/README.ja.md"].removesuffix(".svg") + suffix
                        self.assertIn(expected, body)
                        target.write_text(body.replace(expected, wrong, 1), encoding="utf-8")
                        errors = verifier.validate_readmes(root)
                        self.assertTrue(any("docs/i18n/README.ja.md" in error and expected in error
                                            for error in errors), errors)

    def test_missing_picture_asset_is_detected(self):
        for section_id, locales in (("presence", verifier.LOCALE_PRESENCE_VISUALS),):
            for suffix in (".svg", ".narrow.svg"):
                with self.subTest(section=section_id, source=suffix):
                    tmp, root = self.temp_root()
                    with tmp:
                        asset = locales["docs/i18n/README.ko.md"].removesuffix(".svg") + suffix
                        (root / asset).unlink()
                        errors = verifier.validate_readmes(root)
                        self.assertTrue(any(f"missing {section_id} asset" in error and asset in error
                                            for error in errors), errors)

        for name, asset in verifier.LOCALE_SCENE_VISUALS.items():
            with self.subTest(readme=name):
                tmp, root = self.temp_root()
                with tmp:
                    (root / asset).unlink()
                    errors = verifier.validate_readmes(root)
                    self.assertTrue(any(f"{name}: missing conversation asset" in error and asset in error
                                        for error in errors), errors)

    def test_conversation_picture_must_render_in_its_own_section(self):
        for mutation in ("missing", "commented", "duplicated", "wrong section"):
            with self.subTest(mutation=mutation):
                tmp, root = self.temp_root()
                with tmp:
                    target = root / "README.md"
                    body = target.read_text(encoding="utf-8")
                    pictures = re.findall(r"<picture>.*?</picture>", body, flags=re.S)
                    scene = next(picture for picture in pictures
                                 if verifier.LOCALE_SCENE_VISUALS["README.md"] in picture)
                    replacement = {"missing": "", "commented": "<!-- " + scene + " -->",
                                   "duplicated": scene + "\n\n" + scene, "wrong section": ""}[mutation]
                    body = body.replace(scene, replacement, 1)
                    if mutation == "wrong section":
                        body += "\n\n" + scene
                    target.write_text(body, encoding="utf-8")
                    errors = verifier.validate_readmes(root)
                    self.assertTrue(any("conversation must contain exactly one localized picture" in error
                                        for error in errors), errors)

    def test_each_picture_keeps_its_narrow_breakpoint(self):
        for section_id, locales in verifier.SECTION_VISUALS.items():
            for mutation in ("missing source", "wrong breakpoint"):
                with self.subTest(section=section_id, mutation=mutation):
                    tmp, root = self.temp_root()
                    with tmp:
                        target = root / "README.md"
                        body = target.read_text(encoding="utf-8")

                        def alter(match):
                            if locales["README.md"] not in match[0]:
                                return match[0]
                            if mutation == "missing source":
                                return re.sub(r"(?m)^[ \t]*<source[^>]+>\n?", "", match[0])
                            return match[0].replace("(max-width: 600px)", "(max-width: 300px)")

                        target.write_text(re.sub(r"<picture>.*?</picture>", alter, body, flags=re.S),
                                          encoding="utf-8")
                        errors = verifier.validate_readmes(root)
                        self.assertTrue(any(f"{section_id} picture needs narrow source" in error
                                            for error in errors), errors)

    def test_each_picture_source_must_precede_its_img(self):
        for section_id, locales in verifier.SECTION_VISUALS.items():
            for name, desktop in locales.items():
                with self.subTest(section=section_id, readme=name):
                    tmp, root = self.temp_root()
                    with tmp:
                        target = root / name
                        body = target.read_text(encoding="utf-8")

                        def swap(match):
                            if desktop not in match[0]:
                                return match[0]
                            lines = match[0].splitlines()
                            self.assertIn("<source ", lines[1])
                            self.assertIn("<img ", lines[2])
                            lines[1], lines[2] = lines[2], lines[1]
                            return "\n".join(lines)

                        target.write_text(re.sub(r"<picture>.*?</picture>", swap, body, flags=re.S),
                                          encoding="utf-8")
                        errors = verifier.validate_readmes(root)
                        self.assertTrue(any(name in error and f"{section_id} picture needs source before img" in error
                                            for error in errors), errors)

    def test_presence_paths_hidden_in_comment_are_not_a_picture(self):
        tmp, root = self.temp_root()
        with tmp:
            target = root / "README.md"
            body = target.read_text(encoding="utf-8")
            body = re.sub(r"<picture>.*?</picture>", lambda match: "<!-- " + match[0] + " -->",
                          body, count=1, flags=re.S)
            target.write_text(body, encoding="utf-8")
            errors = verifier.validate_readmes(root)
            self.assertTrue(any("presence must contain exactly one localized picture" in error
                                for error in errors), errors)

    def test_presence_picture_inside_fenced_code_is_not_rendered(self):
        for fence in ("```html", "~~~html"):
            for closed in (True, False):
                with self.subTest(fence=fence, closed=closed):
                    tmp, root = self.temp_root()
                    with tmp:
                        target = root / "README.md"
                        body = target.read_text(encoding="utf-8")
                        ending = fence[:3] if closed else ""
                        body = re.sub(
                            r"<picture>.*?</picture>",
                            lambda match: fence + "\n" + match[0] + "\n" + ending,
                            body, count=1, flags=re.S,
                        )
                        target.write_text(body, encoding="utf-8")
                        errors = verifier.validate_readmes(root)
                        self.assertTrue(any(
                            "presence must contain exactly one localized picture" in error
                            for error in errors
                        ), errors)

    def test_fenced_picture_sample_does_not_hide_actual_picture(self):
        for fence in ("```html", "~~~html"):
            with self.subTest(fence=fence):
                tmp, root = self.temp_root()
                with tmp:
                    target = root / "README.md"
                    body = target.read_text(encoding="utf-8")
                    body = re.sub(
                        r"<picture>.*?</picture>",
                        lambda match: fence + "\n" + match[0] + "\n" + fence[:3]
                        + "\n\n" + match[0],
                        body, count=1, flags=re.S,
                    )
                    target.write_text(body, encoding="utf-8")
                    self.assertEqual([], verifier.validate_readmes(root))

    def test_picture_markup_displayed_as_markdown_code_is_rejected(self):
        wrappers = {
            "four-space indentation": lambda picture: "\n".join(
                "    " + line for line in picture.splitlines()
            ),
            "tab indentation": lambda picture: "\n".join(
                "\t" + line for line in picture.splitlines()
            ),
            "blank line before indented code": lambda picture: "<picture>\n\n"
            + "\n".join("    " + line for line in picture.splitlines()[1:]),
            "inline backticks": lambda picture: "\n".join(
                "`" + line + "`" for line in picture.splitlines()
            ),
            "multiline code span": lambda picture: "`\n" + picture + "\n`",
            "multiline double-backtick span": lambda picture: "``\n" + picture + "\n``",
        }
        for name, wrap in wrappers.items():
            with self.subTest(markup=name):
                tmp, root = self.temp_root()
                with tmp:
                    target = root / "README.md"
                    body = target.read_text(encoding="utf-8")
                    body = re.sub(
                        r"<picture>.*?</picture>", lambda match: wrap(match[0]),
                        body, count=1, flags=re.S,
                    )
                    target.write_text(body, encoding="utf-8")
                    errors = verifier.validate_readmes(root)
                    self.assertTrue(any(
                        "presence must contain exactly one localized picture" in error
                        for error in errors
                    ), errors)

    def test_standalone_picture_allows_indented_child_tags(self):
        for outer_indent in ("", "   "):
            with self.subTest(outer_indent=len(outer_indent)):
                tmp, root = self.temp_root()
                with tmp:
                    target = root / "README.md"
                    body = target.read_text(encoding="utf-8")

                    def indent_children(match):
                        lines = match[0].splitlines()
                        return "\n".join(
                            [outer_indent + lines[0]]
                            + ["    " + line.lstrip() for line in lines[1:-1]]
                            + [outer_indent + lines[-1]]
                        )

                    body = re.sub(
                        r"<picture>.*?</picture>", indent_children,
                        body, count=1, flags=re.S,
                    )
                    target.write_text(body, encoding="utf-8")
                    self.assertEqual([], verifier.validate_readmes(root))

    def test_picture_alt_cannot_be_empty_or_a_filename(self):
        for section_id, locales in verifier.SECTION_VISUALS.items():
            for alt in ("", "   ", Path(locales["README.md"]).name):
                with self.subTest(section=section_id, alt=alt):
                    tmp, root = self.temp_root()
                    with tmp:
                        target = root / "README.md"
                        body = target.read_text(encoding="utf-8")
                        body = re.sub(
                            r"<picture>.*?</picture>",
                            lambda match: re.sub(r'alt="[^"]*"', f'alt="{alt}"', match[0])
                            if locales["README.md"] in match[0] else match[0],
                            body, flags=re.S,
                        )
                        target.write_text(body, encoding="utf-8")
                        errors = verifier.validate_readmes(root)
                        self.assertTrue(any(f"{section_id} picture needs meaningful alt text" in error
                                            for error in errors), errors)

    def test_license_fact_drift_is_detected(self):
        tmp, root = self.temp_root()
        with tmp:
            target = root / "docs/i18n/README.zh-CN.md"
            body = target.read_text(encoding="utf-8")
            body = body.replace("AGPL-3.0-only", "MIT", 1)
            target.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any(
                    "docs/i18n/README.zh-CN.md" in error and "'AGPL-3.0-only'" in error
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

    def test_committed_generated_figures_match_generator(self):
        """Keep current overview and preserved scene SVGs synchronized."""
        assets = ROOT / "docs" / "assets" / "readme"
        spec = importlib.util.spec_from_file_location(
            "readme_concept_visuals", assets / "build_concept_visuals.py"
        )
        visuals = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(visuals)
        expected = {
            f"{kind}.{locale}{suffix}.svg"
            for kind, translations in (("presence-overview", visuals.OVERVIEW),
                                       ("presence-scenes", visuals.SCENES))
            for locale in translations
            for suffix in ("", ".narrow")
        }
        with tempfile.TemporaryDirectory() as tmp:
            generated = Path(tmp)
            with patch.object(visuals, "ROOT", generated):
                for kind, translations, builder in (
                    ("presence-overview", visuals.OVERVIEW, visuals.overview),
                    ("presence-scenes", visuals.SCENES, visuals.scenes),
                ):
                    for locale, data in translations.items():
                        for mobile in (False, True):
                            suffix = ".narrow" if mobile else ""
                            builder(data, mobile).write(f"{kind}.{locale}{suffix}.svg")
            self.assertEqual(expected, {path.name for path in generated.glob("*.svg")})
            committed = {path.name for pattern in ("presence-overview.*.svg", "presence-scenes.*.svg")
                         for path in assets.glob(pattern)}
            self.assertEqual(expected, committed)
            for name in sorted(expected):
                with self.subTest(asset=name):
                    self.assertEqual(
                        (generated / name).read_bytes(),
                        (assets / name).read_bytes(),
                        f"{name} is stale; regenerate with docs/assets/readme/build_concept_visuals.py",
                    )

    def test_scene_panel_requests_route_deterministically(self):
        """Every mail scene routes only after the fixture clears its declared
        unsupported-capability boundary.  The calendar scene reaches
        ``calendar-create`` only through the scripted ``capability-need``
        judgment and the research scene stays on the ordinary conversation
        route, where the Work loop chooses web search (#672): no request word
        and no free model guess supplies an intent."""
        import build_readme_visuals as visuals

        src = ROOT / "src"
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
        from personal_agent import conversation_handoff as handoff
        from personal_agent import quickstart_service as service
        from personal_agent.decision import OUTCOME_DECIDED, FixtureDecisionEngine, SelectionDecision, fixture_confidence

        calendar_scenes = {visuals.SCENES[locale][2][0].replace("\n", " ") for locale in ("en", "ko")}

        def choose(context, candidates, question):
            if context.purpose == 'unsupported-capability':
                return SelectionDecision(OUTCOME_DECIDED, 'none-of-these', candidates, fixture_confidence())
            if context.purpose == 'capability-need':
                answer = 'calendar-create' if context.facts['owner_message'] in calendar_scenes else 'none-of-these'
                return SelectionDecision(OUTCOME_DECIDED, answer, candidates, fixture_confidence())
            return None

        classifier = handoff.IntentClassifier(
            workspace_search=service.workspace_search_request,
            judge=handoff.ConversationJudgments(FixtureDecisionEngine(choose=choose)),
        )
        expected = ("workspace-summary", "mail-search", "calendar-create",
                    "memory", "conversation", "workspace-search")
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
            target = root / "docs/i18n/README.zh-CN.md"
            body = target.read_text(encoding="utf-8")
            body = body.replace(
                "brew install jongtae/agentos/agentos",
                "brew install some/fork/agentos",
                1,
            )
            target.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any(
                    "docs/i18n/README.zh-CN.md" in error
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
            body = body.replace('"version": "1.1.0"', '"version": "9.9.9"', 1)
            manifest.write_text(body, encoding="utf-8")

            errors = verifier.validate_readmes(root)
            self.assertTrue(
                any("expected exactly one 'v9.9.9'" in error for error in errors),
                errors,
            )

    def test_release_boundary_must_stay_beside_installation(self):
        release = verifier.newest_published_release(ROOT)
        for name, template in verifier.README_RELEASE_BOUNDARIES.items():
            with self.subTest(readme=name):
                tmp, root = self.temp_root()
                with tmp:
                    target = root / name
                    body = target.read_text(encoding="utf-8")
                    token = template.format(version=release["version"], date=release["tag_date"])
                    self.assertIn(token, body)
                    body = body.replace(token, "", 1)
                    body += "\n" + token + "\n"
                    target.write_text(body, encoding="utf-8")
                    errors = verifier.validate_readmes(root)
                    self.assertTrue(any(name in error and "try-today is missing its visible published-release/main boundary"
                                        in error for error in errors), errors)

    def test_release_boundary_cannot_be_hidden_in_a_comment(self):
        tmp, root = self.temp_root()
        with tmp:
            release = verifier.newest_published_release(root)
            token = verifier.README_RELEASE_BOUNDARIES["README.md"].format(
                version=release["version"], date=release["tag_date"]
            )
            target = root / "README.md"
            body = target.read_text(encoding="utf-8")
            target.write_text(body.replace(token, "<!-- " + token + " -->", 1), encoding="utf-8")
            errors = verifier.validate_readmes(root)
            self.assertTrue(any("try-today is missing its visible published-release/main boundary" in error
                                for error in errors), errors)

    def test_required_claims_cannot_be_code(self):
        release = verifier.newest_published_release(ROOT)
        wrappers = {
            "backtick fence": lambda text: "\n\n```text\n" + text + "\n```\n\n",
            "tilde fence": lambda text: "\n\n~~~text\n" + text + "\n~~~\n\n",
            "space indentation": lambda text: "\n\n    " + text + "\n\n",
            "tab indentation": lambda text: "\n\n\t" + text + "\n\n",
            "inline backticks": lambda text: "`" + text + "`",
            "double backticks": lambda text: "``" + text + "``",
            "multiline span": lambda text: "``\n" + text + "\n``",
            "indented inline delimiters": lambda text: "\n\n  ``\n" + text + "\n  ``\n\n",
            "indented line inside span": lambda text: "\n\n``example\n  line\n" + text + "\n``\n\n",
            "HTML pre": lambda text: "<pre>" + text + "</pre>",
            "HTML code": lambda text: "<code>" + text + "</code>",
            "HTML mixed case attributes": lambda text: '<CoDe class="example" data-x=">">' + text + "</cOdE>",
            "HTML multiline pre": lambda text: '<PRE\n class="example">\n\n' + text + "\n\n</PRE>",
            "HTML nested pre code": lambda text: '<pre><code class="language-text">\n' + text + "\n</code></pre>",
            "HTML unclosed code": lambda text: "<code>" + text,
            "HTML non-void trailing slash": lambda text: "<code/>" + text,
        }
        for name in verifier.READMES:
            claims = (
                (verifier.README_RELEASE_BOUNDARIES[name].format(
                    version=release["version"], date=release["tag_date"]
                 ), "visible published-release/main boundary"),
                (verifier.README_DIRECTION_DISCLAIMERS[name],
                 "visible illustrative product-direction boundary"),
            )
            for token, expected_error in claims:
                for markup, wrap in wrappers.items():
                    with self.subTest(readme=name, claim=expected_error, markup=markup):
                        tmp, root = self.temp_root()
                        with tmp:
                            target = root / name
                            body = target.read_text(encoding="utf-8")
                            self.assertIn(token, body)
                            target.write_text(body.replace(token, wrap(token), 1), encoding="utf-8")
                            errors = verifier.validate_readmes(root)
                            self.assertTrue(any(name in error and expected_error in error
                                                for error in errors), errors)

    def test_html_code_examples_do_not_hide_later_claims(self):
        samples = (
            "<pre>Example only.</pre>",
            '<CODE class="example">Example only.</CODE>',
            '<pre><code>Example only.</code></pre>',
            '<pre>\n~~~\nExample only.\n</pre>',
            '```html\n<pre>\n```',
            '~~~html\n<code>\n~~~',
            '> ~~~html\n> <pre>\n> ~~~',
            '- ~~~html\n  <code>\n  ~~~',
            'Use `<code>` for an inline example.',
            'Use ``<pre>`` for an inline example.',
            '    <code>',
            '\t<pre>',
            '<pre>`example</pre>`',
        )
        release = verifier.newest_published_release(ROOT)
        for name in verifier.READMES:
            for token in (
                verifier.README_RELEASE_BOUNDARIES[name].format(
                    version=release["version"], date=release["tag_date"]
                ),
                verifier.README_DIRECTION_DISCLAIMERS[name],
            ):
                for sample in samples:
                    with self.subTest(readme=name, sample=sample, claim=token[:20]):
                        tmp, root = self.temp_root()
                        with tmp:
                            target = root / name
                            body = target.read_text(encoding="utf-8")
                            target.write_text(body.replace(token, "\n\n" + sample + "\n\n" + token, 1),
                                              encoding="utf-8")
                            self.assertEqual([], verifier.validate_readmes(root))

    def test_html_code_removal_cannot_join_claim_fragments(self):
        token = verifier.README_DIRECTION_DISCLAIMERS["README.md"]
        first, rest = token.split(" ", 1)
        self.assertNotIn(token, verifier.visible_prose(first + "<code>example</code> " + rest))

    def test_container_fences_cannot_supply_required_claims(self):
        release = verifier.newest_published_release(ROOT)
        wrappers = {
            "quoted": lambda text: "> ~~~text\n> " + text + "\n> ~~~",
            "nested quote": lambda text: ">> ~~~text\n>> " + text + "\n>> ~~~",
            "bullet list": lambda text: "- ~~~text\n  " + text + "\n  ~~~",
            "ordered list": lambda text: "1. ~~~text\n   " + text + "\n   ~~~",
            "nested list": lambda text: "- Example:\n  - ~~~text\n    " + text + "\n    ~~~",
            "list paragraph": lambda text: "- Example:\n\n  ~~~text\n  " + text + "\n  ~~~",
            "quoted list": lambda text: "> - ~~~text\n>   " + text + "\n>   ~~~",
        }
        for name in verifier.READMES:
            claims = (
                (verifier.README_RELEASE_BOUNDARIES[name].format(
                    version=release["version"], date=release["tag_date"]
                 ), "visible published-release/main boundary"),
                (verifier.README_DIRECTION_DISCLAIMERS[name],
                 "visible illustrative product-direction boundary"),
            )
            for token, expected_error in claims:
                for markup, wrap in wrappers.items():
                    with self.subTest(readme=name, claim=expected_error, markup=markup):
                        tmp, root = self.temp_root()
                        with tmp:
                            target = root / name
                            body = target.read_text(encoding="utf-8")
                            hidden = "\n\n" + wrap(token) + "\n\n"
                            target.write_text(body.replace(token, hidden, 1), encoding="utf-8")
                            errors = verifier.validate_readmes(root)
                            self.assertTrue(any(name in error and expected_error in error
                                                for error in errors), errors)
                            # A completed container example must not hide the
                            # real standalone claim immediately after it.
                            visible = "\n\n" + wrap("Example only.") + "\n\n" + token
                            target.write_text(body.replace(token, visible, 1), encoding="utf-8")
                            self.assertEqual([], verifier.validate_readmes(root))

    def test_inline_main_and_fenced_install_commands_remain_valid(self):
        tmp, root = self.temp_root()
        with tmp:
            for name in verifier.READMES:
                target = root / name
                body = target.read_text(encoding="utf-8")
                self.assertIn("```sh\nbrew install jongtae/agentos/agentos", body)
                target.write_text(body.replace("`main`", "`` main ``"), encoding="utf-8")
            self.assertEqual([], verifier.validate_readmes(root))

    def test_claim_prose_keeps_unmatched_ticks_and_paragraph_boundaries(self):
        token = verifier.README_DIRECTION_DISCLAIMERS["README.md"]
        for sample in ("`" + token, "`\n\n" + token + "\n\n`", "\\`" + token + "\\`"):
            with self.subTest(sample=sample):
                self.assertIn(token, verifier.visible_prose(sample))

    def test_core_narrative_cannot_disappear_in_all_locales(self):
        tmp, root = self.temp_root()
        with tmp:
            for name in verifier.READMES:
                target = root / name
                body = target.read_text(encoding="utf-8")
                target.write_text(body.replace("<!-- readme-section:ownership -->", "", 1), encoding="utf-8")
            errors = verifier.validate_readmes(root)
            self.assertTrue(any("missing required core section marker(s): ownership" in error
                                for error in errors), errors)

    def test_status_page_change_requires_korean_mirror(self):
        errors = verifier.validate_changed_paths({"docs/product-status.en.md"})
        self.assertEqual(1, len(errors))
        self.assertIn("product-status.ko.md", errors[0])

    def test_canonical_readme_change_requires_all_locales(self):
        errors = verifier.validate_changed_paths({"README.md", "docs/i18n/README.ko.md"})
        self.assertEqual(1, len(errors))
        self.assertIn("docs/i18n/README.ja.md", errors[0])
        self.assertIn("docs/i18n/README.zh-CN.md", errors[0])

    def test_canonical_readme_change_with_all_locales_passes(self):
        self.assertEqual(
            [],
            verifier.validate_changed_paths(set(verifier.READMES)),
        )

    def test_locale_only_fix_does_not_force_unrelated_locale_churn(self):
        self.assertEqual(
            [],
            verifier.validate_changed_paths({"docs/i18n/README.ko.md"}),
        )


if __name__ == "__main__":
    unittest.main()
