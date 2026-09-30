"""Native Telegram presence for the one paired conversation (PRESENCE-TG-01 / #581, PRESENCE-TG-02 / #835, PRESENCE-TG-03 / #858).

The kernel stays mechanical: Work -> Event -> tool -> Evidence -> outcome.
This module only decides *how an already-decided turn looks in Telegram*:

* a best-effort **reaction** on the owner's own message: 👀 ("looking") the
  moment the Work starts, then the emoji the owner's Judgment AI chooses for
  that message (#858, ``RECEIVED_CANDIDATES``), replaced once the outcome is
  decided and the answer sent (``outcome_reaction``, and for a succeeded
  answer again the Judgment AI's choice among ``CLOSING_CANDIDATES``);
* a **wait surface** while Work runs - nothing, ``typing…``, and from
  ``draft_after`` an ephemeral draft: Telegram's own animated *thinking*
  block (``sendRichMessageDraft``, #858) carrying cycling dots and the
  observed step line (#718), a plain ``sendMessageDraft`` with the same text
  when the rich draft is refused, plus Telegram's Stop button, with
  ``typing…`` kept alive until the answer lands;
* the **reply anchor** and bounded **controls** of the one durable reply;
* the **formatting** of that reply, so model Markdown never leaks as ``**``.

Nothing here is truth.  A reaction is presence, never Evidence that anything
succeeded; a failed reaction, chat action or draft is a presentation failure
that must not fail, duplicate or change Work.  Whether a turn succeeded, was
cancelled or has an unknown external effect is decided elsewhere
(``quickstart_service`` and the existing cancellation/effect state machine)
before anything here runs.

Owner feedback 2026-09-28 (#835): a fixed 👍 on every turn meant nothing.
Until then (#581) a reaction was never allowed to read as "done".  Now a
"done" reaction is allowed, but only *after* the terminal outcome is decided
and only for ``succeeded``; ``partial``, ``failed``, ``unknown`` and every
other non-success outcome removes the 👀 and shows no emoji at all, so no
gesture can be read as success the Work did not have.  The choice is
deterministic from the decided outcome and the Work's observed tool events -
never from the owner's words (no phrase or keyword catalogue here) and never
from an extra model call made only to pick an emoji - and every emoji used is
one Telegram documents as available (``TELEGRAM_REACTION_EMOJI``, pinned by a
test).  The same feedback replaced the "생각 중…" wait text with cycling dots.

Owner direction 2026-09-29 (#858): the wait is animated again - Telegram's
thinking block, which the client renders with its own motion, now holds the
dots instead of a label - and the reaction is no longer one fixed emoji per
outcome.  The Judgment AI (the same DecisionEngine seam as every other
per-turn judgment) chooses it from a curated subset of the documented
reactions: once over the owner's message when the Work starts, once over the
message and the delivered answer after a succeeded reply.  The #835 truth rule
is unchanged: the AI is asked for a closing emoji only when the deterministic
rule would already show one; every other outcome removes the reaction and
asks nothing.  An unavailable or unconfident judgment keeps the deterministic
emoji.

Telegram Bot API baseline verified at implementation time (2026-09-25,
re-checked 2026-09-29): Bot API 10.3 (2026-08-24),
https://core.telegram.org/bots/api - ``setMessageReaction`` (an empty
``reaction`` list removes the bot's reaction), ``sendChatAction``,
``sendMessageDraft`` (``draft_id``, ``can_stop``, ``keep_on_stop``),
``sendRichMessageDraft`` with ``InputRichBlockThinking`` (``type:
thinking``, ``text: RichText``, a plain String allowed; "may be used only in
sendRichMessageDraft"; "changes to drafts with the same identifier are
animated"), the ``stopped_message_generation`` update
(``MessageGenerationStopped``: ``chat``, ``draft_id``), ``ReplyParameters``,
``InlineKeyboardButton.disabled`` / ``DisabledButton`` and the HTML parse mode.
"""
import hashlib
import html
import re
import time
from dataclasses import dataclass, field

from .calendar_conversation import STATE_AWAITING_APPROVAL
from .orchestrator import EVENT_TOOL, PLANNED

# --- typed presentation vocabulary -------------------------------------------

WAIT_NONE = 'none'
WAIT_CHAT_ACTION = 'chat_action'
WAIT_DRAFT = 'draft'

# --- waiting dots (PRESENCE-TG-02 / #835) ----------------------------------------
#
# The draft cycles these frames, one per ``PresenceTiming.dots_refresh``,
# instead of the "생각 중…" / "결과를 살펴보는 중…" text the owner found stiff
# (2026-09-28).  #858: the frames are the *text* of Telegram's thinking block
# (``sendRichMessageDraft``), which the client animates itself - #649 showed
# that motion on Telegram Desktop; #837 lost it by moving to a plain draft
# only to drop the "생각 중…" label the block then carried.  Now the block
# carries the dots and no label.  A refused rich draft falls back to the plain
# ``sendMessageDraft`` with the same text.  The text is never empty: an empty
# ``sendMessageDraft`` renders as a blank bubble on the owner's iOS client
# (#581 live check, 2026-09-26).

