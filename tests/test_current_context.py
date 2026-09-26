"""CONTEXT-STATE-01 / #627: validity, conflict, supersession, expiry, freshness and time.

Unit tests over a temporary QuickStore with an injected clock: the real
``ContextObservations`` ingress (#626) and the ``current_context`` helpers.
No model, network, Telegram or device location is contacted.  Evidence class:
automated synthetic/fixture only.  IDs follow the playbook (CT-09..CT-12,
CT-16, CT-18).
"""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from personal_agent.agent_runtime import MEMORY_OWNER
from personal_agent.context_observations import FRESHNESS_SECONDS, RETENTION_SECONDS, ContextObservations
from personal_agent.current_context import (SNAPSHOT_BYTES, SNAPSHOT_ENTRIES, ContextRefusal, CurrentContext,
                                            PROFILE_OWNER, local_day_end, mark_conflicts, parse_until,
                                            redact_known_secrets, render)
from personal_agent.memory_service import MemoryService
from personal_agent.quickstart_store import QuickStore

CHAT = 4242
GENERATION = 'g1'
SEOUL = 'Asia/Seoul'
#: 2026-09-21 12:00 in Seoul (03:00Z), a synthetic moment, not the owner's.
NOON_SEOUL = datetime(2026, 9, 21, 12, 0, tzinfo=ZoneInfo(SEOUL)).timestamp()
POINT = {'latitude': 37.566512, 'longitude': 126.978031, 'horizontal_accuracy': 12}


def at(zone, *parts):
    return datetime(*parts, tzinfo=ZoneInfo(zone)).timestamp()


class PureHelpers(unittest.TestCase):
    """CT-12: interval arithmetic with the owner's zone, never the server's."""

    def test_today_ends_at_the_source_days_local_midnight_across_dst(self):
        self.assertEqual(local_day_end(NOON_SEOUL, SEOUL), at(SEOUL, 2026, 9, 22, 0, 0))
        ny = 'America/New_York'
        # Spring-forward day (23 h) and fall-back day (25 h): the day still
        # ends at the next local midnight, not source + 24 h.
        spring = at(ny, 2026, 3, 8, 10, 0)
        self.assertEqual(local_day_end(spring, ny), at(ny, 2026, 3, 9, 0, 0))
        self.assertEqual(local_day_end(spring, ny) - spring, 14 * 3600)
        fall = at(ny, 2026, 11, 1, 0, 30)
        self.assertEqual(local_day_end(fall, ny) - fall, 24 * 3600 + 30 * 60, 'the 25-hour day')
        # Late evening: "today" is the source day, not the next day.
        self.assertEqual(local_day_end(at(SEOUL, 2026, 9, 21, 23, 50), SEOUL), at(SEOUL, 2026, 9, 22, 0, 0))

    def test_unknown_timezone_is_refused_not_taken_from_the_server_clock(self):
        for name in ('', 'Mars/Olympus'):
            with self.subTest(name=name), self.assertRaises(ContextRefusal) as refused:
                local_day_end(NOON_SEOUL, name)
            self.assertEqual(refused.exception.code, 'timezone_unknown')

    def test_until_defaults_caps_and_refusals(self):
        now = NOON_SEOUL
        self.assertEqual(parse_until(None, 'work_mode', 'owner_statement_interpretation', now, SEOUL, now),
                         at(SEOUL, 2026, 9, 22, 0, 0))
        self.assertEqual(parse_until(None, 'current_place', 'owner_statement_interpretation', now, SEOUL, now),
                         now + FRESHNESS_SECONDS)
        # An inference never outlives the implicit-place freshness.
        self.assertEqual(parse_until('today', 'work_mode', 'inferred', now, SEOUL, now), now + FRESHNESS_SECONDS)
        # Capped at temporary retention from the source.
        self.assertEqual(parse_until('2026-09-30T00:00:00+09:00', 'availability_hint', 'owner_statement_interpretation',
                                     now, SEOUL, now), now + RETENTION_SECONDS)
        self.assertEqual(parse_until('2026-09-21T15:00:00+09:00', 'availability_hint',
                                     'owner_statement_interpretation', now, '', now),
                         at(SEOUL, 2026, 9, 21, 15, 0), 'an explicit offset needs no owner zone')
        for bad in ('2026-09-21T15:00:00', 'tomorrow-ish', '2026-09-21T11:00:00+09:00'):
            with self.subTest(until=bad), self.assertRaises(ContextRefusal) as refused:
                parse_until(bad, 'availability_hint', 'owner_statement_interpretation', now, SEOUL, now)
            self.assertEqual(refused.exception.code, 'invalid_interval')
        # Said yesterday "today": over by now.
        with self.assertRaises(ContextRefusal):
            parse_until('today', 'work_mode', 'owner_statement_interpretation', now - 86_000, SEOUL, now)

    def test_conflicts_need_the_same_predicate_an_overlap_and_a_different_value(self):
        def claim(predicate, value, start, end, place_ref=None):
            return {'predicate': predicate, 'value': value, 'place_ref': place_ref, 'effective_from': start, 'end': end}
        claims = mark_conflicts([claim('work_mode', 'remote', 0, 10), claim('work_mode', 'office', 5, 15),
                                 claim('work_mode', 'office', 20, 30), claim('current_place', 'Busan', 0, 10)])
        self.assertEqual([c['state'] for c in claims], ['conflicting', 'conflicting', 'supported', 'supported'])
        same = mark_conflicts([claim('work_mode', 'remote', 0, 10), claim('work_mode', 'remote', 0, 10)])
        self.assertEqual([c['state'] for c in same], ['supported', 'supported'])

    def test_the_local_memory_owner_is_the_runtime_owner(self):
        self.assertEqual(PROFILE_OWNER, MEMORY_OWNER)


class ContextCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'state')
        self.now = NOON_SEOUL
        self.obs = ContextObservations(self.store, clock=lambda: self.now)
        self.context = CurrentContext(self.store, self.obs)
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': GENERATION, 'cursor': 0})
        self.update_id, self.message_id = 100, 500
        self.memory = MemoryService(self.store, private_read_sink=MemoryService.NO_EGRESS_GUARD)

    # helpers
    def enable(self, timezone=SEOUL):
        self.obs.set_controls({'enabled': True, 'timezone': timezone})

    def ingest(self, message, edited=False):
        self.update_id += 1
        message = {'from': {'id': CHAT}, 'chat': {'id': CHAT, 'type': 'private'}, 'date': int(self.now), **message}
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            return self.obs.ingest_telegram(db, {'update_id': self.update_id,
                                                 ('edited_message' if edited else 'message'): message},
                                            GENERATION, CHAT)

    def live(self, point=POINT, period=3600):
        self.message_id += 1
        self.ingest({'message_id': self.message_id, 'location': {**point, 'live_period': period}})
        return self.obs_ref()

    def venue(self, title='시청'):
        self.message_id += 1
        self.ingest({'message_id': self.message_id, 'venue': {'title': title, 'location': dict(POINT)}})
        return self.obs_ref()

    def obs_ref(self):
        with self.store.db() as db:
            row = db.execute('SELECT id FROM context_observations ORDER BY received_at DESC, rowid DESC').fetchone()
        return 'obs:' + row['id']

    def request(self, text, telegram=False):
        """An owner message Work with its own source time (the fake clock)."""
        self.message_id += 1
        channel = f'telegram:{GENERATION}' if telegram else 'web'
        job = self.store.enqueue(text, f'k{self.message_id}', channel, CHAT if telegram else None)
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE jobs SET created=? WHERE id=?', (self.now, job))
            if telegram:
                self.obs.note_text_source(db, job, {'chat': {'id': CHAT}, 'message_id': self.message_id,
                                                    'date': int(self.now)}, GENERATION)
        return job, self.message_id

    def propose(self, job, **args):
        return self.context.propose(job, args)

    def claims(self):
        with self.store.db() as db:
            return [dict(row) for row in db.execute('SELECT * FROM current_state_claims ORDER BY created')]

    def anchors(self):
        self.memory.remember_profile(PROFILE_OWNER, 'settings', 'profile.place.home', '합정')
        self.memory.remember_profile(PROFILE_OWNER, 'settings', 'profile.place.work', '판교')


