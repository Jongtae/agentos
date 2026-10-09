"""Exact forget, complete deletion and undo of owner state (#794 phase 3, #918 option B).

The owner asks in conversation; the owner's AI identifies the item (``memory:<id>``
from ``list_memory``/``search_memory``, ``state:<id>`` or ``obs:<id>`` from the
current context) and calls ``forget_record``.  This module only enforces owner
scope, the exact item and version, the state transitions and a truthful,
content-free receipt; it recognises no phrase, site or task (C16).

* ``forget``: the item - for Memory its whole supersession chain - leaves current
  use at once (state ``forgotten``) and stays undoable for ``UNDO_SECONDS``;
  ``purge_due`` then deletes its payload.  Restart keeps the exclusion (it is a
  row state) and the next purge runs overdue cleanup.
* ``delete``: the same exclusion and the purge in one transaction; no undo.
* ``undo``: restores exactly the receipt's items to the states they had, once,
  unless a later value for the same Memory key, claim or observation source
  exists (a later correction is never overwritten), the window ended, or the
  receipt belongs to another owner.

Receipts keep operation, kind, item ids, time, state and counts - never content.
Forgetting a Memory value also records its digest so owner-model upkeep never
re-saves it from a source Work (``is_forgotten``); the owner stating it again
through their AI clears that guard (``restated``).

Scope: the local store.  Copies already sent to a model provider, exported
bundles and backups are outside it, and the result says so.
"""
import json
import time
import uuid

#: #918 option B: a forgotten item stays undoable for a week, then its payload is purged.
UNDO_SECONDS = 7 * 86400
MEMORY_PREFIX, CLAIM_PREFIX, OBSERVATION_PREFIX = 'memory:', 'state:', 'obs:'
KINDS = {MEMORY_PREFIX: 'memory', CLAIM_PREFIX: 'claim', OBSERVATION_PREFIX: 'observation'}
FORGOTTEN = 'forgotten'
#: What a result says about copies outside this store (never claimed erased).
OUTSIDE_SCOPE = 'copies already sent to an AI provider, exports and backups are not affected'

DDL = '''
CREATE TABLE IF NOT EXISTS owner_state_receipts(
  id TEXT PRIMARY KEY, owner_key TEXT NOT NULL, operation TEXT NOT NULL, kind TEXT NOT NULL,
  items_json TEXT NOT NULL, state TEXT NOT NULL, counts_json TEXT NOT NULL DEFAULT '{}',
  created REAL NOT NULL, undo_until REAL, settled REAL, work_id TEXT);
CREATE INDEX IF NOT EXISTS owner_state_receipts_due ON owner_state_receipts(state, undo_until);
CREATE TABLE IF NOT EXISTS forgotten_values(
  owner_key TEXT NOT NULL, digest TEXT NOT NULL, receipt_id TEXT NOT NULL, created REAL NOT NULL,
  PRIMARY KEY(owner_key, digest, receipt_id));
'''