#: Frames of the waiting animation (U+00B7 MIDDLE DOT), in display order.
DOTS_FRAMES = ('·', '· ·', '· · ·')
#: ``draft_step`` text while no observed step is in flight (before the first
#: tool call, or between two): the draft then shows the dots alone.
NO_STEP_LINE = ''
_TRAILING_ELLIPSIS = re.compile(r'(?:\s*(?:…|\.{2,}))+\s*$')


def draft_frame(line, frame, note=None):
    """The draft text: the observed step line (if any) followed by dots frame ``frame``.

    A trailing ellipsis on the line is dropped, since the dots replace it.
    ``note`` (ATTN-WAIT-01 / #839: the one "참, …" attention line) follows on
    its own line.  Never empty.
    """
    dots = DOTS_FRAMES[frame % len(DOTS_FRAMES)]
    line = _TRAILING_ELLIPSIS.sub('', str(line or '')).strip()
    return with_note(f'{line} {dots}' if line else dots, note)


def with_note(text, note=None):
    """``text`` followed, on its own line, by the one attention ``note`` (#839) if any."""
    note = ' '.join(str(note or '').split())
    return f'{text}\n{note}' if note else text


def rich_draft_blocks(text, note=None):
    """The ``InputRichMessage.blocks`` of one waiting draft (#858).

    The first block is Telegram's ``thinking`` block holding ``text`` (the
    step line and dots, never empty); the #839 attention ``note`` follows as
    an ordinary paragraph so the animated block keeps only the wait itself.
    """
    blocks = [{'type': 'thinking', 'text': text or draft_frame('', 0)}]
    note = ' '.join(str(note or '').split())
    if note:
        blocks.append({'type': 'paragraph', 'text': note})
    return blocks


def draft_body_text(body):
    """The text one draft request body shows, for a plain or a rich draft.

    A rich body's blocks are joined by newlines (thinking text first, then the
    attention paragraph), the same shape ``draft_frame`` gives the plain
    draft, so both can be compared as one text.
    """
    if 'rich_message' in body:
        return '\n'.join(str(block.get('text') or '') for block in body['rich_message'].get('blocks') or ())
    return str(body.get('text') or '')


# --- attention while waiting (ATTN-WAIT-01 / #839) ------------------------------
#
# Owner direction 2026-09-28: the waiting draft is a natural breakpoint, so
# it may remind the owner of ONE thing AgentOS already prepared for them.
# Selection is deterministic from existing state (no model call): a fresh
# prepared answer the owner has not received, then an accepted reminder due
# soon, then an ask still waiting for the owner (a proposed preparation, a
# memory ask).  The draft is ephemeral, so the item's durable surface is
# unchanged; nothing is decided, accepted or delivered here.

#: Selection order: lower is shown first.
ATTENTION_PREPARED = 'prepared'
ATTENTION_REMINDER = 'reminder'
ATTENTION_ASK = 'ask'
ATTENTION_RANK = {ATTENTION_PREPARED: 0, ATTENTION_REMINDER: 1, ATTENTION_ASK: 2}
#: A reminder is "soon" within this horizon.
ATTENTION_REMINDER_HORIZON = 12 * 3600
#: The same item is not surfaced again within this cooldown.
ATTENTION_COOLDOWN = 6 * 3600
#: #888: an open memory ask is surfaced only while its conversation is live -
#: sent within this window (as #876 bounds the ask itself).  Shorter than the
#: cooldown, so it is surfaced at most once; afterwards it waits in 내 기록.
ATTENTION_MEMORY_ASK_FRESH = 3600
#: The natural lead-in of the one line.
ATTENTION_PREFIX = '참, '
ATTENTION_LINE_CHARS = 160
#: The recorded tool/host action of one surfacing (the information-use audit reads it).
ATTENTION_ACTION = 'attention_surface'
ATTENTION_TOOL = 'presence'
#: How each kind of item is phrased; ``text`` is the item's own (redacted) words.
ATTENTION_PHRASES = {ATTENTION_PREPARED: '준비해 둔 답이 있어요: {text}',
                     ATTENTION_REMINDER: '{text} 알림 있어요.',
                     ATTENTION_ASK: '아직 답을 기다리는 게 있어요: {text}'}


def attention_line(kind, text):
    """The one "참, …" line for an item of ``kind`` whose own words are ``text``, or None."""
    text = ' '.join(str(text or '').split())
    if not text or kind not in ATTENTION_PHRASES:
        return None
    line = ATTENTION_PREFIX + ATTENTION_PHRASES[kind].format(text=text)
    if len(line) > ATTENTION_LINE_CHARS:
        line = line[:ATTENTION_LINE_CHARS - 1].rstrip() + '…'
    return line


def pick_attention(items, now, surfaced=None, cooldown=ATTENTION_COOLDOWN):
    """The one item to surface, or None: the best-ranked item not surfaced within ``cooldown``.

    ``items`` are ``{'ref', 'kind', 'text', 'at'}`` dicts (``at``: the
    item's own time, used as the tiebreak, earliest first).  ``surfaced``
    maps an item ref to the time it was last surfaced.  Pure and
    deterministic; the caller already excluded the current Work's own items.
    """
    surfaced = surfaced if isinstance(surfaced, dict) else {}
    ranked = sorted((item for item in items or () if isinstance(item, dict) and item.get('ref')
                     and item.get('kind') in ATTENTION_RANK),
                    key=lambda item: (ATTENTION_RANK[item['kind']], item.get('at') or 0, str(item['ref'])))
    for item in ranked:
        last = surfaced.get(item['ref'])
        if isinstance(last, (int, float)) and now - last < cooldown:
            continue
        line = attention_line(item['kind'], item.get('text'))
        if line:
            return {**item, 'line': line}
    return None

