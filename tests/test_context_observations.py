"""CONTEXT-INPUT-01 / #626: Telegram location and source-time input.

Every case drives the real ``AgentService.ingest_update`` / ``poll_telegram``
entry point over a temporary QuickStore with a fake Telegram transport, a
counting fake model and an injected clock.  Evidence class: automated
synthetic/fixture only - no live Telegram, device location or provider call
is made and none is claimed.  IDs match the playbook's CT-01..CT-08.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from personal_agent.context_observations import (FRESHNESS_SECONDS, INDEFINITE_LIVE_PERIOD, RETENTION_SECONDS,
                                                  ContextObservations, normalize_point)
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore

CHAT = 4242
FOREIGN = 777
GENERATION = 'g1'
NOW = 1_790_000_000.0
POINT = {'latitude': 37.5665, 'longitude': 126.978, 'horizontal_accuracy': 12.5}


class ContextInputCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parent))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'data'
        self.store = QuickStore(self.root)
        self.calls = []
        self.model_calls = 0
        self.now = NOW
        self.update_id = 100
        self.message_id = 500
        self.service = self.make_service()
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': GENERATION, 'cursor': 0})

    def make_service(self):
        def transport(url, body=None, headers=None, timeout=60):
            self.calls.append((url.rsplit('/', 1)[-1], body))
            if url.endswith('/sendMessage'):
                return {'ok': True, 'result': {'message_id': 9000 + len(self.calls)}}
            return {'ok': True, 'result': True}

        def model(url, body, headers=None, timeout=60):
            self.model_calls += 1
            return {'message': {'content': 'ok'}}

        service = AgentService(self.store, ModelAdapter(model), transport)
        service.context_observations.clock = lambda: self.now
        self.store.secret('telegram_token', 'bot-token')
        return service

    # --- helpers -----------------------------------------------------------

    def enable(self):
        return self.service.set_current_context({'enabled': True})

    def update(self, body, *, edited=False, sender=CHAT, chat=None, chat_type='private', generation=GENERATION,
               update_id=None):
        if update_id is None:
            self.update_id += 1
            update_id = self.update_id
        message = {'from': {'id': sender}, 'chat': {'id': sender if chat is None else chat, 'type': chat_type},
                   **body}
        message.setdefault('message_id', self.message_id)
        message.setdefault('date', int(self.now))
        self.service.ingest_update({'update_id': update_id, ('edited_message' if edited else 'message'): message},
                                   generation)
        return update_id

    def pin(self, location=POINT, **extra):
        self.message_id += 1
        return self.update({'message_id': self.message_id, 'location': dict(location), **extra})

    def text(self, text, date=None):
        self.message_id += 1
        body = {'message_id': self.message_id, 'text': text}
        if date is not None:
            body['date'] = date
        self.update(body)
        return self.message_id

    def rows(self):
        with self.store.db() as db:
            return [dict(row) for row in db.execute('SELECT * FROM context_observations ORDER BY observed_at')]

    def cursor(self):
        return self.store.config('telegram')['cursor']

    def jobs(self):
        return self.store.jobs()


class StorageMigrationTests(ContextInputCase):
    def test_additive_migration_is_idempotent_and_invents_no_source_time(self):
        job = self.store.enqueue('legacy', 'web:1')
        for _ in range(2):
            QuickStore(self.root)
            ContextObservations(self.store)
        with self.store.db() as db:
            columns = {row['name'] for row in db.execute('PRAGMA table_info(jobs)')}
            row = db.execute('SELECT source_at,source_edited_at,source_message_key,created FROM jobs WHERE id=?',
                             (job,)).fetchone()
            indexes = {row['name'] for row in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        self.assertTrue({'source_at', 'source_edited_at', 'source_message_key'} <= columns)
        self.assertIsNone(row['source_at'])
        self.assertIsNone(row['source_message_key'])
        self.assertIsNotNone(row['created'])
        self.assertTrue({'context_observations_use', 'context_observations_source'} <= indexes)

    def test_context_use_is_off_until_the_owner_enables_it(self):
        status = self.service.context_observations.status()
        self.assertFalse(status['enabled'])
        self.assertFalse(status['used_in_answers'])
        self.assertEqual('', status['timezone'])
        self.pin()
        self.assertEqual([], self.rows())
        self.assertEqual(self.update_id + 1, self.cursor())


class OwnerControlTests(ContextInputCase):
    def test_controls_accept_exactly_enabled_timezone_clear(self):
        status = self.service.set_current_context({'enabled': True, 'timezone': 'Asia/Seoul'})
        self.assertTrue(status['enabled'])
        self.assertEqual('Asia/Seoul', status['timezone'])
        for bad in ({}, {'epoch': 9}, {'enabled': 'yes'}, {'timezone': 'Mars/Base'}, {'timezone': '../etc/passwd'},
                    {'clear': False}, {'retention': 10**9}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.service.set_current_context(bad)
        self.assertEqual('Asia/Seoul', self.service.context_observations.status()['timezone'])
        self.assertEqual('', self.service.set_current_context({'timezone': ''})['timezone'])

    def test_bad_stored_settings_fall_back_to_safe_defaults(self):
        self.store.put('current_context', {'enabled': 'true', 'epoch': -1, 'cutoff': float('inf'),
                                           'timezone': 'Nowhere/City'})
        settings = self.service.context_observations.settings()
        self.assertEqual((False, 0, 0.0, ''), (settings['enabled'], settings['epoch'], settings['cutoff'],
                                               settings['timezone']))

    def test_status_never_returns_coordinates(self):
        self.enable()
        self.message_id += 1
        self.update({'message_id': self.message_id, 'venue': {'location': POINT, 'title': '서울시청',
                                                               'address': '세종대로 110'}})
        status = self.service.settings()['current_context']
        encoded = json.dumps(status)
        self.assertNotIn('37.5665', encoded)
        self.assertNotIn('126.978', encoded)
        self.assertNotIn('세종대로', encoded)
        self.assertEqual('place_reference', status['observations'][0]['kind'])
        self.assertEqual('서울시청', status['observations'][0]['label'])


class CT01OwnerAndForeignTests(ContextInputCase):
    def test_requested_static_location_from_owner_is_a_current_position_report(self):
        job = self.store.enqueue('여기 날씨 알려줘', 'tg:g1:1', f'telegram:{GENERATION}', CHAT)
        self.service.request_current_location(job, '이 위치로 날씨를 확인할게요.')
        prompt = [body for method, body in self.calls if method == 'sendMessage'][-1]
        self.assertTrue(prompt['reply_markup']['keyboard'][0][0]['request_location'])
        self.assertTrue(prompt['reply_markup']['one_time_keyboard'])
        self.now += 10
        self.pin()
        rows = self.rows()
        self.assertEqual(1, len(rows))
        self.assertEqual('current_position_report', rows[0]['source_kind'])
        self.assertEqual(job, rows[0]['source_job_id'])
        self.assertEqual(self.now + FRESHNESS_SECONDS, rows[0]['valid_until'])
        # Consumed once: a second unsolicited pin is only a place reference.
        self.pin()
        self.assertEqual([], [r for r in self.rows()[1:] if r['source_kind'] != 'place_reference'])
        # Context reuse is off: only this task may use the requested point.
        usable = self.service.context_observations.usable(job_id=job)
        self.assertEqual(['current_position_report'], [entry['kind'] for entry in usable])
        self.assertEqual([], self.service.context_observations.usable(job_id='other'))

    def test_foreign_owner_chat_and_generation_are_denied(self):
        self.enable()
        job = self.store.enqueue('여기 날씨', 'tg:g1:1', f'telegram:{GENERATION}', CHAT)
        self.service.request_current_location(job, '위치를 보내 주세요.')
        self.message_id += 1
        self.update({'message_id': self.message_id, 'location': POINT}, sender=FOREIGN)
        self.update({'message_id': self.message_id, 'location': POINT}, chat=CHAT + 1)
        self.update({'message_id': self.message_id, 'location': POINT}, chat_type='group')
        self.update({'message_id': self.message_id, 'location': POINT}, generation='g0')
        self.assertEqual([], self.rows())
        # The pending request was not consumed by any foreign update.
        self.pin()
        self.assertEqual(['current_position_report'], [row['source_kind'] for row in self.rows()])

    def test_unpaired_pairing_path_still_runs_first_and_records_nothing(self):
        self.enable()
        cfg = self.store.config('telegram')
        cfg.update(user_id=None, pair_code='abc123', pair_expires=4_000_000_000)
        self.store.put('telegram', cfg)
        self.message_id += 1
        self.update({'message_id': self.message_id, 'text': '/start abc123'}, sender=FOREIGN)
        self.assertEqual(FOREIGN, self.store.config('telegram')['user_id'])
        self.assertEqual([], self.rows())


class CT02ReplayAndCrashTests(ContextInputCase):
    def test_duplicate_update_does_not_duplicate_observation_work_or_cursor(self):
        self.enable()
        self.message_id += 1
        body = {'message_id': self.message_id, 'location': POINT}
        update_id = self.update(body)
        self.update(body, update_id=update_id)
        self.assertEqual(1, len(self.rows()))
        self.assertEqual(update_id + 1, self.cursor())
        self.assertEqual([], self.jobs())

    def test_failure_before_commit_rolls_back_cursor_and_state_then_retry_records_once(self):
        self.enable()
        self.message_id += 1
        body = {'message_id': self.message_id, 'location': POINT}
        real = ContextObservations.ingest_telegram

        def crash(obs, db, *args):
            real(obs, db, *args)
            raise RuntimeError('crash before commit')

        with mock.patch.object(ContextObservations, 'ingest_telegram', crash), self.assertRaises(RuntimeError):
            self.update(body, update_id=200)
        self.assertEqual([], self.rows())
        self.assertEqual(0, self.cursor())
        self.update(body, update_id=200)
        self.update(body, update_id=200)
        self.assertEqual(1, len(self.rows()))
        self.assertEqual(201, self.cursor())

    def test_text_crash_rolls_back_work_and_cursor(self):
        with mock.patch.object(ContextObservations, 'note_text_source', side_effect=RuntimeError('boom')), \
                self.assertRaises(RuntimeError):
            self.text('점심 추천해줘')
        self.assertEqual([], self.jobs())
        self.assertEqual(0, self.cursor())


class CT03LiveShareTests(ContextInputCase):
    def start_live(self, period=900):
        self.enable()
        self.message_id += 1
        self.live_id = self.message_id
        self.live_date = int(self.now)
        self.update({'message_id': self.live_id, 'location': {**POINT, 'live_period': period}})

    def edit_live(self, latitude, edit_date, period=900, update_id=None):
        location = {**POINT, 'latitude': latitude}
        if period is not None:
            location['live_period'] = period
        return self.update({'message_id': self.live_id, 'date': self.live_date, 'edit_date': edit_date,
                            'location': location}, edited=True, update_id=update_id)

    def test_live_edit_updates_same_source_and_stale_edit_cannot_replace_newer(self):
        self.start_live()
        self.now += 60
        self.edit_live(37.6, int(self.now))
        stale_update = self.update_id + 5
        self.edit_live(37.9, int(self.now) - 30, update_id=stale_update)
        rows = self.rows()
        self.assertEqual(1, len(rows))
        self.assertEqual('live_position_report', rows[0]['source_kind'])
        self.assertEqual(2, rows[0]['source_revision'])
        self.assertEqual(37.6, json.loads(rows[0]['payload_json'])['latitude'])
        self.assertEqual([], self.jobs())

    def test_stop_ends_live_status_without_claiming_movement(self):
        self.start_live()
        self.now += 60
        self.edit_live(37.6, int(self.now))
        self.now += 60
        self.edit_live(12.0, int(self.now), period=None)
        row = self.rows()[0]
        payload = json.loads(row['payload_json'])
        self.assertEqual('ended', row['state'])
        self.assertFalse(payload['live'])
        self.assertEqual(37.6, payload['latitude'])
        self.assertEqual('stale', self.service.context_observations.usable()[0]['freshness'])

    def test_share_window_expiry_and_indefinite_share_both_age_between_updates(self):
        self.start_live(period=120)
        row = self.rows()[0]
        self.assertEqual(self.live_date + 120, row['valid_until'])
        self.now += 121
        self.assertEqual('stale', self.service.context_observations.usable()[0]['freshness'])
        self.service.set_current_context({'clear': True})
        self.now += 1
        self.start_live(period=INDEFINITE_LIVE_PERIOD)
        self.assertEqual('fresh', self.service.context_observations.usable()[0]['freshness'])
        self.now += FRESHNESS_SECONDS + 1
        self.assertEqual('stale', self.service.context_observations.usable()[0]['freshness'])
        # No update arrived: no fabricated stop event either.
        self.assertEqual('current', self.rows()[0]['state'])


class CT04ReferenceTests(ContextInputCase):
    def test_venue_forwarded_and_future_meeting_pins_are_references(self):
        self.enable()
        job = self.store.enqueue('다른 요청', 'tg:g1:1', f'telegram:{GENERATION}', CHAT)
        self.service.request_current_location(job, '위치를 보내 주세요.')
        self.message_id += 1
        self.update({'message_id': self.message_id, 'venue': {'location': POINT, 'title': '카페'}})
        self.pin(forward_origin={'type': 'user', 'date': int(self.now) - 99})
        self.text('내일 여기서 만나')
        with self.store.db() as db:
            request_id = db.execute('SELECT id FROM context_location_requests').fetchone()['id']
        self.service.context_observations.cancel_location_request(request_id)
        self.pin()
        kinds = [row['source_kind'] for row in self.rows()]
        self.assertEqual(['place_reference'] * 3, kinds)
        self.assertEqual(['reference'] * 3, [entry['freshness'] for entry in self.service.context_observations.usable()])


class CT05ValidationTests(ContextInputCase):
    def test_invalid_numbers_and_ranges_are_rejected(self):
        for bad in ({'latitude': float('nan'), 'longitude': 1}, {'latitude': 1, 'longitude': float('inf')},
                    {'latitude': True, 'longitude': 1}, {'latitude': 91, 'longitude': 1},
                    {'latitude': 1, 'longitude': -181}, {'latitude': '1', 'longitude': 1},
                    {'latitude': 1, 'longitude': 1, 'horizontal_accuracy': -1},
                    {'latitude': 1, 'longitude': 1, 'horizontal_accuracy': 1501},
                    {'latitude': 1, 'longitude': 1, 'horizontal_accuracy': float('nan')}):
            with self.subTest(bad=bad):
                self.assertIsNone(normalize_point(bad))
        self.assertIsNone(normalize_point({'latitude': 1, 'longitude': 2})['accuracy_m'])

    def test_rejected_updates_advance_cursor_without_state(self):
        self.enable()
        self.pin({'latitude': float('nan'), 'longitude': 1})
        self.pin({'latitude': 100, 'longitude': 1})
        self.message_id += 1
        self.update({'message_id': self.message_id, 'location': POINT, 'date': int(self.now) + 3600})
        self.message_id += 1
        self.update({'message_id': self.message_id, 'location': POINT, 'date': None})
        self.update({'message_id': True, 'location': POINT})
        self.assertEqual([], self.rows())
        self.assertEqual(self.update_id + 1, self.cursor())

    def test_missing_accuracy_stays_unknown(self):
        self.enable()
        self.pin({'latitude': 1.5, 'longitude': 2.5})
        self.assertIsNone(json.loads(self.rows()[0]['payload_json'])['accuracy_m'])

    def test_future_text_source_time_stays_unknown(self):
        self.text('안녕', date=int(self.now) + 3600)
        job = self.store.job(self.jobs()[0]['id'])
        self.assertIsNone(job['source_at'])
        self.assertIsNotNone(job['source_message_key'])


class CT06SourceTimeAndEditTests(ContextInputCase):
    def test_original_event_time_differs_from_receive_time_and_reaches_history(self):
        sent = int(self.now) - 3 * 3600
        self.text('어제 말한 곳 기억나?', date=sent)
        job = self.store.job(self.jobs()[0]['id'])
        self.assertEqual(sent, job['source_at'])
        self.assertGreater(job['created'], sent + 3600)
        self.service.run_one()
        rows = self.store.history()
        owner = [row for row in rows if row['role'] == 'user'][-1]
        assistant = [row for row in rows if row['role'] == 'assistant'][-1]
        self.assertEqual(sent, owner['source_at'])
        self.assertIsNone(assistant['source_at'])

    def test_edited_text_invalidates_source_without_replaying_the_action(self):
        self.enable()
        message_id = self.text('오늘은 회사에서 일해')
        self.service.run_one()
        job = self.jobs()[0]
        calls_before = self.model_calls
        self.now += 120
        self.update({'message_id': message_id, 'date': int(self.now) - 120, 'edit_date': int(self.now),
                     'text': '오늘은 집에서 일해'}, edited=True)
        self.assertEqual(1, len(self.jobs()))
        self.assertEqual(calls_before, self.model_calls)
        self.assertEqual(self.now, self.store.job(job['id'])['source_edited_at'])
        self.assertEqual('오늘은 회사에서 일해', self.store.job(job['id'])['message'])
        row = [r for r in self.rows() if r['source_kind'] == 'text_edit'][0]
        self.assertEqual(job['id'], row['source_job_id'])
        self.assertEqual('오늘은 집에서 일해', json.loads(row['payload_json'])['text'])
        self.now += 60
        self.update({'message_id': message_id, 'date': int(self.now) - 180, 'edit_date': int(self.now),
                     'text': '오늘은 카페에서 일해'}, edited=True)
        self.assertEqual(2, [r for r in self.rows() if r['source_kind'] == 'text_edit'][0]['source_revision'])
        self.assertEqual(1, len(self.jobs()))

    def test_edit_with_context_off_records_revision_but_keeps_no_text(self):
        message_id = self.text('회의 3시')
        self.update({'message_id': message_id, 'edit_date': int(self.now) + 1, 'text': '회의 4시'}, edited=True)
        row = self.rows()[0]
        self.assertIsNone(json.loads(row['payload_json'])['text'])
        self.assertEqual(1, len(self.jobs()))


class CT07PauseClearRetentionTests(ContextInputCase):
    def test_pause_stops_new_writes_and_resume_does_not_backfill(self):
        self.enable()
        self.pin()
        self.service.set_current_context({'enabled': False})
        self.now += 10
        paused_date = int(self.now)
        self.pin()
        self.assertEqual(1, len(self.rows()))
        self.assertEqual([], self.service.context_observations.usable())
        self.now += 10
        self.enable()
        # A late delivery of the pin sent while paused is not backfilled.
        self.message_id += 1
        self.update({'message_id': self.message_id, 'location': POINT, 'date': paused_date})
        self.assertEqual(1, len(self.rows()))

    def test_clear_restart_and_late_updates_do_not_resurrect_context(self):
        self.enable()
        self.message_id += 1
        live_id, live_date = self.message_id, int(self.now)
        self.update({'message_id': live_id, 'location': {**POINT, 'live_period': 3600}})
        message_id = self.text('오늘은 집에서 일해')
        self.now += 60
        status = self.service.set_current_context({'clear': True})
        self.assertEqual([], status['observations'])
        self.assertEqual([], self.rows())
        self.service = self.make_service()          # restart on the same store
        self.now += 30
        self.update({'message_id': live_id, 'date': live_date, 'edit_date': int(self.now),
                     'location': {**POINT, 'live_period': 3600}}, edited=True)
        self.update({'message_id': message_id, 'date': live_date, 'edit_date': live_date + 1,
                     'text': '늦게 도착한 수정'}, edited=True)
        self.assertEqual([], self.rows())
        # Ordinary text still works with context cleared.
        self.text('점심 추천해줘')
        self.assertEqual(2, len(self.jobs()))

    def test_retention_expiry_is_enforced_on_read_and_pruned_on_next_use(self):
        self.enable()
        self.pin()
        self.now += RETENTION_SECONDS + 1
        self.assertEqual([], self.service.context_observations.usable())
        self.assertEqual([], self.service.context_observations.status()['observations'])
        self.assertEqual([], self.rows())
        self.message_id += 1
        self.update({'message_id': self.message_id, 'location': POINT, 'date': int(self.now) - RETENTION_SECONDS - 5})
        self.assertEqual([], self.rows())


class CT08NoModelOrWorkTests(ContextInputCase):
    def test_twenty_location_updates_make_no_model_tool_work_or_bubble(self):
        self.enable()
        self.message_id += 1
        live_id, live_date = self.message_id, int(self.now)
        self.update({'message_id': live_id, 'location': {**POINT, 'live_period': 3600}})
        for step in range(19):
            self.now += 20
            self.update({'message_id': live_id, 'date': live_date, 'edit_date': int(self.now),
                         'location': {**POINT, 'latitude': 37.5 + step / 1000, 'live_period': 3600}}, edited=True)
        self.assertEqual(0, self.model_calls)
        self.assertEqual([], self.calls)
        self.assertEqual([], self.jobs())
        self.assertFalse(self.service.run_one())
        self.assertEqual(1, len(self.rows()))
        self.assertEqual(20, self.rows()[0]['source_revision'])

    def test_poll_requests_edited_messages_and_text_callback_stop_still_work(self):
        self.enable()
        updates = [
            {'update_id': 1, 'message': {'message_id': 1, 'date': int(self.now), 'from': {'id': CHAT},
                                         'chat': {'id': CHAT, 'type': 'private'}, 'location': POINT}},
            {'update_id': 2, 'message': {'message_id': 2, 'date': int(self.now), 'from': {'id': CHAT},
                                         'chat': {'id': CHAT, 'type': 'private'}, 'text': '안녕'}},
            {'update_id': 3, 'callback_query': {'id': 'cb', 'from': {'id': CHAT}, 'data': 'noop',
                                                'message': {'message_id': 9, 'chat': {'id': CHAT, 'type': 'private'}}}},
            {'update_id': 4, 'stopped_message_generation': {'chat': {'id': CHAT, 'type': 'private'}, 'draft_id': 1}},
        ]
        polled = []

        def transport(url, body=None, headers=None, timeout=60):
            method = url.rsplit('/', 1)[-1]
            if method == 'getUpdates':
                polled.append(body)
                return {'ok': True, 'result': updates}
            return {'ok': True, 'result': True}

        self.service.telegram_transport = transport
        self.service.poll_telegram()
        self.assertIn('edited_message', polled[0]['allowed_updates'])
        self.assertIn('stopped_message_generation', polled[0]['allowed_updates'])
        self.assertEqual(5, self.cursor())
        self.assertEqual(['안녕'], [job['message'] for job in self.jobs()])
        self.assertEqual(['place_reference'], [row['source_kind'] for row in self.rows()])
        self.assertEqual(0, self.model_calls)


if __name__ == '__main__':
    unittest.main()
