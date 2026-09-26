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

from .conversation_projection import object_particle
from .providers import NoRedirect, ProviderError

TELEGRAM_API_ROOT = 'https://api.telegram.org'
TELEGRAM_TIMEOUT = 15
TELEGRAM_FAILURE_TEXT = 'Telegram 요청이 실패했습니다. 봇 설정을 확인하세요.'
#: ``stopped_message_generation`` carries the owner's Stop on a draft (#581).
# #626: edited_message carries live-location updates and owner text edits;
# an edit is recorded as a source revision, never replayed as a request.
TELEGRAM_POLL_UPDATE_KINDS = ('message', 'edited_message', 'callback_query', 'stopped_message_generation')
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
                return {'ok': False, 'error_code': envelope.get('error_code', exc.code),
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

    def answer_callback_query(self, callback_query_id, text=None, show_alert=False):
        body = {'callback_query_id': callback_query_id}
        if text:
            body['text'] = text[:200]
        if show_alert:
            body['show_alert'] = True
        return self.call('answerCallbackQuery', body)

    # --- presence (#581): best-effort, never Evidence -------------------------

    def set_message_reaction(self, chat_id, message_id, emoji):
        """Set one emoji reaction on a message (bots may set at most one)."""
        return self.call('setMessageReaction', {'chat_id': chat_id, 'message_id': message_id,
                                                'reaction': [{'type': 'emoji', 'emoji': emoji}]},
                         timeout=TELEGRAM_PRESENCE_TIMEOUT)

    def send_chat_action(self, chat_id, action='typing'):
        return self.call('sendChatAction', {'chat_id': chat_id, 'action': action},
                         timeout=TELEGRAM_PRESENCE_TIMEOUT)

    def send_message_draft(self, chat_id, draft_id, text='', can_stop=True):
        """Show an ephemeral draft; empty text is Telegram's "Thinking…" placeholder."""
        body = {'chat_id': chat_id, 'draft_id': draft_id, 'text': text}
        if can_stop:
            body['can_stop'] = True
        return self.call('sendMessageDraft', body, timeout=TELEGRAM_PRESENCE_TIMEOUT)

    def send_rich_message_draft(self, chat_id, draft_id, thinking_text, can_stop=True):
        """Show an ephemeral rich draft holding only a "Thinking…" block.

        The block is `InputRichBlockThinking` (`<tg-thinking>`), which Bot API
        10.3 allows only in `sendRichMessageDraft`.
        """
        body = {'chat_id': chat_id, 'draft_id': draft_id,
                'rich_message': {'blocks': [{'type': 'thinking', 'text': thinking_text}]}}
        if can_stop:
            body['can_stop'] = True
        return self.call('sendRichMessageDraft', body, timeout=TELEGRAM_PRESENCE_TIMEOUT)

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

from .decision import MULTI_SELECTION_UNSUPPORTED, OUTCOME_DECIDED, OUTCOME_MALFORMED, DecisionContext, DecisionPolicy, UnavailableDecisionEngine

INTENT_GREETING = 'greeting'
INTENT_KNOWLEDGE = 'personal-knowledge'
INTENT_SETTINGS = 'settings'
INTENT_WORKSPACE_SEARCH = 'workspace-search'
INTENT_NOTE_CREATE = 'note-create'
INTENT_NOTE_LIST = 'note-list'
INTENT_CALENDAR_CREATE = 'calendar-create'
INTENT_MAIL_SEARCH = 'mail-search'
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
    INTENT_CALENDAR_CREATE: '일정 만들기',
    INTENT_MAIL_SEARCH: '메일 찾기',
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
CAPABILITY_NEEDS = {
    INTENT_MAIL_SEARCH: ("search or check the owner's own mailbox (Gmail) for a received message, "
                         "for example whether someone wrote, replied or sent something"),
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

_CALENDAR_OBJECTS = ('일정', '미팅', '회의', '약속', 'calendar', 'meeting', 'appointment', 'event')
_CALENDAR_VERBS = ('잡아', '잡을', '잡고', '잡아줘', '만들어', '등록', '추가', '넣어', '예약',
                   'create', 'add', 'book', 'schedule', 'set up', 'put')

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

_RESEARCH_CUES = ('웹에서', '웹 검색', '인터넷', '온라인', '검색해', '찾아봐', '조사해', '알아봐', '최신 정보',
                  'web search', 'search the web', 'look up', 'research', 'find out', 'online',
                  'latest news', 'google it')

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

WITHDRAWAL_PROPOSITION = ('The owner\'s latest message withdraws or cancels the request that is waiting for '
                          'the listed connection (rather than acknowledging it, changing topic, or asking '
                          'something unrelated).')
UNSUPPORTED_QUESTION = ('Is the owner asking the assistant to do one of these things it does not offer: '
                        + '; '.join(f'{key} = {label}' for key, label in UNSUPPORTED_CAPABILITIES.items())
                        + '? Choose that capability. If the request is anything else (searching mail by '
                        'subject/sender/date, notes, calendar, files, research, ordinary conversation), '
                        'choose none-of-these.')
CAPABILITY_NEED_QUESTION = ('Does answering the owner\'s message require one of these assistant capabilities: '
                            + '; '.join(f'{key} = {label}' for key, label in CAPABILITY_NEEDS.items())
                            + '? Choose that capability only when the owner is asking about their own mail, '
                            'whatever words they use. Choose none-of-these for ordinary conversation, general '
                            'knowledge, public web research, notes, calendar, files, a mail they only mention, '
                            'or when it is unclear. This judgment does not authorize any action.')
MAIL_QUERY_TERM_QUESTION = ('The owner is asking about their own mail. Which one of the listed terms, all taken from '
                            'the owner\'s message, best identifies the mail to look for - its sender, organisation '
                            'or subject? Choose none-of-these if no listed term identifies it. This judgment does '
                            'not authorize any action.')
#: At most this many of the owner's own words are offered as query terms.
MAIL_QUERY_MAX_TERMS = 12
#: Recipient/source endings trimmed from a query-term candidate so a Gmail
#: search gets the bare name ("집주인한테" -> "집주인").  Query formatting only;
#: which term is used is the DecisionEngine's selection.
_TERM_ENDINGS = ('한테서', '에게서', '한테', '께서', '께')
MEMORY_REQUEST_PROPOSITION = ('The owner\'s latest message explicitly instructs the assistant to remember, keep '
                              'in mind or not forget a specific fact, value or preference that the owner states in '
                              'that same message, for later conversations. It is false when the owner asks the '
                              'assistant not to remember something, when there is no stated value to keep (a '
                              'casual remark or a generic "don\'t forget"), when they ask for a note, file or '
                              'reminder instead, or when it is unclear. This judgment does not write anything.')
LOOKUP_WITHHOLD_QUESTION = (
    'A public web search, weather or page lookup is about to send the listed terms. The owner\'s latest message '
    'is given for context. Choose every term that carries sensitive personal information from that message - '
    'for example an identity, passport, account, card or phone number (in any spelling, spacing, with separators, '
    'split across several terms, or written out in words), a personal address, or a health, legal or financial '
    'fact about a person (also when spelled out, split or translated). Choose each part of a split value. Choose '
    'none when every term is an ordinary lookup word such as a city or region, a topic, a kind of place or '
    'business, a product or a date. This judgment does not send anything.')
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
    """

    def __init__(self, engine=None, policy=None):
        self.engine = engine or UnavailableDecisionEngine()
        self.policy = policy or DecisionPolicy()

    def parked_work_withdrawn(self, utterance, parked_connectors):
        """Does ``utterance`` withdraw the owner's request(s) parked for
        ``parked_connectors``?  Unavailable/unknown keeps them parked."""
        labels = ', '.join(CONNECTOR_LABELS.get(c) or LOCAL_AUTHORITY_LABELS.get(c, c) for c in parked_connectors)
        context = DecisionContext('parked-work-withdrawal',
                                  {'waiting_connection': labels, 'owner_message': utterance})
        decision = self.engine.judge(context, WITHDRAWAL_PROPOSITION)
        verdict = self.policy.binary(decision)
        return Judgment(JUDGMENT_UNAVAILABLE if verdict == 'unknown' else verdict,
                        source=decision.confidence.provider or decision.outcome)

    def unsupported_capability(self, utterance):
        """Does ``utterance`` ask for a declared-but-unavailable capability?
        ``value`` is its key on yes; a confident none-of-these is no."""
        # `utterance` is a minimized cue summary assembled by IntentClassifier,
        # never the owner's raw mail query or surrounding private text.
        context = DecisionContext('unsupported-capability', {'owner_message': utterance})
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
        context = DecisionContext('conversation-followup', {
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
        context = DecisionContext('capability-need', {'owner_message': utterance})
        decision = self.engine.choose(context, tuple(CAPABILITY_NEEDS), CAPABILITY_NEED_QUESTION)
        choice = self.policy.selection(decision)
        if choice is not None:
            return Judgment(JUDGMENT_YES, value=choice, source=decision.confidence.provider or decision.outcome)
        if self.policy.confident_selection(decision):
            return Judgment(JUDGMENT_NO, source=decision.confidence.provider or decision.outcome)
        return Judgment(JUDGMENT_UNAVAILABLE, source=decision.outcome)

    def mail_query_term(self, utterance, terms):
        """Which of ``terms`` (the owner's own words) identifies the mail sought?

        Candidates are index labels (``term-1`` ...) so the decision and its
        audit row stay content-free; the caller maps the label back to the
        owner's word.  ``value`` is the index on yes.
        """
        labels = tuple(f'term-{index}' for index in range(1, len(terms) + 1))
        context = DecisionContext('mail-query-term', {
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

    def explicit_memory_request(self, utterance):
        """Does ``utterance`` explicitly ask AgentOS to remember a stated value (#597)?

        Judgment only.  A yes lets AgentOS issue the existing owner-request
        memory approval for this Work; the deterministic value-coverage and
        key-replacement checks (``Capabilities.memory_write_refusal``) still
        decide whether a proposed write is canonical or a MemoryCandidate.
        No / unavailable issues nothing, so any write stays a candidate.
        """
        context = DecisionContext('explicit-memory-request', {'owner_message': utterance})
        decision = self.engine.judge(context, MEMORY_REQUEST_PROPOSITION)
        verdict = self.policy.binary(decision)
        return Judgment(JUDGMENT_UNAVAILABLE if verdict == 'unknown' else verdict,
                        source=decision.confidence.provider or decision.outcome)


    def lookup_term_sensitivity(self, utterance, terms):
        """Which of ``terms`` - the whole outbound term list of one public
        lookup - must be withheld (#605 N3, owner decision R1)?

        One ``choose_many`` judgment over the one owner utterance and the term
        list (index labels only, so the audit row stays content-free), the same
        bounds as ``explicit_memory_request``: no history, Memory or files.
        ``value`` is the set of term indices to withhold on yes; a confident
        empty selection is no.  Any non-answer is unavailable, and AgentOS's
        policy then withholds every current-message term (R4).  Judgment only;
        it sends nothing and grants nothing.
        """
        terms = [str(term) for term in terms]
        if not terms:
            return Judgment(JUDGMENT_NO, value=frozenset())
        labels = tuple(f'term-{index}' for index in range(1, len(terms) + 1))
        context = DecisionContext('public-lookup-sensitivity', {
            'owner_message': utterance,
            'terms': '; '.join(f'{label} = {term}' for label, term in zip(labels, terms)),
        })
        decision = self.engine.choose_many(context, labels, LOOKUP_WITHHOLD_QUESTION)
        chosen = self.policy.selection_set(decision)
        source = decision.confidence.provider or decision.outcome
        if chosen is None:
            # `source` tells AgentOS's refusal text apart: the engine could not
            # answer at all, or it answered without enough confidence.
            if decision.confidence.engine == MULTI_SELECTION_UNSUPPORTED:
                return Judgment(JUDGMENT_UNAVAILABLE, source='route-unsupported')
            return Judgment(JUDGMENT_UNAVAILABLE,
                            source='uncertain' if decision.outcome in (OUTCOME_DECIDED, OUTCOME_MALFORMED)
                            else decision.outcome)
        if not chosen:
            # Releasing every term is a yes/no-strength claim, so it must meet
            # the binary threshold (#605 P3-3), not the selection one.
            if not self.policy.confident_binary(decision):
                return Judgment(JUDGMENT_UNAVAILABLE, source='uncertain')
            return Judgment(JUDGMENT_NO, value=frozenset(), source=source)
        return Judgment(JUDGMENT_YES, value=frozenset(labels.index(label) for label in chosen), source=source)



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

    def _rule_calendar(self, text, lowered):
        """Recognise a create request; the utterance itself is the argument.

        Title, date and time are read from it by ``calendar_conversation``'s
        literal rules, so nothing is extracted or persisted here.
        """
        objects = _cue_hits(text, lowered, _CALENDAR_OBJECTS)
        verbs = _cue_hits(text, lowered, _CALENDAR_VERBS)
        if objects and verbs:
            return _Candidate(INTENT_CALENDAR_CREATE, text, (*objects, *verbs))
        return None

    def _rule_research(self, text, lowered):
        cues = _cue_hits(text, lowered, _RESEARCH_CUES)
        return _Candidate(INTENT_RESEARCH, None, cues) if cues else None

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
            self._rule_note,self._rule_calendar,self._rule_mail,
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
                     self._rule_workspace, self._rule_note, self._rule_calendar,
                     self._rule_mail):
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
        research = self._rule_research(text, lowered)
        if research is not None:
            # Research shares the conversation route, so it never competes for
            # ambiguity; it is named only so the decision is legible.
            return IntentDecision(INTENT_RESEARCH, AUTHORITY_RULE, cues=research.cues)
        return IntentDecision(INTENT_CONVERSATION, AUTHORITY_DEFAULT)

    def _judged_capability(self, text):
        """Ask the DecisionEngine whether a cue-free turn needs a declared capability.

        Reached only when no local rule claimed the turn, so notes, settings,
        private searches and calendar drafts are never sent.  A yes selects
        an AgentOS-declared candidate; the argument is one of the owner's own
        words (``_judged_mail_query``), never text the engine produced.  Unavailable, unsure or
        none-of-these returns ``None`` and the turn stays on conversation.
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