class Proposals(ContextCase):
    """CT-09/CT-10: source/owner/revision-bound hypotheses; never Memory."""

    def test_a_proposal_is_refused_while_context_is_off(self):
        job, _ = self.request('오늘 재택이야')
        result = self.propose(job, predicate='work_mode', value='remote')
        self.assertEqual((result['recorded'], result['reason']), (False, 'context_paused'))
        self.assertEqual(self.claims(), [])

    def test_work_from_home_today_is_a_temporary_hypothesis_that_never_touches_profile(self):
        self.enable()
        self.anchors()
        before = [(row['memory_key'], row['content']) for row in self.store.memories(PROFILE_OWNER)]
        job, _ = self.request('오늘 재택이야')
        result = self.propose(job, predicate='work_mode', value='remote', place_ref='profile:place.home')
        self.assertTrue(result['recorded'], result)
        self.assertEqual(result['kind'], 'owner_statement_interpretation')
        self.assertEqual(result['until'], '2026-09-21T15:00:00Z', 'local midnight in Seoul')
        self.assertNotIn('verified', result['kind'])
        after = [(row['memory_key'], row['content']) for row in self.store.memories(PROFILE_OWNER)]
        self.assertEqual(before, after, 'profile.place.work is still the permanent anchor')
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM memory_candidates').fetchone()[0], 0)
        [live] = self.context.hypotheses()
        self.assertEqual((live['value'], live['place_ref'], live['state']), ('remote', 'profile:place.home', 'supported'))
        # Tomorrow it is gone; the permanent anchor is not.
        self.now = at(SEOUL, 2026, 9, 22, 0, 1)
        self.assertEqual(self.context.hypotheses(), [])
        self.assertIn(('profile.place.work', '판교'), [(r['memory_key'], r['content']) for r in self.store.memories(PROFILE_OWNER)])

    def test_only_a_current_request_or_an_admitted_observation_is_a_source(self):
        self.enable()
        job, _ = self.request('부산이야')
        for source in ('state:abc', 'assistant', 'request:' + job, 'obs:not-a-row'):
            with self.subTest(source=source):
                result = self.propose(job, predicate='current_place', value='Busan', source=source)
                self.assertFalse(result['recorded'])
                self.assertIn(result['reason'], ('unsupported_source', 'source_unavailable'))
        for args, reason in (({'predicate': 'mood', 'value': 'x'}, 'unsupported_predicate'),
                             ({'predicate': 'work_mode', 'value': 'sleeping'}, 'invalid_value'),
                             ({'predicate': 'current_place', 'value': 'x' * 81}, 'invalid_value'),
                             ({'predicate': 'current_place', 'value': '', 'place_ref': 'profile:place.moon'}, 'invalid_place_ref'),
                             ({'predicate': 'current_place', 'value': 'x', 'until': 'tomorrow'}, 'invalid_interval')):
            with self.subTest(args=args):
                self.assertEqual(self.propose(job, **args)['reason'], reason)
        self.assertEqual(self.claims(), [])

    def test_a_foreign_or_re_paired_owners_observation_is_not_a_source(self):
        self.enable()
        ref = self.live()
        job, _ = self.request('여기야')
        self.store.put('telegram', {'enabled': True, 'user_id': 9999, 'generation': 'g2', 'cursor': 0})
        result = self.propose(job, predicate='current_place', value='', place_ref=ref, source=ref)
        self.assertEqual(result['reason'], 'source_unavailable')

    def test_a_message_sent_before_a_clear_cannot_recreate_context(self):
        self.enable()
        job, _ = self.request('오늘 재택이야')
        self.now += 60
        self.obs.set_controls({'clear': True})
        self.assertEqual(self.propose(job, predicate='work_mode', value='remote')['reason'], 'source_unavailable')

    def test_an_observation_restated_is_a_report_bounded_by_its_freshness(self):
        self.enable()
        ref = self.live()
        job, _ = self.request('나 여기야')
        report = self.propose(job, predicate='current_place', value='', place_ref=ref, source=ref, until='today')
        self.assertEqual(report['kind'], 'source_report')
        self.assertEqual(report['until'], datetime.fromtimestamp(self.now + FRESHNESS_SECONDS, ZoneInfo('UTC'))
                         .isoformat(timespec='seconds').replace('+00:00', 'Z'))
        inferred = self.propose(job, predicate='work_mode', value='office', source=ref, until='today')
        self.assertEqual(inferred['kind'], 'inferred')
        self.assertLessEqual(self.claims()[-1]['effective_until'], self.now + FRESHNESS_SECONDS)

    def test_an_unknown_source_time_and_an_unknown_timezone_are_not_invented(self):
        self.enable(timezone='')
        job, _ = self.request('오늘 재택이야')
        self.assertEqual(self.propose(job, predicate='work_mode', value='remote')['reason'], 'timezone_unknown')
        self.assertTrue(self.propose(job, predicate='work_mode', value='remote',
                                     until='2026-09-21T18:00:00+09:00')['recorded'])
        self.enable()
        tg_job = self.store.enqueue('오늘 재택', 'tg-no-date', f'telegram:{GENERATION}', CHAT)
        self.assertEqual(self.propose(tg_job, predicate='work_mode', value='remote')['reason'], 'source_time_unknown')


