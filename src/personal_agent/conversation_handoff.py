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
#   * Anything the rules do not recognise falls through to ``conversation``,
#     the ordinary model-answered route.  An unrecognised utterance never
#     guesses a capability.
#
# Nothing in this module calls a model.  The suggestion seam below exists so
# that a later unit cannot wire one in as authority; no call site supplies a
# suggestion today, and that is an evidence-class statement, not a capability
# claim.
import re
import time

INTENT_GREETING = 'greeting'
INTENT_RECOMMENDATION = 'capability-recommendation'
INTENT_KNOWLEDGE = 'personal-knowledge'
INTENT_SETTINGS = 'settings'
INTENT_ASSISTANT = 'assistant-capability'
INTENT_WORKSPACE_SEARCH = 'workspace-search'
INTENT_NOTE_CREATE = 'note-create'
INTENT_NOTE_LIST = 'note-list'
INTENT_CALENDAR_CREATE = 'calendar-create'
INTENT_RESEARCH = 'research'
INTENT_CONVERSATION = 'conversation'
INTENT_AMBIGUOUS = 'ambiguous'

AUTHORITY_OWNER = 'owner-explicit'
AUTHORITY_RULE = 'agentos-rule'
AUTHORITY_DEFAULT = 'default'

#: Intents whose execution produces an effect the owner would not want guessed.
#: A consequential intent is reachable from an owner-explicit form only.
CONSEQUENTIAL_INTENTS = frozenset({INTENT_CALENDAR_CREATE})

#: Routes that answer with the ordinary model conversation.  They never
#: compete for ambiguity, because losing one costs the owner nothing.
DEFAULT_ROUTE_INTENTS = frozenset({INTENT_CONVERSATION, INTENT_RESEARCH})

#: Intents a bare "keep going" may resolve to.  Every other intent needs its
#: own content, and reusing stale content is exactly the failure mode the
#: correction/topic-change requirement exists to prevent.
CONTINUABLE_INTENTS = frozenset({INTENT_CONVERSATION, INTENT_RESEARCH})

INTENT_LABELS = {
    INTENT_RECOMMENDATION: '검토된 capability 추천',
    INTENT_KNOWLEDGE: '개인 공간 검색',
    INTENT_SETTINGS: '연결 설정 확인/변경',
    INTENT_WORKSPACE_SEARCH: '저장한 작업공간 결과 찾기',
    INTENT_NOTE_CREATE: '메모 기록',
    INTENT_NOTE_LIST: '메모 목록',
    INTENT_CALENDAR_CREATE: '일정 만들기',
    INTENT_RESEARCH: '웹 조사',
    INTENT_CONVERSATION: '대화로 답하기',
}


# --- Cue vocabularies ------------------------------------------------------
# Every cue below is a literal an owner can read and an independent reviewer
# can audit.  Korean cues match as substrings; ASCII cues match on word
# boundaries so that "note" does not fire inside "notebook".

_RECOMMENDATION_CUES = ('추천', '연결할 만한', '뭘 연결', '무엇을 연결', '어떤 걸 붙이', '어떤 capability',
                        'recommend', 'recommendation', 'what should i connect', 'which capability',
                        'suggest a capability', 'suggest capabilities')
# The recommendation orchestrator accepts only its three reviewed outcome
# tags.  Mapping ordinary words onto a reviewed tag is AgentOS policy; the
# orchestrator is never handed free prose.
_RECOMMENDATION_OUTCOMES = (
    ('private-document-research', ('문서 조사', '자료 조사', '문서 연구', '내 문서', '내 자료',
                                   'document research', 'research my documents', 'my documents')),
    ('specialist-research', ('전문가', '전문 조사', '리서치 전문', '심층 조사',
                             'specialist', 'expert research', 'deep research')),
    ('local-specialist-processing', ('로컬 처리', '내 컴퓨터에서', '기기 안에서',
                                     'local processing', 'on-device', 'run locally')),
)

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
_SETTINGS_TARGETS = ('drive', '드라이브', 'calendar', '캘린더', '일정', 'a2a', 'peer', '피어', 'mcp')

_WORKSPACE_CUES = ('작업공간', '워크스페이스', '저장한 결과', '저장된 결과', '저장한 파일', '저장된 파일',
                   '저장해 둔 파일', '내가 저장한',
                   'workspace', 'saved result', 'saved results', 'saved file', 'saved files',
                   'file i saved', 'files i saved')
_WORKSPACE_VERBS = ('찾아', '찾을', '검색', '열어', '보여', '가져와', '불러와', '다시 써', '재사용',
                    'open', 'show', 'find', 'search', 'pull up', 'reuse', 'get')