# --- live step lines (SEC-PROGRESS-01 / #718) ----------------------------------
#
# While a tool call of the running Work is observed in flight (its ``running``
# tool event, or a CLI's own streamed search item), the draft names that step
# before the dots.  The wording is the model's own ``status``
# (validated, bounded and redacted in ``agent_runtime.progress_step``); without
# one, a generic line keyed only on the tool kind plus the host or query taken
# from the observed arguments.  Nothing here names a site, provider or task
# (Constitution C16), and no line is shown for a call that was not observed.

#: Any other tool kind.
DEFAULT_STEP_TEXT = '도구 실행 중'
#: #710: the orchestrator's planned-attempt event (``orchestrator.EVENT_TOOL`` /
#: ``PLANNED``).  #740: a re-delegated attempt is announced with this line
#: only; the plan's worker, model and reason stay in the Work's Evidence
#: (작업 현황), never in the conversation.  The first attempt announces
#: nothing: the draft shows the dots alone until its first step.
ORCHESTRATION_TOOL = EVENT_TOOL
ORCHESTRATION_PLANNED = PLANNED
RETRY_STEP_TEXT = '다른 방법으로 다시 해보는 중'
#: Host action -> (line with the observed target, line without one).  The
#: target placeholder is ``{host}`` or ``{query}``.
FALLBACK_STEP_LINES = {
    'web_search': ('웹 검색 중: {query}', '웹 검색 중'),
    'bounded_public_research': ('웹 검색 중: {query}', '웹 검색 중'),
    'public_page_read': ('{host} 페이지 여는 중', '페이지 여는 중'),
    'browser_open': ('{host} 페이지 여는 중', '페이지 여는 중'),
    'browser_read': ('{host} 페이지 읽는 중', '페이지 읽는 중'),
    'browser_find': ('{host} 페이지에서 찾는 중', '페이지에서 찾는 중'),
    'browser_click': ('{host}에서 선택하는 중', '페이지에서 선택하는 중'),
    'browser_type': ('{host}에서 입력 중', '페이지에서 입력 중'),
    'weather': (None, '날씨 확인 중'),
    'calendar_query': (None, '일정 확인 중'),
    'calendar_draft_create': (None, '일정 변경안 만드는 중'),
    'calendar_draft_update': (None, '일정 변경안 만드는 중'),
    'calendar_draft_cancel': (None, '일정 변경안 만드는 중'),
    'list_roots': (None, '연결된 폴더 확인 중'),
    'find_files': (None, '파일 찾는 중'),
    'read_file': (None, '파일 읽는 중'),
    'list_notes': (None, '메모 확인 중'),
    'save_note': (None, '메모 저장 중'),
    'list_memory': (None, '기억 확인 중'),
    'save_memory': (None, '기억 저장 중'),
    'list_agents': (None, '에이전트 목록 확인 중'),
    'delegate_agent': (None, '전문 에이전트에게 맡기는 중'),
    'propose_current_state': (None, '현재 상황 기록 중'),
    'schedule_preparation': (None, '예약 만드는 중'),
    'ask_location': (None, '위치 요청 중'),
    'settings_read': (None, '설정 확인 중'),
    'information_use': (None, '사용한 정보 확인 중'),
    'settings_change': (None, '설정 변경 초안 만드는 중'),
}


#: #881: the masking marks redaction leaves in a text (``browser_session.REDACTED``,
#: ``[가림: N자]``, ``[경로 가림]``, ``[redacted]``, ``[AgentOS data]``, ``[turn folder]``).
#: They are internal: a step line carrying one is never shown; the next plainer
#: line for the step is.
MASK_MARK = re.compile(r'\[(?:가림(?::[^\]]*)?|경로 가림|redacted|AgentOS data|turn folder)\]', re.IGNORECASE)


def masked(text):
    """Whether ``text`` carries a masking mark (#881)."""
    return isinstance(text, str) and MASK_MARK.search(text) is not None


def step_line(step, last_host=None, clean=None):
    """The draft line for one observed running step, or None for an approval step.

    ``step`` is the recorded ``progress_step`` dict.  The model's ``status``
    wins; otherwise the generic line for its tool kind with the observed
    host (the call's own, else ``last_host`` - the page an earlier observed
    call of this Work opened) or query.  ``clean`` is the display-time
    redaction.  #881: a line that carries a masking mark after it (or that it
    could not redact) gives way to the next plainer one - status, then the
    line with its target, then the bare line - so a mark never reaches the
    owner's screen; if even that is masked, NO_STEP_LINE (the dots).
    """
    if not isinstance(step, dict) or step.get('approval'):
        return None
    with_target, bare = FALLBACK_STEP_LINES.get(step.get('action'), (None, DEFAULT_STEP_TEXT))
    host = step.get('host') or last_host
    values = {'host': host if isinstance(host, str) else '',
              'query': step.get('query') if isinstance(step.get('query'), str) else ''}
    targeted = None
    if with_target:
        needed = 'host' if '{host}' in with_target else 'query'
        if values[needed]:
            targeted = with_target.format(**values)
    lines = [step.get('announce'), step.get('status'), targeted, bare]
    for line in lines:
        if not isinstance(line, str) or not line.strip():
            continue
        try:
            shown = ' '.join(str(clean(line.strip()) if clean is not None else line.strip()).split())
        except Exception:
            continue  # never show a line that could not be redacted
        if shown and not masked(shown):
            return shown
    return NO_STEP_LINE