class Corrections(ContextCase):
    """CT-11: correction supersedes only the matching proposition; no double evidence."""

    def test_a_duplicate_restatement_adds_no_evidence(self):
        self.enable()
        job, _ = self.request('오늘 재택이야')
        first = self.propose(job, predicate='work_mode', value='remote')
        again = self.propose(job, predicate='work_mode', value='remote')
        self.assertTrue(again['duplicate'])
        self.assertEqual(again['state_ref'], first['state_ref'])
        self.assertEqual(len(self.claims()), 1)

    def test_the_owners_correction_supersedes_only_that_proposition(self):
        self.enable()
        job, _ = self.request('오늘 재택이고 3시까지 회의야')
        remote = self.propose(job, predicate='work_mode', value='remote')
        busy = self.propose(job, predicate='availability_hint', value='회의 중', until='2026-09-21T15:00:00+09:00')
        self.now += 600
        fix, _ = self.request('아 오늘 출근이야')
        office = self.propose(fix, predicate='work_mode', value='office', supersedes=remote['state_ref'])
        self.assertEqual(office['superseded'], [remote['state_ref']])
        live = {c['predicate']: c for c in self.context.hypotheses()}
        self.assertEqual(live['work_mode']['value'], 'office')
        self.assertEqual(live['availability_hint']['value'], '회의 중', 'an unrelated hypothesis is untouched')
        self.assertEqual('state:' + live['availability_hint']['id'], busy['state_ref'])
        # A later owner statement of the same proposition corrects it even
        # without naming it.
        self.now += 600
        again, _ = self.request('역시 재택')
        self.propose(again, predicate='work_mode', value='remote')
        self.assertEqual([c['value'] for c in self.context.hypotheses() if c['predicate'] == 'work_mode'], ['remote'])

    def test_a_report_never_overrides_the_owner_and_contradictions_stay_visible(self):
        self.enable()
        job, _ = self.request('나 부산이야')
        stated = self.propose(job, predicate='current_place', value='Busan', until='today')
        ref = self.live()
        report = self.propose(job, predicate='current_place', value='', place_ref=ref, source=ref)
        self.assertTrue(report['recorded'])
        states = {c['kind']: c['state'] for c in self.context.hypotheses()}
        self.assertEqual(states, {'owner_statement_interpretation': 'conflicting', 'source_report': 'conflicting'})
        # A report cannot supersede the owner's statement.
        refused = self.propose(job, predicate='current_place', value='Seoul', source=ref, supersedes=stated['state_ref'])
        self.assertEqual(refused['reason'], 'invalid_supersedes')

    def test_editing_the_source_message_invalidates_what_was_derived_from_it(self):
        """CT-06/CT-11: an edited owner message is a new revision; derived state goes."""
        self.enable()
        job, message_id = self.request('오늘 재택이야', telegram=True)
        other, _ = self.request('3시까지 회의야')
        self.propose(job, predicate='work_mode', value='remote')
        self.propose(other, predicate='availability_hint', value='회의 중')
        self.now += 60
        self.assertEqual(self.ingest({'message_id': message_id, 'text': '오늘 출근이야', 'edit_date': int(self.now)},
                                     edited=True), 'recorded:text_edit')
        self.assertEqual([c['predicate'] for c in self.context.hypotheses()], ['availability_hint'])
        self.assertIn('invalidated', [row['state'] for row in self.claims()])


