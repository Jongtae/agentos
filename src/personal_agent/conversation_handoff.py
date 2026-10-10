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
import json as _json
from urllib.error import HTTPError as _HTTPError, URLError as _URLError
from urllib.request import Request as _Request, build_opener as _build_opener
from urllib.parse import quote as _quote

from .conversation_projection import object_particle
from .providers import NoRedirect, ProviderError

TELEGRAM_API_ROOT = 'https://api.telegram.org'
TELEGRAM_FILE_ROOT = 'https://api.telegram.org/file'
TELEGRAM_TIMEOUT = 15
TELEGRAM_MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
TELEGRAM_FAILURE_TEXT = 'Telegram 요청이 실패했습니다. 봇 설정을 확인하세요.'
#: ``stopped_message_generation`` carries the owner's Stop on a draft (#581).
# #626: edited_message carries live-location updates and owner text edits;
# an edit is recorded as a source revision, never replayed as a request.
# 'managed_bot' (#897): a family member created a bot through the owner's Managed Bots link.
#: #996: ``message_reaction`` - the owner's emoji on an assistant message.  Telegram documents
#: delivery for chats where the bot is an administrator; the bot asks for it anyway and treats
#: every reaction that does arrive as the owner's signal.
TELEGRAM_POLL_UPDATE_KINDS = ('message', 'edited_message', 'callback_query', 'stopped_message_generation', 'managed_bot',
                              'message_reaction')
#: Presence calls (reaction, chat action, draft) are best-effort decoration
#: sent while terminal delivery may be waiting on the same lock, so they get a
#: short budget instead of the full delivery timeout.
TELEGRAM_PRESENCE_TIMEOUT = 4
#: Telegram's documented rejection for malformed formatting entities.
TELEGRAM_ENTITY_REJECTION = "can't parse entities"


class TelegramRejected(ProviderError):
    """Telegram answered and *refused* the request (``ok: false``).

    Unlike a timeout or a lost response this is definite: nothing was
    delivered.  ``error_code``/``description`` come from Telegram's documented
    error envelope; they only classify the refusal and are never shown to the
    owner or logged.
    """

    def __init__(self, error_code=None, description=''):
        super().__init__(TELEGRAM_FAILURE_TEXT, status=error_code)
        self.error_code = error_code
        self.description = str(description or '')

    @property
    def entity_parse_error(self):
        return self.error_code == 400 and TELEGRAM_ENTITY_REJECTION in self.description.lower()


