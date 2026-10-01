"""#932: CLIs and DNS failures outside an interactive shell."""
import os
import stat
import tempfile
import unittest
from pathlib import Path

from personal_agent.browser_worker import navigation_error_code
from personal_agent.subscription_engines import SubscriptionEngines, find_cli


class FindCli(unittest.TestCase):
    def test_a_launchd_path_still_finds_the_official_install_directory(self):
        with tempfile.TemporaryDirectory() as home:
            target = Path(home) / '.local/bin/claude'
            target.parent.mkdir(parents=True)
            target.write_text('#!/bin/sh\n')
            target.chmod(target.stat().st_mode | stat.S_IXUSR)
            self.assertEqual(find_cli('claude', path='/usr/bin:/bin:/usr/sbin:/sbin', home=home), str(target))
            self.assertIsNone(find_cli('agentos-no-such-cli', path='/usr/bin:/bin', home=home))

    def test_path_wins_over_the_install_directory(self):
        with tempfile.TemporaryDirectory() as root:
            first = Path(root) / 'first/claude'
            for path in (first, Path(root) / 'home/.local/bin/claude'):
                path.parent.mkdir(parents=True)
                path.write_text('#!/bin/sh\n')
                path.chmod(path.stat().st_mode | stat.S_IXUSR)
            self.assertEqual(find_cli('claude', path=str(first.parent), home=str(Path(root) / 'home')), str(first))

    def test_engines_use_it_by_default(self):
        self.assertIs(SubscriptionEngines().finder, find_cli)


class NavigationErrorCode(unittest.TestCase):
    class Error:
        def __init__(self, domain, code):
            self._domain, self._code = domain, code

        def domain(self):
            return self._domain

        def code(self):
            return self._code

    def test_a_missing_dns_name_is_its_own_code(self):
        self.assertEqual(navigation_error_code(self.Error('NSURLErrorDomain', -1003)), 'host_not_found')
        self.assertEqual(navigation_error_code(self.Error('NSURLErrorDomain', -1001)), 'navigation_failed')
        self.assertEqual(navigation_error_code(self.Error('WebKitErrorDomain', -1003)), 'navigation_failed')
        self.assertEqual(navigation_error_code(object()), 'navigation_failed')


if __name__ == '__main__':
    unittest.main()