class ExpiryAndControls(ContextCase):
    """CT-12/CT-16/CT-18: expiry, rollover, pause, clear and the disabled flow."""

    def test_date_rollover_expires_today_and_retention_prunes(self):
        self.enable()
        self.now = at(SEOUL, 2026, 9, 21, 23, 0)
        job, _ = self.request('오늘은 재택')
        self.propose(job, predicate='work_mode', value='remote')
        self.assertEqual(len(self.context.hypotheses()), 1)
        self.now = at(SEOUL, 2026, 9, 22, 0, 1)
        self.assertEqual(self.context.hypotheses(), [], 'yesterday\'s exception is not today\'s')
        self.now += RETENTION_SECONDS
        self.obs.status()
        self.assertEqual(self.claims(), [], 'pruned after retention without a daemon')

    def test_pause_hides_and_blocks_clear_removes_and_resume_does_not_replay(self):
        self.enable()
        job, _ = self.request('오늘 재택이야')
        self.propose(job, predicate='work_mode', value='remote')
        self.obs.set_controls({'enabled': False})
        self.assertEqual(self.context.hypotheses(), [])
        self.assertEqual(self.propose(job, predicate='work_mode', value='office')['reason'], 'context_paused')
        self.assertIsNone(self.context.snapshot(job), 'off: the old text flow, no section')
        self.now += 60
        self.obs.set_controls({'enabled': True, 'clear': True})
        self.assertEqual(self.claims(), [])
        self.assertEqual(self.context.hypotheses(), [])
        # The pre-clear message cannot bring it back.
        self.assertEqual(self.propose(job, predicate='work_mode', value='remote')['reason'], 'source_unavailable')

    def test_location_refs_are_checked_at_dispatch(self):
        self.enable()
        self.anchors()
        ref = self.live()
        venue = self.venue()
        job, _ = self.request('여기 날씨')
        fresh = self.context.resolve_location(job, ref)
        self.assertEqual((fresh['latitude'], fresh['longitude']), (37.57, 126.98), 'rounded, not the raw point')
        self.assertEqual(fresh['source']['kind'], 'live_position_report')
        self.assertIn('not verified GPS', fresh['source']['basis'])
        self.assertEqual(self.context.resolve_location(job, 'profile:place.home')['label'], '합정')
        self.now += FRESHNESS_SECONDS + 1
        with self.assertRaises(ContextRefusal) as stale:
            self.context.resolve_location(job, ref)
        self.assertEqual(stale.exception.code, 'location_stale')
        self.assertEqual(self.context.resolve_location(job, venue)['source']['kind'], 'place_reference',
                         'a shared place stays a place, not a current position')
        self.obs.set_controls({'enabled': False})
        with self.assertRaises(ContextRefusal) as paused:
            self.context.resolve_location(job, venue)
        self.assertEqual(paused.exception.code, 'context_paused')
        self.obs.set_controls({'enabled': True, 'clear': True})
        for gone in (venue, 'obs:', 'state:x', 'profile:place.moon', 'https://x', None):
            with self.subTest(ref=gone), self.assertRaises(ContextRefusal) as unknown:
                self.context.resolve_location(job, gone)
            self.assertEqual(unknown.exception.code, 'location_ref_unknown')
        # Deleting the anchor (existing Memory deletion) revokes its ref.
        home = next(r for r in self.store.memories(PROFILE_OWNER) if r['memory_key'] == 'profile.place.home')
        self.memory.delete(PROFILE_OWNER, home['id'])
        with self.assertRaises(ContextRefusal):
            self.context.resolve_location(job, 'profile:place.home')

    def test_a_stored_secret_in_an_anchor_never_leaves(self):
        self.enable()
        self.store.secret('telegram_token', 'opaque-telegram-value-123')
        self.memory.remember_profile(PROFILE_OWNER, 'settings', 'profile.place.home', '합정 opaque-telegram-value-123')
        self.memory.remember_profile(PROFILE_OWNER, 'settings', 'profile.place.lab', 'opaque-telegram-value-123')
        job, _ = self.request('집 날씨')
        self.assertEqual(self.context.resolve_location(job, 'profile:place.home')['label'], '합정 [redacted]')
        with self.assertRaises(ContextRefusal):
            self.context.resolve_location(job, 'profile:place.lab')
        self.assertNotIn('opaque-telegram-value-123', self.context.render(job))
        self.assertEqual(redact_known_secrets(self.store, 'x opaque-telegram-value-123'), 'x [redacted]')