def telegram_request_json(url, body, headers=None, timeout=TELEGRAM_TIMEOUT):
    """``providers.request_json`` for the Bot API, keeping Telegram's error envelope.

    Telegram reports a refused request as HTTP 4xx with a JSON body
    ``{"ok": false, "error_code", "description"}``.  ``request_json`` turns
    every HTTP error into one opaque failure, which makes a definite refusal
    indistinguishable from a lost response.  A bounded, well-formed 4xx
    envelope is returned as data; every other outcome raises the same
    owner-safe ``ProviderError`` texts as ``request_json``.  Each call makes
    exactly one HTTP request.
    """
    req = _Request(url, data=None if body is None else _json.dumps(body).encode(),
                   headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with _build_opener(NoRedirect()).open(req, timeout=timeout) as response:
            raw = response.read(2_000_001)
    except _HTTPError as exc:
        if 400 <= exc.code < 500:
            try:
                envelope = _json.loads(exc.read(65_536))
            except (ValueError, TypeError, OSError):
                envelope = None
            if isinstance(envelope, dict) and envelope.get('ok') is False:
                # #594 item 3: the HTTP status is the classification source;
                # the body's own ``error_code`` is not trusted over it.
                return {'ok': False, 'error_code': exc.code,
                        'description': str(envelope.get('description', ''))[:512]}
        raise ProviderError(f'연결 대상이 HTTP {exc.code} 오류를 반환했습니다. 주소·모델·인증 설정을 확인하세요.',
                            status=exc.code) from None
    except (_URLError, TimeoutError, OSError) as exc:
        timed_out = isinstance(exc, TimeoutError) or isinstance(getattr(exc, 'reason', None), TimeoutError)
        raise ProviderError('연결할 수 없거나 응답 시간이 초과되었습니다. 서버와 네트워크를 확인하세요.',
                            status='timeout' if timed_out else None) from None
    if len(raw) > 2_000_000:
        raise ProviderError('응답이 너무 큽니다. 요청 범위를 줄여 주세요.')
    try:
        return _json.loads(raw)
    except (ValueError, TypeError):
        raise ProviderError('연결 대상이 올바른 JSON 응답을 반환하지 않았습니다.') from None


def telegram_request_file(url, timeout=TELEGRAM_TIMEOUT, max_bytes=TELEGRAM_MAX_DOWNLOAD_BYTES):
    """Fetch one Bot API file without redirects and with a hard byte bound."""
    req = _Request(url, headers={'Accept': 'image/jpeg,image/png,image/webp'})
    try:
        with _build_opener(NoRedirect()).open(req, timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
    except (_HTTPError, _URLError, TimeoutError, OSError) as exc:
        raise ProviderError('Telegram 사진을 내려받지 못했습니다.') from None
    if not isinstance(raw, bytes) or len(raw) > max_bytes:
        raise ProviderError('Telegram 사진이 내려받기 크기 제한을 넘었습니다.')
    return raw


class TelegramChannel:
    """Bounded Telegram Bot API surface used by the personal conversation.

    The channel holds no credential and no durable state.  It is given two
    zero-argument resolvers so that neither the transport nor the token is
    captured at construction time.
    """

    def __init__(self, transport_source, token_source, file_transport_source=None):
        self._transport_source = transport_source
        self._token_source = token_source
        self._file_transport_source = file_transport_source or (lambda: telegram_request_file)

    @property
    def transport(self):
        """Resolve the live transport callable for this one call."""
        return self._transport_source()

    def call_with_token(self, token, method, body, timeout=TELEGRAM_TIMEOUT):
        """Call one Bot API method with an explicitly supplied bot token."""
        result = self.transport(f'{TELEGRAM_API_ROOT}/bot{token}/{method}', body, {}, timeout=timeout)
        if not result.get('ok'):
            raise TelegramRejected(result.get('error_code'), result.get('description'))
        return result['result']

    def call(self, method, body, timeout=TELEGRAM_TIMEOUT):
        """Call one Bot API method with the currently stored bot token."""
        return self.call_with_token(self._token_source(), method, body, timeout=timeout)

    def send_message(self, chat_id, text, reply_markup=None, *, parse_mode=None, reply_to=None):
        """Send one durable message.

        ``reply_to`` anchors it to an owner message through ``reply_parameters``
        with ``allow_sending_without_reply`` so a deleted original never turns
        a delivery into a failure.
        """
        body = {'chat_id': chat_id, 'text': text}
        if reply_markup is not None:
            body['reply_markup'] = reply_markup
        if parse_mode is not None:
            body['parse_mode'] = parse_mode
        if isinstance(reply_to, int):
            body['reply_parameters'] = {'message_id': reply_to, 'allow_sending_without_reply': True}
        return self.call('sendMessage', body)

    def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        body = {'chat_id': chat_id, 'message_id': message_id, 'text': text}
        if reply_markup is not None:
            body['reply_markup'] = reply_markup
        return self.call('editMessageText', body)

    def edit_message_reply_markup(self, chat_id, message_id, reply_markup):
        return self.call('editMessageReplyMarkup', {'chat_id': chat_id, 'message_id': message_id,
                                                    'reply_markup': reply_markup})

    def delete_message(self, chat_id, message_id):
        return self.call('deleteMessage', {'chat_id': chat_id, 'message_id': message_id})

    def answer_callback_query(self, callback_query_id, text=None, show_alert=False):
        body = {'callback_query_id': callback_query_id}
        if text:
            body['text'] = text[:200]
        if show_alert:
            body['show_alert'] = True
        return self.call('answerCallbackQuery', body)

    # --- presence (#581): best-effort, never Evidence -------------------------

    def set_message_reaction(self, chat_id, message_id, emoji):
        """Set one emoji reaction on a message (bots may set at most one); a falsy emoji removes it."""
        return self.call('setMessageReaction', {'chat_id': chat_id, 'message_id': message_id,
                                                'reaction': [{'type': 'emoji', 'emoji': emoji}] if emoji else []},
                         timeout=TELEGRAM_PRESENCE_TIMEOUT)

    def send_chat_action(self, chat_id, action='typing'):
        return self.call('sendChatAction', {'chat_id': chat_id, 'action': action},
                         timeout=TELEGRAM_PRESENCE_TIMEOUT)

    def send_message_draft(self, chat_id, draft_id, text, can_stop=True):
        """Show an ephemeral draft.

        Callers never send empty text: Telegram's empty "Thinking…" placeholder
        renders as a blank bubble on the owner's iOS client (#581, #835).
        """
        body = {'chat_id': chat_id, 'draft_id': draft_id, 'text': text}
        if can_stop:
            body['can_stop'] = True
        return self.call('sendMessageDraft', body, timeout=TELEGRAM_PRESENCE_TIMEOUT)

    def send_rich_message_draft(self, chat_id, draft_id, blocks, can_stop=True):
        """Show an ephemeral rich draft: Telegram's animated thinking block (#858).

        ``blocks`` is the ``InputRichMessage.blocks`` list
        (``telegram_presence.rich_draft_blocks``): first an
        ``InputRichBlockThinking`` (``<tg-thinking>``), which Bot API 10.3
        allows only in ``sendRichMessageDraft``, then optionally one paragraph.
        The same ``draft_id`` as the plain draft, so Stop maps back the same way.
        """
        body = {'chat_id': chat_id, 'draft_id': draft_id, 'rich_message': {'blocks': list(blocks)}}
        if can_stop:
            body['can_stop'] = True
        return self.call('sendRichMessageDraft', body, timeout=TELEGRAM_PRESENCE_TIMEOUT)

    def get_updates(self, offset, timeout=5, allowed_updates=None, limit=20):
        """Long-poll only the update kinds this conversation actually handles."""
        kinds = TELEGRAM_POLL_UPDATE_KINDS if allowed_updates is None else allowed_updates
        return self.call('getUpdates', {'offset': offset, 'timeout': timeout,
                                        'allowed_updates': list(kinds), 'limit': limit})

    def download_photo(self, file_id, max_bytes=TELEGRAM_MAX_DOWNLOAD_BYTES):
        """Download a Telegram photo via getFile, returning bounded bytes and MIME type."""
        if not isinstance(file_id, str) or not file_id or len(file_id) > 512:
            raise ProviderError('Telegram 사진 식별자가 올바르지 않습니다.')
        if not isinstance(max_bytes,int) or isinstance(max_bytes,bool) or not 1<=max_bytes<=TELEGRAM_MAX_DOWNLOAD_BYTES:
            raise ProviderError('Telegram 사진 다운로드 한도를 확인하세요.')
        result = self.call('getFile', {'file_id': file_id})
        path = result.get('file_path') if isinstance(result, dict) else None
        size = result.get('file_size') if isinstance(result, dict) else None
        if isinstance(size, int) and not isinstance(size, bool) and size > max_bytes:
            raise ProviderError('Telegram 사진이 내려받기 크기 제한을 넘었습니다.')
        if not isinstance(path, str) or not path or len(path) > 1024 or path.startswith('/'):
            raise ProviderError('Telegram 사진 경로를 확인할 수 없습니다.')
        pieces = path.split('/')
        if any(piece in ('', '.', '..') for piece in pieces):
            raise ProviderError('Telegram 사진 경로를 확인할 수 없습니다.')
        token = self._token_source()
        url = f'{TELEGRAM_FILE_ROOT}/bot{token}/' + '/'.join(_quote(piece, safe='') for piece in pieces)
        data = self._file_transport_source()(url, timeout=TELEGRAM_TIMEOUT,
                                             max_bytes=max_bytes)
        if not isinstance(data, bytes) or len(data) > max_bytes:
            raise ProviderError('Telegram 사진이 내려받기 크기 제한을 넘었습니다.')
        if data.startswith(b'\xff\xd8\xff'):
            mime = 'image/jpeg'
        elif data.startswith(b'\x89PNG\r\n\x1a\n'):
            mime = 'image/png'
        elif len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            mime = 'image/webp'
        else:
            raise ProviderError('Telegram에서 지원하지 않는 사진 형식을 받았습니다.')
        return {'data': data, 'mime_type': mime}

    def get_me(self, token):
        """Verify an owner-supplied token before it is stored."""
        return self.call_with_token(token, 'getMe', {})

    def get_webhook_info(self, token):
        """Read webhook state for an owner-supplied token before it is stored."""
        return self.call_with_token(token, 'getWebhookInfo', {})


# ---------------------------------------------------------------------------
# Natural intent classification
# ---------------------------------------------------------------------------
# Where authority sits, stated once:
#
#   * An **owner-explicit** form (a slash command or a legacy `메모:`-style
#     prefix) is the owner speaking literally.  It is honoured as written.
#   * An **AgentOS rule** is a literal cue set written in this file and
#     reviewable here.  AgentOS, not a model, decided it.
#   * A **model suggestion** is untrusted input.  It may only *narrow* an
#     ambiguity that the rules already produced, it may never introduce an
#     intent the rules did not find, and it may never select a consequential
#     intent.  ``IntentDecision.authority`` therefore has no ``model`` value
#     and cannot acquire one.
#   * Anything the rules do not recognise is asked, as a bounded semantic
#     question, of the provider-neutral DecisionEngine (PRESENCE-INTENT-01 /
#     #597): does this turn need one of AgentOS's declared capabilities
#     (``CAPABILITY_NEEDS``)?  The engine may only *select* a declared
#     candidate; AgentOS policy thresholds the answer, and an unavailable,
#     abstaining or unsure engine leaves the turn on ``conversation``, the
#     ordinary model-answered route.  No capability is ever guessed, and the
#     judgment grants nothing: the chosen capability still passes its own
#     connection/Grant/approval gates.
#
# The model-suggestion seam below is separate: it can only narrow a rule
# ambiguity, and no call site supplies a suggestion today (an evidence-class
# statement, not a capability claim).
import re
import time

from .decision import MAX_CONTEXT_CHARS, DecisionContext, DecisionPolicy, UnavailableDecisionEngine

INTENT_GREETING = 'greeting'
INTENT_KNOWLEDGE = 'personal-knowledge'
INTENT_SETTINGS = 'settings'
INTENT_WORKSPACE_SEARCH = 'workspace-search'
INTENT_NOTE_CREATE = 'note-create'
INTENT_NOTE_LIST = 'note-list'
#: #1017: the owner-typed ``/ai`` form switches the Main AI with no model in between.
INTENT_MAIN_AI = 'main-ai'
INTENT_CALENDAR_CREATE = 'calendar-create'
INTENT_MAIL_SEARCH = 'mail-search'
#: Read the owner's Picker-selected Google Drive files into this turn, or
#: hand off the Drive connection first (#672: judged, not matched on words).
INTENT_DRIVE_READ = 'drive-read'
#: No longer produced by routing (#672: the Work model loop chooses web
#: search itself).  Kept so a conversation focus or decision recorded before
#: that change still reads as a continuable conversation-route intent.
INTENT_RESEARCH = 'research'
INTENT_CONVERSATION = 'conversation'
INTENT_AMBIGUOUS = 'ambiguous'
#: A request for something this conversation does not offer; answered
#: truthfully, nothing invoked (#478 via #510).
INTENT_UNSUPPORTED = 'unsupported-capability'

AUTHORITY_OWNER = 'owner-explicit'
AUTHORITY_RULE = 'agentos-rule'
AUTHORITY_DEFAULT = 'default'

#: Intents whose *effect* the owner would not want guessed.  Prose may reach
#: a consequential intent, but what it reaches is a draft with an exact
#: preview; the effect needs the owner's explicit approval of that preview,
#: which no classification can supply.  A model suggestion still cannot
#: select one (see ``_with_suggestion``).
CONSEQUENTIAL_INTENTS = frozenset({INTENT_CALENDAR_CREATE})

#: Routes that answer with the ordinary model conversation.  They never
#: compete for ambiguity, because losing one costs the owner nothing.
DEFAULT_ROUTE_INTENTS = frozenset({INTENT_CONVERSATION, INTENT_RESEARCH})

#: Intents a bare "keep going" may resolve to.  Every other intent needs its
#: own content, and reusing stale content is exactly the failure mode the
#: correction/topic-change requirement exists to prevent.
CONTINUABLE_INTENTS = frozenset({INTENT_CONVERSATION, INTENT_RESEARCH})

INTENT_LABELS = {
    INTENT_KNOWLEDGE: '개인 공간 검색',
    INTENT_SETTINGS: '연결 설정 확인/변경',
    INTENT_WORKSPACE_SEARCH: '저장한 작업공간 결과 찾기',
    INTENT_NOTE_CREATE: '메모 기록',
    INTENT_NOTE_LIST: '메모 목록',
    INTENT_MAIN_AI: '기본 AI 바꾸기',
    INTENT_CALENDAR_CREATE: '일정 만들기',
    INTENT_MAIL_SEARCH: '메일 찾기',
    INTENT_DRIVE_READ: 'Google Drive 파일 읽기',
    INTENT_RESEARCH: '웹 조사',
    INTENT_CONVERSATION: '대화로 답하기',
    INTENT_UNSUPPORTED: '제공하지 않는 기능',
}

#: Capabilities an owner may reasonably ask for that this conversation does
#: not offer.  They are declared so the DecisionEngine can *choose* one and
#: the reply can state the actual boundary instead of running the nearest
#: search.  Adding an offered capability is product work, not a new entry.
UNSUPPORTED_CAPABILITIES = {
    'mail-read-body': 'read the body/contents of a found mail',
    'mail-send': 'send a mail or reply to one',
}
UNSUPPORTED_CAPABILITY_TEXT = {
    'mail-read-body': ('찾은 메일의 본문을 읽는 기능은 아직 제공하지 않습니다. 제목, 보낸 사람, 날짜로 찾는 것까지만 '
                       '할 수 있어요.'),
    'mail-send': '메일 보내기나 답장은 제공하지 않습니다. 아무것도 보내지 않았습니다. 메일 찾기는 도울 수 있어요.',
}

#: The capabilities a cue-free turn may be judged to need (#597).  Keys are
#: AgentOS intents or declared-unsupported capabilities; values describe them
#: to the DecisionEngine.  The engine selects among these keys only, so it
#: can never mint an intent.  Adding an offered capability here is product
#: work with its own connector/Grant path, not a phrase list.
#: A judgment key, not an intent: the turn asks for more than one task and
#: at least one needs a declared capability (#672 review).  AgentOS then runs
#: nothing and names the parts, so no part is silently dropped.
SEVERAL_TASKS = 'several-tasks'

#: ``calendar-create`` and ``drive-read`` were matched on request words
#: before #672 ("book", "google drive"); they are judged here instead.
CAPABILITY_NEEDS = {
    INTENT_MAIL_SEARCH: ("search or check the owner's own mailbox (Gmail) for a received message, "
                         "for example whether someone wrote, replied or sent something"),
    INTENT_CALENDAR_CREATE: ("put a new event, meeting or appointment on the owner's own calendar; the "
                             "assistant only drafts it and the owner approves the exact preview"),
    INTENT_DRIVE_READ: ("read, search or summarize files in the owner's own Google Drive, or connect "
                        "Google Drive to do that"),
    SEVERAL_TASKS: ("more than one task in this one message where at least one of them needs one of the "
                    "other listed capabilities, for example creating a calendar event and also saving a note"),
    **UNSUPPORTED_CAPABILITIES,
}


# --- Cue vocabularies ------------------------------------------------------
# Every cue below is a literal an owner can read and an independent reviewer
# can audit.  Korean cues match as substrings; ASCII cues match on word
# boundaries so that "note" does not fire inside "notebook".

_KNOWLEDGE_CUES = ('개인 공간', '내 지식', '내가 저장해 둔', '내가 적어둔', '내 기록에서',
                   'personal space', 'my knowledge', 'knowledge base', 'what do i know about')
_SUBJECT_NOISE_KO = ('에 대해서', '에 대해', '에 대한', '에서', '관련된', '관련', '내용을', '내용',
                       '자료를', '자료', '찾아줘', '찾아 줘', '찾아봐', '찾아', '검색해줘', '검색해',
                       '알려줘', '알려 줘', '보여줘', '보여 줘', '좀',
                      '다시 한번', '다시', '한번', '또')
#: Single-syllable Korean particles are stripped only where they really are
#: particles - at the end of a token - never as a substring, which would
#: corrupt a word such as ``가을``.
_SUBJECT_PARTICLES = ('에서', '에게', '으로', '이랑', '하고', '의', '을', '를', '은', '는', '이', '가')
_SUBJECT_NOISE_EN = ('about', 'find', 'search', 'show', 'tell', 'me', 'the', 'anything',
                       'everything', 'on', 'for', 'please', 'my', 'in', 'from', 'look', 'up')

_SETTINGS_READ_CUES = ('무엇이 연결되어 있어', '무엇을 바꿀 수 있어', '상태 보여', '연결 상태', '어떤 연결',
                       '연결된 것', '연결 목록',
                       "what's connected", 'what is connected', 'show my connections',
                       'connection status', 'what can i change', 'list my connections')
# Mirrors SettingsOrchestrator._intent: an action alone or a target alone is
# never a settings change request.
_SETTINGS_ACTIONS = ('pause', 'disconnect', 'resume', '일시 정지', '연결 해제', '다시 시작', '재개')
_SETTINGS_TARGETS = ('drive', '드라이브', 'calendar', '캘린더', '일정', 'mcp')

_WORKSPACE_CUES = ('작업공간', '워크스페이스', '저장한 결과', '저장된 결과', '저장한 파일', '저장된 파일',
                   '저장해 둔 파일', '내가 저장한',
                   'workspace', 'saved result', 'saved results', 'saved file', 'saved files',
                   'file i saved', 'files i saved')
_WORKSPACE_VERBS = ('찾아', '찾을', '검색', '열어', '보여', '가져와', '불러와', '다시 써', '재사용',
                    'open', 'show', 'find', 'search', 'pull up', 'reuse', 'get')

# Mail is a read.  The object cues below never pair with a send/reply verb,
# so "메일 보내줘" cannot become a mailbox read: it matches no rule and stays
# on the ordinary conversation route.  Sending mail is not a capability this
# conversation offers at all.
_MAIL_OBJECTS = ('메일', '이메일', '받은편지함', '메일함', 'email', 'emails', 'mail', 'inbox', 'gmail')
# The polite ``-해/-해줘`` forms are listed as cues in their own right, not
# stripped afterwards: ``_without_cues`` removes the longest match first, so
# listing them keeps "확인해줘" from leaving "해줘" behind in the query.
_MAIL_VERBS = ('찾아', '찾을', '찾아줘', '검색해줘', '검색해', '검색', '읽어', '확인해줘', '확인해',
               '확인', '보여', '알려', '왔', '열어', '열어줘',
               'search', 'find', 'look', 'check', 'show', 'read', 'open', 'any')
_MAIL_CONTENT_KINDS = {
    'body': ('본문', '내용', '전체 내용', '원문', 'body', 'content', 'full message'),
    'metadata': ('제목', '보낸 사람', '발신자', '날짜', 'subject', 'sender', 'date'),
}

# A note is written when the owner says "write it down", not when the owner
# says "remember" - whether a turn asks AgentOS to remember something is the
# DecisionEngine's ``explicit_memory_request`` judgment (#597) and must not
# be shadowed here.
_NOTE_CREATE_RE = re.compile(
    r'(?:메모|기록)\s*(?::|해\s*줘|해\s*둬|해\s*두|해\s*놔|해\s*놓|로\s*남겨|남겨\s*줘|남겨)'
    r'|적어\s*(?:둬|줘|놔|두)'
    r'|\b(?:note (?:this|that|it)(?: down)?|take a note|make a note|jot (?:this|that|it) down'
    r'|write (?:this|that|it) down|add a note)\b',
    re.I)
_NOTE_PRONOUNS = ('이거', '이것', '그거', '그것', '저거', 'this', 'that', 'it')
_NOTE_LEAD_EN = ('of', 'that', 'about', 'to', 'saying', ':', '-')
_NOTE_TRAIL_KO = ('을', '를', '은', '는', '이', '가', '다음 내용', '내용', '이것', '이거')

# A correction or topic change is the owner overriding what came before.  It
# must never be read as "keep doing the previous thing".
_CORRECTION_CUES = ('아니', '아니라', '그게 아니라', '말고', '대신', '취소', '됐고', '잊어',
                    'no,', 'not that', 'instead', 'forget that', 'never mind', 'nevermind',
                    'scratch that', 'actually no')
_CONTINUATION_CUES = ('계속', '이어서', '계속해', '더 해줘', '그대로',
                      'continue', 'go on', 'keep going', 'same thing', 'carry on')

def _cue_hits(text, lowered, cues):
    """Return the literal cues present in one utterance, in table order."""
    hits = []
    for cue in cues:
        if cue.isascii():
            if re.search(rf'(?<![a-z0-9]){re.escape(cue)}(?![a-z0-9])', lowered):
                hits.append(cue)
        elif cue in text:
            hits.append(cue)
    return hits


def eligible_for_followup_judgment(text):
    """Structural gate for asking the semantic continuity question.

    This does not inspect retry/cancel/reference words. It only bounds the
    extra decision-model call to a non-empty, short follow-up-sized utterance;
    the provider-neutral DecisionEngine decides whether any relation exists.
    """
    return isinstance(text, str) and 0 < len(text.strip()) <= 240


#: Structural bound (not a cue) on asking the capability-need question: an
#: owner request is short; a long pasted text is answered by the ordinary
#: conversation route instead of being sent to the DecisionEngine too.
CAPABILITY_JUDGMENT_MAX_CHARS = 500


def eligible_for_capability_judgment(text):
    """Structural gate for asking which declared capability a turn needs."""
    return isinstance(text, str) and 0 < len(text.strip()) <= CAPABILITY_JUDGMENT_MAX_CHARS


def _trim_particle(token):
    """Drop one trailing Korean particle from a token, never a syllable."""
    for particle in _SUBJECT_PARTICLES:
        if token.endswith(particle) and len(token) > len(particle) + 1:
            return token[:-len(particle)]
    return token


def _without_cues(value, cues):
    """Remove matched cues longest first, so a short cue cannot strand the
    tail of a longer one it overlaps (``my knowledge`` vs ``knowledge base``)."""
    for cue in sorted(cues, key=len, reverse=True):
        value = re.sub(re.escape(cue), ' ', value, flags=re.I)
    return value


def _strip_noise(value):
    """Reduce an utterance to its subject by removing AgentOS cue filler."""
    for token in _SUBJECT_NOISE_KO:
        value = value.replace(token, ' ')
    for token in _SUBJECT_NOISE_EN:
        value = re.sub(rf'(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])', ' ', value, flags=re.I)
    value = ' '.join(_trim_particle(token) for token in value.split())
    return re.sub(r'\s+', ' ', value.strip(' \t?!.,;:·"“”‘’')).strip()


# --- Semantic judgments (PRESENCE-DEC-01 / #417) ----------------------------
# Some routing questions are semantic, not lexical: "does this turn withdraw
# the request that is waiting for a connection?" and "does this mail-shaped
# request ask for an unsupported action?". They are asked of the provider-neutral DecisionEngine
# (decision.py, docs/decision-layer.en.md) and reduced to a three-valued
# result by AgentOS policy.  Anything the engine cannot answer stays
# ``unavailable`` and policy takes its declared fallback; no cue list or
# regex decides in its place.

JUDGMENT_UNAVAILABLE = 'unavailable'
JUDGMENT_YES = 'yes'
JUDGMENT_NO = 'no'

FOLLOWUP_RETRY = 'retry'
FOLLOWUP_REFERENCE = 'reference'
FOLLOWUP_CANCEL = 'cancel'
FOLLOWUP_CORRECTION = 'correction'
FOLLOWUP_RELATIONS = (FOLLOWUP_RETRY, FOLLOWUP_REFERENCE, FOLLOWUP_CANCEL, FOLLOWUP_CORRECTION)
FOLLOWUP_QUESTION = (
    'Classify only how the owner latest message relates to the immediately previous Work. '
    'Choose retry only when they ask to run that previous request again; reference when they '
    'refer to its result/context without repeating it; cancel when they ask to stop or withdraw '
    'that previous Work; correction when they replace or correct its parameters. Choose '
    'none-of-these for a new topic, an unrelated request, or when the relation is unclear. '
    'This judgment does not authorize any action.'
)

#: #999: a message that arrives while an earlier request is still being worked on.
STEER_PROPOSITION = ('The assistant is still working on the owner\'s earlier request (given). The owner\'s latest '
                     'message is meant for that running task: a remark, preference, constraint, choice or correction '
                     'the work in progress should take into account now. It is false when the message is a new, '
                     'separate request, a question to be answered on its own, a request to stop, or when it is '
                     'unclear. This judgment does not authorize any action.')
#: #996: the owner's answer to "기억했어요: ..." - a typed message or an emoji reaction on that notice.
MEMORY_WITHDRAWN_PROPOSITION = ('The assistant has just told the owner that it remembered the facts given. The owner\'s '
                                'response (given: a typed message, or an emoji reaction on that notice) tells the '
                                'assistant not to keep them - a no, "don\'t remember that", "that\'s wrong", a '
                                'dismayed, embarrassed or disapproving reaction, or an equivalent in any language. It is '
                                'false when the response agrees, likes or thanks, is about something else, or is unclear. '
                                'This judgment does not delete anything.')
WITHDRAWAL_PROPOSITION = ('The owner\'s latest message withdraws or cancels the request that is waiting for '
                          'the listed connection (rather than acknowledging it, changing topic, or asking '
                          'something unrelated).')
#: #855: a pending settings draft is confirmed or declined by the owner's next typed
#: message; two propositions, each judged over the draft summary and the message.
SETTINGS_CONFIRM_PROPOSITION = ('A settings change is waiting for the owner\'s confirmation (the pending change '
                                'is given). The owner\'s latest message plainly tells the assistant to go ahead and '
                                'apply that change - a yes, an agreement, "do it", "change it that way" or an '
                                'equivalent in any language. It is false when the message declines, asks for a '
                                'different value, asks a question, changes the topic, or when it is unclear. '
                                'This judgment does not apply anything.')
SETTINGS_DECLINE_PROPOSITION = ('A settings change is waiting for the owner\'s confirmation (the pending change '
                                'is given). The owner\'s latest message plainly declines it - a no, "leave it", '
                                '"don\'t change it", "cancel" or an equivalent in any language. It is false when '
                                'the message agrees, asks a question, asks for a different value, changes the '
                                'topic, or when it is unclear. This judgment does not cancel anything.')
UNSUPPORTED_QUESTION = ('Is the owner asking the assistant to do one of these things it does not offer: '
                        + '; '.join(f'{key} = {label}' for key, label in UNSUPPORTED_CAPABILITIES.items())
                        + '? Choose that capability. If the request is anything else (searching mail by '
                        'subject/sender/date, notes, calendar, files, research, ordinary conversation), '
                        'choose none-of-these.')
CAPABILITY_NEED_QUESTION = ('Does answering the owner\'s message require one of these assistant capabilities: '
                            + '; '.join(f'{key} = {label}' for key, label in CAPABILITY_NEEDS.items())
                            + '? Choose a capability only when the owner is asking for exactly that on their own '
                            'account, whatever words they use; choose several-tasks when the message also asks '
                            'for something else. Choose none-of-these for ordinary conversation, '
                            'general knowledge, public web research, notes, reading or changing existing calendar '
                            'events, local files, something they only mention, or when it is unclear. This '
                            'judgment does not authorize any action.')
MAIL_QUERY_TERM_QUESTION = ('The owner is asking about their own mail. Which one of the listed terms, all taken from '
                            'the owner\'s message, best identifies the mail to look for - its sender, organisation '
                            'or subject? Choose none-of-these if no listed term identifies it. This judgment does '
                            'not authorize any action.')
#: At most this many of the owner's own words are offered as query terms.
MAIL_QUERY_MAX_TERMS = 12
# #858: the reaction emoji on the owner's Telegram message, chosen by the
# Judgment AI.  The candidates come from the caller (``telegram_presence``
# keeps the curated, documented set); the questions here only frame the choice.
TURN_REACTION_QUESTION = ('The owner just sent this message to their personal assistant, which is starting to work '
                          'on it. Choose the one reaction emoji that best acknowledges the message itself - its '
                          'tone, mood and what it asks - as a warm, attentive secretary would tap on it. Vary with '
                          'the message; do not default to the same emoji. Choose none-of-these only if no listed '
                          'emoji fits. This judgment is presentation only and does not authorize any action.')
CLOSING_REACTION_QUESTION = ('The assistant has answered the owner\'s message; the answer was delivered and the work '
                             'succeeded. Choose the one reaction emoji that best closes this exchange, fitting the '
                             'owner\'s message and the content-free fact that it received a successful answer, '
                             'as a warm secretary would tap on the request once it is done. '
                             'Vary with the exchange; do not default to the same emoji. Choose none-of-these only if '
                             'no listed emoji fits. This judgment is presentation only and never claims more than '
                             'the observed Work outcome.')
PROGRESS_REACTION_QUESTION = ('The assistant is partway through the current step described here. Choose the one listed '
                              'reaction emoji that best acknowledges this progress without implying the whole request '
                              'is finished. Vary it across different steps when a different emoji fits. Choose '
                              'none-of-these if no listed emoji fits. This judgment is presentation only.')
#: Recipient/source endings trimmed from a query-term candidate so a Gmail
#: search gets the bare name ("집주인한테" -> "집주인").  Query formatting only;
#: which term is used is the DecisionEngine's selection.
_TERM_ENDINGS = ('한테서', '에게서', '한테', '께서', '께')
MEMORY_REQUEST_PROPOSITION = ('The owner\'s latest message explicitly instructs the assistant to remember, keep '
                              'in mind or not forget a specific fact, value or preference that the owner states in '
                              'that same message, for later conversations. It is also true when the owner asserts, '
                              'in the first person and without hedging, a durable fact about themselves or their '
                              'household for the assistant to use from now on - an allergy or dietary restriction, '
                              'a food or product preference, where they live or work, a store or service they '
                              'prefer - even without the word "remember". It is false when the owner asks the '
                              'assistant not to remember something, when there is no stated value to keep (a '
                              'casual remark or a generic "don\'t forget"), when the statement is hedged, '
                              'uncertain or hypothetical rather than asserted, when they ask for a note, file or '
                              'reminder instead, or when it is unclear. This judgment does not write anything.')
#: #805 review: the #597 question asked per proposed owner-model fact.
MEMORY_FACT_PROPOSITION = ('The owner\'s latest message itself asks the assistant to remember the proposed memory, or '
                           'asserts it in the first person and without hedging as a durable fact about the owner or '
                           'their household for the assistant to use from now on. The proposed value must be what '
                           'the owner said in that message, not an inference, a summary of an answer or a one-off '
                           'plan. It is false when the message does not say it, when it is hedged, uncertain or '
                           'hypothetical, when it is about someone else, when the owner asks not to remember it, or '
                           'when it is unclear. This judgment does not write anything.')
#: SEC-ATTN-01 (#659): is the owner's own message the acceptance of this preparation?
PREPARATION_REQUEST_PROPOSITION = ('The owner\'s latest message itself asks the assistant to remind them of something, or '
                                   'to prepare or look something up for them ahead of a later time or on a repeating '
                                   'schedule, and the proposed preparation matches that request: its kind, its goal, its '
                                   'time (as the owner stated it, or derived from what the owner referred to, such as '
                                   'shortly before an event the owner asked to be reminded of) and its repetition (none '
                                   'unless the owner asked for one). It is false when the owner only asks something to be '
                                   'answered now, when the assistant would be offering the preparation on its own '
                                   'initiative, when the time or repetition differs from what the owner asked, or when it '
                                   'is unclear. This judgment schedules nothing.')
#: SEC-ATTN-02 (#719): does one run of an owner-accepted watch need to reach the owner now?
WATCH_NOTIFY_PROPOSITION = ('The owner accepted a standing watch with the goal shown and asked to be told only when '
                            'it matters. This run\'s result shows something the goal asks the owner to be told about '
                            'or to act on now, and it is new compared with the last notification the owner received '
                            '(a changed situation or a different action). It is false when the result says nothing '
                            'needs the owner\'s attention yet, when it only repeats what the last notification already '
                            'said, when the run could not observe what the goal needs, or when it is unclear. This '
                            'judgment sends nothing.')
#: SEC-LOOP-01 (#657), ARCH-THIN-01 (#820): the one outcome judgment of a Work -
#: did the reply serve the owner's message, given the conversation?  Step
#: bookkeeping is evidence for it, never a verdict of its own.
GOAL_REACHED_PROPOSITION = ('The reply serves the owner\'s message, read in the light of the recent conversation and '
                            'what AgentOS knows about the owner (owner_context). What the message refers to is read '
                            'from the recent conversation and continues (the earlier exchange it follows up) first; '
                            'owner_context settles it only when the conversation does not, and a saved fact that '
                            'merely shares words with the message is not its subject. The reply answers what the message asks, does '
                            'what it asks, or - when the owner tells something rather than asks - responds to it the way '
                            'a capable personal secretary would. A reply that asks the owner for information or a '
                            'decision the message needs, which neither the message, the recent conversation nor the owner '
                            'context provides, also serves it. Judge whether it serves the message, not whether it is '
                            'perfect: a useful reply that could be more detailed still serves it. Every statement in the '
                            'reply that something was found, read, saved, added, booked, sent or changed is supported by '
                            'the observations - results that tools actually returned, as AgentOS recorded them; the '
                            'reply\'s own claims are not evidence. A current fact that changes over time or depends on '
                            'place is acceptable when the observations or the owner context support it, or when the reply '
                            'plainly presents it as approximate or unverified; a source the reply names counts only when '
                            'that source appears in the observations. A worker\'s own web search whose results AgentOS '
                            'could not see shows that the lookup was made: what the reply presents as found there was '
                            'looked up, not invented, though unverified, and does not by itself make the reply false; a '
                            'claim that something was saved, added, booked, sent or changed still needs the observations. '
                            'It is '
                            'false when the reply does not address the owner\'s message or addresses a different or '
                            'earlier topic, serves only part of it, claims an action the observations do not show, states '
                            'a changing fact as checked when nothing supports it, asks for something the message, the '
                            'conversation or the owner context already says, says the message carries an attachment '
                            '(a photo, a file) the message states it does not have, or - when the message asks about something '
                            'or asks for something to be done - says instead that it lacks the information, offers to '
                            'look it up, check it or do it, or asks the owner what it is or why they ask, when the '
                            'observations show no attempt to find it: the assistant can look things up, so an offer to '
                            'is not an answer.')
UNSUPPORTED_JUDGMENT_UNAVAILABLE = ('요청을 안전하게 구분할 판단 기능을 사용할 수 없어 메일을 검색하거나 다른 처리를 하지 않았습니다. '
                                   '메일을 찾으려는 요청이라면 검색할 내용을 다시 구체적으로 적어 주세요.')
MIXED_MAIL_ACTION_CLARIFICATION = ('지원하지 않는 메일 발송 요청과 다른 작업이 함께 있어 아무 작업도 실행하지 않았습니다. '
                                   '메일은 보내지 않으며, 나머지 작업만 따로 요청해 주세요.')

class Judgment:
    """One bounded judgment reduced by policy.  It informs routing; it never authorizes."""

    __slots__ = ('outcome', 'value', 'source')

    def __init__(self, outcome, value=None, source='policy'):
        self.outcome, self.value, self.source = outcome, value, source

    def __repr__(self):  # pragma: no cover - diagnostic only
        return f'<Judgment {self.outcome} from {self.source}>'


class ConversationJudgments:
    """The conversation's bounded semantic questions, asked over minimal context.

    Builds a ``DecisionContext``, asks the engine, and applies
    ``DecisionPolicy``. Swapping the engine changes no authority semantics.

    Every context is built by :meth:`_context`, which passes each fact through
    ``redactor(text, private)`` first (#672 review, pilot boundary 1: secrets
    never enter a model prompt).  The service supplies the redactor - the
    stored secrets' literal values and credential shapes, and with
    ``private`` the current Work's saved private values - so this module never
    imports the service.  As for the completion judgment (#657
    ``goal_judgment``), the owner's own words (``OWNER_FACTS``) have only
    secrets removed: the values a Work saved came from them, and removing
    those would change the question asked.  Credential-shaped tokens are
    removed even with no redactor, and a failing redactor withholds the fact
    rather than sending it unredacted.
    """

    #: Facts that are the owner's own words.
    #: #836: ``already_noted`` is what the owner's own message already gave the Work
    #: (its saved values, #831), so it is treated like the owner's words.
    OWNER_FACTS = frozenset({'owner_message', 'owner_request', 'owner_followup', 'terms', 'owner_context', 'already_noted',
                             'pending_change'})

    def __init__(self, engine=None, policy=None, redactor=None):
        self.engine = engine or UnavailableDecisionEngine()
        self.policy = policy or DecisionPolicy()
        self.redactor = redactor

    def redact(self, text, private=True):
        """``text`` as it may reach the decision engine (deterministic, no judgment)."""
        from .bounded_execution import SECRET_PATTERN
        text = str(text or '')
        try:
            if self.redactor is not None:
                text = str(self.redactor(text, private=private))
        except Exception:
            return '[redacted]'
        return SECRET_PATTERN.sub('[redacted]', text)

    def _context(self, purpose, facts, *, uncut=None, **options):
        """The one ``DecisionContext`` builder: every fact redacted first.

        ``uncut`` names one fact (or a tuple of facts) whose length widens the
        bound instead of being cut (#657 ``goal-reached``: the owner's message;
        #820: also the caller-bounded reply and conversation).
        """
        facts = {label: self.redact(value, private=label not in self.OWNER_FACTS) for label, value in facts.items()}
        if uncut is not None:
            names = (uncut,) if isinstance(uncut, str) else tuple(uncut)
            options['max_chars'] = MAX_CONTEXT_CHARS + sum(len(facts[name]) for name in names)
        return DecisionContext(purpose, facts, **options)

    def parked_work_withdrawn(self, utterance, parked_connectors):
        """Does ``utterance`` withdraw the owner's request(s) parked for
        ``parked_connectors``?  Unavailable/unknown keeps them parked."""
        labels = ', '.join(CONNECTOR_LABELS.get(c) or LOCAL_AUTHORITY_LABELS.get(c, c) for c in parked_connectors)
        context = self._context('parked-work-withdrawal',
                                  {'waiting_connection': labels, 'owner_message': utterance})
        decision = self.engine.judge(context, WITHDRAWAL_PROPOSITION)
        verdict = self.policy.binary(decision)
        return Judgment(JUDGMENT_UNAVAILABLE if verdict == 'unknown' else verdict,
                        source=decision.confidence.provider or decision.outcome)

    def steers_running_work(self, running_request, utterance):
        """Is ``utterance`` meant for the Work still running on ``running_request`` (#999)?

        Both texts are the owner's own words.  Unavailable or unknown leaves the
        message to run as its own Work afterwards, as before.
        """
        context = self._context('running-work-steer',
                                {'running_request': running_request, 'owner_message': utterance},
                                uncut='owner_message')
        decision = self.engine.judge(context, STEER_PROPOSITION)
        verdict = self.policy.binary(decision)
        return Judgment(JUDGMENT_UNAVAILABLE if verdict == 'unknown' else verdict,
                        source=decision.confidence.provider or decision.outcome)

    def memory_withdrawn(self, remembered, response):
        """Does the owner's ``response`` to a saved-memory notice ask not to keep ``remembered`` (#996)?

        ``response`` is the owner's typed message or a description of their
        reaction.  Unavailable or unknown keeps the facts.
        """
        context = self._context('memory-withdrawal', {'remembered': remembered, 'owner_response': response},
                                uncut='owner_response')
        decision = self.engine.judge(context, MEMORY_WITHDRAWN_PROPOSITION)
        verdict = self.policy.binary(decision)
        return Judgment(JUDGMENT_UNAVAILABLE if verdict == 'unknown' else verdict,
                        source=decision.confidence.provider or decision.outcome)

    def settings_draft_confirmed(self, pending_change, utterance):
        """Does ``utterance`` plainly confirm applying ``pending_change`` (#855)?  Unavailable applies nothing."""
        context = self._context('settings-draft-confirmation',
                                {'pending_change': pending_change, 'owner_message': utterance})
        decision = self.engine.judge(context, SETTINGS_CONFIRM_PROPOSITION)
        verdict = self.policy.binary(decision)
        return Judgment(JUDGMENT_UNAVAILABLE if verdict == 'unknown' else verdict,
                        source=decision.confidence.provider or decision.outcome)

    def settings_draft_declined(self, pending_change, utterance):
        """Does ``utterance`` plainly decline ``pending_change`` (#855)?  Unavailable keeps it pending."""
        context = self._context('settings-draft-decline',
                                {'pending_change': pending_change, 'owner_message': utterance})
        decision = self.engine.judge(context, SETTINGS_DECLINE_PROPOSITION)
        verdict = self.policy.binary(decision)
        return Judgment(JUDGMENT_UNAVAILABLE if verdict == 'unknown' else verdict,
                        source=decision.confidence.provider or decision.outcome)

    def unsupported_capability(self, utterance):
        """Does ``utterance`` ask for a declared-but-unavailable capability?
        ``value`` is its key on yes; a confident none-of-these is no."""
        # `utterance` is a minimized cue summary assembled by IntentClassifier,
        # never the owner's raw mail query or surrounding private text.
        context = self._context('unsupported-capability', {'owner_message': utterance})
        decision = self.engine.choose(context, tuple(UNSUPPORTED_CAPABILITIES), UNSUPPORTED_QUESTION)
        choice = self.policy.selection(decision)
        if choice is not None:
            return Judgment(JUDGMENT_YES, value=choice, source=decision.confidence.provider or decision.outcome)
        if self.policy.confident_selection(decision):
            return Judgment(JUDGMENT_NO, source=decision.confidence.provider or decision.outcome)
        return Judgment(JUDGMENT_UNAVAILABLE, source=decision.outcome)

    def followup_relation(self, utterance, previous_intent, previous_status):
        """Classify one short anaphoric turn against one focused Work.

        Previous request/result content is deliberately absent. The engine
        sees only the current short utterance plus prior intent/status; the
        selected relation still passes deterministic execution gates later.
        """
        context = self._context('conversation-followup', {
            'owner_message': utterance,
            'previous_intent': previous_intent or '',
            'previous_status': previous_status or '',
        })
        decision = self.engine.choose(context, FOLLOWUP_RELATIONS, FOLLOWUP_QUESTION)
        choice = self.policy.selection(decision)
        if choice is not None:
            return Judgment(JUDGMENT_YES, value=choice,
                            source=decision.confidence.provider or decision.outcome)
        if self.policy.confident_selection(decision):
            return Judgment(JUDGMENT_NO, source=decision.confidence.provider or decision.outcome)
        return Judgment(JUDGMENT_UNAVAILABLE, source=decision.outcome)

    def capability_need(self, utterance):
        """Which declared capability, if any, does ``utterance`` need (#597)?

        ``value`` is a ``CAPABILITY_NEEDS`` key on yes; a confident
        none-of-these is no; anything else is unavailable and the caller
        stays on the ordinary conversation route.  The context is the one
        short owner utterance only - no history, Memory, files or mail.
        """
        context = self._context('capability-need', {'owner_message': utterance})
        decision = self.engine.choose(context, tuple(CAPABILITY_NEEDS), CAPABILITY_NEED_QUESTION)
        choice = self.policy.selection(decision)
        if choice is not None:
            return Judgment(JUDGMENT_YES, value=choice, source=decision.confidence.provider or decision.outcome)
        if self.policy.confident_selection(decision):
            return Judgment(JUDGMENT_NO, source=decision.confidence.provider or decision.outcome)
        return Judgment(JUDGMENT_UNAVAILABLE, source=decision.outcome)

    def turn_reaction(self, utterance, candidates):
        """The reaction emoji for the owner's message when its Work starts (#858).

        ``candidates`` is the curated set of documented Telegram reactions;
        the choice is one of them or None (unavailable, unconfident, or
        none-of-these), in which case the caller keeps its deterministic emoji.
        The context is the one owner message only.
        """
        candidates = tuple(candidates)
        if not candidates:
            return None
        context = self._context('turn-reaction', {'owner_message': utterance}, uncut='owner_message')
        decision = self.engine.choose(context, candidates, TURN_REACTION_QUESTION)
        return self.policy.selection(decision)

    def closing_reaction(self, utterance, candidates, wrote=False):
        """The reaction emoji that closes a succeeded, delivered answer (#858).

        Asked only when ``outcome_reaction`` already allows a closing emoji;
        the context contains the owner message and content-free delivery facts,
        never the answer text, which may contain private source material.
        ``wrote`` says the Work observably saved a note or Memory item.
        """
        candidates = tuple(candidates)
        if not candidates:
            return None
        facts = {'owner_message': utterance,
                 'answer_delivered': 'yes',
                 'saved_a_note_or_memory': 'yes' if wrote else 'no'}
        context = self._context('closing-reaction', facts, uncut='owner_message')
        decision = self.engine.choose(context, candidates, CLOSING_REACTION_QUESTION)
        return self.policy.selection(decision)

    def progress_reaction(self, step_description, candidates):
        """Choose a presentation reaction for one already-redacted running step.

        The context contains only the current generic progress line, never the
        owner request or Work history. AgentOS sends a result only if it is in
        the curated candidates; unavailable leaves the current reaction alone.
        """
        candidates = tuple(candidates)
        if not candidates:
            return None
        context = self._context('progress-reaction', {'current_step': step_description})
        decision = self.engine.choose(context, candidates, PROGRESS_REACTION_QUESTION)
        return self.policy.selection(decision)

    def mail_query_term(self, utterance, terms):
        """Which of ``terms`` (the owner's own words) identifies the mail sought?

        Candidates are index labels (``term-1`` ...) so the decision and its
        audit row stay content-free; the caller maps the label back to the
        owner's word.  ``value`` is the index on yes.
        """
        labels = tuple(f'term-{index}' for index in range(1, len(terms) + 1))
        context = self._context('mail-query-term', {
            'owner_message': utterance,
            'terms': '; '.join(f'{label} = {term}' for label, term in zip(labels, terms)),
        })
        decision = self.engine.choose(context, labels, MAIL_QUERY_TERM_QUESTION)
        choice = self.policy.selection(decision)
        if choice is not None:
            return Judgment(JUDGMENT_YES, value=labels.index(choice),
                            source=decision.confidence.provider or decision.outcome)
        if self.policy.confident_selection(decision):
            return Judgment(JUDGMENT_NO, source=decision.confidence.provider or decision.outcome)
        return Judgment(JUDGMENT_UNAVAILABLE, source=decision.outcome)

    def goal_reached(self, request, observations, failed_steps='', work_id=None, answer='', conversation='',
                     owner_context='', continues=''):
        """Did the reply serve the owner's ``request`` (#657, #820)?  The one outcome judgment.

        One ``judge`` call over the owner's message (never cut), the recent
        conversation, the worker's reply (model-stated, not evidence), the
        tool results AgentOS recorded and the run's failed steps.  Only a
        confident yes lets the Work succeed; no or unavailable leaves it
        short of succeeded, and the reply is delivered either way.  The
        caller bounds and redacts the other facts.
        """
        request = str(request or '')
        facts = {'owner_request': request, 'recent_conversation': conversation or 'none',
                 # #980: the earlier exchange this message was judged to follow up, when linked.
                 'continues': continues or 'none',
                 'owner_context': owner_context or 'none',
                 'reply': answer or 'none (only the observations are known)',
                 'observations': observations, 'failed_steps': failed_steps or 'none'}
        context = self._context('goal-reached', facts, work_id=work_id,
                                uncut=('owner_request', 'reply', 'recent_conversation', 'continues', 'owner_context'))
        decision = self.engine.judge(context, GOAL_REACHED_PROPOSITION)
        verdict = self.policy.binary(decision)
        return Judgment(JUDGMENT_UNAVAILABLE if verdict == 'unknown' else verdict,
                        source=decision.confidence.provider or decision.outcome)

    def explicit_memory_request(self, utterance):
        """Does ``utterance`` explicitly ask AgentOS to remember a stated value (#597)?

        Judgment only.  A yes lets AgentOS issue the existing owner-request
        memory approval for this Work; the deterministic value-coverage and
        key-replacement checks (``Capabilities.memory_write_refusal``) still
        decide whether a proposed write is canonical or a MemoryCandidate.
        No / unavailable issues nothing, so any write stays a candidate.
        """
        context = self._context('explicit-memory-request', {'owner_message': utterance})
        decision = self.engine.judge(context, MEMORY_REQUEST_PROPOSITION)
        verdict = self.policy.binary(decision)
        return Judgment(JUDGMENT_UNAVAILABLE if verdict == 'unknown' else verdict,
                        source=decision.confidence.provider or decision.outcome)

    def owner_model_proposals(self, request, answer, profile, clock, work_id=None, cancelled=None, noted=(),
                              situation=None, situation_turns=''):
        """``(data, decision)``: durable owner-model proposals from one finished Work (#805).

        One ``structured`` call over the owner's request (owner words, never
        cut), the final answer excerpt (model-stated), the profile snapshot and
        the clock, each redacted first, plus what the same Work already noted
        (``noted``, #836) so a fact is asked about once, and the live running note of
        the owner's day (``situation``, #1004; None or '' is said as none) with the
        earlier turns it does not include yet (``situation_turns``).  ``data`` is the answer only when
        decided with enough confidence; what may be stored is the caller's
        deterministic validation.  Judgment only: it writes nothing.
        """
        from .decision import OUTCOME_UNAVAILABLE, StructuredDecision
        from .owner_model import (ANSWER_CHARS, CLOCK_CHARS, PROFILE_CHARS, PURPOSE, QUESTION, SCHEMA, SITUATION_CHARS,
                                  SITUATION_TURNS_CHARS, shape)
        # Redacted before they are cut, so a cut never leaves part of a secret.
        facts = {'owner_request': str(request or ''),
                 'final_answer_excerpt': self.redact(answer)[:ANSWER_CHARS] or 'none',
                 'owner_profile': self.redact(profile)[:PROFILE_CHARS] or 'none',
                 'clock': self.redact(clock)[:CLOCK_CHARS] or 'unknown',
                 'already_noted': self.redact('\n'.join(str(item) for item in noted or ()),
                                              private=False)[:PROFILE_CHARS] or 'none',
                 'current_situation': self.redact(situation or '')[:SITUATION_CHARS] or 'none',
                 'turns_since_situation': self.redact(situation_turns or '')[-SITUATION_TURNS_CHARS:] or 'none'}
        context = self._context(PURPOSE, facts, work_id=work_id, uncut='owner_request', cancelled=cancelled)
        method = getattr(self.engine, 'structured', None)
        decision = (method(context, QUESTION, SCHEMA, shape) if method is not None
                    else StructuredDecision(OUTCOME_UNAVAILABLE))
        return self.policy.structured(decision), decision

    def self_review(self, request, answer, outcome, evaluation, followup, profile, reason, work_id=None, cancelled=None):
        """``(data, decision)``: one self-review of a Work that fell short (#998).

        One ``structured`` call over the owner's request and follow-up (owner
        words, never cut), the final answer excerpt (model-stated), the
        Work's outcome, the orchestrator's verdict texts, the profile
        snapshot and the typed review reason, each redacted first.  ``data``
        is the answer only when decided with enough confidence; what may be
        kept is the caller's deterministic validation.  Judgment only: it
        writes nothing.
        """
        from .decision import OUTCOME_UNAVAILABLE, StructuredDecision
        from .owner_model import (ANSWER_CHARS, EVALUATION_CHARS, FOLLOWUP_CHARS, PROFILE_CHARS, REVIEW_PURPOSE,
                                  REVIEW_QUESTION, REVIEW_SCHEMA, review_shape)
        facts = {'review_reason': str(reason or ''),
                 'owner_request': str(request or ''),
                 'final_answer_excerpt': self.redact(answer)[:ANSWER_CHARS] or 'none',
                 'work_outcome': str(outcome or 'unknown'),
                 'evaluation': self.redact(evaluation)[:EVALUATION_CHARS] or 'none',
                 'owner_followup': self.redact(str(followup or ''))[:FOLLOWUP_CHARS] or 'none',
                 'owner_profile': self.redact(profile)[:PROFILE_CHARS] or 'none'}
        context = self._context(REVIEW_PURPOSE, facts, work_id=work_id, uncut=('owner_request', 'owner_followup'),
                                cancelled=cancelled)
        method = getattr(self.engine, 'structured', None)
        decision = (method(context, REVIEW_QUESTION, REVIEW_SCHEMA, review_shape) if method is not None
                    else StructuredDecision(OUTCOME_UNAVAILABLE))
        return self.policy.structured(decision), decision

    def explicit_memory_fact(self, utterance, memory_key, content, work_id=None, cancelled=None):
        """``(judgment, decision)``: does ``utterance`` itself ask to keep, or assert, this one
        proposed fact (#597, #805 review)?

        Asked per fact, so one yes never covers another proposal.  A yes lets
        AgentOS issue the owner-request memory approval for that fact; the
        value-coverage and key-replacement checks still decide.  The decision
        says whether a call reached the engine's transport (the call budget).
        """
        context = self._context('explicit-memory-fact', {'owner_message': utterance,
                                                         'proposed_memory': f'{memory_key} = {content}'},
                                work_id=work_id, uncut='owner_message', cancelled=cancelled)
        decision = self.engine.judge(context, MEMORY_FACT_PROPOSITION)
        verdict = self.policy.binary(decision)
        return Judgment(JUDGMENT_UNAVAILABLE if verdict == 'unknown' else verdict,
                        source=decision.confidence.provider or decision.outcome), decision

    def explicit_preparation_request(self, utterance, proposal):
        """Is ``utterance`` the owner's own request for ``proposal`` (#659)?

        Judgment only, over the owner's message and a one-line summary of the
        proposed preparation.  A yes lets AgentOS schedule it as accepted by
        the owner's request; no / unavailable keeps it a proposal the owner
        accepts explicitly (Telegram button or Settings).
        """
        context = self._context('explicit-preparation-request', {'owner_message': utterance,
                                                                   'proposed_preparation': proposal})
        decision = self.engine.judge(context, PREPARATION_REQUEST_PROPOSITION)
        verdict = self.policy.binary(decision)
        return Judgment(JUDGMENT_UNAVAILABLE if verdict == 'unknown' else verdict,
                        source=decision.confidence.provider or decision.outcome)

    def watch_notification_needed(self, goal, result, last_notified, work_id=None):
        """Should this watch run's ``result`` reach the owner now (#719)?

        One ``judge`` call over the accepted goal, the run's result and the
        last notification sent for this watch; the caller bounds the texts.
        A yes is ``notify``, a no is ``quiet``; unavailable is left to the
        caller's typed fallback.
        """
        context = self._context('watch-notification', {'watch_goal': goal or '', 'run_result': result or '',
                                                       'last_notification': last_notified or 'none'},
                                work_id=work_id)
        decision = self.engine.judge(context, WATCH_NOTIFY_PROPOSITION)
        verdict = self.policy.binary(decision)
        return Judgment(JUDGMENT_UNAVAILABLE if verdict == 'unknown' else verdict,
                        source=decision.confidence.provider or decision.outcome)


class IntentDecision:
    """One routing decision AgentOS made, with the evidence it used.

    ``authority`` records *who* decided.  It is one of ``owner-explicit``,
    ``agentos-rule`` or ``default``; there is deliberately no model value.
    """

    __slots__ = ('intent', 'authority', 'argument', 'cues', 'alternatives',
                 'clarification', 'consequential', 'supersedes_previous',
                 'continuation', 'model_suggestion')

    def __init__(self, intent, authority, *, argument=None, cues=(), alternatives=(),
                 clarification=None, supersedes_previous=False, continuation=False,
                 model_suggestion=None):
        self.intent = intent
        self.authority = authority
        self.argument = argument
        self.cues = tuple(cues)
        self.alternatives = tuple(alternatives)
        self.clarification = clarification
        self.consequential = intent in CONSEQUENTIAL_INTENTS
        self.supersedes_previous = supersedes_previous
        self.continuation = continuation
        self.model_suggestion = model_suggestion

    @property
    def executes(self):
        """True when the service may invoke the capability for this decision."""
        return self.clarification is None and self.intent != INTENT_AMBIGUOUS

    def __repr__(self):  # pragma: no cover - diagnostic only
        return f'<IntentDecision {self.intent} by {self.authority}>'


class ConversationFocus:
    """Content-free short-horizon pointer to the current conversation Work.

    The utterance, subject, result text and tool payloads never live here. A
    Work id only points at the canonical Work that already owns the request.
    """

    KEY = 'conversation_focus'
    TTL_SECONDS = 60 * 60

    def __init__(self, store, now=time.time):
        self.store, self.now = store, now

    def current(self):
        row = self.store.config(self.KEY, {})
        if not isinstance(row, dict):
            return {}
        at = row.get('at')
        if not isinstance(at, (int, float)) or isinstance(at, bool) or self.now() - at > self.TTL_SECONDS:
            return {}
        work_id = row.get('work_id')
        if work_id is not None and (not isinstance(work_id, str) or not self.store.job(work_id)):
            return {key: row[key] for key in ('intent', 'at') if key in row}
        return row

    def record(self, decision, work_id=None):
        if decision.intent == INTENT_AMBIGUOUS:
            return
        row = {'intent': decision.intent, 'at': self.now()}
        if isinstance(work_id, str) and work_id:
            row['work_id'] = work_id
        self.store.put(self.KEY, row)

    def clear(self):
        self.store.put(self.KEY, {})


_QUOTED = re.compile(r'["“]([^"”]{2,160})["”]')

AMBIGUOUS_PREFIX = '이 요청이 '
AMBIGUOUS_SUFFIX = (' 중 무엇인지 확실하지 않아 아무 작업도 실행하지 않았습니다. '
                    '하나만 골라 다시 말씀해 주세요.')
SETTINGS_READ_FORM = '/settings'
KNOWLEDGE_CLARIFICATION = '개인 공간에서 무엇을 찾을지 두 글자 이상으로 알려 주세요.'
NOTE_CLARIFICATION = '무엇을 기록할지 내용을 함께 적어 주세요.'
MAIL_CLARIFICATION = '메일에서 무엇을 찾을지 두 글자 이상으로 알려 주세요.'
#: A turn that asks for several tasks at once (#672 review): nothing runs, so
#: no part is done while another is silently dropped.
MIXED_TASKS_PREFIX = '이 요청에 여러 작업이 함께 들어 있습니다: '
MIXED_TASKS_SUFFIX = ('. 일부만 처리하고 나머지를 빠뜨리지 않도록 아무 작업도 실행하지 않았습니다. '
                      '한 번에 하나씩 다시 말씀해 주세요.')
MIXED_TASKS_CLARIFICATION = ('이 요청에 여러 작업이 함께 들어 있습니다. 일부만 처리하고 나머지를 빠뜨리지 않도록 '
                             '아무 작업도 실행하지 않았습니다. 한 번에 하나씩 다시 말씀해 주세요.')


class _Candidate:
    """One rule match, before ambiguity and consequence policy is applied."""

    __slots__ = ('intent', 'argument', 'cues', 'clarification')

    def __init__(self, intent, argument, cues, clarification=None):
        self.intent, self.argument, self.cues, self.clarification = intent, argument, tuple(cues), clarification


class IntentClassifier:
    """AgentOS-owned routing for one owner utterance.

    Explicit forms and the literal cue tables above are read by AgentOS
    code; semantic questions such as parked-request withdrawal, unsupported
    mail actions and - for a turn no local rule claimed - which declared
    capability it needs (#597) are asked of the DecisionEngine through
    ``judge`` and reduced by AgentOS policy (PRESENCE-DEC-01 / #417,
    superseding PA1-CONV-01's "consults no model").  A missing cue word
    therefore no longer excludes a capability.  Every decision records
    which cue or judgment produced it, and a model's answer can only select
    among candidates AgentOS declared; it never mints an intent, argument or
    authority of its own.

    ``workspace_search`` is injected rather than imported so that this module
    stays free of any dependency on the service that uses it.
    """

    def __init__(self, workspace_search=None, judge=None):
        self._workspace_search = workspace_search
        self._judge = judge or ConversationJudgments()

    # -- owner-explicit forms ------------------------------------------------
    # Supported slash commands and the legacy Korean colon forms are no longer
    # the *required* entry path, but they remain owner-authoritative. Retired
    # compatibility commands deliberately fall through to ordinary routing.
    def explicit(self, text):
        if text in ('/start', '/help'):
            return IntentDecision(INTENT_GREETING, AUTHORITY_OWNER)
        if text.startswith('/knowledge '):
            return IntentDecision(INTENT_KNOWLEDGE, AUTHORITY_OWNER, argument=text[len('/knowledge '):].strip())
        if text.startswith('/settings '):
            return IntentDecision(INTENT_SETTINGS, AUTHORITY_OWNER, argument=text[len('/settings '):])
        if text in ('/settings', '무엇이 연결되어 있어?', '무엇을 바꿀 수 있어?'):
            return IntentDecision(INTENT_SETTINGS, AUTHORITY_OWNER, argument=text)
        if text == '/ai' or text.startswith('/ai '):
            return IntentDecision(INTENT_MAIN_AI, AUTHORITY_OWNER, argument=text[len('/ai'):].strip())
        if text in ('/notes', '메모 목록'):
            return IntentDecision(INTENT_NOTE_LIST, AUTHORITY_OWNER)
        if text.startswith('/note '):
            return IntentDecision(INTENT_NOTE_CREATE, AUTHORITY_OWNER, argument=text[len('/note '):])
        if text.startswith(('메모:', '기록:')):
            return IntentDecision(INTENT_NOTE_CREATE, AUTHORITY_OWNER, argument=text.split(':', 1)[1].strip())
        return None

    # -- natural-language rules ---------------------------------------------
    def _rule_knowledge(self, text, lowered):
        cues = _cue_hits(text, lowered, _KNOWLEDGE_CUES)
        if not cues:
            return None
        residue = _without_cues(text, cues)
        query = _strip_noise(residue)
        if len(query) < 2:
            return _Candidate(INTENT_KNOWLEDGE, None, cues, KNOWLEDGE_CLARIFICATION)
        return _Candidate(INTENT_KNOWLEDGE, query, cues)

    def _rule_settings(self, text, lowered):
        read = _cue_hits(text, lowered, _SETTINGS_READ_CUES)
        if read:
            # SettingsOrchestrator.handle_text reads its own small literal
            # vocabulary.  Normalising to that literal keeps every paraphrase
            # on the read path instead of falling into `draft`, which would
            # reject the utterance.
            return _Candidate(INTENT_SETTINGS, SETTINGS_READ_FORM, read)
        actions = _cue_hits(text, lowered, _SETTINGS_ACTIONS)
        targets = _cue_hits(text, lowered, _SETTINGS_TARGETS)
        if actions and targets:
            return _Candidate(INTENT_SETTINGS, text, (*actions, *targets))
        return None

    def _rule_workspace(self, text, lowered):
        legacy = self._workspace_search(text) if self._workspace_search else None
        if legacy:
            return _Candidate(INTENT_WORKSPACE_SEARCH, legacy, ('workspace_search_request',))
        cues = _cue_hits(text, lowered, _WORKSPACE_CUES)
        verbs = _cue_hits(text, lowered, _WORKSPACE_VERBS)
        if not (cues and verbs):
            return None
        quoted = _QUOTED.findall(text)
        if quoted:
            return _Candidate(INTENT_WORKSPACE_SEARCH, quoted[0], (*cues, *verbs))
        residue = _without_cues(text, (*cues, *verbs))
        # What survives cue removal is often only stranded particles.  Emit
        # the owner's most recent saved result rather than a junk query.
        subject = ' '.join(token for token in _strip_noise(residue).split() if len(token) > 1)
        return _Candidate(INTENT_WORKSPACE_SEARCH, subject or '__latest__', (*cues, *verbs))

    def _rule_note(self, text, lowered):
        match = _NOTE_CREATE_RE.search(text)
        if not match:
            return None
        content = self._note_content(text, match)
        cues = (match.group(0).strip(),)
        if not content:
            return _Candidate(INTENT_NOTE_CREATE, None, cues, NOTE_CLARIFICATION)
        return _Candidate(INTENT_NOTE_CREATE, content, cues)

    @staticmethod
    def _note_content(text, match):
        """Take what follows the cue, or what preceded it in Korean order."""
        tail = text[match.end():].lstrip(' \t:,-–—')
        tail = re.sub(r'^(?:of|that|about|to|saying)\b\s*', '', tail, flags=re.I).strip()
        if tail and tail.casefold() not in _NOTE_PRONOUNS:
            return tail
        head = text[:match.start()].strip(' \t,')
        # A correction preamble is the owner discarding the previous turn, not
        # something to write down.
        lowered = head.casefold()
        for cue in _CORRECTION_CUES:
            if cue in lowered:
                head = head[lowered.rindex(cue) + len(cue):].strip(' \t,')
                lowered = head.casefold()
        for token in _NOTE_TRAIL_KO:
            if head.endswith(token):
                head = head[:-len(token)].strip()
                break
        if head and head.casefold() not in _NOTE_PRONOUNS:
            return head
        return None

    def _rule_mail(self, text, lowered):
        """Recognise a mailbox *read*; the query is never persisted anywhere."""
        objects = _cue_hits(text, lowered, _MAIL_OBJECTS)
        verbs = _cue_hits(text, lowered, _MAIL_VERBS)
        if not (objects and verbs):
            return None
        quoted = _QUOTED.findall(text)
        query = quoted[0] if quoted else _strip_noise(_without_cues(text, (*objects, *verbs)))
        if len(query) < 2:
            return _Candidate(INTENT_MAIL_SEARCH, None, (*objects, *verbs), MAIL_CLARIFICATION)
        return _Candidate(INTENT_MAIL_SEARCH, query, (*objects, *verbs))

    def has_local_candidate(self, text):
        """Whether deterministic capability routing already owns this utterance.

        Continuity may use a remote DecisionEngine, so a turn that already
        matches one of AgentOS's concrete local/private capability rules must
        never be sent there merely because it also contains "again", "no",
        or another follow-up hint.  This method performs only the same literal
        candidate checks as :meth:`classify`; it makes no semantic judgment
        and authorizes nothing.
        """
        if not isinstance(text,str) or not text.strip():
            return False
        value=text.strip();lowered=value.casefold()
        if self.explicit(value) is not None:
            return True
        return any(rule(value,lowered) is not None for rule in (
            self._rule_knowledge,self._rule_settings,self._rule_workspace,
            self._rule_note,self._rule_mail,
        ))

    # -- decision assembly ---------------------------------------------------
    def classify(self, text, model_suggestion=None, focus=None):
        """Return the one routing decision AgentOS is prepared to justify."""
        if not isinstance(text, str) or not text.strip():
            return self._with_suggestion(IntentDecision(INTENT_CONVERSATION, AUTHORITY_DEFAULT),
                                         (), model_suggestion)
        text = text.strip()
        lowered = text.casefold()
        focus_intent = (focus or {}).get('intent')

        explicit = self.explicit(text)
        if explicit is not None:
            explicit.supersedes_previous = bool(focus_intent) and focus_intent != explicit.intent
            return self._with_suggestion(explicit, (), model_suggestion)

        correction = _cue_hits(text, lowered, _CORRECTION_CUES)
        candidates = []
        for rule in (self._rule_knowledge, self._rule_settings,
                     self._rule_workspace, self._rule_note, self._rule_mail):
            found = rule(text, lowered)
            if found is not None:
                candidates.append(found)

        # Restrict semantic boundary judgment to mail-shaped requests that
        # are not already recognized as local work. The DecisionEngine may be
        # remote, so local-only turns (notes, settings, ordinary conversation)
        # must never be sent to it. A reply/send verb still qualifies even
        # when it is not a supported mailbox-read cue.
        mail_objects = _cue_hits(text, lowered, _MAIL_OBJECTS)
        mail_verbs = _cue_hits(text, lowered, _MAIL_VERBS)
        mail_action = _cue_hits(text, lowered, ('답장', '회신', '보내', '전송', 'reply', 'send'))
        content_kind = tuple(f'mail-{kind}' for kind, cues in _MAIL_CONTENT_KINDS.items()
                             if _cue_hits(text, lowered, cues))
        has_mail_focus = focus_intent == INTENT_MAIL_SEARCH
        cue_summary = ' '.join(dict.fromkeys((*(('최근 메일 검색',) if has_mail_focus and not mail_objects else ()),
                                               *mail_objects, *mail_verbs, *mail_action, *content_kind)))
        local_only = bool(candidates) and all(candidate.intent != INTENT_MAIL_SEARCH for candidate in candidates)
        mixed_mail_action = (bool(mail_objects and mail_action)
                             and any(candidate.intent not in (INTENT_MAIL_SEARCH, INTENT_NOTE_CREATE,
                                                              INTENT_SETTINGS, INTENT_WORKSPACE_SEARCH)
                                     for candidate in candidates))
        if mixed_mail_action:
            return self._with_suggestion(
                IntentDecision(INTENT_AMBIGUOUS, AUTHORITY_RULE,
                               cues=('mixed-mail-action',), clarification=MIXED_MAIL_ACTION_CLARIFICATION),
                candidates, model_suggestion)
        mail_boundary_eligible = ((mail_objects and (mail_verbs or mail_action))
                                  or (has_mail_focus and mail_action))
        unsupported = (self._judge.unsupported_capability(cue_summary)
                       if mail_boundary_eligible and not local_only
                       else Judgment(JUDGMENT_NO, source='local-prefilter'))
        if unsupported.outcome == JUDGMENT_YES:
            return self._with_suggestion(
                IntentDecision(INTENT_UNSUPPORTED, AUTHORITY_RULE, argument=unsupported.value,
                               cues=('judgment:unsupported-capability',),
                               clarification=UNSUPPORTED_CAPABILITY_TEXT[unsupported.value]),
                (), model_suggestion)

        # Mail search reads private metadata. If the semantic boundary check
        # could not distinguish a search from an unsupported read/send request,
        # fail closed instead of letting lexical cues trigger the connector.
        if (unsupported.outcome == JUDGMENT_UNAVAILABLE and mail_boundary_eligible
                and (has_mail_focus or any(candidate.intent == INTENT_MAIL_SEARCH for candidate in candidates))):
            return self._with_suggestion(
                IntentDecision(INTENT_AMBIGUOUS, AUTHORITY_RULE,
                               cues=('judgment:unsupported-capability-unavailable',),
                               clarification=UNSUPPORTED_JUDGMENT_UNAVAILABLE),
                candidates, model_suggestion)

        # #672 review: a local rule no longer hides the rest of the turn.  Unless
        # a pending calendar draft owns follow-ups, a turn a rule claimed is
        # still asked which declared capability it needs; one the rules did
        # not find makes the turn mixed, and a mixed turn runs nothing.
        if candidates and not (focus or {}).get('calendar_pending'):
            judged = self._judged_capability(text)
            if judged is not None and (judged.intent == INTENT_AMBIGUOUS
                                       or judged.intent not in {item.intent for item in candidates}):
                # No suggestion may narrow a mixed turn to one of its parts.
                return self._with_suggestion(self._mixed(candidates, judged), (), model_suggestion)

        if len(candidates) == 1:
            decision = self._single(candidates[0])
        elif candidates:
            decision = self._ambiguous(candidates)
        else:
            decision = self._fallback(text, lowered, focus_intent, bool(correction),
                                      calendar_pending=bool((focus or {}).get('calendar_pending')))

        if focus_intent and (correction or focus_intent != decision.intent) and decision.intent != INTENT_AMBIGUOUS:
            decision.supersedes_previous = True
        return self._with_suggestion(decision, candidates, model_suggestion)

    @staticmethod
    def _single(candidate):
        if candidate.clarification:
            return IntentDecision(candidate.intent, AUTHORITY_RULE, cues=candidate.cues,
                                  clarification=candidate.clarification)
        # A consequential candidate executes only as far as a draft and an
        # exact preview; ``decision.consequential`` tells the worker so, and
        # the effect itself waits for the owner's explicit approval.
        return IntentDecision(candidate.intent, AUTHORITY_RULE, argument=candidate.argument,
                              cues=candidate.cues)

    @staticmethod
    def _ambiguous(candidates):
        options = tuple(dict.fromkeys(item.intent for item in candidates))
        labels = ', '.join(INTENT_LABELS.get(option, option) for option in options)
        return IntentDecision(INTENT_AMBIGUOUS, AUTHORITY_RULE, alternatives=options,
                              cues=tuple(cue for item in candidates for cue in item.cues),
                              clarification=AMBIGUOUS_PREFIX + labels + AMBIGUOUS_SUFFIX)

    @staticmethod
    def _mixed(candidates, judged):
        """The rules' candidates plus a judged capability they did not find."""
        options = tuple(dict.fromkeys([*(item.intent for item in candidates),
                                       *(() if judged.intent == INTENT_AMBIGUOUS else (judged.intent,))]))
        labels = ', '.join(INTENT_LABELS.get(option, option) for option in options)
        return IntentDecision(INTENT_AMBIGUOUS, AUTHORITY_RULE, alternatives=options,
                              cues=(*(cue for item in candidates for cue in item.cues), *judged.cues),
                              clarification=MIXED_TASKS_PREFIX + labels + MIXED_TASKS_SUFFIX)

    def _fallback(self, text, lowered, focus_intent, correction, calendar_pending=False):
        """No capability rule fired: stay on the ordinary conversation route.

        The one exception is a pending calendar draft.  Its follow-ups - a
        title, a time, "승인", "취소", "아니 4시로" - carry no calendar cue, so
        while the service reports a draft pending they are handed back to it
        as a continuation.  The service then asks ``CalendarConversation``
        whether the utterance really belongs to the draft, and re-routes an
        unrelated one here with the draft dropped.
        """
        if calendar_pending:
            return IntentDecision(INTENT_CALENDAR_CREATE, AUTHORITY_RULE, argument=text,
                                  cues=('calendar-draft-pending',), continuation=True)
        continuation = _cue_hits(text, lowered, _CONTINUATION_CUES)
        if continuation and not correction and focus_intent in CONTINUABLE_INTENTS:
            return IntentDecision(focus_intent, AUTHORITY_RULE, cues=continuation, continuation=True)
        judged = self._judged_capability(text)
        if judged is not None:
            return judged
        # Public web research is the ordinary conversation route: the Work
        # model loop chooses ``web_search`` / ``bounded_public_research``
        # itself, so no word in the request selects it (#672).
        return IntentDecision(INTENT_CONVERSATION, AUTHORITY_DEFAULT)

    def _judged_capability(self, text):
        """Ask the DecisionEngine whether a turn needs a declared capability.

        Asked for every turn that is not an explicit form or a pending
        calendar draft's follow-up (#672 review): a rule-claimed turn is asked
        too, so a part the rules did not see makes it mixed instead of being
        dropped.  The owner text is redacted by ``ConversationJudgments``
        before it reaches the engine.  A yes selects an AgentOS-declared
        candidate (``several-tasks`` yields the mixed-turn clarification); the argument is
        the owner's own words (``_judged_mail_query``, or the utterance for a
        calendar draft), never text the engine produced.  Unavailable, unsure
        or none-of-these returns ``None`` and the turn stays on conversation,
        where the Work model loop chooses its own tools; no word list stands
        in for the judgment (#672).
        """
        if not eligible_for_capability_judgment(text):
            return None
        need = self._judge.capability_need(text)
        if need.outcome != JUDGMENT_YES:
            return None
        cues = ('judgment:capability-need',)
        if need.value == INTENT_MAIL_SEARCH:
            query = self._judged_mail_query(text)
            if query is None:
                # Still a mail request: a missing connection is handed off
                # first, and the owner is asked what to look for instead of
                # the whole question being sent to Gmail as a query.
                return IntentDecision(INTENT_MAIL_SEARCH, AUTHORITY_RULE, cues=cues, clarification=MAIL_CLARIFICATION)
            return IntentDecision(INTENT_MAIL_SEARCH, AUTHORITY_RULE, argument=query, cues=cues)
        if need.value == INTENT_CALENDAR_CREATE:
            # The utterance is the argument, as it always was: title, date
            # and time are read by ``CalendarConversation``, which ends in a
            # draft and an exact preview; only the owner's approval executes.
            return IntentDecision(INTENT_CALENDAR_CREATE, AUTHORITY_RULE, argument=text, cues=cues)
        if need.value == INTENT_DRIVE_READ:
            return IntentDecision(INTENT_DRIVE_READ, AUTHORITY_RULE, cues=cues)
        if need.value == SEVERAL_TASKS:
            return IntentDecision(INTENT_AMBIGUOUS, AUTHORITY_RULE, cues=cues, clarification=MIXED_TASKS_CLARIFICATION)
        if need.value in UNSUPPORTED_CAPABILITY_TEXT:
            return IntentDecision(INTENT_UNSUPPORTED, AUTHORITY_RULE, argument=need.value, cues=cues,
                                  clarification=UNSUPPORTED_CAPABILITY_TEXT[need.value])
        return None

    def _judged_mail_query(self, text):
        """A bounded Gmail query for a cue-free mail request, or None.

        A quoted phrase is the owner's literal query.  Otherwise the
        DecisionEngine selects one of the owner's own words (sender,
        organisation or subject); a single candidate needs no judgment.  No
        selection means no query - never the whole question.
        """
        quoted = _QUOTED.findall(text)
        if quoted:
            return quoted[0]
        terms = []
        for token in _strip_noise(text).split():
            token = _trim_particle(token.strip('?!.,;:·"“”‘’()'))
            for ending in _TERM_ENDINGS:
                if token.endswith(ending) and len(token) > len(ending) + 1:
                    token = token[:-len(ending)]
                    break
            if len(token) >= 2 and token not in terms:
                terms.append(token)
        terms = terms[:MAIL_QUERY_MAX_TERMS]
        if len(terms) == 1:
            return terms[0]
        if not terms:
            return None
        judged = self._judge.mail_query_term(text, terms)
        return terms[judged.value] if judged.outcome == JUDGMENT_YES else None

    # -- the model-suggestion gate ------------------------------------------
    @staticmethod
    def _with_suggestion(decision, candidates, suggestion):
        """Let an untrusted suggestion narrow an AgentOS ambiguity, nothing more.

        Every rejection is recorded on the decision so that an owner or a
        reviewer can see that a suggestion arrived and what happened to it.
        The accepted path still returns ``agentos-rule`` authority, because
        AgentOS produced both the option set and the argument; the suggestion
        only picked one of AgentOS's own options.
        """
        if suggestion is None:
            return decision
        proposed = suggestion.get('intent') if isinstance(suggestion, dict) else None
        record = {'received': proposed, 'state': 'rejected', 'reason': 'no-ambiguity-to-resolve'}
        if decision.intent != INTENT_AMBIGUOUS:
            decision.model_suggestion = record
            return decision
        by_intent = {item.intent: item for item in candidates}
        if proposed not in by_intent:
            record['reason'] = 'not-a-deterministic-candidate'
        elif proposed in CONSEQUENTIAL_INTENTS:
            record['reason'] = 'consequential-intent'
        elif by_intent[proposed].clarification:
            record['reason'] = 'candidate-needs-owner-detail'
        else:
            chosen = by_intent[proposed]
            return IntentDecision(chosen.intent, AUTHORITY_RULE, argument=chosen.argument,
                                  cues=chosen.cues, alternatives=decision.alternatives,
                                  supersedes_previous=decision.supersedes_previous,
                                  model_suggestion={'received': proposed, 'state': 'accepted',
                                                    'reason': 'narrowed-an-agentos-candidate'})
        decision.model_suggestion = record
        return decision


# ---------------------------------------------------------------------------
# Connector prerequisites, connection handoff and exactly-once resume
# ---------------------------------------------------------------------------
# Nothing below invents a replay, owner-binding, one-time-state or expiry
# scheme.  Two pieces of hard-won repository machinery are reused as-is:
#
#   * the Wave 0 ``PendingWorkRegistry`` owns the authority state machine -
#     pending/claimed/completed/superseded/expired, the hashed owner binding,
#     exact scope equality, connector-definition drift detection, and the
#     claim digest that distinguishes an authorized claimant recovering a lost
#     response from a second claimant replaying one.  Its own docstrings name
#     #393 as the layer that must "durably schedule with the same
#     caller-supplied handoff ID before it calls ``complete``".  That durable
#     schedule is the missing half supplied here.
#   * ``quickstart_service``'s Telegram ``generation`` is the existing marker
#     for "this bot connection is no longer the one that was talking".  A
#     handoff parked under an older generation is refused rather than resumed,
#     exactly as ``ingest_update`` and ``poll_telegram`` already refuse an
#     update from a superseded generation.
#
# The compare-and-set on the parked job row is modelled on the shipped Drive
# resume (``select_drive_files`` -> ``UPDATE jobs ... WHERE id=? AND
# status='awaiting_drive'``), generalised from one connector to the contract.
import secrets as _secrets
import threading
import uuid

from .calendar import CALENDAR_WRITE_CONNECTOR_ID
# ``_owner_key`` is imported rather than reimplemented on purpose.  The
# index below and the contract row it points at must agree on what "the same
# owner" means; two independent hashes could only ever disagree, and a
# disagreement would be a wrong-owner check that quietly stops matching.
from .connector_contract import (ConnectorContractError, ConnectorResult, ConnectorResultKind,
                                 ConnectorState, PendingWorkRegistry, RecoveryAction, _owner_key)
from .gmail import GMAIL_CONNECTOR_ID
from .google_drive_read import DRIVE_CONNECTOR_ID

#: Which connector one routing decision needs, decided by AgentOS before any
#: capability is touched.  A missing entry means the intent needs no connector.
#: ``calendar-create`` maps to the *write* connector deliberately: this
#: repository models the calendar read and write grants as two connectors so a
#: read grant can never imply a write grant, so "the calendar scope is
#: missing" and "the calendar is not connected" are the same owner-safe
#: handoff against different connector rows.
CONNECTOR_BY_INTENT = {
    INTENT_MAIL_SEARCH: GMAIL_CONNECTOR_ID,
    INTENT_CALENDAR_CREATE: CALENDAR_WRITE_CONNECTOR_ID,
}

CONNECTOR_LABELS = {
    GMAIL_CONNECTOR_ID: 'Gmail',
    CALENDAR_WRITE_CONNECTOR_ID: 'Google Calendar 일정 만들기',
    DRIVE_CONNECTOR_ID: 'Google Drive',
}

#: One sentence of guidance per unmet state, naming exactly one next action.
#: None of these claims a connection happened, that a tool ran, or how long it
#: will take.  The request is explicitly described as *not executed*.
HANDOFF_GUIDANCE = {
    ConnectorResultKind.CONNECTION_REQUIRED:
        '{label} 연결이 아직 없어 이 요청을 실행하지 않았습니다. 지금 필요한 다음 단계는 하나입니다: '
        '{label}{obj} 연결해 주세요. 연결이 확인되면 방금 요청을 한 번만 이어서 처리합니다.',
    ConnectorResultKind.REAUTH_REQUIRED:
        '{label} 연결을 다시 인증해야 해서 이 요청을 실행하지 않았습니다. 지금 필요한 다음 단계는 하나입니다: '
        '{label}{obj} 다시 인증해 주세요. 인증이 확인되면 방금 요청을 한 번만 이어서 처리합니다.',
    ConnectorResultKind.BLOCKED:
        '{label} 접근이 차단되어 있어 이 요청을 실행하지 않았습니다. 지금 필요한 다음 단계는 하나입니다: '
        '{label}의 접근 권한을 확인해 주세요. 차단이 풀릴 때까지 이 요청은 이어서 처리하지 않습니다.',
}

CONNECTOR_UNAVAILABLE = ('{label} 기능이 이 로컬 설치에 구성되어 있지 않습니다. '
                         '소유자가 로컬 설정을 마친 뒤 다시 요청해 주세요.')

#: Appended to the guidance above only when the caller observed a start route
#: this installation can actually offer.  Telling the owner a connection is
#: required while shipping no way to reach it is the dead end J3/J7 name, so
#: the one next action carries the one address that performs it.
#:
#: The URL is always this computer's own loopback start route.  That route
#: still requires the owner session and refuses a tunnel host, so naming it in
#: a message is not a Grant and does not widen who can start an authorization.
CONNECT_LINK = ' 이 컴퓨터의 브라우저에서 {url} 주소를 열면 연결을 진행할 수 있습니다.'

#: BLOCKED is deliberately absent.  Its single next action is reviewing the
#: access that is blocked, and appending an authorization URL there would name
#: a second action this guidance does not claim will help.
LINKABLE_KINDS = (ConnectorResultKind.CONNECTION_REQUIRED, ConnectorResultKind.REAUTH_REQUIRED)

#: Durable key for the one owner-safe pending-resume index.  It is written to
#: the secret store rather than ``config`` so the opaque resume handle is not
#: reachable from status, onboarding, progress or portable-state surfaces.
CONVERSATION_RESUME_KEY = 'conversation_pending_resume'

RESUME_TTL_SECONDS = 900

#: Mirrors the process-wide locks in ``connector_contract`` and
#: ``drive_web_oauth``: the index may be reconstructed by another handoff
#: instance in the same runtime, so the lock must not be instance-local.
_RESUME_LOCK = threading.RLock()


class ConversationHandoffError(ValueError):
    """Fail-closed resume refusal whose text discloses no owner data."""

    def __init__(self, reason='rejected'):
        super().__init__('conversation resume rejected')
        self.reason = reason


#: Every refusal is a stated outcome, never a silent no-op.  Reasons coming
#: from the Wave 0 contract keep the contract's own vocabulary.
#: The one claim refusal that leaves the parked Work worth keeping.  The
#: contract transitions its row to SUPERSEDED on *every* authority and scope
#: failure -- `require_connected` included -- so a premature callback is
#: terminal by design even though the reason it surfaces ("disconnected")
#: does not say so, and a bare `invalid_resume` names a handle that resolves
#: to nothing.  `resume_claimed` is different: another claim is in flight and
#: may still complete the Work, so failing it here would be wrong.
#:
#: The contract exposes no public state accessor, so this is derived from its
#: transitions rather than read back. If `PendingWorkRegistry` ever grows one,
#: ask it instead of inferring -- recorded for #394.
RETRYABLE_RESUME_REASONS = frozenset({'resume_claimed'})

RESUME_REFUSALS = {
    'no_pending_work': '이어서 처리할 요청이 없어 아무 작업도 실행하지 않았습니다.',
    'wrong_owner': '이 연결은 다른 소유자의 것이라 요청을 이어서 처리하지 않았습니다.',
    'generation_changed': 'Telegram 봇 연결이 교체되어 이전 요청은 이어서 처리하지 않았습니다. 필요하면 다시 요청해 주세요.',
    'expired_resume': '연결을 기다리던 요청이 만료되어 이어서 처리하지 않았습니다. 다시 요청해 주세요.',
    'superseded_resume': '요청이 바뀌어 이전 요청은 이어서 처리하지 않았습니다.',
    'replayed_resume': '이미 이어서 처리한 요청이라 다시 실행하지 않았습니다.',
    'resume_claimed': '이 요청은 이미 다른 연결 완료 처리가 진행 중이라 다시 실행하지 않았습니다.',
    'unclaimed_resume': '연결 확인이 완료되지 않아 요청을 이어서 처리하지 않았습니다.',
    'scope_mismatch': '승인된 권한 범위가 요청에 필요한 범위와 달라 요청을 이어서 처리하지 않았습니다.',
    'disconnected': '연결이 확인되지 않아 요청을 이어서 처리하지 않았습니다.',
    'reauth_required': '연결을 다시 인증해야 해서 요청을 이어서 처리하지 않았습니다.',
    'blocked': '연결이 차단되어 있어 요청을 이어서 처리하지 않았습니다.',
    'denied': '연결이 승인되지 않아 요청을 실행하지 않았습니다. 필요하면 다시 연결한 뒤 요청해 주세요.',
    'callback_failed': '연결을 완료하지 못해 요청을 실행하지 않았습니다. 다시 연결해 주세요.',
    'work_already_claimed': '이 요청의 연결 처리가 이미 진행 중입니다. 새로 실행하지 않았습니다.',
    'work_already_completed': '이 요청은 이미 처리되어 다시 실행하지 않았습니다.',
    'invalid_resume': '이어서 처리할 유효한 연결 요청을 찾지 못했습니다.',
}

RESUME_REFUSAL_DEFAULT = '연결을 확인하지 못해 요청을 이어서 처리하지 않았습니다.'

SUPERSEDED_WORK_ERROR = '요청이 바뀌어 이전 요청을 취소했습니다. 연결이 끝나도 이전 요청은 실행하지 않습니다.'


class ConnectorHandoff:
    """Prerequisite detection, owner-safe parking and exactly-once resume.

    The pending record persisted here is deliberately as content free as
    :class:`ConversationFocus`.  It holds a connector identifier, two opaque
    identifiers, one opaque handle, a hashed owner and the Telegram
    generation - no utterance, no subject, no extracted argument and no
    connector payload.  The owner's words stay in the ``jobs`` row they
    already created; this record points at that Work rather than copying it,
    so a pasted secret cannot reach durable state through the resume path.
    """

    def __init__(self, store, connector_registry, pending_registry=None, *,
                 now=time.time, ttl_seconds=RESUME_TTL_SECONDS, requirements=None):
        self.store = store
        self.connectors = connector_registry
        self.pending = pending_registry or PendingWorkRegistry(store, connector_registry, clock=now)
        self.now = now
        self.ttl_seconds = ttl_seconds
        # Declared non-connector requirements (#505): a local authority such
        # as a folder read grant is parked in this same index with the same
        # owner/generation binding, but its scopes come from this table
        # rather than a ConnectorRegistry definition.
        self.requirements = dict(requirements or {})

    def _required_scopes(self, key):
        if key in self.requirements:
            return tuple(self.requirements[key])
        return self.connectors.definition(key).required_scopes

    # -- prerequisite detection ---------------------------------------------
    @staticmethod
    def requirement(decision):
        """The connector one routing decision needs, before anything runs.

        An ambiguous decision selected no capability, so it can require none.
        """
        if decision is None or decision.intent == INTENT_AMBIGUOUS:
            return None
        return CONNECTOR_BY_INTENT.get(decision.intent)

    def known(self, connector_id):
        try:
            self.connectors.definition(connector_id)
        except ConnectorContractError:
            return False
        return True

    def prerequisite(self, owner_id, connector_id):
        """Return the unmet :class:`ConnectorResult`, or None when ready."""
        connector = self.connectors.definition(connector_id)
        status = self.connectors.status(owner_id, connector_id)
        if status.state is not ConnectorState.CONNECTED:
            return self.connectors.required_result(owner_id, connector_id)
        if not set(connector.required_scopes).issubset(status.granted_scopes):
            # Defence in depth.  ``ConnectorRegistry.transition`` refuses to
            # record CONNECTED unless the granted set equals the required set,
            # so a connected row with a narrower grant can only come from a
            # stale or edited store.  Treating it as ready would run a request
            # against authority the owner never approved, so it fails closed
            # into the same re-authentication handoff.
            return ConnectorResult(ConnectorResultKind.REAUTH_REQUIRED, connector_id,
                                   connector.required_scopes, RecoveryAction.REAUTHENTICATE)
        return None

    @staticmethod
    def guidance(result, connect_url=''):
        """The smallest next action, with no claim that anything ran.

        ``connect_url`` is supplied by the caller rather than derived here:
        this module knows the connector contract, not which port the running
        installation bound, and a guessed address would be an invented fact.
        It is appended to the existing instruction rather than replacing it,
        so an installation with no reachable start route still reads exactly
        as it did before and still claims nothing about a connection.
        """
        label = CONNECTOR_LABELS.get(result.connector_id, result.connector_id)
        # #598: the object particle matches the label (을/를), not 을(를).
        text = HANDOFF_GUIDANCE[result.kind].format(label=label, obj=object_particle(label))
        if connect_url and result.kind in LINKABLE_KINDS:
            text += CONNECT_LINK.format(url=connect_url)
        return text

    @staticmethod
    def unavailable(connector_id):
        return CONNECTOR_UNAVAILABLE.format(label=CONNECTOR_LABELS.get(connector_id, connector_id))

    # -- the owner-safe pending record --------------------------------------
    def _rows(self):
        raw = self.store.secret(CONVERSATION_RESUME_KEY)
        return dict(raw) if isinstance(raw, dict) else {}

    def record(self, connector_id):
        row = self._rows().get(connector_id)
        if not isinstance(row, dict) or not row.get('resume_token') or not row.get('work_id'):
            return None
        return row

    def park(self, owner_id, work_id, connector_id, *, generation=''):
        """Park one Work against one connector and return (handle, superseded).

        One conversation has one pending handoff per connector.  Parking a new
        Work therefore releases whatever was pending for that connector and
        reports it, so the caller can cancel the Work that is being replaced
        rather than leaving two resume paths racing for the same connection.
        """
        handle = self.pending.issue(owner_id, work_id, connector_id,
                                    self._required_scopes(connector_id), ttl_seconds=self.ttl_seconds)
        row = {'connector_id': connector_id,
               'work_id': work_id,
               'handoff_id': str(uuid.uuid4()),
               'resume_token': handle.token,
               'owner': _owner_key(owner_id),
               'generation': generation if isinstance(generation, str) else ''}
        with _RESUME_LOCK:
            rows = self._rows()
            previous = rows.get(connector_id)
            rows[connector_id] = row
            self.store.secret(CONVERSATION_RESUME_KEY, rows)
        superseded = (previous.get('work_id')
                      if isinstance(previous, dict) and previous.get('work_id') != work_id else None)
        return handle, superseded

    def _release(self, connector_id, handoff_id=None):
        """Drop one index entry, but never one a newer park already replaced."""
        with _RESUME_LOCK:
            rows = self._rows()
            current = rows.get(connector_id)
            if not isinstance(current, dict):
                return None
            if handoff_id is not None and current.get('handoff_id') != handoff_id:
                return None
            rows.pop(connector_id, None)
            self.store.secret(CONVERSATION_RESUME_KEY, rows)
            return current.get('work_id')

    def parked_for(self, owner_id):
        """Connector ids this owner has a request parked for; no content."""
        owner = _owner_key(owner_id)
        return tuple(key for key, row in self._rows().items()
                     if isinstance(row, dict) and _secrets.compare_digest(str(row.get('owner', '')), owner))

    def supersede(self, connector_id=None, owner_id=None):
        """Destroy resume paths so a changed request cannot execute later.

        ``owner_id`` limits this to the owner who changed course: one owner's
        correction never cancels a request another owner identity parked.

        Supersession is enforced by destroying the only copy of the resume
        handle.  Without it nothing can claim the handoff, so the contract row
        can only terminate by expiry; the Wave 0 contract has no owner
        initiated cancel for a *different* Work on the same connector, and
        adding one belongs to a file this issue does not own.  Recorded as an
        integration need for PA1-INT-01 / #394.
        """
        with _RESUME_LOCK:
            rows = self._rows()
            owner = _owner_key(owner_id) if owner_id is not None else None
            targets = [key for key in rows
                       if (connector_id is None or key == connector_id)
                       and (owner is None or (isinstance(rows[key], dict)
                                              and _secrets.compare_digest(str(rows[key].get('owner', '')), owner)))]
            dropped = [rows[key]['work_id'] for key in targets
                       if isinstance(rows.get(key), dict) and rows[key].get('work_id')]
            if not targets:
                return []
            for key in targets:
                rows.pop(key, None)
            self.store.secret(CONVERSATION_RESUME_KEY, rows)
        return dropped

    def deny(self, owner_id, connector_id):
        """Record an explicitly refused or failed connection, and resume nothing."""
        record = self.record(connector_id)
        if record is None:
            raise ConversationHandoffError('no_pending_work')
        self._assert_owner(record, owner_id)
        self._release(connector_id, record.get('handoff_id'))
        return record['work_id']

    @staticmethod
    def _assert_owner(record, owner_id):
        if not _secrets.compare_digest(str(record.get('owner', '')), _owner_key(owner_id)):
            raise ConversationHandoffError('wrong_owner')

    # -- exactly-once resume -------------------------------------------------
    def resume(self, owner_id, connector_id, granted_scopes, schedule, *, generation='', abandon=None):
        """Resume the parked Work exactly once after a reported connection.

        The order is ``claim`` -> durable schedule -> ``complete``, which is
        the order the Wave 0 contract documents, and it gives three
        independent barriers against a second execution:

        1. the index entry is released once the resume finishes, so an
           ordinary duplicate callback finds nothing to resume;
        2. the contract row is COMPLETED, so a duplicate that still holds the
           handle is refused as ``replayed_resume``;
        3. ``schedule`` is a compare-and-set on the parked Work row, so even
           an authorized claimant recovering a lost response after a restart
           re-queues nothing.

        Barrier 3 is the one that actually enforces exactly-once, because it
        is the only one that stays correct when the process dies between
        ``claim`` and ``complete``: that recovery path is *meant* to succeed
        at the contract layer.  Removing the ``AND status=...`` predicate
        would make this at-least-once.
        """
        record = self.record(connector_id)
        if record is None:
            raise ConversationHandoffError('no_pending_work')
        self._assert_owner(record, owner_id)
        expected = generation if isinstance(generation, str) else ''
        if str(record.get('generation', '')) != expected:
            raise ConversationHandoffError('generation_changed')
        try:
            reference = self.pending.claim(record['resume_token'], owner_id, connector_id,
                                           granted_scopes, record['handoff_id'])
        except ConnectorContractError as exc:
            # Every exit from `awaiting_connection` is reached through this
            # index -- resume, supersession and denial all look the record up
            # -- so releasing the handle without also giving the Work a
            # terminal state stranded it: the job reported "연결 대기" forever,
            # the task card draws its cancel button for `queued` alone, and no
            # owner action could clear it.
            if exc.reason in RETRYABLE_RESUME_REASONS:
                raise ConversationHandoffError(exc.reason) from None
            # Terminal: drop the dead handle, and give the Work a terminal
            # state too, because C8 requires the failure to stay explicit
            # rather than leaving an unreachable parked job behind.
            self._release(connector_id, record.get('handoff_id'))
            if abandon is not None:
                abandon(record['work_id'], exc.reason)
            raise ConversationHandoffError(exc.reason) from None
        scheduled = bool(schedule(reference.work_id))
        self.pending.complete(record['resume_token'], owner_id, connector_id, record['handoff_id'])
        self._release(connector_id, record.get('handoff_id'))
        return reference.work_id, scheduled

    @staticmethod
    def refusal_text(reason):
        return RESUME_REFUSALS.get(reason, RESUME_REFUSAL_DEFAULT)


# ---------------------------------------------------------------------------
# Contextual local authority (PRESENCE-CAP-01 / #505)
# ---------------------------------------------------------------------------
# A file request that finds no covering folder grant is parked exactly like a
# request waiting for a connector: the same content-free index row, the same
# hashed owner and Telegram-generation binding, the same `resume` order
# (claim -> durable compare-and-set schedule -> complete) and the same
# supersede/deny exits.  Only two things differ, and both are declared here:
#
#   * the requirement is a declared local authority, not a ConnectorRegistry
#     row, so its scope comes from ``LOCAL_AUTHORITY_SCOPES``;
#   * the single-use pending state is ``LocalGrantPending`` below, because the
#     Wave 0 ``PendingWorkRegistry`` re-checks ``require_connected`` against a
#     connector definition inside ``claim`` and a folder grant has none.  It
#     keeps that registry's interface and refusal vocabulary so
#     ``ConnectorHandoff.resume`` is reused unchanged.
#
# What is deliberately *not* here: which folder.  A folder is chosen only on
# the owner's Mac through the local approval surface, never inferred from
# conversation text and never accepted from Telegram.  The index row names
# the authority kind only; no path, folder name or utterance is stored in it.
import hashlib as _hashlib

LOCAL_FOLDER_READ = 'local-folder-read'
LOCAL_REFERENCE_READ = 'local-reference-read'
LOCAL_RESULT_WRITE = 'local-result-write'

#: The one scope each declared local authority carries.  Read and result-write
#: are distinct authorities: a read grant never implies a write grant, and a
#: result-write grant only lets AgentOS create *new* result files.
LOCAL_AUTHORITY_SCOPES = {
    LOCAL_FOLDER_READ: ('folder:read',),
    LOCAL_REFERENCE_READ: ('folder:read',),
    LOCAL_RESULT_WRITE: ('folder:create-result',),
}
LOCAL_AUTHORITY_KIND = {LOCAL_FOLDER_READ: 'read', LOCAL_REFERENCE_READ: 'read', LOCAL_RESULT_WRITE: 'write'}

LOCAL_AUTHORITY_LABELS = {
    LOCAL_FOLDER_READ: '이 Mac의 참고 폴더 읽기',
    LOCAL_REFERENCE_READ: '이 Mac의 원본 폴더 읽기',
    LOCAL_RESULT_WRITE: '이 Mac의 결과 저장 폴더',
}

#: Plain-language authority previews, shown before the owner chooses and again
#: next to the chosen folder.  They state what is included and what is not.
LOCAL_AUTHORITY_PREVIEWS = {
    LOCAL_FOLDER_READ: ('선택한 폴더 하나를 읽기만 허용합니다. 파일을 바꾸거나 지우지 않고, '
                        '이 허용만으로 파일 내용을 외부 AI에 보내지 않습니다.'),
    LOCAL_REFERENCE_READ: ('선택한 폴더 하나를 정리할 원본으로 읽기만 허용합니다. 파일을 바꾸거나 지우지 않고, '
                           '이 허용만으로 파일 내용을 외부 AI에 보내지 않습니다.'),
    LOCAL_RESULT_WRITE: ('선택한 폴더 하나에 새 결과 파일을 만드는 것만 허용합니다. 기존 파일을 덮어쓰거나 '
                         '지우지 않고, 이 허용만으로 파일을 외부로 보내지 않습니다.'),
}

#: The one next action, in conversation.  Telegram never receives a path, a
#: folder name, a handle or an internal identifier: the message is the
#: trigger, and the folder is chosen only on the Mac.
LOCAL_AUTHORITY_GUIDANCE = {
    LOCAL_FOLDER_READ: '이 요청에는 이 Mac의 폴더를 읽는 권한이 필요해 아직 파일을 찾지 않았습니다.',
    LOCAL_REFERENCE_READ: '이 요청에는 정리할 원본 폴더를 읽는 권한이 필요해 아직 실행하지 않았습니다.',
    LOCAL_RESULT_WRITE: '이 요청은 결과 파일을 저장할 폴더가 필요해 아직 실행하지 않았습니다.',
}
LOCAL_AUTHORITY_NEXT_ACTION = (' 지금 필요한 다음 단계는 하나입니다: Mac에서 계속 — Mac에서 AgentOS를 열고 '
                               '설정 → 파일 · 저장에서 폴더를 선택해 주세요.')
LOCAL_AUTHORITY_LINK = ' (Mac의 브라우저에서 {url} 주소를 열어도 됩니다.)'
LOCAL_AUTHORITY_REMOTE = (' 휴대폰이나 다른 기기에서는 Mac 폴더 권한을 줄 수 없으며, 요청은 그대로 기다립니다. '
                          '허용하면 방금 요청을 한 번만 이어서 처리합니다.')

LOCAL_RESUME_TTL_SECONDS = 3600
LOCAL_PENDING_KEY = 'local_authority_pending'
LOCAL_PENDING_MAX = 64

LOCAL_REFUSALS = {
    'no_pending_work': '폴더 권한을 기다리는 요청이 없어 아무 작업도 실행하지 않았습니다.',
    'wrong_owner': '이 요청은 현재 연결된 소유자의 것이 아니라 이어서 처리하지 않았습니다.',
    'generation_changed': 'Telegram 봇 연결이 교체되어 이전 요청은 이어서 처리하지 않았습니다. 필요하면 다시 요청해 주세요.',
    'expired_resume': ('폴더 권한을 기다리던 요청이 만료되어 이어서 처리하지 않았습니다. 폴더 권한은 추가하지 않았습니다. '
                       '다시 요청해 주세요.'),
    'superseded_resume': '요청이 바뀌어 이전 요청은 이어서 처리하지 않았습니다.',
    'replayed_resume': '이미 이어서 처리한 요청이라 다시 실행하지 않았습니다.',
    'resume_claimed': '이 요청은 이미 다른 승인 처리가 진행 중이라 다시 실행하지 않았습니다.',
    'scope_mismatch': '허용한 권한이 요청에 필요한 권한과 달라 요청을 이어서 처리하지 않았습니다.',
    'denied': '폴더 권한을 허용하지 않아 요청을 실행하지 않았습니다. 폴더 권한은 추가하지 않았습니다.',
    'work_already_completed': '이 요청은 이미 끝났거나 취소되어 다시 실행하지 않았습니다.',
    'invalid_resume': '이어서 처리할 유효한 폴더 요청을 찾지 못했습니다.',
}
LOCAL_REFUSAL_DEFAULT = '폴더 권한을 확인하지 못해 요청을 이어서 처리하지 않았습니다.'
LOCAL_RESUMED_NOTICE = {
    'read': '선택한 폴더를 읽기로 허용했습니다. 방금 요청을 이어서 처리합니다.',
    'write': '선택한 폴더에 결과 파일을 만들도록 허용했습니다. 방금 요청을 이어서 처리합니다.',
}


def local_authority_guidance(key, local_url=''):
    """The one contextual next action for a missing local authority."""
    text = LOCAL_AUTHORITY_GUIDANCE[key] + LOCAL_AUTHORITY_NEXT_ACTION
    if local_url:
        text += LOCAL_AUTHORITY_LINK.format(url=local_url)
    return text + ' ' + LOCAL_AUTHORITY_PREVIEWS[key] + LOCAL_AUTHORITY_REMOTE


def local_refusal_text(reason):
    return LOCAL_REFUSALS.get(reason, LOCAL_REFUSAL_DEFAULT)


class _LocalHandle:
    __slots__ = ('token',)

    def __init__(self, token):
        self.token = token


class _LocalReference:
    __slots__ = ('work_id',)

    def __init__(self, work_id):
        self.work_id = work_id


class LocalGrantPending:
    """Single-use, owner-bound, expiring pending state for a local authority.

    Same interface and refusal vocabulary as ``PendingWorkRegistry`` so the
    shared ``ConnectorHandoff.resume`` order applies unchanged.  Rows are
    keyed by a hash of the handle, hold a hashed owner, and never hold a
    path or any request content.  States: pending -> claimed -> completed;
    pending -> expired.  A completed row answers a replay with
    ``replayed_resume`` for its retention window.
    """

    def __init__(self, store, *, clock=time.time, token_factory=lambda: _secrets.token_urlsafe(32),
                 retention_seconds=3600, max_records=LOCAL_PENDING_MAX):
        self.store = store
        self.clock = clock
        self.token_factory = token_factory
        self.retention_seconds = retention_seconds
        self.max_records = max_records

    @staticmethod
    def _key(token):
        return _hashlib.sha256(str(token).encode()).hexdigest()

    def _rows(self):
        raw = self.store.secret(LOCAL_PENDING_KEY)
        return dict(raw) if isinstance(raw, dict) else {}

    def _save(self, rows):
        self.store.secret(LOCAL_PENDING_KEY, rows)

    def _prune(self, rows, now):
        for row in rows.values():
            if row.get('state') == 'pending' and now >= float(row.get('expires_at', 0)):
                row['state'], row['terminal_at'] = 'expired', now
        for key in [k for k, row in rows.items()
                    if row.get('state') in ('completed', 'expired')
                    and now - float(row.get('terminal_at') or 0) >= self.retention_seconds]:
            rows.pop(key, None)
        while len(rows) > self.max_records:
            oldest = min(rows, key=lambda k: float(rows[k].get('issued_at', 0)))
            rows.pop(oldest, None)

    def issue(self, owner_id, work_id, key, required_scopes, *, ttl_seconds=LOCAL_RESUME_TTL_SECONDS):
        if key not in LOCAL_AUTHORITY_SCOPES or tuple(required_scopes) != LOCAL_AUTHORITY_SCOPES[key]:
            raise ConnectorContractError('scope_mismatch')
        token = self.token_factory()
        now = self.clock()
        with _RESUME_LOCK:
            rows = self._rows()
            self._prune(rows, now)
            rows[self._key(token)] = {'owner': _owner_key(owner_id), 'work_id': str(work_id), 'key': key,
                                      'scopes': list(required_scopes), 'issued_at': now,
                                      'expires_at': now + float(ttl_seconds), 'state': 'pending',
                                      'claim': None, 'terminal_at': None}
            self._save(rows)
        return _LocalHandle(token)

    def _row(self, rows, token, owner_id, key):
        row = rows.get(self._key(token)) if isinstance(token, str) and token else None
        if not isinstance(row, dict) or row.get('key') != key:
            raise ConnectorContractError('invalid_resume')
        if not _secrets.compare_digest(str(row.get('owner', '')), _owner_key(owner_id)):
            raise ConnectorContractError('wrong_owner')
        return row

    def claim(self, token, owner_id, key, granted_scopes, handoff_id):
        now = self.clock()
        claim = _hashlib.sha256(str(handoff_id).encode()).hexdigest()
        with _RESUME_LOCK:
            rows = self._rows()
            self._prune(rows, now)
            try:
                row = self._row(rows, token, owner_id, key)
                state = row.get('state')
                if state == 'expired':
                    raise ConnectorContractError('expired_resume')
                if state == 'completed':
                    raise ConnectorContractError('replayed_resume')
                if tuple(granted_scopes) != tuple(row.get('scopes') or ()):
                    raise ConnectorContractError('scope_mismatch')
                if state == 'claimed':
                    if row.get('claim') == claim:
                        return _LocalReference(row['work_id'])
                    raise ConnectorContractError('resume_claimed')
                if state != 'pending':
                    raise ConnectorContractError('invalid_resume')
                row['state'], row['claim'] = 'claimed', claim
                return _LocalReference(row['work_id'])
            finally:
                self._save(rows)

    def complete(self, token, owner_id, key, handoff_id):
        now = self.clock()
        claim = _hashlib.sha256(str(handoff_id).encode()).hexdigest()
        with _RESUME_LOCK:
            rows = self._rows()
            row = self._row(rows, token, owner_id, key)
            if row.get('state') != 'claimed' or row.get('claim') != claim:
                raise ConnectorContractError('unclaimed_resume')
            row['state'], row['terminal_at'] = 'completed', now
            self._save(rows)


def local_authority_handoff(store, *, now=time.time, ttl_seconds=LOCAL_RESUME_TTL_SECONDS):
    """The #393 handoff, parameterised for declared local authorities."""
    return ConnectorHandoff(store, None, LocalGrantPending(store, clock=now), now=now,
                            ttl_seconds=ttl_seconds, requirements=LOCAL_AUTHORITY_SCOPES)
