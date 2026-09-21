"""Tests for the Telegram transport seam used by the personal conversation.

The existing suite is the behaviour-preservation evidence for the extraction.
These tests cover the seam itself: that conversation policy routes through the
named channel methods instead of building Telegram payloads inline, that the
transport and the bot token are resolved per call rather than captured, and
that the wire shape and failure translation are exact.
"""
import tempfile
import unittest

from personal_agent.conversation_handoff import TelegramChannel
from personal_agent.providers import ModelAdapter, ProviderError
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore


def recording_transport(log, result=None):
    """Return a transport that records the exact call it received."""
    def transport(url, body, headers, *, timeout):
        log.append({'url': url, 'body': body, 'headers': headers, 'timeout': timeout})
        return {'ok': True, 'result': {} if result is None else result}
    return transport


class RecordingChannel:
    """Stand-in channel that records the seam method policy actually used.

    ``call`` and ``call_with_token`` are recorded as well.  A policy call site
    that goes back to constructing a raw Telegram payload therefore shows up as
    a different recorded name instead of passing unnoticed.
    """

    def __init__(self, results=None, probe=None):
        self.calls = []
        self.probes = []
        self._results = results or {}
        self._probe = probe

    def _record(self, name, **kwargs):
        self.calls.append((name, kwargs))
        if self._probe is not None:
            self.probes.append(self._probe())
        return self._results.get(name, {'message_id': 7})

    @property
    def names(self):
        return [name for name, _kwargs in self.calls]

    def call(self, method, body):
        return self._record('call', method=method, body=body)

    def call_with_token(self, token, method, body):
        return self._record('call_with_token', token=token, method=method, body=body)

    def send_message(self, chat_id, text, reply_markup=None):
        return self._record('send_message', chat_id=chat_id, text=text, reply_markup=reply_markup)

    def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        return self._record('edit_message_text', chat_id=chat_id, message_id=message_id,
                            text=text, reply_markup=reply_markup)

    def answer_callback_query(self, callback_query_id, text):
        return self._record('answer_callback_query', callback_query_id=callback_query_id, text=text)

    def get_updates(self, offset, timeout=5, allowed_updates=None, limit=20):
        self._record('get_updates', offset=offset, timeout=timeout,
                     allowed_updates=allowed_updates, limit=limit)
        return self._results.get('get_updates', [])

    def get_me(self, token):
        return self._record('get_me', token=token)

    def get_webhook_info(self, token):
        return self._record('get_webhook_info', token=token)


