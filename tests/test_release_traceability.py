"""The release artifact must be traceable from this repository.

For most of this program the only links between this repository and the
published build were a prose URL in QUICKSTART.md and a Python default buried
in `delivery.py`.  That was enough for an audit to run `git ls-files`, find no
`.rb` and no checksum, and conclude that no release artifact existed at all --
while a live tap, `Jongtae/homebrew-agentos`, was serving `v1.0.4` and was
installed on the machine doing the audit.  The absence was real; the inference
from it was wrong, and it was repeated into several permanent records.

These tests make the relationship checkable instead of narrated, and make the
two drift conditions fail loudly:

* the in-tree version silently equalling the newest published release, which
  makes source indistinguishable from the shipped build;
* a formula template acquiring a fabricated checksum, which would review as
  valid and install nothing.
"""
import json
import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'deploy' / 'homebrew' / 'agentos.rb.template'
MANIFEST = ROOT / 'docs' / 'release-manifest.json'
RUNBOOK = ROOT / 'docs' / 'release.en.md'
READMES = ('README.md', 'README.ko.md', 'README.ja.md', 'README.zh-CN.md')

#: The tap this repository's formula is published to. Hardcoded on purpose:
#: if the tap moves, this test should fail and make someone update the
#: runbook and the template together.
TAP = 'Jongtae/homebrew-agentos'
FORMULA_NAME = 'jongtae/agentos/agentos'


def project_version():
    with open(ROOT / 'pyproject.toml', 'rb') as handle:
        return tomllib.load(handle)['project']['version']


def manifest():
    return json.loads(MANIFEST.read_text(encoding='utf-8'))


class ReleaseTraceabilityTests(unittest.TestCase):
    def test_the_release_manifest_and_runbook_exist(self):
        self.assertTrue(MANIFEST.is_file())
        self.assertTrue(RUNBOOK.is_file())
        self.assertTrue(TEMPLATE.is_file())

    def test_the_in_tree_version_is_not_a_published_version(self):
        """Source must be distinguishable from the newest shipped build.

        `pyproject.toml` read `1.0.4` while `v1.0.4` was the newest tag, so
        nothing in the tree said whether a checkout was the release or nine
        merged children past it.
        """
        published = {row['version'] for row in manifest()['published']}
        self.assertTrue(published, 'the manifest records no published release')
        self.assertNotIn(
            project_version(), published,
            'pyproject version equals a published release, so source and '
            'shipped build are indistinguishable by version')

    def test_every_unpublished_entry_refuses_to_invent_a_checksum(self):
        for row in manifest()['unpublished']:
            with self.subTest(version=row['version']):
                self.assertIsNone(row['archive_sha256'])
                self.assertIsNone(row['tag'])
                self.assertTrue(row.get('why_no_checksum'),
                                'an absent checksum must say why')

    def test_every_published_entry_carries_a_real_checksum(self):
        for row in manifest()['published']:
            with self.subTest(version=row['version']):
                self.assertRegex(row['archive_sha256'], r'^[0-9a-f]{64}$')
                self.assertEqual(row['tag'], 'v' + row['version'])

    def test_the_current_version_is_in_the_manifest(self):
        known = {row['version'] for row in manifest()['published']}
        known |= {row['version'] for row in manifest()['unpublished']}
        self.assertIn(project_version(), known,
                      'the version in pyproject.toml is not recorded anywhere')

    # -- the template ------------------------------------------------------

    def test_the_template_keeps_its_placeholders(self):
        body = TEMPLATE.read_text(encoding='utf-8')
        self.assertIn('__VERSION__', body)
        self.assertIn('sha256 "__SHA256__"', body)

    def test_the_template_never_carries_a_plausible_fake_checksum(self):
        """A fabricated hex string would review as valid and install nothing."""
        body = TEMPLATE.read_text(encoding='utf-8')
        for found in re.findall(r'sha256\s+"([^"]*)"', body):
            with self.subTest(sha256=found):
                self.assertEqual(found, '__SHA256__')
        self.assertIsNone(re.search(r'\b[0-9a-f]{64}\b', body),
                          'the template contains a 64-hex string; the archive '
                          'it would describe cannot exist before the tag is pushed')

    def test_the_template_has_the_shape_the_tap_formula_has(self):
        body = TEMPLATE.read_text(encoding='utf-8')
        self.assertIn('class Agentos < Formula', body)
        self.assertIn('homepage "https://github.com/Jongtae/personal-agentos"', body)
        self.assertIn('url "https://github.com/Jongtae/personal-agentos/archive/'
                      'refs/tags/v__VERSION__.tar.gz"', body)
        for block in ('def install', 'def caveats', 'test do'):
            self.assertIn(block, body)

    def test_the_template_records_where_the_published_formula_lives(self):
        """The link the repository was missing."""
        self.assertIn(TAP, TEMPLATE.read_text(encoding='utf-8'))

    # -- the claims made to the owner --------------------------------------

    def test_the_runbook_names_the_tap_and_the_post_publication_boundary(self):
        body = RUNBOOK.read_text(encoding='utf-8')
        self.assertIn(TAP, body)
        self.assertIn('everything below publishes', body)
        self.assertIn('owner_validation_pending', body)

    def test_no_readme_offers_brew_install_without_saying_what_it_installs(self):
        """`brew install` works. Calling it "the current baseline" did not.

        It resolves the newest published release, which predates every PA1
        child. Each README that offers the command must say so within sight
        of it, not only in QUICKSTART.
        """
        newest = sorted(row['version'] for row in manifest()['published'])[-1]
        for name in READMES:
            body = (ROOT / name).read_text(encoding='utf-8')
            if 'brew install ' + FORMULA_NAME not in body:
                continue
            with self.subTest(readme=name):
                index = body.index('brew install ' + FORMULA_NAME)
                window = body[index:index + 1200]
                self.assertIn(newest, window,
                              f'{name} offers brew install without naming the '
                              f'version it actually installs')

    def test_the_executable_remediation_names_a_formula_that_exists(self):
        """`brew reinstall personal-agentos` fails: that is the PyPI name.

        This string is the advice given on the one path that fires when the
        installed executable cannot be resolved, so it misfired exactly when
        the owner was already stuck.
        """
        body = (ROOT / 'src' / 'personal_agent' / 'service_control.py').read_text(encoding='utf-8')
        self.assertIn('brew reinstall ' + FORMULA_NAME, body)
        self.assertNotIn('brew reinstall personal-agentos', body)


if __name__ == '__main__':
    unittest.main()
