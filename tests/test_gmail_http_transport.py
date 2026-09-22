"""Gmail's data plane, which production never wired.

`GmailConnector` accepts `transport=None` and `quickstart.configured_service`
supplied none, so an owner who completed the OAuth -- a path that was wired,
tested and reviewed -- hit `transport_unavailable` on their first real mail
search. `grep -rn transport_unavailable tests/` returned nothing: the failure
the shipped configuration always reached had no coverage at all.

The connection half was proven against a fixture token endpoint and the
retrieval half was a seam nobody connected. That is the same defect class
PA1-INT-01 was created to find, and narrower than the others it found: the
caller existed, the argument did not.
"""
import json
import unittest
from urllib.error import HTTPError

from personal_agent.gmail import GmailError
from personal_agent.quickstart import gmail_http_transport


class Response:
    def __init__(self, payload=b'{"messages": []}'):
        self.payload = payload

    def read(self, limit=None):
        return self.payload[:limit] if limit else self.payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class GmailHttpTransportTests(unittest.TestCase):
    def setUp(self):
        self.requests = []

    def opener(self, response=None, error=None):
        def open_it(request, timeout=None):
            self.requests.append(request)
            if error is not None:
                raise error
            return response or Response()
        return open_it

    def test_the_production_construction_supplies_a_callable_transport(self):
        """The regression that matters: the argument must not go missing again."""
        import tempfile
        from pathlib import Path
        from cryptography.fernet import Fernet
        from personal_agent.quickstart import configured_service
        from personal_agent.quickstart_store import QuickStore
        with tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parent)) as temp:
            service = configured_service(QuickStore(Path(temp) / 'data'), {
                'AGENTOS_GMAIL_LOCAL_ONLY': '1',
                'AGENTOS_GMAIL_CLIENT_ID': 'client',
                'AGENTOS_GMAIL_CLIENT_SECRET': 'secret',
                'AGENTOS_GMAIL_LOCAL_PORT': '8787',
                'AGENTOS_GMAIL_ENCRYPTION_KEY': Fernet.generate_key().decode()})
            self.assertIsNotNone(service.gmail)
            self.assertTrue(callable(service.gmail.transport),
                            'the shipped connector has no data plane')

    def test_transport_unavailable_is_what_happens_without_one(self):
        """The failure the shipped configuration always reached, now covered.

        `GmailConnector._get` refuses before building a request when
        `transport` is not callable. Nothing asserted this, so the one error
        an owner was guaranteed to hit was the one nothing described.
        """
        from personal_agent.gmail import GmailConnector
        stub = GmailConnector.__new__(GmailConnector)
        stub.transport = None
        stub._assert_current_request = lambda *a, **k: None
        with self.assertRaises(GmailError) as raised:
            GmailConnector._get(stub, 'owner',
                                'https://gmail.googleapis.com/gmail/v1/users/me/messages',
                                {}, {}, 'revision', 'token')
        # The message is deliberately redacted; the reason is the field.
        self.assertEqual(getattr(raised.exception, 'reason', None), 'transport_unavailable')

    def test_only_get_is_permitted(self):
        send = gmail_http_transport(opener=self.opener())
        for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            with self.subTest(method=method):
                with self.assertRaises(GmailError):
                    send(method, 'https://gmail.googleapis.com/gmail/v1/users/me/messages',
                         None, {})
        self.assertEqual(self.requests, [], 'nothing may reach the opener')

    def test_the_destination_is_an_allowlist(self):
        """A bearer token must not leave the host it was minted for.

        `headers` already carries the resolved token by the time this runs,
        so an arbitrary endpoint would be a credential handed to whoever the
        caller named.
        """
        send = gmail_http_transport(opener=self.opener())
        for url in ('https://evil.test/gmail/v1/users/me/messages',
                    'http://gmail.googleapis.com/gmail/v1/users/me/messages',
                    'https://gmail.googleapis.com.evil.test/x',
                    'file:///etc/passwd', ''):
            with self.subTest(url=url):
                with self.assertRaises(GmailError):
                    send('GET', url, None, {'Authorization': 'Bearer secret-token'})
        self.assertEqual(self.requests, [])

    def test_a_permitted_request_carries_the_callers_headers_and_params(self):
        send = gmail_http_transport(opener=self.opener())
        result = send('GET', 'https://gmail.googleapis.com/gmail/v1/users/me/messages',
                      {'q': 'receipt', 'maxResults': 5, 'pageToken': None},
                      {'Authorization': 'Bearer t'})
        self.assertEqual(result, {'messages': []})
        request = self.requests[0]
        self.assertIn('q=receipt', request.full_url)
        self.assertIn('maxResults=5', request.full_url)
        self.assertNotIn('pageToken', request.full_url)
        self.assertEqual(request.get_header('Authorization'), 'Bearer t')

    def test_a_401_is_returned_as_a_status_not_raised(self):
        """That is how the connector learns the grant died.

        `GmailConnector` inspects `status_code` and moves the connector to
        REAUTH_REQUIRED on 401. Raising here would lose that and leave a dead
        grant looking connected.
        """
        error = HTTPError('https://gmail.googleapis.com/x', 401, 'no', {}, None)
        send = gmail_http_transport(opener=self.opener(error=error))
        self.assertEqual(send('GET', 'https://gmail.googleapis.com/x', None, {}),
                         {'status_code': 401})

    def test_an_oversized_response_is_refused_for_being_oversized(self):
        """Assert the reason, not the type.

        Removing the size guard still raises `GmailError` -- the truncated
        read fails to parse as JSON and lands in the same handler -- so an
        `assertRaises(GmailError)` passed either way and the mutant survived.
        The distinction matters: one is a bounded refusal, the other is an
        unbounded read that happened to produce invalid JSON.
        """
        big = Response(b'{"x": "' + b'a' * 2_000_050 + b'"}')
        send = gmail_http_transport(opener=self.opener(response=big))
        with self.assertRaises(GmailError) as raised:
            send('GET', 'https://gmail.googleapis.com/x', None, {})
        self.assertEqual(getattr(raised.exception, 'reason', None),
                         'provider_response_too_large')

    def test_a_transport_error_does_not_leak_the_cause(self):
        send = gmail_http_transport(opener=self.opener(error=OSError('connect to 10.0.0.5 failed')))
        with self.assertRaises(GmailError) as raised:
            send('GET', 'https://gmail.googleapis.com/x', None, {})
        self.assertNotIn('10.0.0.5', json.dumps(list(raised.exception.args), default=str))


if __name__ == '__main__':
    unittest.main()
