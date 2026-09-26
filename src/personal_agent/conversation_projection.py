"""Owner-facing conversation projection (PRESENCE-CONV-01 / #510).

The kernel stays mechanical: Work -> Event -> tool -> Evidence -> outcome.
This module is the policy layer between that state and the one paired
conversation.  It decides *what the owner reads*, never what is true: the
outcome (succeeded / failed / partial / interrupted) and the blocker that
stopped a turn are fixed by the service before anything here runs, and no
wording below may soften them.  See docs/presence-experience-contract.en.md
("Conversation projection rules").

Two things live here:

* the terminal bubble for one Work, which was `telegram_result_text` and
  keeps its #476/#488 truth rules - a failed turn never carries the model's
  prose, a partial turn separates what completed from what did not;
* blocked turns - a request that could not start because something the
  owner controls is missing (no AI route, an unverified model, a document
  approval).  The first such turn gets the useful explanation and the next
  action available *in conversation*; a repeat of the same blocker gets a
  one-line reminder instead of the same failure again.  Which blocker it is
  comes from typed state at the raise site, not from reading the wording.
"""
import time

TELEGRAM_RESULT_PREVIEW_CHARS = 3200

TERMINAL_FAILED_HEADER = '이 요청은 완료하지 못했습니다.'
TERMINAL_PARTIAL_HEADER = '일부 단계만 완료했습니다.'
TERMINAL_INTERRUPTED_HEADER = '이 요청은 중단되었습니다. 자동으로 다시 실행하지 않았습니다.'
TERMINAL_NEXT_ACTION = 'AgentOS 웹에서 실행 기록과 다음 단계를 확인하세요.'
#: Used only when an ``unknown`` Work carries no statement of its own.
TERMINAL_UNKNOWN_EFFECT = ('외부 결과를 확인할 수 없습니다. 실제 결과를 직접 확인해 주세요. '
                           '자동으로 다시 시도하지 않았습니다.')
TERMINAL_UNVERIFIED_MARKER = ('AI가 작성한 답변 전체는 AgentOS 웹 기록에서 볼 수 있습니다. '
                              '확인된 결과가 아니므로 그대로 신뢰하지 마세요.')
#: Opens the portion of a partial Work that its own typed Evidence supports
#: (#598 H1).  What follows is AgentOS's rendering of observed tool results,
#: never the model's prose.
TERMINAL_VERIFIED_LABEL = '확인된 부분:'
#: Opens the portion that did not complete, so it reads apart from the above.
TERMINAL_UNFINISHED_LABEL = '완료하지 못한 부분'
#: Upper bound for the verified portion inside one bubble; the full record
#: stays in the AgentOS web Task detail.
TERMINAL_VERIFIED_CHARS = 1600
TERMINAL_VERIFIED_MORE = '… (나머지는 AgentOS 웹 기록에서 확인하세요.)'

# --- owner words for internal tool ids (#598 X1) -----------------------------
#: The same owner vocabulary the web Task detail uses (``TOOL_NAMES`` in
#: web/app.js; shared keys must match, see tests).  Exact ids stay in
#: 상세/기술 정보; conversation says what kind of step it was.
TOOL_LABELS = {
    'subscription_engine': '구독 CLI 실행', 'model': 'AI 응답', 'web_search': '웹 검색',
    'list_notes': '메모 조회', 'save_note': '메모 저장', 'save_memory': '기억 저장',
    'list_memory': '기억 조회', 'local_authority': '폴더 권한', 'calendar_create': '일정 만들기',
    'calendar_query': '일정 조회', 'calendar_draft_create': '일정 초안', 'calendar_draft_update': '일정 초안',
    'calendar_draft_cancel': '일정 초안', 'weather': '날씨 조회', 'ask_location': '위치 확인',
    'delegate_agent': '다른 에이전트에 맡김', 'list_agents': '에이전트 목록 조회',
    'find_files': '파일 찾기', 'read_file': '파일 읽기', 'public_page_read': '공개 페이지 읽기',
    'bounded_public_research': '공개 자료 조사',
    # SEC-BROWSER-01 (#656): steps in the owner-logged-in browser profile.
    'browser_open': '브라우저 페이지 열기', 'browser_read': '브라우저 페이지 읽기', 'browser_find': '브라우저 페이지에서 찾기', 'browser_click': '브라우저에서 누르기', 'browser_type': '브라우저에 입력',
    # CONTEXT-STATE-01 (#627): a revisable hypothesis about today's situation.
    'propose_current_state': '현재 상황 기록',
    # SEC-ATTN-01 (#659): an owner-accepted reminder or preparation.
    'schedule_preparation': '준비 예약',
}
#: A tool this catalogue does not name (for example an AgentPackage tool).
TOOL_LABEL_FALLBACK = '도구 실행'