def draft_step(events, live=None, clean=None):
    """``(text, approval)`` for the draft of one running Work, from observed events only.

    ``events`` are the Work's tool events in order (``QuickStore.task_events``
    shape).  The step in flight is the latest ``running`` event carrying a
    ``step`` that no later terminal event of the same tool and call has
    closed.  ``live`` is the CLI's own streamed step, ``{'at', 'running',
    'id', 'step'}``, or None; it counts only when not older than that event.
    ``approval`` is true while the step in flight is a payment step: then
    the only surface is the existing approval prompt and ``text`` is None.
    With no step in flight ``text`` is NO_STEP_LINE (the draft shows dots).
    """
    text, approval, _identity = draft_step_details(events, live, clean)
    return text, approval


def draft_step_details(events, live=None, clean=None):
    """Return ``(text, approval, identity)`` for the current observed step.

    ``identity`` is present only for a real running tool/CLI step and remains
    stable across wait polls. Presentation can therefore react once per
    observed transition instead of once per refresh.
    """
    current = None          # (created, tool, call_id, step, host, identity)
    last_host = None
    for event in events or ():
        trace = event.get('trace') if isinstance(event.get('trace'), dict) else {}
        step = trace.get('step')
        if event.get('tool') == ORCHESTRATION_TOOL:
            # #710/#718/#740: a re-delegated attempt announces itself until its
            # first observed step, without the plan's reasoning.
            attempt = trace.get('attempt')
            if event.get('status') == ORCHESTRATION_PLANNED and isinstance(attempt, int):
                # #753: attempt 1 closes any earlier step's line (for example a preflight).
                current = ((event.get('created') or 0, ORCHESTRATION_TOOL, None, {'announce': RETRY_STEP_TEXT}, last_host, None)
                           if attempt > 1 else None)
            continue
        if event.get('status') == 'running' and isinstance(step, dict):
            created = event.get('created') or 0
            tool = event.get('tool')
            call_id = trace.get('call_id')
            identity = (event.get('id'), created, tool, call_id)
            current = (created, tool, call_id, step, step.get('host') or last_host, identity)
            if step.get('host'):
                last_host = step['host']
        elif (event.get('status') != 'running' and current is not None and event.get('tool') == current[1]
              and trace.get('call_id') == current[2]):
            current = None
    if isinstance(live, dict) and isinstance(live.get('step'), dict):
        if live.get('at', 0) >= (current[0] if current else float('-inf')):
            identity = ('live', live.get('id')) if live.get('id') is not None else ('live', live.get('at'))
            current = (live.get('at', 0), None, None, live['step'], last_host, identity) if live.get('running') else None
    if current is not None:
        if current[3].get('approval'):
            return None, True, current[5]
        return step_line(current[3], current[4], clean), False, current[5]
    return NO_STEP_LINE, False, None

CONTROL_RETRY = 'retry'
CONTROL_DETAILS = 'details'

# --- reactions (PRESENCE-TG-02 / #835) -------------------------------------------

#: ``ReactionTypeEmoji.emoji`` values documented by Bot API 10.3, verbatim.
#: Bots may set only these (or a custom emoji already on the message, which
#: this module never uses); paid reactions are unavailable to bots.
TELEGRAM_REACTION_EMOJI = frozenset((
    '❤', '👍', '👎', '🔥', '🥰', '👏', '😁', '🤔', '🤯', '😱', '🤬', '😢', '🎉', '🤩', '🤮', '💩', '🙏', '👌',
    '🕊', '🤡', '🥱', '🥴', '😍', '🐳', '❤‍🔥', '🌚', '🌭', '💯', '🤣', '⚡', '🍌', '🏆', '💔', '🤨', '😐',
    '🍓', '🍾', '💋', '🖕', '😈', '😴', '😭', '🤓', '👻', '👨‍💻', '👀', '🎃', '🙈', '😇', '😨', '🤝', '✍',
    '🤗', '🫡', '🎅', '🎄', '☃', '💅', '🤪', '🗿', '🆒', '💘', '🙉', '🦄', '😘', '💊', '🙊', '😎', '👾',
    '🤷‍♂', '🤷', '🤷‍♀', '😡',
))

#: On the owner's message when the Work starts: "looking at it".  Not "done".
RECEIVED_REACTION = '👀'
#: ``succeeded``: done.
DONE_REACTION = '👌'
#: ``succeeded`` and this Work observably saved a note or a Memory item.
WROTE_REACTION = '✍'
#: Remove the bot's reaction (an empty ``setMessageReaction`` list).
CLEAR_REACTION = ''
#: Every emoji this module sets.  Each must be in TELEGRAM_REACTION_EMOJI
#: (pinned by a test).
PRESENCE_REACTIONS = (RECEIVED_REACTION, DONE_REACTION, WROTE_REACTION)

