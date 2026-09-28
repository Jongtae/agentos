"""Multi-turn owner scenarios: format, validation and loading.

A scenario file is JSON: one scenario object or a list of them.  The bundled
set under ``evals/scenarios`` is synthetic and generalized.  Scenarios derived
from the owner's real conversations live only in the owner's local folders
(``paths.local_scenario_dirs``) and are never committed.

Scenario fields:

- ``id`` (unique slug), ``title``, ``split`` (``dev`` or ``heldout``);
- ``turns``: owner turns, each ``{"say": str, "note": str?}``.  ``note`` is a
  simulated clock or current-context note.  It is shown to the judge; it is
  sent to AgentOS only when the turn sets ``"note_in_message": true``, because
  the sandbox runs on the real clock and a hidden note must not leak into the
  owner's words;
- ``rubric``: the rubric dimensions this scenario is judged on;
- ``expect`` (optional deterministic expectations): ``memory_any`` (a list of
  groups; each group is a list of alternative substrings and one of them must
  appear in a new Memory row or MemoryCandidate), ``preparation`` (a new
  preparation/reminder must exist), ``no_memory_of_request`` (no new Memory
  row or MemoryCandidate may hold an owner turn's sentence as its content: a
  request is not a fact about the owner, #846), ``allow_status`` (extra terminal statuses
  that count as not failed, e.g. ``awaiting_context``);
- ``good_secretary``: what a good secretary would do, for the judge;
- ``tags``: free labels for grouping.
"""
import json
import re
from pathlib import Path

from .paths import BUNDLED_SCENARIOS, local_scenario_dirs

#: The secretary rubric (docs/secretary-agency-contract.en.md, issue #821).
RUBRIC = {
    'owner_model': 'Uses what AgentOS knows about the owner (stated facts, preferences, places, earlier memory) '
                   'instead of asking again or answering generically.',
    'context_carry': 'Carries the conversation context: a follow-up is read against the earlier turns '
                     '(places, times, items already named).',
    'specific_sourced': 'Specific and sourced: concrete places, menus, prices, times or links, with where they '
                        'came from, rather than generic advice.',
    'honest_unverified': 'Honest about what is unverified: no invented facts, prices, bookings, saved state or '
                         'tool runs; says plainly what it could not check.',
    'follow_through': 'Follows through: sets or offers the reminder, records the memory, acknowledges a missed '
                      'timing, or corrects its own earlier advice when the owner adds new facts.',
    'no_wrong_narrowing': 'Does not wrongly narrow a new, unrelated request to the previous topic.',
}

SPLITS = ('dev', 'heldout')
_ID = re.compile(r'^[a-z0-9][a-z0-9-]{2,79}$')
_EXPECT_KEYS = {'memory_any', 'preparation', 'no_memory_of_request', 'allow_status'}
_TURN_KEYS = {'say', 'note', 'note_in_message'}
_KEYS = {'id', 'title', 'split', 'turns', 'rubric', 'expect', 'good_secretary', 'tags'}


class ScenarioError(ValueError):
    """A scenario file that does not match the format."""