def tool_label(tool_id):
    """Owner words for one tool id; never the id itself."""
    return TOOL_LABELS.get(tool_id, TOOL_LABEL_FALLBACK) if isinstance(tool_id, str) else TOOL_LABEL_FALLBACK


#: Latin letters and digits whose Korean reading ends in a final consonant
#: (엘, 엠, 엔, 알 / 영, 일, 삼, 육, 칠, 팔), for names such as ``Gmail``.
_FINAL_CONSONANT_READINGS = frozenset('lmnr013678')


def object_particle(word):
    """``을`` or ``를`` for ``word`` - never the ``을(를)`` template (#598).

    Hangul uses the final syllable's own consonant (Unicode composition:
    ``(code - 0xAC00) % 28``); a Latin letter or digit uses how it is read.
    Anything else keeps the neutral template rather than guessing.
    """
    text = str(word or '').rstrip(' )]}\'"')
    if not text:
        return '을(를)'
    last = text[-1]
    if '가' <= last <= '힣':
        return '를' if (ord(last) - 0xAC00) % 28 == 0 else '을'
    if last.isascii() and last.isalnum():
        return '을' if last.lower() in _FINAL_CONSONANT_READINGS else '를'
    return '을(를)'


def owner_cause(steps):
    """The owner-language cause of a failed/partial Work, or ``None``.

    ``steps`` are ``(tool_id, reason)`` pairs observed for the Work, with the
    reason already redacted by the caller.  The technical cause (with ids)
    stays on the Work record for Task detail; this is what the conversation
    reads.  One generic rendering: no tool gets its own wording here.
    """
    entries = []
    for tool, reason in steps:
        label = tool_label(tool)
        text = (reason or '').strip()
        entry = f'{label}: {text}' if text else label
        if entry not in entries:
            entries.append(entry)
    if not entries:
        return None
    return (TERMINAL_UNFINISHED_LABEL + ' — ' + ' · '.join(entries[:3]))[:400]


#: SEC-LOOP-01 (#657): the report lines after the failed steps.
REPORT_STATED_FAILED_LABEL = '진행하지 못한 점:'
REPORT_UNKNOWN_LABEL = '확인하지 못한 부분:'
REPORT_NEXT_LABEL = '다음 단계 제안:'
REPORT_QUESTION_LABEL = '확인이 필요한 질문:'
REPORT_STATEMENT_CHARS = 1200


def report_statement(report):
    """The unknown / next part of a run's typed report (#657), or ``None``.

    ``report`` is ``agent_runtime.agency_report``: requested, observed
    (rendered as the verified portion), failed (tool failures are rendered by
    ``owner_cause``; only the worker's own ``assistant`` statements appear
    here), unknown, the one question a ``needs_owner`` finish asks, and next.
    Nothing here says a step completed.
    """
    if not isinstance(report, dict):
        return None
    lines = []
    stated = [str(reason).strip() for tool, reason in report.get('failed') or ()
              if tool == 'assistant' and str(reason or '').strip()]
    if stated:
        lines.append(REPORT_STATED_FAILED_LABEL + ' ' + ' · '.join(stated))
    unknown = [str(item).strip() for item in report.get('unknown') or () if str(item or '').strip()]
    if unknown:
        lines.append(REPORT_UNKNOWN_LABEL + ' ' + ' · '.join(unknown))
    question = str(report.get('question') or '').strip()
    if question:
        lines.append(REPORT_QUESTION_LABEL + ' ' + question)
    step = str(report.get('next') or '').strip()
    if step:
        lines.append(REPORT_NEXT_LABEL + ' ' + step)
    return '\n'.join(lines)[:REPORT_STATEMENT_CHARS] if lines else None


def verified_portion(parts):
    """Join AgentOS-rendered verified parts into one bounded block, or ``None``."""
    text = '\n\n'.join(part.strip() for part in parts or () if isinstance(part, str) and part.strip())
    if not text:
        return None
    if len(text) > TERMINAL_VERIFIED_CHARS:
        text = text[:TERMINAL_VERIFIED_CHARS].rstrip() + TERMINAL_VERIFIED_MORE
    return text

