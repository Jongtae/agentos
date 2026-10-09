"""#794 phase 3: exact forget, complete deletion and undo of owner state (``owner_forget``)."""
import json
import tempfile
import unittest
from pathlib import Path

from personal_agent.agent_runtime import MEMORY_OWNER, Capabilities, ToolError
from personal_agent.memory_service import MemoryService
from personal_agent.owner_forget import UNDO_SECONDS, ForgetError, OwnerForget
from personal_agent.quickstart_store import QuickStore
from personal_agent.subscription_engines import SubscriptionEngines  # noqa: F401 (store fixtures import order)

from test_current_context import ContextCase, SEOUL


class Clock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


class MemoryForget(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / 'state'
        self.store = QuickStore(self.root)
        self.clock = Clock()
        self.forget = OwnerForget(self.store, clock=self.clock)
        self.memory = MemoryService(self.store, private_read_sink=MemoryService.NO_EGRESS_GUARD)

    def save(self, key, content, **kwargs):
        return self.store.save_memory(key, content, MEMORY_OWNER, work_id='w-source', **kwargs)

    def current(self):
        return {row['memory_key']: row['content'] for row in self.memory.list_memories(MEMORY_OWNER)['memories']}

    def searched(self, term):
        return [row['content'] for row in self.memory.search_memories(MEMORY_OWNER, term)['memories']]

    def states(self):
        with self.store.db() as db:
            return {row['content']: row['state'] for row in db.execute('SELECT content,state FROM memories')}

    def test_forget_excludes_the_whole_chain_at_once_and_the_receipt_has_no_content(self):
        self.save('profile.place.home', '망원동')
        row = self.save('profile.place.home', '합정동')
        receipt = self.forget.forget(MEMORY_OWNER, 'memory:' + row['id'])
        self.assertEqual((receipt['operation'], receipt['state'], receipt['items']), ('forget', 'forgotten', 2))
        self.assertEqual(receipt['undo_until'], self.clock.now + UNDO_SECONDS)
        self.assertNotIn('profile.place.home', self.current())
        self.assertEqual(self.searched('합정동'), [])
        self.assertEqual(self.searched('망원동'), [], 'an older value of the key does not come back either')
        self.assertNotIn('합정', json.dumps(receipt, ensure_ascii=False))
        with self.store.db() as db:
            stored = json.dumps([dict(r) for r in db.execute('SELECT * FROM owner_state_receipts')], ensure_ascii=False)
        self.assertNotIn('합정', stored)
        self.assertNotIn('profile.place', stored)
        self.assertTrue(receipt['local_scope_only'])
        self.assertIn('AI provider', receipt['outside_scope'])

    def test_undo_restores_exactly_once_and_a_repeat_changes_nothing(self):
        old = self.save('diet', '채식')
        row = self.save('diet', '페스코', corrected=True)
        receipt = self.forget.forget(MEMORY_OWNER, 'memory:' + row['id'])
        undone = self.forget.undo(MEMORY_OWNER, receipt['receipt'])
        self.assertEqual(undone['state'], 'undone')
        self.assertEqual(self.current(), {'diet': '페스코'})
        self.assertEqual(self.states(), {'채식': 'corrected', '페스코': 'current'}, 'prior states restored exactly')
        self.assertEqual(self.forget.undo(MEMORY_OWNER, receipt['receipt'])['state'], 'undone')
        self.assertEqual(self.current(), {'diet': '페스코'})
        self.assertTrue(old['id'])

    def test_wrong_owner_stale_target_and_bad_ref_are_refused(self):
        row = self.save('city', '서울')
        for ref, code in (('memory:missing', 'stale'), ('city', 'bad_ref'), ('', 'bad_ref'), (None, 'bad_ref')):
            with self.subTest(ref=ref), self.assertRaises(ForgetError) as caught:
                self.forget.forget(MEMORY_OWNER, ref)
            self.assertEqual(caught.exception.code, code)
        with self.assertRaises(ForgetError) as caught:
            self.forget.forget('someone-else', 'memory:' + row['id'])
        self.assertEqual(caught.exception.code, 'stale')
        receipt = self.forget.forget(MEMORY_OWNER, 'memory:' + row['id'])
        with self.assertRaises(ForgetError) as caught:
            self.forget.undo('someone-else', receipt['receipt'])
        self.assertEqual(caught.exception.code, 'no_receipt')
        with self.assertRaises(ForgetError) as caught:
            self.forget.forget(MEMORY_OWNER, 'memory:' + row['id'])
        self.assertEqual(caught.exception.code, 'stale', 'a repeated forget changes nothing')

    def test_a_superseded_version_is_stale(self):
        first = self.save('city', '서울')
        self.save('city', '부산')
        with self.assertRaises(ForgetError) as caught:
            self.forget.forget(MEMORY_OWNER, 'memory:' + first['id'])
        self.assertEqual(caught.exception.code, 'stale')

    def test_a_later_value_before_undo_is_never_overwritten(self):
        row = self.save('city', '서울')
        receipt = self.forget.forget(MEMORY_OWNER, 'memory:' + row['id'])
        self.save('city', '부산')
        with self.assertRaises(ForgetError) as caught:
            self.forget.undo(MEMORY_OWNER, receipt['receipt'])
        self.assertEqual(caught.exception.code, 'later_value')
        self.assertEqual(self.current(), {'city': '부산'})

    def test_restart_keeps_the_exclusion_and_purges_overdue_items(self):
        row = self.save('city', '서울')
        receipt = self.forget.forget(MEMORY_OWNER, 'memory:' + row['id'])
        # A restart: a new store and module over the same files, the window already over.
        store = QuickStore(self.root)
        later = Clock(self.clock.now + UNDO_SECONDS + 1)
        again = OwnerForget(store, clock=later)
        self.assertNotIn('city', {r['memory_key'] for r in MemoryService(store, private_read_sink=MemoryService.NO_EGRESS_GUARD)
                                  .list_memories(MEMORY_OWNER)['memories']})
        self.assertEqual(again.purge_due(), 1)
        self.assertEqual(again.purge_due(), 0, 'a second purge finds nothing')
        with store.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM memories').fetchone()[0], 0)
            settled = db.execute('SELECT state,counts_json FROM owner_state_receipts WHERE id=?', (receipt['receipt'],)).fetchone()
        self.assertEqual(settled['state'], 'purged')
        self.assertEqual(json.loads(settled['counts_json'])['memories'], 1)
        with self.assertRaises(ForgetError) as caught:
            again.undo(MEMORY_OWNER, receipt['receipt'])
        self.assertEqual(caught.exception.code, 'settled')

    def test_undo_after_the_window_is_refused_even_before_the_purge_ran(self):
        row = self.save('city', '서울')
        receipt = self.forget.forget(MEMORY_OWNER, 'memory:' + row['id'])
        self.clock.now += UNDO_SECONDS
        with self.assertRaises(ForgetError) as caught:
            self.forget.undo(MEMORY_OWNER, receipt['receipt'])
        self.assertEqual(caught.exception.code, 'expired')

    def test_delete_purges_now_with_no_undo(self):
        self.save('city', '서울')
        row = self.save('city', '부산')
        receipt = self.forget.forget(MEMORY_OWNER, 'memory:' + row['id'], delete=True)
        self.assertEqual((receipt['operation'], receipt['state'], receipt['undo_until']), ('delete', 'deleted', None))
        self.assertEqual(receipt['counts']['memories'], 2)
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM memories').fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM memories_search WHERE memories_search MATCH '부산'").fetchone()[0], 0,
                             'the search index entry went with the row')
        with self.assertRaises(ForgetError) as caught:
            self.forget.undo(MEMORY_OWNER, receipt['receipt'])
        self.assertEqual(caught.exception.code, 'no_receipt')

    def test_a_pending_candidate_with_the_value_cannot_bring_it_back(self):
        row = self.save('city', '서울')
        candidate = self.store.save_memory_candidate('w-other', 'city', '서울')
        receipt = self.forget.forget(MEMORY_OWNER, 'memory:' + row['id'])
        self.assertEqual(receipt['items'], 2)
        self.assertEqual(self.memory.list_candidates(MEMORY_OWNER)['candidates'], [])
        self.forget.undo(MEMORY_OWNER, receipt['receipt'])
        self.assertEqual([c['id'] for c in self.memory.list_candidates(MEMORY_OWNER)['candidates']], [candidate['id']])

    def test_upkeep_guard_holds_until_the_owner_states_the_value_again(self):
        row = self.save('city', '서울')
        self.forget.forget(MEMORY_OWNER, 'memory:' + row['id'])
        self.assertTrue(self.forget.is_forgotten(MEMORY_OWNER, 'city', '서울'))
        self.assertFalse(self.forget.is_forgotten(MEMORY_OWNER, 'city', '부산'))
        self.forget.restated(MEMORY_OWNER, 'city', '서울')
        self.assertFalse(self.forget.is_forgotten(MEMORY_OWNER, 'city', '서울'))

    def test_undoable_lists_what_each_forget_covered(self):
        row = self.save('city', '서울')
        receipt = self.forget.forget(MEMORY_OWNER, 'memory:' + row['id'])
        [entry] = self.forget.undoable(MEMORY_OWNER)
        self.assertEqual((entry['receipt'], entry['item']), (receipt['receipt'], {'memory_key': 'city', 'content': '서울'}))
        self.forget.undo(MEMORY_OWNER, receipt['receipt'])
        self.assertEqual(self.forget.undoable(MEMORY_OWNER), [])