_CALENDAR_OBJECTS = ('일정', '미팅', '회의', '약속', 'calendar', 'meeting', 'appointment', 'event')
_CALENDAR_VERBS = ('잡아', '잡을', '잡고', '잡아줘', '만들어', '등록', '추가', '넣어', '예약',
                   'create', 'add', 'book', 'schedule', 'set up', 'put')

_RESEARCH_CUES = ('웹에서', '웹 검색', '인터넷', '온라인', '검색해', '찾아봐', '조사해', '알아봐', '최신 정보',
                  'web search', 'search the web', 'look up', 'research', 'find out', 'online',
                  'latest news', 'google it')

# A note is written when the owner says "write it down", not when the owner
# says "remember" - `AgentService.explicit_memory_request` already owns the
# memory vocabulary and must not be shadowed here.
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
    """Content-free record of what the one conversation is currently about.

    Only the decided intent and a timestamp are persisted.  The utterance,
    its subject and any extracted argument stay out of durable state, so a
    pasted secret or document excerpt is never written here.
    """

    KEY = 'conversation_focus'

    def __init__(self, store, now=time.time):
        self.store, self.now = store, now

    def current(self):
        row = self.store.config(self.KEY, {})
        return row if isinstance(row, dict) else {}

    def record(self, decision):
        if decision.intent == INTENT_AMBIGUOUS:
            return
        self.store.put(self.KEY, {'intent': decision.intent, 'at': self.now()})

    def clear(self):
        self.store.put(self.KEY, {})


_QUOTED = re.compile(r'["“]([^"”]{2,160})["”]')

AMBIGUOUS_PREFIX = '이 요청이 '
AMBIGUOUS_SUFFIX = (' 중 무엇인지 확실하지 않아 아무 작업도 실행하지 않았습니다. '
                    '하나만 골라 다시 말씀해 주세요.')
CONSEQUENTIAL_CLARIFICATIONS = {
    INTENT_CALENDAR_CREATE: ('일정을 만드는 것은 되돌리기 어려운 작업이라 추측으로 진행하지 않았습니다. '
                             '만들 일정의 제목과 시작/종료 시각을 알려 주시면 초안을 만들어 승인을 요청할게요.'),
}
RECOMMENDATION_CLARIFICATION = ('추천할 수 있는 결과 유형은 private-document-research, specialist-research, '
                                'local-specialist-processing 입니다. 어떤 결과를 원하시는지 하나만 알려 주세요.')
SETTINGS_READ_FORM = '/settings'
KNOWLEDGE_CLARIFICATION = '개인 공간에서 무엇을 찾을지 두 글자 이상으로 알려 주세요.'
NOTE_CLARIFICATION = '무엇을 기록할지 내용을 함께 적어 주세요.'


class _Candidate:
    """One rule match, before ambiguity and consequence policy is applied."""

    __slots__ = ('intent', 'argument', 'cues', 'clarification')

    def __init__(self, intent, argument, cues, clarification=None):
        self.intent, self.argument, self.cues, self.clarification = intent, argument, tuple(cues), clarification