# --- Judgment-AI-chosen reactions (PRESENCE-TG-03 / #858) -------------------------
#
# Owner direction 2026-09-29: the reaction should vary with the message, and
# the owner's Judgment AI picks it (model-first; no cue list ever maps words
# to an emoji here).  AgentOS keeps only the policy: which emoji may be used
# at all (documented reactions, curated so that nothing rude, mocking or
# dismissive can land on the owner's own message), and *when* a closing
# emoji is allowed (``outcome_reaction``).  Both sets are subsets of
# TELEGRAM_REACTION_EMOJI (pinned by a test).

#: Offered when the Work starts, over the owner's message: acknowledgements
#: that fit a question, a request, news, a plan or a feeling.
RECEIVED_CANDIDATES = (
    '👀', '🤔', '👍', '🫡', '🤗', '😁', '🙏', '🔥', '🤩', '😎', '🤓', '👨\u200d💻', '❤', '🥰', '🎉', '😢',
    '😱', '🤯', '💯', '⚡', '😴', '🤝', '😇', '😍', '☃', '🎄', '🎃', '🍓', '🍌', '🌚', '🕊', '🦄',
)
#: Offered after a succeeded, delivered answer, over the message and the
#: reply: a closing gesture.  The deterministic 👌 / ✍ stay in the set so the
#: AI may also simply confirm them.
CLOSING_CANDIDATES = (
    '👌', '✍', '👍', '🎉', '🏆', '💯', '🔥', '🤝', '🫡', '🙏', '😎', '🤓', '🍾', '⚡', '🆒', '❤', '🥰',
    '😁', '🤗', '😇', '🕊', '🤩', '☃', '🎄',
)
#: Offered for an observed running step. The Judgment AI selects from these;
#: no action/tool/category is mapped to a fixed reaction in AgentOS.
PROGRESS_CANDIDATES = (
    '👀', '🤔', '👍', '🫡', '🤗', '🔥', '🤩', '🤓', '👨\u200d💻', '⚡', '🤝', '🙏', '💯', '🆒',
)
#: The deterministic closing emoji, the only ones that let the AI be asked.
DONE_REACTIONS = (DONE_REACTION, WROTE_REACTION)

#: Decided outcomes that end a Work.  Anything else (queued, running, parked
#: for a connection, Drive or context) is not decided yet and keeps 👀.
TERMINAL_OUTCOMES = frozenset({'succeeded', 'partial', 'failed', 'unknown', 'cancelled', 'interrupted'})
#: Tool kinds whose ``succeeded`` event with ``evidence.saved`` true is an
#: owner record actually written (a pending MemoryCandidate is not ``saved``).
#: The same kinds as ``AgentService.RETAINED_TOOLS``.
RECORD_WRITE_TOOLS = frozenset({'save_note', 'save_memory'})


def wrote_record(events):
    """Did this Work observably save a note or Memory item?  From tool events only."""
    for event in events or ():
        trace = event.get('trace') if isinstance(event.get('trace'), dict) else {}
        evidence = trace.get('evidence') if isinstance(trace.get('evidence'), dict) else {}
        tool = trace.get('host_action') or event.get('tool')
        if tool in RECORD_WRITE_TOOLS and event.get('status') == 'succeeded' and evidence.get('saved') is True:
            return True
    return False


#: Typed flags a tool result carries while its effect waits for the owner's
#: decision (a calendar draft, a settings draft, a proposed preparation),
#: unless ``applied`` is true.  The same fields ``agent_runtime.event_trail``
#: and ``withheld_effect`` read.
OWNER_DECISION_FLAGS = ('requires_owner_approval', 'requires_owner_confirmation', 'requires_owner_acceptance')


def awaits_owner(events):
    """Does an observed tool event of this Work still wait for the owner's approval?"""
    for event in events or ():
        trace = event.get('trace') if isinstance(event.get('trace'), dict) else {}
        evidence = trace.get('evidence') if isinstance(trace.get('evidence'), dict) else {}
        for record in (trace, evidence):
            if record.get('state') == STATE_AWAITING_APPROVAL:
                return True
            if record.get('applied') is not True and any(record.get(flag) for flag in OWNER_DECISION_FLAGS):
                return True
    return False


def outcome_reaction(outcome, events=(), *, delivered=True, blocked=False, awaiting_owner=False):
    """The reaction that replaces 👀 once the answer was sent, or None to leave it.

    Deterministic from the decided ``outcome`` (the Work status) and the
    Work's observed tool ``events`` (``QuickStore.task_events`` shape):

    * not a terminal outcome -> None: the Work is parked and will resume, so
      👀 stays;
    * ``succeeded``, answer ``delivered``, not a ``blocked`` projection and
      nothing awaiting the owner -> WROTE_REACTION when a note or Memory
      write was observed, else DONE_REACTION;
    * every other terminal case (``partial``, ``failed``, ``unknown``,
      ``cancelled``, ``interrupted``, a blocked reply, an answer whose
      delivery is uncertain, or a succeeded Work whose effect or proposal
      still waits for the owner's approval - ``awaiting_owner`` or
      ``awaits_owner(events)``) -> CLEAR_REACTION.  No emoji at all rather
      than a neutral one: the reply states the truth, and any gesture there
      could be read as success (a 👌 under a calendar preview would read as
      "scheduled").
    """
    if outcome not in TERMINAL_OUTCOMES:
        return None
    if outcome != 'succeeded' or blocked or not delivered or awaiting_owner or awaits_owner(events):
        return CLEAR_REACTION
    return WROTE_REACTION if wrote_record(events) else DONE_REACTION