class TelegramChannelTests(unittest.TestCase):
    """The wire boundary itself: URL, body, signature, failure, late binding."""

    def test_transport_is_resolved_on_every_call_and_not_captured(self):
        seen = []

        def first(url, body, headers, *, timeout):
            seen.append('first')
            return {'ok': True, 'result': 1}

        def second(url, body, headers, *, timeout):
            seen.append('second')
            return {'ok': True, 'result': 2}

        holder = {'transport': first}
        channel = TelegramChannel(lambda: holder['transport'], lambda: 'token')
        self.assertEqual(channel.send_message(42, 'first message'), 1)
        holder['transport'] = second
        self.assertEqual(channel.send_message(42, 'second message'), 2)
        self.assertEqual(seen, ['first', 'second'])

    def test_bot_token_is_resolved_on_every_call_and_not_captured(self):
        log = []
        token = {'value': 'first-token'}
        channel = TelegramChannel(lambda: recording_transport(log), lambda: token['value'])
        channel.send_message(42, 'before rotation')
        token['value'] = 'rotated-token'
        channel.send_message(42, 'after rotation')
        self.assertEqual([entry['url'] for entry in log],
                         ['https://api.telegram.org/botfirst-token/sendMessage',
                          'https://api.telegram.org/botrotated-token/sendMessage'])

    def test_wire_shape_and_call_signature_are_exact(self):
        log = []
        channel = TelegramChannel(lambda: recording_transport(log), lambda: 'BOT:TOKEN')
        channel.send_message(42, '안녕하세요')
        self.assertEqual(log, [{'url': 'https://api.telegram.org/botBOT:TOKEN/sendMessage',
                                'body': {'chat_id': 42, 'text': '안녕하세요'},
                                'headers': {}, 'timeout': 15}])

    def test_falsy_ok_raises_provider_error_without_leaking_the_api_description(self):
        def transport(url, body, headers, *, timeout):
            return {'ok': False, 'description': 'Unauthorized: bot token is invalid'}

        channel = TelegramChannel(lambda: transport, lambda: 'BOT:TOKEN')
        with self.assertRaises(ProviderError) as caught:
            channel.send_message(42, 'hello')
        self.assertEqual(str(caught.exception), 'Telegram 요청이 실패했습니다. 봇 설정을 확인하세요.')
        self.assertNotIn('Unauthorized', str(caught.exception))

    def test_reply_markup_key_is_absent_unless_supplied(self):
        log = []
        channel = TelegramChannel(lambda: recording_transport(log), lambda: 'BOT:TOKEN')
        keyboard = {'inline_keyboard': [[{'text': '진행 보기', 'callback_data': 'p7v:job-1'}]]}
        channel.send_message(42, 'no keyboard')
        channel.send_message(42, 'with keyboard', keyboard)
        channel.edit_message_text(42, 5, 'no keyboard')
        # Clearing a keyboard is an explicit empty keyboard, not "no keyboard".
        channel.edit_message_text(42, 5, 'cleared keyboard', {'inline_keyboard': []})
        bodies = [entry['body'] for entry in log]
        self.assertEqual(bodies[0], {'chat_id': 42, 'text': 'no keyboard'})
        self.assertEqual(bodies[1], {'chat_id': 42, 'text': 'with keyboard', 'reply_markup': keyboard})
        self.assertEqual(bodies[2], {'chat_id': 42, 'message_id': 5, 'text': 'no keyboard'})
        self.assertEqual(bodies[3], {'chat_id': 42, 'message_id': 5, 'text': 'cleared keyboard',
                                     'reply_markup': {'inline_keyboard': []}})

    def test_get_updates_polls_only_the_handled_update_kinds(self):
        log = []
        channel = TelegramChannel(lambda: recording_transport(log, result=[]), lambda: 'BOT:TOKEN')
        channel.get_updates(11)
        self.assertEqual(log[0]['url'], 'https://api.telegram.org/botBOT:TOKEN/getUpdates')
        self.assertEqual(log[0]['body'], {'offset': 11, 'timeout': 5,
                                          'allowed_updates': ['message', 'callback_query'], 'limit': 20})

    def test_answer_callback_query_body_is_exact(self):
        log = []
        channel = TelegramChannel(lambda: recording_transport(log), lambda: 'BOT:TOKEN')
        channel.answer_callback_query('cb-1', '처리했습니다.')
        self.assertEqual(log[0]['url'], 'https://api.telegram.org/botBOT:TOKEN/answerCallbackQuery')
        self.assertEqual(log[0]['body'], {'callback_query_id': 'cb-1', 'text': '처리했습니다.'})

    def test_connection_verification_uses_the_supplied_token_not_the_stored_one(self):
        log = []
        channel = TelegramChannel(lambda: recording_transport(log, result={'username': 'owner_bot'}),
                                  lambda: 'STORED:TOKEN')
        channel.get_me('CANDIDATE:TOKEN')
        channel.get_webhook_info('CANDIDATE:TOKEN')
        self.assertEqual([entry['url'] for entry in log],
                         ['https://api.telegram.org/botCANDIDATE:TOKEN/getMe',
                          'https://api.telegram.org/botCANDIDATE:TOKEN/getWebhookInfo'])


