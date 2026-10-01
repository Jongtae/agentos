"""#942: the Work's context names the browser sign-ins, and a shared one says so."""
import tempfile
import types
import unittest
from pathlib import Path

from personal_agent import family_share
from personal_agent.information_use import context_claims
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore


class BrowserSessionsInContext(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(Path(self.temp.name))
        self.service = types.SimpleNamespace(store=self.store, browser_profile=None)
        self.text = lambda: AgentService.browser_sessions_text(self.service)

    def view(self, *sites):
        self.service.browser_profile = types.SimpleNamespace(_jar_view=lambda: ('stored', [{'site': site} for site in sites]))

    def test_no_sign_in_no_line(self):
        self.assertIsNone(self.text())
        self.view()
        self.assertIsNone(self.text())

    def test_sites_are_named_and_a_shared_one_says_so(self):
        self.view('shop.test', 'news.test')
        self.store.put(family_share.SHARED_KEY, {'shop.test': {'from': 'owner', 'since': 1}})
        line = self.text()
        self.assertIn("shop.test (the owner's sign-in shared with you", line)
        self.assertIn('payment is the owner', line)
        self.assertIn(', news.test', line)
        self.assertNotIn("news.test (the owner's", line)

    def test_a_broken_view_is_no_line(self):
        def broken():
            raise OSError('keychain')
        self.service.browser_profile = types.SimpleNamespace(_jar_view=broken)
        self.assertIsNone(self.text())

    def test_the_information_use_record_still_reads_the_context_json(self):
        rendered = 'Current context (legend)\n{"local_time": "2026-10-01T14:00", "timezone": "Asia/Seoul"}\nBrowser sign-ins: shop.test'
        self.assertEqual(context_claims(rendered)[0]['ref'], 'clock')


if __name__ == '__main__':
    unittest.main()