class ForgetError(ValueError):
    """A refused forget/delete/undo; ``code`` is typed, the message is owner-facing Korean."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def _refuse(code):
    return ForgetError({
        'bad_ref': '잊을 항목을 확인할 수 없어요. 기억은 memory:<id>, 현재 상태는 state:<id>, 관찰은 obs:<id>로 지정해 주세요.',
        'stale': '그 항목은 이미 바뀌었거나 없어요. 지금 값을 다시 확인해 주세요.',
        'no_receipt': '되돌릴 기록을 찾지 못했어요.',
        'expired': '되돌릴 수 있는 기간(7일)이 지났어요.',
        'later_value': '그 뒤에 새로 저장된 값이 있어 되돌리지 않았어요. 지금 값은 그대로예요.',
        'settled': '이미 완전히 지워져 되돌릴 수 없어요.',
    }[code], code)


class OwnerForget:
    def __init__(self, store, clock=time.time):
        self.store, self.clock = store, clock
        with store.db() as db:
            db.executescript(DDL)

    # -- refs ----------------------------------------------------------------
    @staticmethod
    def parse(ref):
        if isinstance(ref, str):
            for prefix, kind in KINDS.items():
                if ref.startswith(prefix) and len(ref) > len(prefix) and len(ref) <= 200:
                    return kind, ref[len(prefix):]
        raise _refuse('bad_ref')

    # -- forget / delete -----------------------------------------------------
    def forget(self, owner_id, ref, *, delete=False, work_id=None):
        """Exclude one item from current use now; ``delete`` also purges it now (no undo)."""
        kind, item_id = self.parse(ref)
        owner_key = self.store._memory_binding(owner_id)
        now = self.clock()
        receipt_id = str(uuid.uuid4())
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            items = getattr(self, f'_exclude_{kind}')(db, owner_key, item_id, receipt_id, now)
            db.execute('INSERT INTO owner_state_receipts(id,owner_key,operation,kind,items_json,state,created,undo_until,work_id) '
                       'VALUES (?,?,?,?,?,?,?,?,?)',
                       (receipt_id, owner_key, 'delete' if delete else 'forget', kind, json.dumps(items), FORGOTTEN, now,
                        None if delete else now + UNDO_SECONDS, work_id if isinstance(work_id, str) else None))
            if delete:
                self._purge(db, receipt_id, now, final='deleted')
            row = db.execute('SELECT * FROM owner_state_receipts WHERE id=?', (receipt_id,)).fetchone()
        return self._receipt(row)

    def _exclude_memory(self, db, owner_key, memory_id, receipt_id, now):
        current = db.execute("SELECT * FROM memories WHERE id=? AND owner_key=? AND state='current'",
                             (memory_id, owner_key)).fetchone()
        if current is None:
            raise _refuse('stale')
        chain, cursor = [], current
        while cursor is not None:
            chain.append(cursor)
            cursor = (db.execute('SELECT * FROM memories WHERE id=? AND owner_key=?', (cursor['supersedes'], owner_key)).fetchone()
                      if cursor['supersedes'] else None)
        items = []
        for row in chain:
            if row['state'] == FORGOTTEN:
                continue
            items.append({'table': 'memories', 'id': row['id'], 'prior': row['state']})
            db.execute('UPDATE memories SET state=? WHERE id=?', (FORGOTTEN, row['id']))
            db.execute('INSERT OR IGNORE INTO forgotten_values VALUES (?,?,?,?)',
                       (owner_key, row['content_digest'], receipt_id, now))
        # A pending candidate holding a forgotten value would bring it back once accepted.
        digests = {row['content_digest'] for row in chain}
        for candidate in db.execute("SELECT id,memory_key,content,state FROM memory_candidates WHERE owner_key=? AND state='pending'",
                                    (owner_key,)).fetchall():
            if self.store.memory_digest(candidate['memory_key'], candidate['content']) in digests:
                items.append({'table': 'memory_candidates', 'id': candidate['id'], 'prior': candidate['state']})
                db.execute('UPDATE memory_candidates SET state=? WHERE id=?', (FORGOTTEN, candidate['id']))
        # An approval issued against the key must not re-apply the value later.
        db.execute("UPDATE memory_approvals SET state='revoked',memory_key='' WHERE owner_key=? AND memory_key=? AND state='issued'",
                   (owner_key, current['memory_key']))
        return {'rows': items}

    def _context_scope(self, db, owner_key=None):
        """Claims and observations belong to the paired Telegram owner and generation (``current_context``).

        That context belongs to this installation's one owner; any other owner
        id has no claims or observations here (review P2).
        """
        from .agent_runtime import MEMORY_OWNER
        from .current_context import _owner_scope
        if owner_key is not None and owner_key != self.store._memory_binding(MEMORY_OWNER):
            raise _refuse('stale')
        return tuple(_owner_scope(db))

    @staticmethod
    def _claim_id(value):
        """A claim's ``supersedes`` is stored as ``state:<id>`` (``current_context``)."""
        value = str(value or '')
        return value[len(CLAIM_PREFIX):] if value.startswith(CLAIM_PREFIX) else value

    def _exclude_claim(self, db, owner_key, claim_id, receipt_id, now):
        scope = self._context_scope(db, owner_key)
        current = db.execute("SELECT * FROM current_state_claims WHERE id=? AND owner_key=? AND generation=? AND state='current'",
                             (claim_id, *scope)).fetchone()
        if current is None:
            raise _refuse('stale')
        items, cursor = [], current
        while cursor is not None:
            if cursor['state'] != FORGOTTEN:
                items.append({'table': 'current_state_claims', 'id': cursor['id'], 'prior': cursor['state']})
                db.execute('UPDATE current_state_claims SET state=? WHERE id=?', (FORGOTTEN, cursor['id']))
            cursor = (db.execute('SELECT * FROM current_state_claims WHERE id=? AND owner_key=? AND generation=?',
                                 (self._claim_id(cursor['supersedes']), *scope)).fetchone() if cursor['supersedes'] else None)
        return {'rows': items, 'scope': list(scope), 'predicate': current['predicate']}

    def _exclude_observation(self, db, owner_key, observation_id, receipt_id, now):
        scope = self._context_scope(db, owner_key)
        row = db.execute("SELECT * FROM context_observations WHERE id=? AND owner_key=? AND generation=? "
                         "AND state NOT IN ('invalidated',?)", (observation_id, *scope, FORGOTTEN)).fetchone()
        if row is None:
            raise _refuse('stale')
        db.execute('UPDATE context_observations SET state=? WHERE id=?', (FORGOTTEN, observation_id))
        return {'rows': [{'table': 'context_observations', 'id': observation_id, 'prior': row['state'],
                          'revision': row['source_revision']}], 'scope': list(scope)}

    # -- undo ----------------------------------------------------------------
    def undo(self, owner_id, receipt_id):
        """Restore exactly what one forget excluded, once, within its window."""
        owner_key = self.store._memory_binding(owner_id)
        now = self.clock()
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            receipt = db.execute('SELECT * FROM owner_state_receipts WHERE id=? AND owner_key=?',
                                 (str(receipt_id or ''), owner_key)).fetchone()
            if receipt is None or receipt['operation'] != 'forget':
                raise _refuse('no_receipt')
            if receipt['state'] == 'undone':
                return self._receipt(receipt)   # a repeated undo changes nothing
            if receipt['state'] != FORGOTTEN:
                raise _refuse('settled')
            if receipt['undo_until'] is None or now >= receipt['undo_until']:
                raise _refuse('expired')
            items = json.loads(receipt['items_json'])
            rows = items.get('rows') or []
            self._refuse_later_value(db, owner_key, receipt['kind'], items, rows)
            for row in rows:
                db.execute(f"UPDATE {row['table']} SET state=? WHERE id=? AND state=?", (row['prior'], row['id'], FORGOTTEN))
            db.execute('DELETE FROM forgotten_values WHERE receipt_id=?', (receipt['id'],))
            db.execute("UPDATE owner_state_receipts SET state='undone',settled=? WHERE id=?", (now, receipt['id']))
            return self._receipt(db.execute('SELECT * FROM owner_state_receipts WHERE id=?', (receipt['id'],)).fetchone())

    def _refuse_later_value(self, db, owner_key, kind, items, rows):
        ids = [row['id'] for row in rows]
        # A re-paired or disconnected Telegram owner is another context owner: never restored for them.
        if items.get('scope') is not None and list(self._context_scope(db, owner_key)) != items['scope']:
            raise _refuse('no_receipt')
        if kind == 'memory':
            current = [row for row in rows if row['table'] == 'memories' and row['prior'] == 'current']
            if current:
                key = db.execute('SELECT memory_key FROM memories WHERE id=?', (current[0]['id'],)).fetchone()
                if key is None or db.execute("SELECT 1 FROM memories WHERE owner_key=? AND memory_key=? AND state='current'",
                                             (owner_key, key['memory_key'])).fetchone():
                    raise _refuse('later_value')
        elif kind == 'claim':
            # Review P1: a later statement of the same kind is a new, independent claim (the forgotten one
            # was out of use, so nothing supersedes it); either way the newer claim wins.
            scope = items.get('scope') or []
            if db.execute("SELECT 1 FROM current_state_claims WHERE owner_key=? AND generation=? AND predicate=? AND state='current'",
                          (*scope, items.get('predicate'))).fetchone():
                raise _refuse('later_value')
        for row in rows:
            found = db.execute(f"SELECT state{', source_revision' if row['table'] == 'context_observations' else ''} "
                               f"FROM {row['table']} WHERE id=?", (row['id'],)).fetchone()
            if found is None:
                raise _refuse('settled')
            if found['state'] != FORGOTTEN or (row.get('revision') is not None and found['source_revision'] != row['revision']):
                raise _refuse('later_value')

    # -- purge ---------------------------------------------------------------
    def purge_due(self, now=None):
        """Purge every forget whose undo window ended; safe to repeat and after a restart."""
        now = self.clock() if now is None else now
        purged = 0
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            for row in db.execute("SELECT id FROM owner_state_receipts WHERE state=? AND undo_until IS NOT NULL AND undo_until<=?",
                                  (FORGOTTEN, now)).fetchall():
                self._purge(db, row['id'], now, final='purged')
                purged += 1
        return purged

    def _purge(self, db, receipt_id, now, *, final):
        receipt = db.execute('SELECT * FROM owner_state_receipts WHERE id=?', (receipt_id,)).fetchone()
        rows = json.loads(receipt['items_json']).get('rows') or []
        counts = {}
        for row in rows:
            table = row['table']
            # Only a row still forgotten: one a new location point revived is current information again.
            counts[table] = counts.get(table, 0) + db.execute(f'DELETE FROM {table} WHERE id=? AND state=?',
                                                              (row['id'], FORGOTTEN)).rowcount
            if table == 'memories':
                counts['memory_approvals'] = counts.get('memory_approvals', 0) + db.execute(
                    'DELETE FROM memory_approvals WHERE subject_id=? OR result_id=?', (row['id'], row['id'])).rowcount
            ref = {'current_state_claims': CLAIM_PREFIX, 'context_observations': OBSERVATION_PREFIX}.get(table)
            if ref:
                # Strings this item exposed to earlier Works are a derived copy of it.
                counts['exposures'] = counts.get('exposures', 0) + db.execute(
                    'DELETE FROM current_context_exposures WHERE source_ref=?', (ref + row['id'],)).rowcount
        db.execute('UPDATE owner_state_receipts SET state=?,settled=?,counts_json=? WHERE id=?',
                   (final, now, json.dumps(counts, sort_keys=True), receipt_id))

    # -- reads ---------------------------------------------------------------
    def undoable(self, owner_id, limit=20):
        """Forgets the owner can still undo, newest first, with what each covers (a private read for the AI)."""
        owner_key = self.store._memory_binding(owner_id)
        now = self.clock()
        out = []
        with self.store.db() as db:
            for receipt in db.execute('SELECT * FROM owner_state_receipts WHERE owner_key=? AND state=? AND undo_until>? '
                                      'ORDER BY created DESC LIMIT ?', (owner_key, FORGOTTEN, now, int(limit))).fetchall():
                entry = self._receipt(receipt)
                head = (json.loads(receipt['items_json']).get('rows') or [{}])[0]
                if receipt['kind'] == 'memory' and head.get('id'):
                    found = db.execute('SELECT memory_key,content FROM memories WHERE id=?', (head['id'],)).fetchone()
                    if found:
                        entry['item'] = {'memory_key': found['memory_key'], 'content': found['content']}
                elif receipt['kind'] == 'claim' and head.get('id'):
                    found = db.execute('SELECT predicate,value_json FROM current_state_claims WHERE id=?', (head['id'],)).fetchone()
                    if found:
                        entry['item'] = {'predicate': found['predicate'], 'value': json.loads(found['value_json']).get('value', '')}
                elif head.get('id'):
                    found = db.execute('SELECT source_kind FROM context_observations WHERE id=?', (head['id'],)).fetchone()
                    if found:
                        entry['item'] = {'kind': found['source_kind']}
                out.append(entry)
        return out

    def is_forgotten(self, owner_id, memory_key, content):
        """Whether this exact Memory value was forgotten (upkeep must not re-save it from a source Work)."""
        digest = self.store.memory_digest(memory_key, content)
        with self.store.db() as db:
            return db.execute('SELECT 1 FROM forgotten_values WHERE owner_key=? AND digest=?',
                              (self.store._memory_binding(owner_id), digest)).fetchone() is not None

    def restated(self, owner_id, memory_key, content):
        """The owner stated a forgotten value again through their AI: it is no longer withheld from upkeep."""
        digest = self.store.memory_digest(memory_key, content)
        with self.store.db() as db:
            db.execute('DELETE FROM forgotten_values WHERE owner_key=? AND digest=?', (self.store._memory_binding(owner_id), digest))

    def _receipt(self, row):
        rows = json.loads(row['items_json']).get('rows') or []
        return {'receipt': row['id'], 'operation': row['operation'], 'kind': row['kind'], 'state': row['state'],
                'items': len(rows), 'at': row['created'], 'undo_until': row['undo_until'], 'settled_at': row['settled'],
                'counts': json.loads(row['counts_json'] or '{}'), 'local_scope_only': True, 'outside_scope': OUTSIDE_SCOPE}