# --- blockers ---------------------------------------------------------------
BLOCKER_NO_AI_ROUTE = 'no-ai-route'
BLOCKER_MODEL_UNVERIFIED = 'model-unverified'
BLOCKER_DOCUMENT_APPROVAL = 'document-approval'


class BlockedTurn(ValueError):
    """A turn that could not start for a reason the owner can resolve.

    ``kind`` is the deterministic blocker identity the projection keys on;
    ``str(exc)`` stays the plain cause for records that need it.
    """

    def __init__(self, kind, text):
        super().__init__(text)
        self.kind = kind


def terminal_text(response, error=None, outcome=None, next_action=None, verified=None):
    """The one readable terminal bubble for a paired owner.

    * ``failed`` - no tool produced anything, so no model sentence is
      attributable to an observed result.  The failure, its cause and the
      next step go out; the model text does not.
    * ``partial`` / ``interrupted`` - something may have completed, but
      which model sentence rests on it cannot be decided here.  The bubble
      states the portion the Work's own typed Evidence supports
      (``verified``, rendered by AgentOS from observed tool results - never
      the model's prose), then the portion that did not complete, and points
      at the record for the rest (#598 H1).  The model text is not deleted;
      the web card still offers it under 확인 필요.
    * ``unknown`` - a consequential external effect was attempted and its
      result could not be observed.  ``error`` is the effect owner's own
      complete statement (what could not be confirmed and what to check);
      it is the whole bubble.  Model text is never shown, nothing claims
      success, and no retry is offered here (#598 I1).
    * ``succeeded`` and any unrecognised status - unchanged.

    ``next_action`` replaces the generic web pointer when a safer, more
    specific action exists; it never replaces the truth header.  Nothing
    here upgrades the outcome: ``verified`` only adds what was observed.
    """
    cause = (error or '').strip()
    action = next_action or TERMINAL_NEXT_ACTION
    if outcome == 'failed':
        body = [TERMINAL_FAILED_HEADER]
        if cause:
            body.append(cause)
        body.append(action)
        text = '\n\n'.join(body)
    elif outcome in ('partial', 'interrupted'):
        body = [TERMINAL_PARTIAL_HEADER if outcome == 'partial' else TERMINAL_INTERRUPTED_HEADER]
        observed = verified_portion([verified]) if outcome == 'partial' else None
        if observed:
            body.append(TERMINAL_VERIFIED_LABEL + '\n' + observed)
        if cause:
            body.append(cause)
        body.append(TERMINAL_UNVERIFIED_MARKER if (outcome == 'partial' and (response or '').strip()) else action)
        text = '\n\n'.join(body)
    elif outcome == 'unknown':
        text = cause or TERMINAL_UNKNOWN_EFFECT
    else:
        text = response or (TERMINAL_FAILED_HEADER + ' ' + (cause or action))
    if len(text) > TELEGRAM_RESULT_PREVIEW_CHARS:
        return text[:TELEGRAM_RESULT_PREVIEW_CHARS] + '\n\n전체 결과는 AgentOS 웹에서 확인하세요.'
    return text


class ConversationProjection:
    """Blocked-turn replies with once-per-blocker explanation.

    The store keeps only ``{owner: {'kind', 'at'}}``: which blocker this owner
    was last told about, never the utterance.  ``settings_url`` returns the
    local AgentOS address when the installation can name one, else ''.
    """

    KEY = 'conversation_blocker'

    def __init__(self, store, settings_url=None, now=time.time):
        self.store, self.settings_url, self.now = store, settings_url or (lambda: ''), now

    def _rows(self):
        rows = self.store.config(self.KEY, {})
        return rows if isinstance(rows, dict) else {}

    def clear(self, owner):
        rows = self._rows()
        if rows.pop(str(owner), None) is not None:
            self.store.put(self.KEY, rows)

    def blocked_reply(self, owner, kind, cause):
        """The reply for a blocked turn; a repeat of the same blocker is short."""
        rows = self._rows()
        previous = rows.get(str(owner))
        repeat = isinstance(previous, dict) and previous.get('kind') == kind
        rows[str(owner)] = {'kind': kind, 'at': float(self.now())}
        self.store.put(self.KEY, rows)
        if kind == BLOCKER_NO_AI_ROUTE:
            return self._no_ai_route(repeat)
        if kind == BLOCKER_MODEL_UNVERIFIED:
            return self._model_unverified(repeat)
        # Other blockers (a document approval the notification below asks
        # for) already carry their next action in the cause.
        return cause

    def _where_to_connect(self):
        url = self.settings_url()
        if url:
            return f'AI 연결은 이 컴퓨터의 AgentOS 설정에서 할 수 있습니다: {url}'
        return ('AI 연결은 이 컴퓨터의 AgentOS 설정에서 할 수 있습니다. AgentOS를 시작할 때 표시된 주소'
                '(setup-link.txt)를 브라우저에서 여세요.')

    def _no_ai_route(self, repeat):
        if repeat:
            return 'AI가 아직 연결되지 않아 이 요청은 처리하지 못했습니다. ' + self._where_to_connect()
        return ('아직 AI가 연결되지 않아 이 요청은 처리하지 못했습니다.\n\n'
                '지금 바로 되는 일: 메모 남기기와 메모 목록 보기, 저장한 파일 찾기. '
                '캘린더는 연결하면 쓸 수 있습니다. 메일 검색에는 Gmail 연결과 판단 기능 설정이 모두 필요합니다.\n\n'
                + self._where_to_connect())

    def _model_unverified(self, repeat):
        if repeat:
            return '연결한 AI의 확인이 아직 끝나지 않아 이 요청은 처리하지 못했습니다. ' + self._where_to_connect()
        return ('연결한 AI가 도구 호출까지 되는지 아직 확인하지 못해 이 요청은 처리하지 못했습니다. '
                '설정에서 “모델 연결 확인”을 한 번 실행하면 이어서 쓸 수 있습니다.\n\n' + self._where_to_connect())