class ReviewFindings(ContextCase):
    """#670 review: stale observations, CLI empty value, secrets and consent copy."""

    def test_every_obs_derived_claim_is_capped_at_the_observation_and_stale_is_refused(self):
        self.enable()
        ref = self.live()
        job, _ = self.request('여기야')
        inferred = self.propose(job, predicate='availability_hint', value='외출 중', source=ref, until='today')
        self.assertTrue(inferred['recorded'])
        self.assertLessEqual(self.claims()[-1]['effective_until'], self.now + FRESHNESS_SECONDS)
        stated = self.propose(job, predicate='current_place', value='', place_ref=ref, until='today')
        self.assertLessEqual(self.claims()[-1]['effective_until'], self.now + FRESHNESS_SECONDS,
                             'an owner statement naming a position is capped by it too')
        self.assertTrue(stated['recorded'])
        self.now += FRESHNESS_SECONDS + 1
        for args in ({'source': ref, 'place_ref': ref}, {'place_ref': ref}):
            with self.subTest(args=args):
                refused = self.propose(job, predicate='current_place', value='', until='today', **args)
                self.assertEqual(refused['reason'], 'source_stale')
        venue = self.venue()
        place = self.propose(job, predicate='current_place', value='', source=venue, place_ref=venue)
        self.assertEqual(place['kind'], 'inferred', 'a shared place is never a position report')

    def test_an_empty_value_with_a_place_ref_works_through_the_cli_facade(self):
        from personal_agent.agent_runtime import Capabilities
        from personal_agent.bounded_execution import AgentOSMcpTools, profile_actions
        self.enable()
        ref = self.live()
        job, _ = self.request('나 여기야')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job,))
        caps = Capabilities(self.store, None, {}, '', job, lambda *a: None, document_access=False,
                            allowed_tools=set(profile_actions(AgentOSMcpTools.PROFILE)), current_context=self.context)
        result = AgentOSMcpTools(caps).call('propose_current_state',
                                            {'predicate': 'current_place', 'value': '', 'place_ref': ref})
        self.assertTrue(result['recorded'], result)
        refused = AgentOSMcpTools(caps).call('propose_current_state', {'predicate': 'current_place', 'value': ''})
        self.assertEqual(refused['reason'], 'invalid_value', 'a value or a place_ref is still required')

    def test_a_stored_secret_never_becomes_a_hypothesis_value(self):
        self.enable()
        self.store.secret('telegram_token', 'opaque-telegram-value-123')
        job, _ = self.request('회의 중')
        result = self.propose(job, predicate='availability_hint', value='회의 opaque-telegram-value-123 sk-abcdefghijkl')
        self.assertEqual(result['value'], '회의 [redacted] [redacted]')
        self.assertNotIn('opaque-telegram-value-123', json.dumps(self.claims(), ensure_ascii=False))
        self.assertNotIn('opaque-telegram-value-123', self.context.render(job))

    def test_recorded_arguments_hide_the_proposed_value(self):
        from personal_agent.agent_runtime import recorded_arguments, recorded_calls
        args = {'predicate': 'availability_hint', 'value': 'secret words'}
        self.assertEqual(recorded_arguments('propose_current_state', args)['value'], '[가림: 12자]')
        calls = [{'id': 'c1', 'function': {'name': 'propose_current_state', 'arguments': json.dumps(args)}}]
        tools = {'propose_current_state': {'host_action': 'propose_current_state'}}
        self.assertNotIn('secret words', json.dumps(recorded_calls(calls, tools)))

    def test_withdrawn_strings_follow_pause_correction_and_anchor_changes(self):
        self.enable()
        self.anchors()
        ref = self.live()
        job, _ = self.request('근처')
        self.context.render(job)
        self.assertEqual(self.context.withdrawn_strings(job), [], 'every exposed source still valid')
        self.now += 60
        self.message_id -= 0
        with self.store.db() as db:
            db.execute('UPDATE context_observations SET source_revision=source_revision+1')
        self.assertIn('37.57,126.98', self.context.withdrawn_strings(job), 'a corrected point withdraws the old text')
        self.assertNotIn('합정', self.context.withdrawn_strings(job))
        self.memory.remember_profile(PROFILE_OWNER, 'settings', 'profile.place.home', '망원')
        self.assertIn('합정', self.context.withdrawn_strings(job), 'a corrected anchor withdraws its old label')
        self.assertNotIn('판교', self.context.withdrawn_strings(job))
        self.assertTrue(ref)

    def test_the_settings_consent_copy_says_what_is_sent(self):
        root = Path(__file__).resolve().parents[1] / 'src' / 'personal_agent' / 'web'
        html = (root / 'index.html').read_text()
        app = (root / 'app.js').read_text()
        self.assertNotIn('아직 답변에는 사용하지 않습니다', html)
        self.assertNotIn('not used in answers yet', app)
        self.assertIn('AI에게 보내는 요청에 포함되고', html)
        self.assertIn('included in requests to the AI', app)
        self.assertIn('pause or clear it at any time', app)