class IntentClassifier:
    """Deterministic, AgentOS-owned routing for one owner utterance.

    The class consults no model.  It reads the utterance against literal cue
    tables declared above, and returns an :class:`IntentDecision` recording
    which cues fired.  A capability is therefore never selected by anything
    that cannot be re-derived and justified from the utterance alone.

    ``workspace_search`` is injected rather than imported so that this module
    stays free of any dependency on the service that uses it.
    """

    def __init__(self, workspace_search=None):
        self._workspace_search = workspace_search

    # -- owner-explicit forms ------------------------------------------------
    # Slash commands and the legacy Korean colon forms are no longer the
    # *required* entry path, but they remain exactly as authoritative as they
    # were.  An owner who learned them keeps them.
    def explicit(self, text):
        if text in ('/start', '/help'):
            return IntentDecision(INTENT_GREETING, AUTHORITY_OWNER)
        if text.startswith('/recommend '):
            return IntentDecision(INTENT_RECOMMENDATION, AUTHORITY_OWNER, argument=text[len('/recommend '):].strip())
        if text.startswith('/knowledge '):
            return IntentDecision(INTENT_KNOWLEDGE, AUTHORITY_OWNER, argument=text[len('/knowledge '):].strip())
        if text.startswith('/settings '):
            return IntentDecision(INTENT_SETTINGS, AUTHORITY_OWNER, argument=text[len('/settings '):])
        if text in ('/settings', '무엇이 연결되어 있어?', '무엇을 바꿀 수 있어?'):
            return IntentDecision(INTENT_SETTINGS, AUTHORITY_OWNER, argument=text)
        if text.startswith('/assistant '):
            return IntentDecision(INTENT_ASSISTANT, AUTHORITY_OWNER, argument=text[len('/assistant '):])
        if text in ('/notes', '메모 목록'):
            return IntentDecision(INTENT_NOTE_LIST, AUTHORITY_OWNER)
        if text.startswith('/note '):
            return IntentDecision(INTENT_NOTE_CREATE, AUTHORITY_OWNER, argument=text[len('/note '):])
        if text.startswith(('메모:', '기록:')):
            return IntentDecision(INTENT_NOTE_CREATE, AUTHORITY_OWNER, argument=text.split(':', 1)[1].strip())
        return None

    # -- natural-language rules ---------------------------------------------
    def _rule_recommendation(self, text, lowered):
        cues = _cue_hits(text, lowered, _RECOMMENDATION_CUES)
        if not cues:
            return None
        matched = [(tag, hits) for tag, words in _RECOMMENDATION_OUTCOMES
                   if (hits := _cue_hits(text, lowered, words))]
        if len(matched) != 1:
            return _Candidate(INTENT_RECOMMENDATION, None, cues, RECOMMENDATION_CLARIFICATION)
        return _Candidate(INTENT_RECOMMENDATION, matched[0][0], (*cues, *matched[0][1]))

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

    def _rule_calendar(self, text, lowered):
        objects = _cue_hits(text, lowered, _CALENDAR_OBJECTS)
        verbs = _cue_hits(text, lowered, _CALENDAR_VERBS)
        if objects and verbs:
            return _Candidate(INTENT_CALENDAR_CREATE, None, (*objects, *verbs))
        return None

    def _rule_research(self, text, lowered):
        cues = _cue_hits(text, lowered, _RESEARCH_CUES)
        return _Candidate(INTENT_RESEARCH, None, cues) if cues else None

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
        for rule in (self._rule_recommendation, self._rule_knowledge, self._rule_settings,
                     self._rule_workspace, self._rule_note, self._rule_calendar):
            found = rule(text, lowered)
            if found is not None:
                candidates.append(found)

        if len(candidates) == 1:
            decision = self._single(candidates[0])
        elif candidates:
            decision = self._ambiguous(candidates)
        else:
            decision = self._fallback(text, lowered, focus_intent, bool(correction))

        if focus_intent and (correction or focus_intent != decision.intent) and decision.intent != INTENT_AMBIGUOUS:
            decision.supersedes_previous = True
        return self._with_suggestion(decision, candidates, model_suggestion)

    @staticmethod
    def _single(candidate):
        if candidate.clarification:
            return IntentDecision(candidate.intent, AUTHORITY_RULE, cues=candidate.cues,
                                  clarification=candidate.clarification)
        if candidate.intent in CONSEQUENTIAL_INTENTS:
            # A consequential effect is never inferred.  The rules recognised
            # it, and that recognition buys the owner an explanation, not an
            # execution.
            return IntentDecision(candidate.intent, AUTHORITY_RULE, cues=candidate.cues,
                                  clarification=CONSEQUENTIAL_CLARIFICATIONS[candidate.intent])
        return IntentDecision(candidate.intent, AUTHORITY_RULE, argument=candidate.argument,
                              cues=candidate.cues)

    @staticmethod
    def _ambiguous(candidates):
        options = tuple(dict.fromkeys(item.intent for item in candidates))
        labels = ', '.join(INTENT_LABELS.get(option, option) for option in options)
        return IntentDecision(INTENT_AMBIGUOUS, AUTHORITY_RULE, alternatives=options,
                              cues=tuple(cue for item in candidates for cue in item.cues),
                              clarification=AMBIGUOUS_PREFIX + labels + AMBIGUOUS_SUFFIX)

    def _fallback(self, text, lowered, focus_intent, correction):
        """No capability rule fired: stay on the ordinary conversation route."""
        continuation = _cue_hits(text, lowered, _CONTINUATION_CUES)
        if continuation and not correction and focus_intent in CONTINUABLE_INTENTS:
            return IntentDecision(focus_intent, AUTHORITY_RULE, cues=continuation, continuation=True)
        research = self._rule_research(text, lowered)
        if research is not None:
            # Research shares the conversation route, so it never competes for
            # ambiguity; it is named only so the decision is legible.
            return IntentDecision(INTENT_RESEARCH, AUTHORITY_RULE, cues=research.cues)
        return IntentDecision(INTENT_CONVERSATION, AUTHORITY_DEFAULT)

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
