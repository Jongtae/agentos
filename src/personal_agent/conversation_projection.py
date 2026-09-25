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
TERMINAL_UNVERIFIED_MARKER = ('완료한 단계까지의 내용은 AgentOS 웹 기록에서 확인할 수 있습니다. '
                              '확인된 결과가 아니므로 그대로 신뢰하지 마세요.')

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


def terminal_text(response, error=None, outcome=None, next_action=None):
    """The one readable terminal bubble for a paired owner.

    * ``failed`` - no tool produced anything, so no model sentence is
      attributable to an observed result.  The failure, its cause and the
      next step go out; the model text does not.
    * ``partial`` / ``interrupted`` - something may have completed, but
      which sentence rests on it cannot be decided here, so the bubble says
      what completed and what did not and points at the record.  The text
      is not deleted; the web card still offers it under 확인 필요.
    * ``succeeded`` and any unrecognised status - unchanged.

    ``next_action`` replaces the generic web pointer when a safer, more
    specific action exists; it never replaces the truth header.
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
        if cause:
            body.append(cause)
        body.append(TERMINAL_UNVERIFIED_MARKER if (outcome == 'partial' and (response or '').strip()) else action)
        text = '\n\n'.join(body)
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
UNVERIFIED_OUTCOMES = ('failed', 'partial', 'interrupted')
TRANSCRIPT_LABELS = {'failed': '완료하지 못함', 'partial': '일부 완료', 'interrupted': '중단됨'}
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