class TelegramPolicyRoutingTests(unittest.TestCase):
    """Conversation policy must speak to the seam, never to the wire."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(self.temp.name)

        def refuse(url, body, headers=None, timeout=60):
            raise AssertionError(f'conversation policy reached the Telegram wire directly: {url}')

        self.refuse = refuse
        self.service = AgentService(self.store, ModelAdapter(), refuse)
        self.channel = RecordingChannel()
        self.service.telegram = self.channel

    def pair(self):
        self.store.secret('telegram_token', 'BOT:TOKEN')
        self.store.put('telegram', {'enabled': True, 'generation': 'g', 'user_id': 42, 'cursor': 11})

    def test_task_card_lifecycle_routes_through_named_channel_methods(self):
        self.service.create_task_card('job-1', '자료를 요약해 줘', 42)
        self.service.update_task_card({'id': 'job-1', 'message': '자료를 요약해 줘'}, 'running')
        self.assertEqual(self.channel.names, ['send_message', 'edit_message_text'])
        sent = self.channel.calls[0][1]
        self.assertEqual(sent['chat_id'], 42)
        self.assertEqual(sent['reply_markup'], self.service.task_card_markup('job-1', 'queued'))
        edited = self.channel.calls[1][1]
        self.assertEqual((edited['chat_id'], edited['message_id']), (42, 7))
        self.assertEqual(edited['reply_markup'], self.service.task_card_markup('job-1', 'running'))

    def test_polling_routes_through_get_updates_with_the_durable_cursor(self):
        self.pair()
        self.service.poll_telegram()
        self.assertEqual(self.channel.names, ['get_updates'])
        self.assertEqual(self.channel.calls[0][1]['offset'], 11)

    def test_callback_acknowledgement_routes_through_answer_callback_query(self):
        self.pair()
        self.service.ingest_callback({'id': 'cb-1', 'from': {'id': 42}, 'data': 'unhandled',
                                      'message': {'message_id': 5, 'chat': {'id': 42, 'type': 'private'}}}, 'g')
        self.assertEqual(self.channel.names, ['answer_callback_query'])
        self.assertEqual(self.channel.calls[0][1],
                         {'callback_query_id': 'cb-1', 'text': '처리할 수 있는 요청이 아닙니다.'})

    def test_connect_verifies_the_candidate_token_through_the_seam_before_storing_it(self):
        self.channel = RecordingChannel(results={'get_me': {'username': 'owner_bot'},
                                                 'get_webhook_info': {'url': ''}},
                                        probe=lambda: self.store.secret('telegram_token'))
        self.service.telegram = self.channel
        self.service.connect_telegram({'token': '123456:TEST_TOKEN'})
        self.assertEqual(self.channel.names[:2], ['get_me', 'get_webhook_info'])
        self.assertEqual(self.channel.calls[0][1]['token'], '123456:TEST_TOKEN')
        self.assertEqual(self.channel.calls[1][1]['token'], '123456:TEST_TOKEN')
        # The token is proved against Telegram before it becomes stored state.
        self.assertFalse(self.channel.probes[0])
        self.assertFalse(self.channel.probes[1])
        self.assertEqual(self.store.secret('telegram_token'), '123456:TEST_TOKEN')

    def test_service_delegations_still_reach_the_channel(self):
        self.service.telegram_method('sendMessage', {'chat_id': 42, 'text': 'x'})
        self.service.telegram_call('EXPLICIT:TOKEN', 'getMe', {})
        self.assertEqual(self.channel.names, ['call', 'call_with_token'])
        self.assertEqual(self.channel.calls[0][1], {'method': 'sendMessage', 'body': {'chat_id': 42, 'text': 'x'}})
        self.assertEqual(self.channel.calls[1][1]['token'], 'EXPLICIT:TOKEN')

    def test_transport_reassigned_after_construction_is_honoured(self):
        self.pair()
        service = AgentService(self.store, ModelAdapter(), self.refuse)
        log = []
        service.telegram_transport = recording_transport(log, result={'message_id': 1})
        service.telegram.send_message(42, '재할당된 전송을 사용합니다.')
        self.assertEqual([entry['url'] for entry in log],
                         ['https://api.telegram.org/botBOT:TOKEN/sendMessage'])


if __name__ == '__main__':
    unittest.main()
