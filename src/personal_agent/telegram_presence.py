"""Native Telegram presence for the one paired conversation (PRESENCE-TG-01 / #581).

The kernel stays mechanical: Work -> Event -> tool -> Evidence -> outcome.
This module only decides *how an already-decided turn looks in Telegram*:

* a best-effort **reaction** on the owner's own message as a small "got it";
* a **wait surface** while Work runs - nothing, ``typing…``, or an ephemeral
  ``sendMessageDraft`` "Thinking…" placeholder with Telegram's Stop button;
* the **reply anchor** and bounded **controls** of the one durable reply;
* the **formatting** of that reply, so model Markdown never leaks as ``**``.

Nothing here is truth.  A reaction is presence, never Evidence that anything
succeeded; a failed reaction, chat action or draft is a presentation failure
that must not fail, duplicate or change Work.  Whether a turn succeeded, was
cancelled or has an unknown external effect is decided elsewhere
(``quickstart_service`` and the existing cancellation/effect state machine)
before anything here runs.

Two rules keep this from becoming a conversation rule engine:

* the semantic class comes from typed values AgentOS already has - the
  DecisionEngine-backed follow-up relation and the routed intent - never from
  reading the owner's words (no phrase or keyword catalogue here) and never
  from an extra model call made only to pick an emoji;
* the class maps deterministically to a reaction Telegram documents as
  available.  An unknown class, or a turn whose meaning is an effect or an
  ambiguity, gets **no** reaction rather than a guess.

Telegram Bot API baseline verified at implementation time (2026-09-25):
Bot API 10.3 (2026-08-24), https://core.telegram.org/bots/api -
``setMessageReaction``, ``sendChatAction``, ``sendMessageDraft`` (``draft_id``,
``can_stop``, ``keep_on_stop``), the ``stopped_message_generation`` update
(``MessageGenerationStopped``: ``chat``, ``draft_id``), ``ReplyParameters``,
``InlineKeyboardButton.disabled`` / ``DisabledButton`` and the HTML parse mode.
"""
import hashlib
import html
import re
import time
from dataclasses import dataclass, field

from .conversation_handoff import (FOLLOWUP_CANCEL, FOLLOWUP_CORRECTION, FOLLOWUP_REFERENCE, FOLLOWUP_RETRY,
                                   INTENT_CONVERSATION, INTENT_GREETING, INTENT_KNOWLEDGE, INTENT_MAIL_SEARCH,
                                   INTENT_NOTE_LIST, INTENT_RESEARCH, INTENT_WORKSPACE_SEARCH)

# --- typed presentation vocabulary -------------------------------------------

ACK_NONE = 'none'
ACK_REACTION = 'reaction'

SEMANTIC_ACKNOWLEDGE = 'acknowledge'
SEMANTIC_AGREE = 'agree'
SEMANTIC_CELEBRATE = 'celebrate'
SEMANTIC_APPRECIATE = 'appreciate'
SEMANTIC_EMPATHIZE = 'empathize'
SEMANTIC_TOPIC_POSITIVE = 'topic_positive'
REACTION_SEMANTICS = (SEMANTIC_ACKNOWLEDGE, SEMANTIC_AGREE, SEMANTIC_CELEBRATE, SEMANTIC_APPRECIATE,
                      SEMANTIC_EMPATHIZE, SEMANTIC_TOPIC_POSITIVE)

WAIT_NONE = 'none'
WAIT_CHAT_ACTION = 'chat_action'
WAIT_DRAFT = 'draft'
#: Declared so the vocabulary matches #581; not produced today.  AgentOS
#: routes return one finished answer rather than a token stream, so a rich
#: draft would carry nothing a plain "Thinking…" draft does not.
WAIT_RICH_DRAFT = 'rich_draft'

ANCHOR_NONE = 'none'
ANCHOR_OWNER_MESSAGE = 'owner_message'

CONTROL_RETRY = 'retry'
CONTROL_DETAILS = 'details'

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

#: Deterministic semantic class -> reaction.  Every value must be in
#: TELEGRAM_REACTION_EMOJI (pinned by a test).
REACTION_FOR_SEMANTICS = {
    SEMANTIC_ACKNOWLEDGE: '👍',
    SEMANTIC_AGREE: '👌',
    SEMANTIC_CELEBRATE: '🎉',
    SEMANTIC_APPRECIATE: '🙏',
    SEMANTIC_EMPATHIZE: '❤',
    SEMANTIC_TOPIC_POSITIVE: '😍',
}

#: Routed intents whose turn is an ordinary question/request.  A reaction on
#: those says only "received".  Everything else - an effect (note, calendar,
#: settings change), an ambiguity, an unsupported capability, a command -
#: gets no reaction, so a reaction can never be read as "done".
_ACKNOWLEDGED_INTENTS = frozenset({INTENT_CONVERSATION, INTENT_RESEARCH, INTENT_KNOWLEDGE, INTENT_WORKSPACE_SEARCH,
                                   INTENT_NOTE_LIST, INTENT_MAIL_SEARCH, INTENT_GREETING})

