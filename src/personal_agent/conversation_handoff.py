"""Transport seam for the one personal conversation carried over Telegram.

Conversation policy in :mod:`personal_agent.quickstart_service` decides *what*
the owner is told and *when*.  This module owns *how* that reaches Telegram:
the API base, the per-method URL shape, the request body keys, the timeout and
the failure translation.  Policy code constructs no Telegram API payload.

Two resolution rules are deliberate and load bearing:

* the HTTP transport is read from its owner on every call, so an owner or a
  test may replace ``AgentService.telegram_transport`` after construction and
  the next call honours it;
* the bot token is read from the secret store on every call, so rotating,
  replacing or disconnecting the bot is never served from a captured copy.

``call_with_token`` exists for the connection-verification path only: a token
supplied by the owner is checked against Telegram *before* it is stored, so
that path cannot use the stored-token resolver.
"""
from .providers import ProviderError

TELEGRAM_API_ROOT = 'https://api.telegram.org'
TELEGRAM_TIMEOUT = 15
TELEGRAM_FAILURE_TEXT = 'Telegram 요청이 실패했습니다. 봇 설정을 확인하세요.'
TELEGRAM_POLL_UPDATE_KINDS = ('message', 'callback_query')


class TelegramChannel:
    """Bounded Telegram Bot API surface used by the personal conversation.

    The channel holds no credential and no durable state.  It is given two
    zero-argument resolvers so that neither the transport nor the token is
    captured at construction time.
    """

    def __init__(self, transport_source, token_source):
        self._transport_source = transport_source
        self._token_source = token_source

    @property
    def transport(self):
        """Resolve the live transport callable for this one call."""
        return self._transport_source()

    def call_with_token(self, token, method, body):
        """Call one Bot API method with an explicitly supplied bot token."""
        result = self.transport(f'{TELEGRAM_API_ROOT}/bot{token}/{method}', body, {}, timeout=TELEGRAM_TIMEOUT)
        if not result.get('ok'):
            raise ProviderError(TELEGRAM_FAILURE_TEXT)
        return result['result']

    def call(self, method, body):
        """Call one Bot API method with the currently stored bot token."""
        return self.call_with_token(self._token_source(), method, body)

    def send_message(self, chat_id, text, reply_markup=None):
        body = {'chat_id': chat_id, 'text': text}
        if reply_markup is not None:
            body['reply_markup'] = reply_markup
        return self.call('sendMessage', body)

    def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        body = {'chat_id': chat_id, 'message_id': message_id, 'text': text}
        if reply_markup is not None:
            body['reply_markup'] = reply_markup
        return self.call('editMessageText', body)

    def answer_callback_query(self, callback_query_id, text):
        return self.call('answerCallbackQuery', {'callback_query_id': callback_query_id, 'text': text})

    def get_updates(self, offset, timeout=5, allowed_updates=None, limit=20):
        """Long-poll only the update kinds this conversation actually handles."""
        kinds = TELEGRAM_POLL_UPDATE_KINDS if allowed_updates is None else allowed_updates
        return self.call('getUpdates', {'offset': offset, 'timeout': timeout,
                                        'allowed_updates': list(kinds), 'limit': limit})

    def get_me(self, token):
        """Verify an owner-supplied token before it is stored."""
        return self.call_with_token(token, 'getMe', {})

    def get_webhook_info(self, token):
        """Read webhook state for an owner-supplied token before it is stored."""
        return self.call_with_token(token, 'getWebhookInfo', {})