class ToolPath(unittest.TestCase):
    """The owner's AI reaches it through ``forget_record``; the receipt is what Evidence keeps."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'state')
        self.events = []
        self.job = self.store.enqueue('내 사는 곳 잊어줘', 'forget-1')

    def caps(self, job=None):
        return Capabilities(self.store, None, {}, '', job or self.job, lambda *e: self.events.append(e))

    def test_forget_list_undo_and_delete_through_the_tool(self):
        row = self.store.save_memory('city', '서울', MEMORY_OWNER, work_id='w-source')
        caps = self.caps()
        result = caps.execute('forget_record', {'action': 'forget', 'ref': 'memory:' + row['id']})
        self.assertEqual((result['action'], result['state']), ('forget', 'forgotten'))
        listed = caps.execute('forget_record', {'action': 'list'})
        self.assertEqual(listed['undoable'][0]['item']['content'], '서울')
        undone = caps.execute('forget_record', {'action': 'undo', 'receipt': result['receipt']})
        self.assertEqual(undone['state'], 'undone')
        deleted = caps.execute('forget_record', {'action': 'delete', 'ref': 'memory:' + row['id']})
        self.assertEqual(deleted['state'], 'deleted')
        with self.assertRaises(ToolError) as caught:
            caps.execute('forget_record', {'action': 'delete', 'ref': 'memory:' + row['id']})
        self.assertEqual(caught.exception.code, 'stale')
        # Evidence keeps the receipt, never the forgotten value.
        from personal_agent.agent_runtime import evidence_summary
        self.assertNotIn('서울', json.dumps(evidence_summary('forget_record', listed), ensure_ascii=False))
        self.assertEqual(evidence_summary('forget_record', listed)['undoable'], 1)

    def test_the_ai_saves_a_forgotten_value_again_only_when_this_request_states_it(self):
        row = self.store.save_memory('city', '서울', MEMORY_OWNER, work_id='w-source')
        OwnerForget(self.store).forget(MEMORY_OWNER, 'memory:' + row['id'])
        refused = self.caps().execute('save_memory', {'memory_key': 'city', 'content': '서울'})
        self.assertEqual((refused['saved'], refused['refused_because']), (False, 'forgotten-value'))
        stated = self.store.enqueue('나 서울 살아. 기억해 줘', 'restate-1')
        saved = self.caps(stated).execute('save_memory', {'memory_key': 'city', 'content': '서울'})
        self.assertTrue(saved['saved'])
        self.assertFalse(OwnerForget(self.store).is_forgotten(MEMORY_OWNER, 'city', '서울'))

    def test_a_correction_marks_the_previous_value_wrong_not_outdated(self):
        self.store.save_memory('allergy', '땅콩', MEMORY_OWNER, work_id='w-source')
        caps = self.caps()
        caps.execute('save_memory', {'memory_key': 'allergy', 'content': '호두', 'correction': True})
        caps.execute('save_memory', {'memory_key': 'allergy', 'content': '호두와 잣'})
        with self.store.db() as db:
            states = {row['content']: row['state'] for row in db.execute('SELECT content,state FROM memories')}
        self.assertEqual(states, {'땅콩': 'corrected', '호두': 'superseded', '호두와 잣': 'current'})


class ClaimAndObservationForget(ContextCase):
    """A current-state claim and an observation leave use the same way."""

    def setUp(self):
        super().setUp()
        self.enable(SEOUL)
        self.forget = OwnerForget(self.store, clock=lambda: self.now)

    def test_a_forgotten_observation_and_the_claim_derived_from_it_leave_use(self):
        ref = self.live()
        job, _ = self.request('지금 여기야')
        claim = self.propose(job, predicate='current_place', value='', place_ref=ref, source=ref)
        self.assertTrue(claim.get('recorded'), claim)
        self.assertEqual(len(self.context.hypotheses()), 1)
        receipt = self.forget.forget(MEMORY_OWNER, ref)
        self.assertEqual(receipt['kind'], 'observation')
        self.assertEqual([e['id'] for e in self.obs.usable()], [])
        self.assertEqual(self.context.hypotheses(), [], 'a claim derived from it is invalidated')
        self.forget.undo(MEMORY_OWNER, receipt['receipt'])
        self.assertEqual(['obs:' + e['id'] for e in self.obs.usable()], [ref])

    def test_a_forgotten_claim_is_purged_with_its_exposures(self):
        job, _ = self.request('오늘 재택이야')
        result = self.propose(job, predicate='work_mode', value='remote')
        self.assertTrue(result.get('recorded'), result)
        [claim] = self.context.hypotheses()
        with self.store.db() as db:
            db.execute('INSERT INTO current_context_exposures VALUES (?,?,?,?,?)',
                       ('w-earlier', 'state:' + claim['id'], '1', json.dumps(['remote']), self.now))
        receipt = self.forget.forget(MEMORY_OWNER, 'state:' + claim['id'])
        self.assertEqual(self.context.hypotheses(), [])
        self.now += UNDO_SECONDS + 1
        self.assertEqual(self.forget.purge_due(), 1)
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM current_state_claims').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM current_context_exposures').fetchone()[0], 0)
        self.assertTrue(receipt['receipt'])


if __name__ == '__main__':
    unittest.main()