class Snapshot(ContextCase):
    """S2: bounded, source-qualified, and absent when off."""

    def test_the_snapshot_carries_time_ages_refs_and_hypotheses(self):
        self.enable()
        self.anchors()
        ref = self.live()
        self.now += 120
        job, _ = self.request('오늘 재택이야')
        self.propose(job, predicate='work_mode', value='remote', place_ref='profile:place.home')
        body = self.context.snapshot(job)
        self.assertEqual(body['as_of'], '2026-09-21T03:02:00Z')
        self.assertEqual(body['timezone'], SEOUL)
        self.assertTrue(body['local_time'].startswith('2026-09-21T12:02+09:00 Mon'))
        self.assertEqual(body['request_sent_at'], '2026-09-21T03:02:00Z')
        [location] = body['locations']
        self.assertEqual((location['ref'], location['status'], location['age_min'], location['approx']),
                         (ref, 'fresh', 2, '37.57,126.98'))
        self.assertEqual([a['ref'] for a in body['anchors']], ['profile:place.home', 'profile:place.work'])
        [hypothesis] = body['hypotheses']
        self.assertEqual((hypothesis['predicate'], hypothesis['place_ref'], hypothesis['state']),
                         ('work_mode', 'profile:place.home', 'supported'))
        text = self.context.render(job)
        self.assertIn('not verified GPS', text)
        self.assertNotIn('37.566512', text, 'no precise coordinate in the model snapshot')
        self.now += FRESHNESS_SECONDS
        self.assertEqual(self.context.snapshot(job)['locations'][0]['status'], 'stale')

    def test_unknown_timezone_is_stated_not_guessed(self):
        self.enable(timezone='')
        body = self.context.snapshot()
        self.assertEqual(body['timezone'], 'unknown')
        self.assertNotIn('local_time', body)

    def test_off_sends_nothing_except_a_location_requested_for_this_work(self):
        job, _ = self.request('여기 날씨', telegram=True)
        self.assertIsNone(self.context.snapshot(job))
        self.obs.open_location_request(job, CHAT, GENERATION)
        self.message_id += 1
        self.assertEqual(self.ingest({'message_id': self.message_id, 'location': dict(POINT)}),
                         'recorded:current_position_report')
        body = self.context.snapshot(job)
        self.assertEqual([item['kind'] for item in body['locations']], ['current_position_report'])
        self.assertNotIn('hypotheses', body)
        self.assertNotIn('anchors', body)
        other, _ = self.request('다른 일')
        self.assertIsNone(self.context.snapshot(other), 'task scope serves only its task')

    def test_the_snapshot_is_bounded_in_entries_and_bytes(self):
        self.enable()
        for index in range(12):
            self.memory.remember_profile(PROFILE_OWNER, 'settings', f'profile.place.p{index:02d}', '가' * 110)
        job, _ = self.request('오늘 재택')
        self.propose(job, predicate='work_mode', value='remote')
        body = self.context.snapshot(job)
        entries = sum(len(body.get(section, [])) for section in ('hypotheses', 'locations', 'anchors'))
        self.assertLessEqual(entries, SNAPSHOT_ENTRIES)
        self.assertLessEqual(len(render(body).encode()), SNAPSHOT_BYTES)
        self.assertEqual(len(body['hypotheses']), 1, 'hypotheses are kept first')

    def test_status_lets_the_owner_inspect_hypotheses(self):
        self.enable()
        job, _ = self.request('오늘 재택')
        self.propose(job, predicate='work_mode', value='remote')
        status = self.context.status()
        self.assertTrue(status['used_in_answers'])
        self.assertEqual([(h['predicate'], h['value'], h['kind']) for h in status['hypotheses']],
                         [('work_mode', 'remote', 'owner_statement_interpretation')])
        self.assertNotIn('latitude', json.dumps(status))