# --- timing -------------------------------------------------------------------

@dataclass(frozen=True)
class PresenceTiming:
    """Configurable wait-surface thresholds, in seconds since the request.

    These choose *which* surface to show while Work is really running; they
    never delay a ready answer.  ``chat_action_refresh`` stays under the
    documented 5-second typing lifetime, and ``typing…`` is refreshed at that
    cadence for as long as the Work runs, a draft shown or not (#835).
    ``dots_refresh`` stays far under the documented 30-second draft preview
    lifetime.
    """

    chat_action_after: float = 1.0
    draft_after: float = 5.0
    chat_action_refresh: float = 4.0
    #: #835: one draft edit per this many seconds, each advancing the dots
    #: (DOTS_FRAMES) and showing the latest observed step line (#718), never
    #: a queued old one.  With ``typing…`` every 4 s this stays under
    #: Telegram's guidance of about one message per second in one chat.
    dots_refresh: float = 1.5

    def wait_surface(self, elapsed, *, durable_surface=False, draft_available=True):
        """The one wait surface for Work that has been waiting ``elapsed`` seconds.

        ``durable_surface`` is true when a task card already represents this
        Work; then a draft would be a second progress surface, so only
        ``typing…`` is used.
        """
        if elapsed < self.chat_action_after:
            return WAIT_NONE
        if elapsed >= self.draft_after and draft_available and not durable_surface:
            return WAIT_DRAFT
        return WAIT_CHAT_ACTION


def draft_id_for(work_id):
    """A stable, non-zero 31-bit draft id for one Work.

    Deterministic, so a ``stopped_message_generation`` update can be mapped
    back to its Work without storing anything.
    """
    digest = hashlib.sha256(str(work_id).encode()).digest()
    return int.from_bytes(digest[:4], 'big') % 0x7FFFFFFE + 1


@dataclass
class WaitState:
    """In-memory presentation state for one running Work (never persisted)."""

    reacted: bool = False
    #: #858: the emoji currently on the owner's message (None: none set by
    #: this run), and whether the Judgment AI was already asked for it.
    reaction: str = None
    reaction_asked: bool = False
    #: Identity of the last observed progress step considered for a reaction.
    progress_reaction_step: object = None
    chat_action_at: float = None
    draft_at: float = None
    draft_failed: bool = False
    #: #858: the rich (thinking-block) draft was refused for this Work, so
    #: the plain dots draft is used instead; ``draft_failed`` then covers that.
    rich_draft_failed: bool = False
    stopped: bool = False
    shown: set = field(default_factory=set)
    #: #718/#835: the text the draft last showed (step line and dots), the
    #: next DOTS_FRAMES index, and the (raw, displayed) pair of the last
    #: display-time redaction of a step line.
    draft_text: str = None
    dots_frame: int = 0
    scrubbed: tuple = None
    #: #839: the one attention item chosen for this Work's draft (None: not
    #: chosen yet; {}: nothing to surface), and whether it was shown and recorded.
    attention: dict = None
    attention_shown: bool = False


# --- durable reply controls -----------------------------------------------------

RETRY_LABEL = '다시 시도'
RETRY_CONSUMED_LABEL = '다시 시도 요청함'
DETAILS_LABEL = '상세'


def reply_controls_markup(work_id, controls, consumed=()):
    """Inline keyboard for the durable reply; consumed controls are disabled."""
    row = []
    for control in controls:
        if control == CONTROL_RETRY:
            if CONTROL_RETRY in consumed:
                row.append({'text': RETRY_CONSUMED_LABEL, 'disabled': {}})
            else:
                row.append({'text': RETRY_LABEL, 'callback_data': f'p7r:{work_id}'})
        elif control == CONTROL_DETAILS:
            row.append({'text': DETAILS_LABEL, 'callback_data': f'p7d:{work_id}'})
    return {'inline_keyboard': [row]} if row else None


def without_consumed(markup):
    """The same keyboard with disabled buttons dropped (fallback edit)."""
    rows = []
    for row in (markup or {}).get('inline_keyboard', []):
        kept = [button for button in row if 'disabled' not in button]
        if kept:
            rows.append(kept)
    return {'inline_keyboard': rows}


# --- formatting -------------------------------------------------------------------

