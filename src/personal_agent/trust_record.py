"""CONNECT-TRUST-01 (#1297): the owner's trust record for AI-side hands.

Connection and Delegation Contract §6/§7.  Which operation of a connected
service may run is owner state, not a repository list:

* **Per hand** (a claude.ai connector by its service name, or an owner MCP
  server by its name): the owner's decision per operation (``read``,
  ``mutate``, ``payment`` or ``refused``), whether the hand is
  money-capable, its rung on the trust ladder, and a short history of
  changes and corrections.
* **Raising is an owner decision.** Classes, money marking and a higher rung
  change only through a confirmed settings draft.  ``lower`` is the one
  automatic change (after a failure or an owner correction) and is recorded.
* **The seed list** (``connector_read_operations.json``) still answers for an
  operation the owner never decided, except on a money-capable hand, where
  only the owner's own ``read`` decision makes a call a read.
* **Names only.** No service, server or site is named here (C16); popularity,
  annotations and labels never move a rung (C9).
"""
from __future__ import annotations

import re
import time

KEY = 'trust_record'
CLASSES = ('read', 'mutate', 'payment', 'refused')
#: Contract §6: report → propose → act after per-action approval → act within a standing mandate.
RUNGS = ('report', 'propose', 'approve', 'mandate')
HAND = re.compile(r'^[^|\x00-\x1f]{1,64}$')
OPERATION = re.compile(r'^[A-Za-z0-9_.-]{1,60}$')
MAX_HANDS = 32
MAX_OPERATIONS = 64
MAX_HISTORY = 20


def valid_hand(name):
    return isinstance(name, str) and bool(HAND.match(name)) and name == name.strip()


def valid_operation(name):
    return isinstance(name, str) and bool(OPERATION.match(name))


def default_rung(money):
    """Contract §6 starting rung: report for a money-capable hand, act-after-approval otherwise."""
    return 'report' if money else 'approve'


def _hands(store):
    rows = store.config(KEY, {}) or {}
    hands = rows.get('hands') if isinstance(rows, dict) else None
    return hands if isinstance(hands, dict) else {}


def hand(store, name):
    """One hand's record, normalised; an unknown hand has the defaults and no decisions."""
    row = _hands(store).get(name) if valid_hand(name) else None
    row = row if isinstance(row, dict) else {}
    money = row.get('money') is True
    operations = row.get('operations') if isinstance(row.get('operations'), dict) else {}
    rung = row.get('rung') if row.get('rung') in RUNGS else default_rung(money)
    if money and rung == 'mandate':
        rung = 'approve'    # payment never reaches a standing mandate in the pilot
    return {'name': name, 'money': money, 'rung': rung,
            'operations': {op: cls for op, cls in operations.items() if valid_operation(op) and cls in CLASSES},
            'history': [item for item in (row.get('history') or []) if isinstance(item, dict)][-MAX_HISTORY:]}


def hands(store):
    """Every recorded hand, normalised."""
    return {name: hand(store, name) for name in sorted(_hands(store)) if valid_hand(name)}


def _write(store, name, change, update):
    if not valid_hand(name):
        raise ValueError('연결 이름 형식이 아닙니다.')
    rows = store.config(KEY, {}) or {}
    rows = dict(rows) if isinstance(rows, dict) else {}
    all_hands = dict(rows.get('hands') or {}) if isinstance(rows.get('hands'), dict) else {}
    if name not in all_hands and len(all_hands) >= MAX_HANDS:
        raise ValueError(f'기록할 수 있는 연결은 {MAX_HANDS}개까지입니다.')
    current = hand(store, name)
    record = {'money': current['money'], 'rung': current['rung'], 'operations': dict(current['operations']),
              'history': current['history']}
    update(record)
    if len(record['operations']) > MAX_OPERATIONS:
        raise ValueError(f'한 연결에 기록할 수 있는 동작은 {MAX_OPERATIONS}개까지입니다.')
    record['history'] = (record['history'] + [{'at': time.time(), **change}])[-MAX_HISTORY:]
    all_hands[name] = record
    rows['hands'] = all_hands
    store.put(KEY, rows)
    return hand(store, name)


def set_operation(store, name, operation, cls):
    """The owner's decision for one operation (through a confirmed draft)."""
    if not valid_operation(operation) or cls not in CLASSES:
        raise ValueError('동작 이름이나 분류를 확인하세요.')
    return _write(store, name, {'change': 'operation', 'operation': operation, 'class': cls},
                  lambda record: record['operations'].__setitem__(operation, cls))


def set_money(store, name, money):
    """Mark a hand money-capable (or not); marking resets the rung to that marking's starting rung."""
    def update(record):
        record['money'] = bool(money)
        if money:
            record['rung'] = default_rung(True)
    return _write(store, name, {'change': 'money', 'money': bool(money)}, update)


def set_rung(store, name, rung):
    """The owner's chosen rung (through a confirmed draft)."""
    if rung not in RUNGS:
        raise ValueError('신뢰 단계를 확인하세요.')
    if rung == 'mandate' and hand(store, name)['money']:
        raise ValueError('돈이 오가는 연결은 상시 위임 단계로 올릴 수 없습니다.')
    return _write(store, name, {'change': 'rung', 'rung': rung}, lambda record: record.__setitem__('rung', rung))


def lower(store, name, reason):
    """The one automatic change: one rung down after a failure or an owner correction (recorded)."""
    current = hand(store, name)
    index = RUNGS.index(current['rung'])
    if index == 0:
        return current
    return _write(store, name, {'change': 'lowered', 'rung': RUNGS[index - 1], 'reason': str(reason)[:120]},
                  lambda record: record.__setitem__('rung', RUNGS[index - 1]))


def is_read(store, name, operation, seed=frozenset()):
    """Whether a call to ``name``'s ``operation`` is a read AgentOS may run.

    The owner's own decision wins; without one, the seed list answers, except
    on a money-capable hand (contract §4: there only an owner-reviewed read is a read).
    """
    record = hand(store, name)
    decided = record['operations'].get(operation)
    if decided is not None:
        return decided == 'read'
    return not record['money'] and operation in (seed or ())


def readable(store, name, seed=frozenset()):
    """Whether ``name`` has at least one operation that may run as a read."""
    record = hand(store, name)
    if any(cls == 'read' for cls in record['operations'].values()):
        return True
    return not record['money'] and any(record['operations'].get(op) is None for op in (seed or ()))


def describe(record):
    """An owner-readable one-line summary (names and decisions only)."""
    labels = {'read': '읽기', 'mutate': '변경', 'payment': '결제', 'refused': '막음'}
    rungs = {'report': '보고만', 'propose': '제안까지', 'approve': '건별 승인 후 실행', 'mandate': '위임 범위 안에서 실행'}
    operations = ', '.join(f'{op}({labels[cls]})' for op, cls in sorted(record['operations'].items())) or '검토한 동작 없음'
    return f"{record['name']}: {rungs[record['rung']]}{' · 돈이 오가는 연결' if record['money'] else ''} · {operations}"