# --- truth qualifiers for stored turns (#494) -------------------------------
#
# #476 keeps an unverified model sentence out of the terminal bubble; the
# same sentence is also stored in ``messages`` and read back by the web API,
# by project views and by the next turn's model context.  The stored text is
# never rewritten or deleted - preserving it is the point.  Instead every
# reader attaches the producing Work's typed outcome at read time, through
# the functions below, so one policy decides what "unverified" means for
# every surface.  The outcome comes from the Work record, never from reading
# the wording.

#: Work outcomes whose assistant text is preserved and offered, not asserted.
#: ``unknown``: a consequential effect was attempted and not observed (#598 I1).
UNVERIFIED_OUTCOMES = ('failed', 'partial', 'interrupted', 'unknown')
TRANSCRIPT_LABELS = {'failed': '완료하지 못함', 'partial': '일부 완료', 'interrupted': '중단됨',
                     'unknown': '외부 결과 불확실'}
TRANSCRIPT_NOTICE = '확인된 결과가 아니므로 그대로 신뢰하지 마세요.'
#: What a later model turn reads in front of an unverified earlier reply.  It
#: names only the typed outcome, so no cause text or tool payload is added to
#: what the route already receives.
CONTEXT_QUALIFIER = ('[AgentOS record: the Work behind this earlier assistant reply ended "{outcome}". '
                     'Any result, action or completion it states is unverified and is not an observed fact.]')


def turn_qualifier(outcome, cause=None):
    """The typed truth qualifier for one Work's text, or ``None`` when none is needed."""
    if outcome not in UNVERIFIED_OUTCOMES:
        return None
    return {'outcome': outcome, 'verified': False, 'label': TRANSCRIPT_LABELS[outcome],
            'notice': TRANSCRIPT_NOTICE, 'cause': (cause or '').strip() or None}


def qualify_transcript(rows):
    """Attach ``qualifier`` to every stored turn; the stored text is untouched.

    ``rows`` carry ``work_outcome`` / ``work_error`` joined from the Work that
    produced them.  Those join columns are consumed here, so every reader sees
    the same single field.  Owner turns are never qualified: they are
    requests, not claims.
    """
    projected = []
    for row in rows:
        row = dict(row)
        outcome, cause = row.pop('work_outcome', None), row.pop('work_error', None)
        row['qualifier'] = turn_qualifier(outcome, cause) if row.get('role') == 'assistant' else None
        projected.append(row)
    return projected


def context_message(row):
    """One stored turn as a later model turn may read it.

    A qualified assistant reply keeps its full text - the owner may refer to
    it ("try that again") - but is preceded by its outcome, so an unobserved
    claim cannot re-enter the model's own context as an established fact.
    """
    content = str(row.get('content') or '')
    qualifier = row.get('qualifier')
    if (row.get('role') == 'assistant' and isinstance(qualifier, dict)
            and qualifier.get('outcome') in UNVERIFIED_OUTCOMES):
        content = CONTEXT_QUALIFIER.format(outcome=qualifier['outcome']) + '\n' + content
    return {'role': row.get('role'), 'content': content}