class TurnContextSection(unittest.TestCase):
    """S2/CT-17: the section rides in the one shared context and is counted in its budget."""

    def test_the_section_is_rendered_counted_and_absent_when_empty(self):
        from personal_agent.agent_runtime import (CONTEXT_BUDGET_BYTES, CURRENT_CONTEXT_HEADING, context_sections,
                                                  current_context_section, render_turn_prompt, turn_context)
        history = [{'role': 'user', 'content': 'a'}, {'role': 'assistant', 'content': 'b'},
                   {'role': 'user', 'content': '여기 비 와?'}]
        current = render({'version': 'current-context-v1', 'as_of': '2026-09-21T03:00:00Z', 'timezone': SEOUL})
        for route in ('api', 'cli'):
            context = turn_context(history, route, current_context=current, profile='profile.place.home: 합정')
            text = render_turn_prompt(context)
            self.assertLess(text.index('# Owner profile'), text.index(CURRENT_CONTEXT_HEADING))
            self.assertLess(text.index(CURRENT_CONTEXT_HEADING), text.index('# Current request'))
            self.assertEqual(context_sections(context).split('\n\n')[-1], current_context_section(context))
        for empty in (None, ''):
            context = turn_context(history, 'api', current_context=empty)
            self.assertNotIn('current_context', context)
            self.assertEqual(context_sections(context), '')
            self.assertNotIn(CURRENT_CONTEXT_HEADING, render_turn_prompt(context))
        big = [{'role': 'assistant', 'content': 'x' * 10_000} for _ in range(20)]
        request = 'y' * 5_000
        long_current = 'z' * SNAPSHOT_BYTES
        without = turn_context([*big, {'role': 'user', 'content': request}], 'cli')
        with_current = turn_context([*big, {'role': 'user', 'content': request}], 'cli', current_context=long_current)
        self.assertEqual(with_current['request'], request, 'the request is never shortened')
        self.assertLess(len(with_current['conversation']), len(without['conversation']), 'older turns go first')
        size = sum(len(m['content'].encode()) for m in with_current['conversation'])
        self.assertLessEqual(size + len(request.encode()) + len(with_current['instructions'].encode())
                             + len(current_context_section(with_current).encode()), CONTEXT_BUDGET_BYTES)


if __name__ == '__main__':
    unittest.main()