def validate(raw, origin='scenario'):
    """Return a normalized scenario dict or raise ``ScenarioError``."""
    if not isinstance(raw, dict):
        raise ScenarioError(f'{origin}: a scenario must be an object')
    unknown = set(raw) - _KEYS
    if unknown:
        raise ScenarioError(f'{origin}: unknown fields {sorted(unknown)}')
    ident = raw.get('id')
    if not isinstance(ident, str) or not _ID.match(ident):
        raise ScenarioError(f'{origin}: id must be a lowercase slug')
    where = f'{origin}:{ident}'
    split = raw.get('split', 'dev')
    if split not in SPLITS:
        raise ScenarioError(f'{where}: split must be one of {SPLITS}')
    turns = raw.get('turns')
    if not isinstance(turns, list) or not 1 <= len(turns) <= 12:
        raise ScenarioError(f'{where}: turns must be a list of 1-12 owner turns')
    normalized_turns = []
    for index, turn in enumerate(turns):
        if isinstance(turn, str):
            turn = {'say': turn}
        if not isinstance(turn, dict) or set(turn) - _TURN_KEYS:
            raise ScenarioError(f'{where}: turn {index} must be a string or {{say, note?, note_in_message?}}')
        say = turn.get('say')
        if not isinstance(say, str) or not say.strip() or len(say) > 4000:
            raise ScenarioError(f'{where}: turn {index} needs 1-4000 characters of owner text')
        note = turn.get('note')
        if note is not None and (not isinstance(note, str) or len(note) > 1000):
            raise ScenarioError(f'{where}: turn {index} note must be text up to 1000 characters')
        normalized_turns.append({'say': say.strip(), 'note': (note or '').strip(),
                                 'note_in_message': turn.get('note_in_message') is True})
    rubric = raw.get('rubric', list(RUBRIC))
    if not isinstance(rubric, list) or not rubric or any(item not in RUBRIC for item in rubric):
        raise ScenarioError(f'{where}: rubric must name dimensions from {sorted(RUBRIC)}')
    expect = raw.get('expect', {})
    if not isinstance(expect, dict) or set(expect) - _EXPECT_KEYS:
        raise ScenarioError(f'{where}: expect may only hold {sorted(_EXPECT_KEYS)}')
    memory_any = expect.get('memory_any', [])
    if (not isinstance(memory_any, list) or any(not isinstance(group, list) or not group or
                                                any(not isinstance(item, str) or not item.strip() for item in group)
                                                for group in memory_any)):
        raise ScenarioError(f'{where}: expect.memory_any must be a list of non-empty lists of text')
    allow_status = expect.get('allow_status', [])
    if not isinstance(allow_status, list) or any(not isinstance(item, str) for item in allow_status):
        raise ScenarioError(f'{where}: expect.allow_status must be a list of status names')
    tags = raw.get('tags', [])
    if not isinstance(tags, list) or any(not isinstance(item, str) for item in tags):
        raise ScenarioError(f'{where}: tags must be a list of text')
    return {'id': ident, 'title': str(raw.get('title') or ident), 'split': split, 'turns': normalized_turns,
            'rubric': list(dict.fromkeys(rubric)),
            'expect': {'memory_any': [[item.strip() for item in group] for group in memory_any],
                       'preparation': expect.get('preparation') is True,
                       'no_memory_of_request': expect.get('no_memory_of_request') is True,
                       'allow_status': list(allow_status)},
            'good_secretary': str(raw.get('good_secretary') or ''), 'tags': list(tags)}


def load_file(path):
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ScenarioError(f'{path.name}: cannot read JSON ({exc})') from None
    items = data if isinstance(data, list) else [data]
    return [validate(item, path.name) for item in items]


def load(dirs=None, include_local=True, split=None, ids=None, environ=None):
    """Load scenarios from the bundled set and, by default, the owner-local folders.

    Every scenario records its ``source`` (``bundled`` or ``local``) so a
    report can keep owner-derived cases apart without printing their text.
    Duplicate ids fail loudly rather than shadowing each other.
    """
    sources = [(BUNDLED_SCENARIOS, 'bundled')] if dirs is None else [(Path(item), 'bundled') for item in dirs]
    if include_local:
        sources.extend((folder, 'local') for folder in local_scenario_dirs(environ))
    found = {}
    for folder, source in sources:
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob('*.json')):
            for scenario in load_file(path):
                if scenario['id'] in found:
                    raise ScenarioError(f'{path.name}: duplicate scenario id {scenario["id"]}')
                found[scenario['id']] = {**scenario, 'source': source}
    scenarios = list(found.values())
    if split:
        scenarios = [item for item in scenarios if item['split'] == split]
    if ids:
        wanted = set(ids)
        missing = wanted - {item['id'] for item in scenarios}
        if missing:
            raise ScenarioError(f'unknown scenario ids: {sorted(missing)}')
        scenarios = [item for item in scenarios if item['id'] in wanted]
    return scenarios


def owner_message(turn):
    """The text actually sent to AgentOS for one turn."""
    if turn.get('note_in_message') and turn.get('note'):
        return f"({turn['note']}) {turn['say']}"
    return turn['say']
