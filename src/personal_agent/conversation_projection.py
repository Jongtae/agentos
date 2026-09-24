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
                '메일과 캘린더는 연결하면 쓸 수 있습니다.\n\n' + self._where_to_connect())

    def _model_unverified(self, repeat):
        if repeat:
            return '연결한 AI의 확인이 아직 끝나지 않아 이 요청은 처리하지 못했습니다. ' + self._where_to_connect()
        return ('연결한 AI가 도구 호출까지 되는지 아직 확인하지 못해 이 요청은 처리하지 못했습니다. '
                '설정에서 “모델 연결 확인”을 한 번 실행하면 이어서 쓸 수 있습니다.\n\n' + self._where_to_connect())