_FENCE = re.compile(r'```[^\n`]*\n(.*?)```', re.S)
_HEADING = re.compile(r'^[ \t]{0,3}#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$')
_BULLET = re.compile(r'^([ \t]*)[*+-][ \t]+(.*)$')
_CODE = re.compile(r'`([^`\n]+)`')
_LINK = re.compile(r'\[([^\]\n]+)\]\((https?://[^\s()"<>]+)\)')
#: ``**`` is a delimiter only where it cannot be arithmetic or an identifier:
#: never next to an ASCII letter/digit/``*`` outside the span.  Korean
#: particles directly after a closing ``**`` ("**갈비탕**을") stay allowed.
#: ``__`` is never a delimiter: ``__init__`` and snake_case are content.
_BOLD = re.compile(r'(?<![A-Za-z0-9*])\*\*(?=[^\s*])(.+?)(?<=[^\s*])\*\*(?![A-Za-z0-9*])')
_ITALIC = re.compile(r'(?<![A-Za-z0-9*])\*(?=[^\s*])([^*\n]+?)(?<=[^\s*])\*(?![A-Za-z0-9*])')


def _escape(text):
    return html.escape(text, quote=False)


#: Telegram nesting rule (Bot API "Formatting options"): bold and italic may
#: contain links, but no entity may contain ``code``/``pre`` or sit inside one.
#: Code and link spans are therefore cut out first and replaced by
#: placeholders, so emphasis delimiters around them still pair up (#581 live
#: discrepancy: ``**[title](url)**`` and ``**`cmd`**`` used to leak ``**``).
_SPAN_OPEN, _SPAN_CLOSE = '\ue000', '\ue001'
_SPAN_REF = re.compile(_SPAN_OPEN + r'(\d+)' + _SPAN_CLOSE)
_EMPTY_EMPHASIS = re.compile(r'<(b|i)></\1>')


def _leaf(text, spans=(), stack=()):
    """Escape a text leaf and put back its code/link spans.

    ``stack`` is the emphasis open around this leaf.  A code span closes it
    and reopens it afterwards, because Telegram rejects emphasis containing
    code.  An unmatched marker is left as written: a literal ``**`` is
    better than silently changing what the answer says.
    """
    out, pos = [], 0
    for match in _SPAN_REF.finditer(text):
        out.append(_escape(text[pos:match.start()]))
        kind, value = spans[int(match.group(1))]
        if kind == 'code':
            out.append(''.join(f'</{tag}>' for tag in reversed(stack)) + '<code>' + _escape(value) + '</code>'
                       + ''.join(f'<{tag}>' for tag in stack))
        else:
            label, url = value
            # A link may not contain a code entity, so code inside its label
            # is restored as plain text.
            label = _SPAN_REF.sub(lambda ref: spans[int(ref.group(1))][1], label)
            out.append('<a href="' + html.escape(url, quote=True) + '">' + _escape(label) + '</a>')
        pos = match.end()
    out.append(_escape(text[pos:]))
    return ''.join(out)


def _italic(text, spans, stack):
    out, pos = [], 0
    for match in _ITALIC.finditer(text):
        out.append(_leaf(text[pos:match.start()], spans, stack))
        if 'i' in stack:
            out.append(_leaf(match.group(1), spans, stack))
        else:
            out.append('<i>' + _leaf(match.group(1), spans, stack + ('i',)) + '</i>')
        pos = match.end()
    out.append(_leaf(text[pos:], spans, stack))
    return ''.join(out)


def _bold(text, spans, stack):
    out, pos = [], 0
    for match in _BOLD.finditer(text):
        out.append(_italic(text[pos:match.start()], spans, stack))
        # Telegram entities of one type are not nested: inside an already
        # bold span (a heading) the delimiters are consumed without a tag.
        if 'b' in stack:
            out.append(_italic(match.group(1), spans, stack))
        else:
            out.append('<b>' + _italic(match.group(1), spans, stack + ('b',)) + '</b>')
        pos = match.end()
    out.append(_italic(text[pos:], spans, stack))
    return ''.join(out)


def _spans(text, in_bold=False):
    """Inline code, links and emphasis for one line, as valid Telegram HTML."""
    spans = []

    def cut(kind):
        def replace(match):
            if kind == 'link' and _SPAN_REF.search(match.group(2)):
                return match.group(0)  # code inside a URL: not a link
            spans.append((kind, match.group(1) if kind == 'code' else (match.group(1), match.group(2))))
            return f'{_SPAN_OPEN}{len(spans) - 1}{_SPAN_CLOSE}'
        return replace

    # Strip the placeholder characters from the source so a model can never
    # forge a span reference; they are private-use code points with no text.
    text = text.replace(_SPAN_OPEN, '').replace(_SPAN_CLOSE, '')
    text = _CODE.sub(cut('code'), text)
    text = _LINK.sub(cut('link'), text)
    return _bold(text, spans, ('b',) if in_bold else ())


#: #848: a Markdown table row and its header/body separator (``|---|:--:|---:|``).
#: Telegram has no tables; each data row becomes one line of cells joined
#: with ``TABLE_CELL_JOIN`` and the header row is kept as one bold line.
_TABLE_ROW = re.compile(r'^[ \t]*\|.*\|[ \t]*$')
_TABLE_SEPARATOR = re.compile(r'^[ \t]*\|(?:[ \t]*:?-+:?[ \t]*\|)+[ \t]*$')
#: The tokens that matter in a row: a run of backslashes, or a pipe.  Only an
#: odd run right before a pipe escapes it (``\|`` is content, ``\\|`` is a
#: cell ending in a backslash then a delimiter); a fixed-width lookbehind
#: cannot count the run (#852).  Each run is matched once, so a long run
#: (a pathological model response) scans in linear time (#872 review P2).
_TABLE_TOKEN = re.compile(r'\\+|\|')
TABLE_CELL_JOIN = ' · '