#: DecisionEngine follow-up relation -> semantic class.  A retry is only
#: acknowledged (it may fail again); a correction is "okay, changing it";
#: a cancel request gets none, because whether anything was cancelled is
#: decided by the cancellation state machine, not by a gesture.
_RELATION_SEMANTICS = {
    FOLLOWUP_RETRY: SEMANTIC_ACKNOWLEDGE,
    FOLLOWUP_REFERENCE: SEMANTIC_ACKNOWLEDGE,
    FOLLOWUP_CORRECTION: SEMANTIC_AGREE,
    FOLLOWUP_CANCEL: None,
}


@dataclass(frozen=True)
class PresenceGesture:
    """The typed presentation decision for one owner turn."""

    ack_mode: str = ACK_NONE
    reaction_semantics: str = None
    reply_anchor: str = ANCHOR_OWNER_MESSAGE
    controls: tuple = ()

    @property
    def reaction(self):
        """The Telegram reaction, or ``None`` - never a guessed emoji."""
        if self.ack_mode != ACK_REACTION:
            return None
        emoji = REACTION_FOR_SEMANTICS.get(self.reaction_semantics)
        return emoji if emoji in TELEGRAM_REACTION_EMOJI else None


def turn_gesture(*, relation=None, intent=None, executes=True, semantics=None):
    """Derive the acknowledgement for a turn from typed decisions only.

    ``relation`` is the DecisionEngine-judged follow-up relation and wins when
    present.  ``intent``/``executes`` are the routed IntentDecision.
    ``semantics`` lets a future DecisionEngine interpretation that already
    carries a semantic class (for example ``celebrate``) supply it; no call
    site invents one, and an unknown value yields no reaction.
    """
    if semantics is not None:
        cls = semantics if semantics in REACTION_SEMANTICS else None
    elif relation is not None:
        cls = _RELATION_SEMANTICS.get(relation)
    elif intent is not None and executes and intent in _ACKNOWLEDGED_INTENTS:
        cls = SEMANTIC_ACKNOWLEDGE
    else:
        cls = None
    if cls is None:
        return PresenceGesture()
    return PresenceGesture(ack_mode=ACK_REACTION, reaction_semantics=cls)


# --- timing -------------------------------------------------------------------

@dataclass(frozen=True)
class PresenceTiming:
    """Configurable wait-surface thresholds, in seconds since the request.

    These choose *which* surface to show while Work is really running; they
    never delay a ready answer.  ``chat_action_refresh`` stays under the
    documented 5-second typing lifetime and ``draft_refresh`` under the
    documented 30-second draft preview lifetime.
    """

    chat_action_after: float = 1.0
    draft_after: float = 5.0
    chat_action_refresh: float = 4.0
    draft_refresh: float = 20.0

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
    chat_action_at: float = None
    draft_at: float = None
    draft_failed: bool = False
    stopped: bool = False
    shown: set = field(default_factory=set)


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
_BOLD = re.compile(r'\*\*(?=\S)(.+?)(?<=\S)\*\*|__(?=\S)(.+?)(?<=\S)__')
_ITALIC = re.compile(r'(?<![\w*])\*(?=[^\s*])([^*\n]+?)(?<=[^\s*])\*(?![\w*])')


def _escape(text):
    return html.escape(text, quote=False)


def _leaf(text):
    # An unmatched ``**`` is a leaked control marker, not content.
    return _escape(text.replace('**', ''))


def _italic(text):
    out, pos = [], 0
    for match in _ITALIC.finditer(text):
        out.append(_leaf(text[pos:match.start()]))
        out.append('<i>' + _leaf(match.group(1)) + '</i>')
        pos = match.end()
    out.append(_leaf(text[pos:]))
    return ''.join(out)


def _bold(text):
    out, pos = [], 0
    for match in _BOLD.finditer(text):
        out.append(_italic(text[pos:match.start()]))
        out.append('<b>' + _italic(match.group(1) or match.group(2)) + '</b>')
        pos = match.end()
    out.append(_italic(text[pos:]))
    return ''.join(out)


def _links(text):
    out, pos = [], 0
    for match in _LINK.finditer(text):
        out.append(_bold(text[pos:match.start()]))
        out.append('<a href="' + html.escape(match.group(2), quote=True) + '">' + _leaf(match.group(1)) + '</a>')
        pos = match.end()
    out.append(_bold(text[pos:]))
    return ''.join(out)


def _spans(text):
    out, pos = [], 0
    for match in _CODE.finditer(text):
        out.append(_links(text[pos:match.start()]))
        out.append('<code>' + _escape(match.group(1)) + '</code>')
        pos = match.end()
    out.append(_links(text[pos:]))
    return ''.join(out)


def _lines(text):
    rendered = []
    for line in text.split('\n'):
        heading = _HEADING.match(line)
        if heading:
            rendered.append('<b>' + _spans(heading.group(1)) + '</b>')
            continue
        bullet = _BULLET.match(line)
        if bullet:
            line = bullet.group(1) + '• ' + bullet.group(2)
        rendered.append(_spans(line))
    return '\n'.join(rendered)


def render_telegram_html(text):
    """Render reply text for Telegram ``parse_mode='HTML'``.

    Handles the Markdown a model commonly emits - bold, italic, inline code,
    fenced code, headings, bullets and http(s) links.  Every text leaf is
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
    return ''.join(out)


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
