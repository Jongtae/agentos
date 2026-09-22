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

#: Words that mark the published build as older than `main`, in each language
#: a README is written in. Naming the version without one of these is how the
#: original defect read.
BEHIND_WORDS = ('behind', 'predates', '뒤입니다', '遅れて', '落后')

#: The executable body, pinned literally. Changing the formula means changing
#: this too, deliberately, in the same commit.
EXPECTED_FORMULA = '''class Agentos < Formula
  desc "Self-hosted personal agent with browser setup and Telegram"
  homepage "https://github.com/Jongtae/personal-agentos"
  url "https://github.com/Jongtae/personal-agentos/archive/refs/tags/v__VERSION__.tar.gz"
  sha256 "__SHA256__"
  depends_on "python@3.13"

  def install
    system Formula["python@3.13"].opt_bin/"python3.13", "-m", "venv", libexec
    system libexec/"bin/pip", "install", buildpath
    (bin/"agentos").write <<~PYTHON
      #!#{libexec}/bin/python
      from personal_agent.quickstart import main
      main()
    PYTHON
  end

  def caveats
    <<~EOS
      Run agentos start to open browser setup.
      Data: ~/.local/share/agentos
      Keep the process running to receive Telegram requests.
    EOS
  end

  test do
    assert_match "personal agent", shell_output("#{bin}/agentos --help")
  end
end'''


def project_version():
    with open(ROOT / 'pyproject.toml', 'rb') as handle:
        return tomllib.load(handle)['project']['version']


def manifest():
    return json.loads(MANIFEST.read_text(encoding='utf-8'))


def version_key(value):
    """Numeric ordering. ``sorted()`` on the strings puts 1.0.4 after 1.0.10."""
    return tuple(int(part) for part in value.split('.'))


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
                # The tagged commit is the squash-merge commit, which does
                # not exist yet. Any SHA recorded here is wrong on merge.
                self.assertIsNone(row['commit'])
                self.assertTrue(row.get('why_no_commit'))

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
        newest = max((row['version'] for row in manifest()['published']), key=version_key)
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
                # Naming the version is not enough. Review replaced the
                # caveat with "v1.0.4, the fully current baseline with every
                # feature described below" -- the exact claim this test
                # exists to prevent -- and it still passed.
                self.assertTrue(
                    any(word in window for word in BEHIND_WORDS),
                    f'{name} names the version but does not say it is behind '
                    f'`main`; naming it while calling it current is the defect')
                for claim in ('current baseline', '최신 빌드', '现行基线'):
                    self.assertNotIn(claim, window,
                                     f'{name} still presents the published '
                                     f'release as current')

    def test_the_template_body_is_the_expected_formula_and_nothing_else(self):
        """The part that actually runs on the owner's machine.

        The other template tests pin four strings -- class, homepage, url and
        the placeholder slots -- and leave the install block free. Review
        inserted a ``curl … | sh`` into ``def install`` and all twelve tests
        passed. This is a file whose whole purpose is to be rendered into
        something Homebrew executes, so the executable body is pinned
        literally and a change has to be made deliberately here.
        """
        body = TEMPLATE.read_text(encoding='utf-8')
        # Everything from the class declaration on; the comment header above
        # it is documentation and may change freely.
        formula = body[body.index('class Agentos < Formula'):]
        self.assertEqual(formula.strip(), EXPECTED_FORMULA.strip())

    def test_the_template_contains_no_shell_execution(self):
        """A second, independent net: pinning equality above could be updated
        carelessly, so name the shapes that must never appear at all."""
        body = TEMPLATE.read_text(encoding='utf-8').casefold()
        for forbidden in ('curl', 'wget', '/bin/sh', '/bin/bash', 'eval',
                          'base64', 'system "sh"', 'popen'):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, body)

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