def _table_cells(line):
    """The cells of one row: the text between unescaped pipes, an escaped pipe unescaped."""
    line = line.strip()
    cells, start, run_len, run_end = [], 0, 0, -1
    for match in _TABLE_TOKEN.finditer(line):
        if match.group()[0] == '\\':
            run_len, run_end = len(match.group()), match.end()
            continue
        if run_end == match.start() and run_len % 2:
            continue  # an odd run of backslashes: the pipe is cell content
        cells.append(line[start:match.start()])
        start = match.end()
    cells.append(line[start:])
    return [cell.strip().replace('\\|', '|') for cell in cells][1:-1]


def _table_lines(rows):
    """One line per row: the header in bold, then each data row's cells joined."""
    rendered = []
    header = _table_cells(rows[0])
    if any(header):
        rendered.append('<b>' + _spans(TABLE_CELL_JOIN.join(cell for cell in header if cell), in_bold=True) + '</b>')
    for row in rows[2:]:
        cells = [cell for cell in _table_cells(row) if cell]
        if cells:
            rendered.append(_spans(TABLE_CELL_JOIN.join(cells)))
    return rendered


def _lines(text):
    rendered = []
    lines = text.split('\n')
    index = 0
    while index < len(lines):
        line = lines[index]
        if _TABLE_ROW.match(line) and index + 1 < len(lines) and _TABLE_SEPARATOR.match(lines[index + 1]):
            end = index + 2
            while end < len(lines) and _TABLE_ROW.match(lines[end]):
                end += 1
            rendered.extend(_table_lines(lines[index:end]))
            index = end
            continue
        index += 1
        heading = _HEADING.match(line)
        if heading:
            rendered.append('<b>' + _spans(heading.group(1), in_bold=True) + '</b>')
            continue
        bullet = _BULLET.match(line)
        if bullet:
            line = bullet.group(1) + '• ' + bullet.group(2)
        rendered.append(_spans(line))
    return '\n'.join(rendered)


def render_telegram_html(text):
    """Render reply text for Telegram ``parse_mode='HTML'``.

    Handles the Markdown a model commonly emits - ``**bold**``, ``*italic*``, inline code,
    fenced code, headings, bullets, http(s) links and tables (one line per
    row, #848).  Every text leaf is
    HTML-escaped and every tag is emitted as a balanced, properly nested
    pair, so the result is always valid Telegram HTML: a send rejected for
    bad entities cannot be told apart from a lost response and would leave
    delivery ``unknown``, so validity is a correctness property here, not a
    cosmetic one.
    """
    text = str(text or '')
    out, pos = [], 0
    for match in _FENCE.finditer(text):
        out.append(_lines(text[pos:match.start()]))
        out.append('<pre>' + _escape(match.group(1).rstrip('\n')) + '</pre>')
        pos = match.end()
    out.append(_lines(text[pos:]))
    rendered = ''.join(out)
    # Closing emphasis around a code span can leave empty pairs; drop them.
    while True:
        cleaned = _EMPTY_EMPHASIS.sub('', rendered)
        if cleaned == rendered:
            return rendered
        rendered = cleaned


# --- Telegram addressing ----------------------------------------------------------

class TelegramTurnAddressing:
    """Which Telegram messages belong to one Work - transport addressing only.

    ``source_message_id`` is the owner's message (reaction target and reply
    anchor); ``reply_message_id`` is the durable reply carrying controls, so
    a control tap is honoured only from that exact message.  This is not a
    conversation store: no text, no outcome and no Evidence is kept here;
    Work state stays in ``jobs``.
    """

    def __init__(self, store):
        self.store = store
        with store.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS telegram_turns(job_id TEXT PRIMARY KEY, chat_id INTEGER NOT NULL, '
                       'source_message_id INTEGER, reply_message_id INTEGER, created REAL NOT NULL)')

    def record_source(self, job_id, chat_id, message_id, db=None):
        if not isinstance(message_id, int) or not isinstance(chat_id, int):
            return
        statement = ('INSERT INTO telegram_turns(job_id,chat_id,source_message_id,created) VALUES (?,?,?,?) '
                     'ON CONFLICT(job_id) DO NOTHING')
        if db is not None:
            db.execute(statement, (job_id, chat_id, message_id, time.time()))
            return
        with self.store.db() as conn:
            conn.execute(statement, (job_id, chat_id, message_id, time.time()))

    def record_reply(self, job_id, chat_id, message_id):
        if not isinstance(message_id, int):
            return
        with self.store.db() as db:
            db.execute('INSERT INTO telegram_turns(job_id,chat_id,reply_message_id,created) VALUES (?,?,?,?) '
                       'ON CONFLICT(job_id) DO UPDATE SET reply_message_id=excluded.reply_message_id',
                       (job_id, chat_id, message_id, time.time()))

    def get(self, job_id):
        with self.store.db() as db:
            row = db.execute('SELECT * FROM telegram_turns WHERE job_id=?', (job_id,)).fetchone()
        return dict(row) if row else None

    def source(self, job_id):
        row = self.get(job_id)
        return row['source_message_id'] if row else None
