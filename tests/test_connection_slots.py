"""CONN-API: AgentOS-held connections as read-only ``api_request`` slots."""
import json
import tempfile
import unittest
from pathlib import Path

from personal_agent import connection_slots
from personal_agent.agent_runtime import Capabilities
from personal_agent.api_requests import ApiError, ApiRequests, context_line, save_slot
from personal_agent.connector_contract import ConnectorState
from personal_agent.quickstart_store import QuickStore

TOKEN = 'ya29.connection-access-token-value'
EVENT_URL = 'https://www.googleapis.com/calendar/v3/calendars/primary/events/lunch'


def calendar_slot(token=lambda: TOKEN):
    return connection_slots._slot('google-calendar', token)


class Transport:
    def __init__(self, body=None, status=200):
        self.calls, self.body, self.status = [], body, status

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, dict(headers)))
        payload = self.body if self.body is not None else {'id': 'lunch', 'attendees': [{'email': 'kim@example.com'}]}
        return self.status, {}, json.dumps(payload).encode()


class ConnectionSlots(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'data')

    def api(self, transport, slots=None, **kwargs):
        held = slots if slots is not None else {'google-calendar': calendar_slot()}
        return ApiRequests(self.store, 'w', transport=transport, connections=lambda: held, **kwargs)

    def test_the_ai_reads_whatever_the_provider_api_returns_with_a_token_it_never_sees(self):
        transport = Transport()
        result = self.api(transport).call({'slot': 'google-calendar', 'url': EVENT_URL, 'effect': 'read'})
        self.assertEqual(result['data']['attendees'], [{'email': 'kim@example.com'}])
        method, url, headers = transport.calls[0]
        self.assertEqual((method, url, headers['Authorization']), ('GET', EVENT_URL, 'Bearer ' + TOKEN))
        self.assertEqual(result['provenance']['source']['connection'], 'google-calendar')
        self.assertNotIn(TOKEN, json.dumps(result))

    def test_a_token_echoed_by_the_provider_is_scrubbed(self):
        result = self.api(Transport({'id': 'x', 'echo': TOKEN})).call({'slot': 'google-calendar', 'url': EVENT_URL})
        self.assertNotIn(TOKEN, json.dumps(result))

    def test_the_token_is_resolved_for_every_call(self):
        issued = []

        def token():
            issued.append(len(issued))
            return f'token-{len(issued)}-value-long-enough'
        transport = Transport()
        api = self.api(transport, {'google-calendar': calendar_slot(token)})
        api.call({'slot': 'google-calendar', 'url': EVENT_URL})
        api.call({'slot': 'google-calendar', 'url': EVENT_URL})
        self.assertEqual([c[2]['Authorization'] for c in transport.calls],
                         ['Bearer token-1-value-long-enough', 'Bearer token-2-value-long-enough'])

    def test_an_undeclared_effect_on_a_read_grant_is_a_read(self):
        transport = Transport()
        self.api(transport).call({'slot': 'google-calendar', 'url': EVENT_URL})
        self.assertEqual(len(transport.calls), 1)

    def test_a_read_grant_never_sends_a_change(self):
        transport = Transport()
        for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            with self.subTest(method=method), self.assertRaises(ApiError) as caught:
                self.api(transport).call({'slot': 'google-calendar', 'url': EVENT_URL, 'method': method,
                                          'effect': 'mutate', 'body': '{}' if method != 'DELETE' else None})
            self.assertEqual(caught.exception.code, 'api_read_only')
        self.assertEqual(transport.calls, [])

    def test_the_token_reaches_only_its_own_api_path_and_host(self):
        transport = Transport()
        for url in ('https://www.googleapis.com/drive/v3/files', 'https://www.googleapis.com/oauth2/v3/userinfo',
                    'https://evil.example/calendar/v3/x', 'http://www.googleapis.com/calendar/v3/x'):
            with self.subTest(url=url), self.assertRaises(ApiError) as caught:
                self.api(transport).call({'slot': 'google-calendar', 'url': url})
            self.assertEqual(caught.exception.code, 'api_host_not_allowed')
        self.assertEqual(transport.calls, [])

    def test_an_unusable_connection_is_setup_required_and_nothing_is_sent(self):
        def broken():
            raise ValueError('reauthentication required')
        transport = Transport()
        with self.assertRaises(ApiError) as caught:
            self.api(transport, {'google-calendar': calendar_slot(broken)}).call({'slot': 'google-calendar', 'url': EVENT_URL})
        self.assertEqual((caught.exception.code, caught.exception.requires), ('needs_setup', 'connection:google-calendar'))
        self.assertEqual(transport.calls, [])

    def test_an_owner_slot_of_the_same_name_wins_and_slots_are_listed_for_the_ai(self):
        save_slot(self.store, 'google-calendar', ['example.com'], 'owner-registered-secret-1')
        api = self.api(Transport())
        self.assertEqual(list(api.slots()['google-calendar']['hosts']), ['example.com'])
        line = context_line(self.store, {'google-drive': connection_slots._slot('google-drive', lambda: TOKEN)})
        self.assertIn('google-drive (www.googleapis.com', line)
        self.assertNotIn(TOKEN, line)

    def test_capabilities_offer_api_request_when_only_a_connection_exists(self):
        job = self.store.enqueue('점심은 누구랑?', 'k')
        bare = Capabilities(self.store, None, {}, '', job, lambda *a: None)
        self.assertNotIn('api_request', bare.offered_tools())
        held = Capabilities(self.store, None, {}, '', job, lambda *a: None, connections=lambda: {'google-calendar': calendar_slot()})
        self.assertIn('api_request', held.offered_tools())


class Build(unittest.TestCase):
    """Only a connected read connector becomes a slot."""

    class Registry:
        def __init__(self, connected):
            self.connected = connected

        def status(self, owner, connector_id):
            state = ConnectorState.CONNECTED if connector_id in self.connected else ConnectorState.DISCONNECTED
            return type('Status', (), {'state': state})()

    def service(self, connected, **attrs):
        return type('Service', (), {'connector_registry': self.Registry(connected), 'calendar_oauth': object(),
                                    'drive_oauth': object(), 'gmail': None, **attrs})()

    def test_connected_connectors_become_slots(self):
        built = connection_slots.build(self.service({'google-calendar'}), 'owner')
        self.assertEqual(sorted(built), ['google-calendar'])
        self.assertTrue(built['google-calendar']['read_only'])
        self.assertEqual(connection_slots.build(self.service(set()), 'owner'), {})
        self.assertEqual(connection_slots.build(type('S', (), {})(), 'owner'), {})
        both = connection_slots.build(self.service({'google-calendar', 'google-drive'}), 'owner')
        self.assertEqual(sorted(both), ['google-calendar', 'google-drive'])


if __name__ == '__main__':
    unittest.main()
