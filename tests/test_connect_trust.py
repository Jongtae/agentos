"""CONNECT-TRUST-01 (#1297): the owner's trust record replaces the developer-reviewed list as the authority.

Model-free: the real store, service and settings orchestrator; nothing reaches a model or a service.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from personal_agent import owner_mcp, trust_record
from personal_agent.quickstart_store import QuickStore
from personal_agent.settings_orchestrator import SettingsError

LIST = 'mcp__notes__list_notes'
SAVE = 'mcp__notes__save_note'
DRIVE_SEARCH = 'mcp__claude_ai_Google_Drive__search_files'


class TrustRecordTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = QuickStore(Path(temp.name) / 'state')

    def test_starting_rungs_follow_the_money_marking(self):
        self.assertEqual(trust_record.hand(self.store, 'notes')['rung'], 'approve')
        trust_record.set_money(self.store, 'broker', True)
        self.assertEqual(trust_record.hand(self.store, 'broker')['rung'], 'report')
        with self.assertRaises(ValueError):
            trust_record.set_rung(self.store, 'broker', 'mandate')
        self.store.put(trust_record.KEY, {'hands': {'broker': {'money': True, 'rung': 'mandate'}}})
        self.assertEqual(trust_record.hand(self.store, 'broker')['rung'], 'approve', 'a stored mandate on a money hand is capped')

    def test_the_owner_decision_wins_over_the_seed_and_a_money_hand_ignores_the_seed(self):
        seed = frozenset({'search_files'})
        self.assertTrue(trust_record.is_read(self.store, 'Google Drive', 'search_files', seed))
        trust_record.set_operation(self.store, 'Google Drive', 'search_files', 'refused')
        self.assertFalse(trust_record.is_read(self.store, 'Google Drive', 'search_files', seed))
        trust_record.set_money(self.store, 'broker', True)
        self.assertFalse(trust_record.is_read(self.store, 'broker', 'balance', frozenset({'balance'})),
                         'on a money-capable hand only an owner-reviewed read is a read')
        trust_record.set_operation(self.store, 'broker', 'balance', 'read')
        self.assertTrue(trust_record.is_read(self.store, 'broker', 'balance'))
        self.assertTrue(trust_record.readable(self.store, 'broker'))
        self.assertFalse(trust_record.readable(self.store, 'other'))

    def test_lowering_is_one_rung_and_recorded(self):
        trust_record.set_rung(self.store, 'notes', 'mandate')
        trust_record.lower(self.store, 'notes', 'owner correction')
        row = trust_record.hand(self.store, 'notes')
        self.assertEqual(row['rung'], 'approve')
        self.assertEqual(row['history'][-1]['change'], 'lowered')
        trust_record.set_rung(self.store, 'notes', 'report')
        self.assertEqual(trust_record.lower(self.store, 'notes', 'x')['rung'], 'report', 'nothing below report')

    def test_values_are_validated(self):
        for name, operation, cls in (('a|b', 'op', 'read'), ('ok', 'bad op', 'read'), ('ok', 'op', 'maybe'), ('', 'op', 'read')):
            with self.assertRaises(ValueError):
                trust_record.set_operation(self.store, name, operation, cls)
        self.store.put(trust_record.KEY, {'hands': {'notes': {'operations': {'list_notes': 'read', 'x y': 'read', 'z': 'admin'}}}})
        self.assertEqual(trust_record.hand(self.store, 'notes')['operations'], {'list_notes': 'read'})


class DecisionTests(unittest.TestCase):
    def setUp(self):
        from personal_agent.quickstart_service import AgentService
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = QuickStore(Path(temp.name) / 'state')
        self.service = AgentService(self.store)
        self.job = {'id': self.store.enqueue('notes', 'k1')}
        self.service.set_ai_connections({'enabled': True})
        owner_mcp.set_confirmed(self.store, 'codex', ['notes', 'broker'])
        patcher = mock.patch.object(type(self.service), 'reviewed_connector_reads',
                                    staticmethod(lambda: {'Google Drive': frozenset({'search_files'}),
                                                          'broker': frozenset({'balance'})}))
        patcher.start()
        self.addCleanup(patcher.stop)

    def decide(self, tool):
        return self.service.connector_permission(self.job, {'tool_name': tool, 'input': {}})

    def test_an_undecided_operation_is_introduced_with_the_exact_value_to_propose(self):
        denied = self.decide(LIST)
        self.assertEqual(denied['behavior'], 'deny')
        self.assertIn('notes|list_notes|read', denied['message'])
        self.assertIn('소개', denied['message'])
        trust_record.set_operation(self.store, 'notes', 'list_notes', 'read')
        self.assertEqual(self.decide(LIST)['behavior'], 'allow', 'decided once, not asked again')
        trust_record.set_operation(self.store, 'notes', 'save_note', 'mutate')
        denied = self.decide(SAVE)
        self.assertEqual(denied['behavior'], 'deny', 'only reads run until #1298')
        self.assertNotIn('|read', denied['message'], 'a decided operation is not re-introduced')

    def test_the_seed_still_answers_for_a_non_money_hand_only(self):
        self.assertEqual(self.decide(DRIVE_SEARCH)['behavior'], 'allow')
        self.assertEqual(self.decide('mcp__broker__balance')['behavior'], 'allow')
        trust_record.set_money(self.store, 'broker', True)
        self.assertEqual(self.decide('mcp__broker__balance')['behavior'], 'deny')

    def test_a_call_that_ran_undecided_lowers_the_rung(self):
        trust_record.set_rung(self.store, 'notes', 'mandate')
        self.service.record_turn_provenance(self.job['id'], connector_reads=[{'tool': SAVE, 'status': 'succeeded'}])
        self.assertEqual(trust_record.hand(self.store, 'notes')['rung'], 'approve')


class ConversationTests(unittest.TestCase):
    def setUp(self):
        from personal_agent.quickstart_service import AgentService
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = QuickStore(Path(temp.name) / 'state')
        self.service = AgentService(self.store)
        self.service.owner_mcp_available = lambda: {'claude-code': [], 'codex': ['notes', 'broker']}
        self.orchestrator = self.service.settings_orchestrator

    def change(self, setting, value):
        draft = self.orchestrator.propose('local-owner', 'web', 'ai_connections', setting, value)
        self.assertFalse(draft['applied'], 'a draft changes nothing')
        return draft, self.orchestrator.confirm('local-owner', 'web', draft['draft_id'], draft['digest'])

    def test_servers_are_confirmed_only_from_what_the_owner_configured(self):
        draft, _done = self.change('servers', 'codex|notes')
        self.assertIn('notes', draft['summary'])
        self.assertEqual(owner_mcp.confirmed(self.store, 'codex'), ['notes'])
        for bad in ('codex|unknown', 'other|notes', 'codex|claude_ai_x', 'notes'):
            with self.assertRaises(SettingsError):
                self.orchestrator.propose('local-owner', 'web', 'ai_connections', 'servers', bad)
        with self.assertRaises(SettingsError):
            self.orchestrator.propose('local-owner', 'web', 'ai_connections', 'servers', 'codex|notes')
        self.change('servers', 'codex|')
        self.assertEqual(owner_mcp.confirmed(self.store, 'codex'), [])

    def test_a_review_is_confirmed_once_and_an_undo_is_the_reverse_draft(self):
        draft, _done = self.change('review', 'notes|list_notes|read')
        self.assertIn("'읽기'", draft['summary'])
        self.assertEqual(trust_record.hand(self.store, 'notes')['operations'], {'list_notes': 'read'})
        with self.assertRaises(SettingsError):
            self.orchestrator.propose('local-owner', 'web', 'ai_connections', 'review', 'notes|list_notes|read')
        self.change('review', 'notes|list_notes|refused')
        self.assertFalse(trust_record.is_read(self.store, 'notes', 'list_notes'))
        read = self.service.conversation_settings_request({'operation': 'read', 'category': 'ai_connections'})
        self.assertIn('list_notes(막음)', read['response'])

    def test_money_marking_and_rungs_are_owner_decisions(self):
        self.change('money', 'broker|on')
        self.assertEqual(trust_record.hand(self.store, 'broker')['rung'], 'report')
        with self.assertRaises(SettingsError):
            self.orchestrator.propose('local-owner', 'web', 'ai_connections', 'rung', 'broker|mandate')
        self.change('rung', 'broker|approve')
        self.assertEqual(trust_record.hand(self.store, 'broker')['rung'], 'approve')
        for bad in ('broker|maybe', 'broker', 'a|b|c'):
            with self.assertRaises(SettingsError):
                self.orchestrator.propose('local-owner', 'web', 'ai_connections', 'rung', bad)


class AvailableTests(unittest.TestCase):
    def test_names_come_from_each_cli_configuration_only(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        home = Path(temp.name)
        (home / '.claude.json').write_text(json.dumps({'mcpServers': {'files': {'command': 'x', 'env': {'K': 'secret'}},
                                                                      'claude_ai_x': {}, 'agentos': {}}}))
        (home / 'codex').mkdir()
        (home / 'codex' / 'config.toml').write_text('[mcp_servers.notes]\ncommand = "n"\n[mcp_servers.figma]\nurl = "https://x"\n')
        found = owner_mcp.available(home=home, codex_home=home / 'codex')
        self.assertEqual(found, {'claude-code': ['files'], 'codex': ['figma', 'notes']})
        self.assertNotIn('secret', json.dumps(found))
        self.assertEqual(owner_mcp.available(home=home / 'missing', codex_home=home / 'missing'), {'claude-code': [], 'codex': []})


if __name__ == '__main__':
    unittest.main()
