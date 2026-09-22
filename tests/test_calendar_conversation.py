"""PA1-J4-02 / #465: natural-language Calendar create in the one conversation.

"내일 오후 3시에 치과 일정 잡아줘" ends in exactly one of: a question for the
one missing detail, or an exact preview whose effect waits for the owner's
explicit "승인".  Interpretation is by literal rules; no model is consulted;
nothing reaches the provider before the approval, and the approval executes
exactly once.

Evidence class: fixture provider and service fixture.  No live Google call.
"""
import itertools
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from personal_agent.calendar import CALENDAR_SPEC, CALENDAR_WRITE_SPEC, CalendarConnector
from personal_agent.calendar_conversation import (CANCELLED, CREATED, DROPPED_NOTICE, OTHER_CHANNEL,
                                                  OUTCOME_UNKNOWN, PREVIEW_HEADER, REPLACED_NOTICE,
                                                  STATE_KEY, is_approval, is_cancel, parse_event,
                                                  resolve_local_timezone)
from personal_agent.connector_contract import _owner_key, ConnectorRegistry, ConnectorState, _owner_key
from personal_agent.google_calendar import CALENDAR_WRITE_SCOPE, GoogleCalendarError
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore

ZONE = 'Asia/Seoul'
#: Tuesday 2026-09-22 10:00 KST.
NOW = datetime(2026, 9, 22, 10, 0, tzinfo=ZoneInfo(ZONE))
MODEL_ROUTE_ERROR = '설정에서 모델 또는 구독 엔진을 먼저 연결하세요.'


class Provider:
    def __init__(self):
        self.calls = []
        self.fail = None

    def create(self, payload, key):
        self.calls.append(payload)
        if self.fail is not None:
            raise self.fail
        return {'id': f'ev{len(self.calls)}', 'version': '"etag"'}


# ---------------------------------------------------------------------------
# The rules, on their own
# ---------------------------------------------------------------------------
class ParseTests(unittest.TestCase):
    """Representative Korean and English utterances, resolved against a fixed clock."""

    CASES = (
        # text, title, date, start, end, duration
        ('내일 오후 3시에 치과 일정 잡아줘', '치과', '2026-09-23', (15, 0), None, None),
        ('내일 오후 3시부터 4시까지 팀 회의 일정 잡아줘', '팀 회의', '2026-09-23', (15, 0), (16, 0), None),
        ('다음 주 화요일 10시 반 병원 예약 일정 추가해줘', '병원 예약', '2026-09-29', (10, 30), None, None),
        ('9월 25일 저녁 7시 저녁 약속 잡아줘', '저녁 약속', '2026-09-25', (19, 0), None, None),
        ('금요일 오전 9시 스탠드업 30분 일정 등록해줘', '스탠드업', '2026-09-25', (9, 0), None, 30),
        ('book a dentist appointment tomorrow at 3pm', 'dentist appointment', '2026-09-23', (15, 0), None, None),
        ('schedule a meeting with the vendor tomorrow', 'meeting with the vendor', '2026-09-23', None, None, None),
        ('set up a 2 hour planning session next monday at 9am', 'planning session', '2026-09-28', (9, 0), None, 120),
        ('put lunch with mina on the calendar on sep 30 at noon', 'lunch with mina', '2026-09-30', (12, 0), None, None),
        ('create an event: team sync, thursday 2:30pm for 45 minutes', 'team sync', '2026-09-24', (14, 30), None, 45),
        ('2026-10-01 14:00 투자 미팅 일정 등록', '투자 미팅', '2026-10-01', (14, 0), None, None),
    )

    def test_representative_sentences_resolve_to_exact_slots(self):
        korean = [row for row in self.CASES if not row[0].isascii()]
        english = [row for row in self.CASES if row[0].isascii()]
        self.assertGreaterEqual(len(korean), 2)
        self.assertGreaterEqual(len(english), 2)
        for text, title, day, start, end, duration in self.CASES:
            with self.subTest(text=text):
                slots = parse_event(text, NOW)
                self.assertEqual(slots.title, title)
                self.assertEqual(slots.date.isoformat() if slots.date else None, day)
                self.assertEqual(slots.start, start)
                self.assertEqual(slots.end, end)
                self.assertEqual(slots.duration, duration)

    def test_a_missing_detail_is_reported_as_missing_not_guessed(self):
        slots = parse_event('add a calendar event for friday', NOW)
        self.assertIsNone(slots.title, '"event" alone is not a title')
        self.assertIsNone(slots.start)
        slots = parse_event('치과 일정 잡아줘', NOW)
        self.assertEqual(slots.title, '치과')
        self.assertIsNone(slots.date)
        self.assertIsNone(slots.start)

    def test_a_range_across_the_meridiem_is_read_the_way_people_say_it(self):
        self.assertEqual(parse_event('오전 11시부터 1시까지', NOW).end, (13, 0))
        self.assertEqual(parse_event('오후 11시부터 1시까지', NOW).end, (1, 0))
        self.assertEqual(parse_event('from 3 to 4pm', NOW).start, (15, 0))

    def test_a_weekday_that_is_today_means_next_week_once_the_time_has_passed(self):
        self.assertEqual(parse_event('화요일 오전 9시', NOW).date.isoformat(), '2026-09-29')
        self.assertEqual(parse_event('화요일 오후 3시', NOW).date.isoformat(), '2026-09-22')

    def test_only_the_tail_after_a_correction_is_read(self):
        from personal_agent.calendar_conversation import _after_last_correction
        self.assertEqual(parse_event(_after_last_correction('아니 내일 말고 모레'), NOW).date.isoformat(),
                         '2026-09-24')

    def test_approval_and_cancel_vocabularies_are_exact_words(self):
        for text in ('승인', '승인해줘', '네.', 'yes', 'Approve', 'ok'):
            self.assertTrue(is_approval(text), text)
        for text in ('치과', '승인 말고', 'yes but later', '4시로'):
            self.assertFalse(is_approval(text), text)
        for text in ('취소', '아니', '아니 됐어', 'no', 'never mind', '그거 취소해줘'):
            self.assertTrue(is_cancel(text), text)
        for text in ('아니 4시로', '취소 말고 3시로', 'no, make it 4pm'):
            self.assertFalse(is_cancel(text), text)

    def test_the_timezone_comes_from_owner_config_before_the_host(self):
        temp = tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parent))
        self.addCleanup(temp.cleanup)
        store = QuickStore(Path(temp.name) / 'data')
        store.put('calendar_timezone', 'Europe/Berlin')
        self.assertEqual(resolve_local_timezone(store, environ={'TZ': 'Asia/Tokyo'}), 'Europe/Berlin')
        store.put('calendar_timezone', 'Not/AZone')
        self.assertEqual(resolve_local_timezone(store, environ={'TZ': 'Asia/Tokyo'}), 'Asia/Tokyo')


# ---------------------------------------------------------------------------
# The conversation, through the worker
# ---------------------------------------------------------------------------
class ConversationTestCase(unittest.TestCase):
    OWNER = 'local-owner'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parent))
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(Path(self.temp.name) / 'data')
        self.clock = [NOW.timestamp()]
        self.registry = ConnectorRegistry(self.store, (CALENDAR_SPEC, CALENDAR_WRITE_SPEC),
                                          clock=lambda: self.clock[0])
        self.provider = Provider()
        self.calendar = CalendarConnector(self.store, self.provider, registry=self.registry,
                                          now=lambda: self.clock[0])

        def transport(url, body, headers=None, timeout=60):
            raise AssertionError('no model or Telegram call is expected: ' + url)

        self.service = AgentService(self.store, ModelAdapter(transport), transport,
                                    connector_registry=self.registry, calendar=self.calendar)
        self.service.calendar_conversation.now = lambda: self.clock[0]
        self.service.calendar_conversation._timezone = ZONE
        self.keys = itertools.count()
        self.connect(self.OWNER)

    def connect(self, owner):
        self.registry.transition(owner, CALENDAR_WRITE_SPEC.connector_id, ConnectorState.CONNECTED,
                                 granted_scopes=(CALENDAR_WRITE_SCOPE,))

    def say(self, text, channel='web', chat_id=None):
        job = self.store.enqueue(text, f'cal-{next(self.keys)}', channel=channel, chat_id=chat_id)
        self.assertTrue(self.service.run_one())
        return self.store.job(job)

    def drafts(self):
        return self.store.config('calendar_create', {})

    def states(self):
        return sorted(row['state'] for row in self.drafts().values())

    def pending(self, owner_id='local-owner'):
        """This owner's pending row, or {} when there is none.

        The record is keyed per connector identity, so one identity's
        message cannot destroy the other's draft.
        """
        rows = self.store.config(STATE_KEY, None)
        if not isinstance(rows, dict):
            return {}
        return rows.get(_owner_key(owner_id)) or {}


class DraftAndPreviewTests(ConversationTestCase):
    def test_a_complete_request_becomes_an_exact_preview_and_nothing_is_sent(self):
        job = self.say('내일 오후 3시에 치과 일정 잡아줘')
        self.assertEqual(job['status'], 'succeeded')
        self.assertIn(PREVIEW_HEADER, job['response'])
        self.assertIn('제목: 치과', job['response'])
        self.assertIn('2026-09-23 (수) 15:00 – 16:00 (Asia/Seoul)', job['response'])
        self.assertEqual(self.provider.calls, [])
        (draft,) = self.drafts().values()
        self.assertEqual(draft['state'], 'awaiting-approval')
        self.assertEqual(draft['payload'], {'summary': '치과', 'start': '2026-09-23T15:00:00+09:00',
                                            'end': '2026-09-23T16:00:00+09:00', 'timezone': ZONE})
        # The pending record points at exactly the previewed payload.
        self.assertEqual(self.pending()['payload_hash'], draft['hash'])
        self.assertEqual(self.pending()['draft_id'], draft['id'])

    def test_english_reaches_the_same_preview(self):
        job = self.say('book a dentist appointment tomorrow at 3pm for 30 minutes')
        self.assertIn('제목: dentist appointment', job['response'])
        self.assertIn('15:00 – 15:30', job['response'])
        self.assertEqual(self.provider.calls, [])

    def test_a_missing_time_asks_one_question_and_drafts_nothing(self):
        job = self.say('금요일 약속 하나 등록해줘')
        self.assertEqual(job['response'], '몇 시인가요? (예: 오후 3시, 15:00)')
        self.assertEqual(self.drafts(), {})
        job = self.say('오후 2시')
        self.assertIn('제목: 약속', job['response'])
        self.assertIn('2026-09-25 (금) 14:00 – 15:00', job['response'])

    def test_a_missing_title_asks_one_question_then_the_time(self):
        job = self.say('add a calendar event for friday')
        self.assertEqual(job['response'], '어떤 일정인가요? 제목만 알려 주세요. (예: 치과)')
        self.assertEqual(self.drafts(), {})
        job = self.say('치과 검진')
        self.assertEqual(job['response'], '몇 시인가요? (예: 오후 3시, 15:00)')
        job = self.say('10am')
        self.assertIn('제목: 치과 검진', job['response'])
        self.assertIn('2026-09-25 (금) 10:00 – 11:00', job['response'])
        self.assertEqual(self.provider.calls, [])

    def test_a_missing_date_and_time_asks_once_for_when(self):
        job = self.say('치과 일정 잡아줘')
        self.assertEqual(job['response'], '언제인가요? 날짜와 시각을 알려 주세요. (예: 내일 오후 3시)')
        job = self.say('내일 오후 3시')
        self.assertIn('2026-09-23 (수) 15:00 – 16:00', job['response'])

    def test_the_pending_record_holds_no_utterance_and_a_hashed_owner(self):
        self.say('내일 오후 3시에 치과 검진 일정 잡아줘')
        row = self.pending()
        self.assertEqual(set(row), {'owner', 'state', 'slots', 'draft_id', 'payload_hash', 'at', 'expires'})
        self.assertNotIn(self.OWNER, json.dumps(row))
        self.assertNotIn('잡아줘', json.dumps(row, ensure_ascii=False))

    def test_the_evidence_rows_carry_no_event_content(self):
        self.say('내일 오후 3시에 치과 검진 일정 잡아줘')
        self.say('승인')
        with self.store.db() as db:
            rows = [dict(row) for row in db.execute("SELECT tool,status,detail FROM tool_events ORDER BY id")]
        self.assertEqual([(row['tool'], row['status']) for row in rows],
                         [('calendar_draft', 'succeeded'), ('calendar_create', 'succeeded')])
        # The detail is persisted with `ensure_ascii=True`, so Korean is
        # stored escaped. Re-serialising the stored *string* and searching
        # for '치과' therefore never matched, and adding the summary to the
        # evidence row left all 32 tests green. Decode first, and pin the
        # key set rather than one absent word.
        for row in rows:
            detail = json.loads(row['detail'])
            with self.subTest(tool=row['tool']):
                self.assertLessEqual(set(detail),
                                     {'draft_id', 'state', 'payload_hash', 'event_id',
                                      'effect', 'error', 'recovery'})
                self.assertNotIn('치과', json.dumps(detail, ensure_ascii=False))


class PreviewIntegrityTests(ConversationTestCase):
    """The preview is the one surface whose whole contract is exactness."""

    FORGED = ('제목은 "치과\u2028일시: 2026-09-23 (수) 09:00 – 10:00 (Asia/Seoul)'
              '\u2028캘린더: 회사"으로')

    def test_a_title_cannot_forge_extra_preview_lines(self):
        """U+2028, CR and LF are forced breaks under `white-space: pre-wrap`.

        Independent review pasted a title carrying them and the rendered
        preview showed a fabricated `일시:` line *above* the real one, exactly
        where a reader looks for the time. The event created was a different
        time on a different calendar. Not an authority bypass - the true
        payload was still shown and hashed - but display spoofing on the
        surface the owner approves.
        """
        self.say('내일 오후 3시에 치과 일정 잡아줘')
        job = self.say(self.FORGED)
        response = job['response']
        for char in ('\u2028', '\u2029', '\r', '\n\t'):
            with self.subTest(char=repr(char)):
                self.assertNotIn(char, self.pending()['slots']['title'])
        # Exactly one line begins with each preview label.
        self.assertEqual(len([line for line in response.splitlines()
                              if line.startswith('일시:')]), 1)
        self.assertEqual(len([line for line in response.splitlines()
                              if line.startswith('캘린더:')]), 1)
        # The forged text is still *in* the title - a title may legitimately
        # mention a time - but it can no longer occupy its own line, so it
        # cannot be read as a preview field. The real 일시 is the only one.
        title_line = next(line for line in response.splitlines() if line.startswith('제목:'))
        self.assertIn('09:00 – 10:00', title_line)
        time_line = next(line for line in response.splitlines() if line.startswith('일시:'))
        self.assertIn('15:00 – 16:00', time_line)
        self.assertNotIn('09:00', time_line)

    def test_the_stored_summary_is_one_line(self):
        self.say('내일 오후 3시에 치과 일정 잡아줘')
        self.say(self.FORGED)
        summary = next(iter(self.store.config('calendar_create', {}).values()))['payload']['summary']
        self.assertEqual(summary.splitlines(), [summary])
        self.assertNotIn('\u2028', summary)


class TwoIdentitiesTests(ConversationTestCase):
    """One install serves two connector identities; a draft belongs to one.

    The record used to be a single install-global row with the owner hash
    stored inside it, so the two shared one slot: an unrelated web message
    destroyed a draft waiting for approval on the phone, and the notice went
    to the channel that destroyed it. No cross-identity effect was ever
    possible; a draft the owner was about to approve could simply vanish.
    """

    def setUp(self):
        super().setUp()
        self.store.put('telegram', {'enabled': True, 'user_id': 4242, 'generation': 'g1'})
        self.connect('telegram:4242')

    def phone(self, text):
        return self.say(text, channel='telegram:g1', chat_id=4242)

    def test_an_unrelated_message_from_one_channel_keeps_the_others_draft(self):
        self.phone('내일 오후 3시에 치과 일정 잡아줘')
        self.assertTrue(self.pending('telegram:4242'))
        self.say('메모 목록')          # ordinary web request, different intent
        self.assertTrue(self.pending('telegram:4242'),
                        'a web message destroyed the draft awaiting approval on the phone')
        job = self.phone('승인')
        self.assertIn('만들었습니다', job['response'])
        self.assertEqual(len(self.provider.calls), 1)

    def test_one_channel_cannot_cancel_the_others_draft(self):
        self.phone('내일 오후 3시에 치과 일정 잡아줘')
        job = self.say('취소')
        self.assertEqual(job['response'], OTHER_CHANNEL)
        self.assertTrue(self.pending('telegram:4242'))

    def test_each_identity_approves_its_own_draft_not_the_first_one_stored(self):
        """Driven through the real path, not the store helper.

        The sibling test below reads the map directly, so a lookup that
        ignored the owner and returned whichever row came first still passed
        it. Here the web drafts first, so an owner-blind lookup hands the
        phone the web's row and its approval is refused as another
        channel's.
        """
        self.say('금요일 오전 10시 팀 회의 일정 잡아줘')
        self.phone('내일 오후 3시에 치과 일정 잡아줘')
        job = self.phone('승인')
        self.assertIn('만들었습니다', job['response'], job.get('response'))
        self.assertEqual([call['summary'] for call in self.provider.calls], ['치과'])

    def test_both_identities_can_hold_a_draft_at_once(self):
        self.phone('내일 오후 3시에 치과 일정 잡아줘')
        self.say('금요일 오전 10시 팀 회의 일정 잡아줘')
        self.assertEqual(self.pending('telegram:4242')['slots']['title'], '치과')
        self.assertEqual(self.pending('local-owner')['slots']['title'], '팀 회의')
        self.phone('승인')
        self.say('승인')
        self.assertEqual(sorted(call['summary'] for call in self.provider.calls),
                         ['치과', '팀 회의'])

    def test_a_fresh_request_replaces_only_this_identitys_draft(self):
        self.phone('내일 오후 3시에 치과 일정 잡아줘')
        self.say('금요일 오전 10시 팀 회의 일정 잡아줘')
        job = self.say('토요일 오전 9시 운동 일정 잡아줘')
        self.assertTrue(job['response'].startswith(REPLACED_NOTICE))
        self.assertEqual(self.pending('telegram:4242')['slots']['title'], '치과')


class ApprovalTests(ConversationTestCase):
    def test_approval_executes_exactly_once(self):
        self.say('내일 오후 3시에 치과 일정 잡아줘')
        job = self.say('승인')
        self.assertEqual(job['status'], 'succeeded')
        self.assertIn(CREATED, job['response'])
        self.assertIn('제목: 치과', job['response'])
        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(self.states(), ['completed'])
        self.assertEqual(self.pending(), {})
        # A second approval has nothing to approve; it falls to the ordinary
        # route and touches neither the provider nor the completed draft.
        again = self.say('승인')
        self.assertEqual(again['status'], 'failed')
        self.assertIn(MODEL_ROUTE_ERROR, again['error'])
        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(self.states(), ['completed'])

    def test_english_approval_words_work_too(self):
        self.say('schedule a meeting with the vendor tomorrow at 3pm')
        job = self.say('approve')
        self.assertIn(CREATED, job['response'])
        self.assertEqual(len(self.provider.calls), 1)

    def test_a_bare_yes_before_the_preview_is_not_an_approval(self):
        self.say('금요일 약속 하나 등록해줘')
        job = self.say('네')
        self.assertEqual(job['response'], '몇 시인가요? (예: 오후 3시, 15:00)')
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.drafts(), {})

    def test_an_expired_preview_cannot_be_approved(self):
        self.say('내일 오후 3시에 치과 일정 잡아줘')
        self.clock[0] += 901
        job = self.say('승인')
        self.assertEqual(job['status'], 'failed')
        self.assertIn(MODEL_ROUTE_ERROR, job['error'])
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.states(), ['awaiting-approval'])

    def test_the_approval_must_come_from_the_identity_that_drafted(self):
        self.store.put('telegram', {'enabled': True, 'user_id': 4242, 'generation': 'g1'})
        self.connect('telegram:4242')
        self.say('내일 오후 3시에 치과 일정 잡아줘', channel='telegram:g1', chat_id=4242)
        job = self.say('승인')  # from the web, `local-owner`
        self.assertEqual(job['response'], OTHER_CHANNEL)
        self.assertEqual(self.provider.calls, [])
        job = self.say('승인', channel='telegram:g1', chat_id=4242)
        self.assertIn(CREATED, job['response'])
        self.assertEqual(len(self.provider.calls), 1)
        (draft,) = self.drafts().values()
        self.assertEqual(draft['owner'], _owner_key('telegram:4242'))

    def test_the_other_channel_cannot_take_over_a_half_collected_request(self):
        self.store.put('telegram', {'enabled': True, 'user_id': 4242, 'generation': 'g1'})
        self.connect('telegram:4242')
        self.say('금요일 약속 하나 등록해줘', channel='telegram:g1', chat_id=4242)
        before = self.pending()
        job = self.say('네')  # from the web
        self.assertEqual(job['response'], OTHER_CHANNEL)
        self.assertEqual(self.pending(), before, 'the collecting record must not change owner')
        job = self.say('오후 2시', channel='telegram:g1', chat_id=4242)
        self.assertIn(PREVIEW_HEADER, job['response'])
        (draft,) = self.drafts().values()
        self.assertEqual(draft['owner'], _owner_key('telegram:4242'))

    def test_a_preview_that_changed_underneath_is_not_approved(self):
        self.say('내일 오후 3시에 치과 일정 잡아줘')
        row = dict(self.pending())
        row['payload_hash'] = 'not-the-hash-that-was-shown'
        self.store.put(STATE_KEY, {_owner_key('local-owner'): row})
        job = self.say('승인')
        self.assertIn('미리보기와 달라', job['response'])
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.pending(), {})

    def test_an_unknown_provider_outcome_is_reported_and_never_retried(self):
        self.say('내일 오후 3시에 치과 일정 잡아줘')
        self.provider.fail = GoogleCalendarError('provider-timeout', 'unknown')
        job = self.say('승인')
        self.assertEqual(job['status'], 'succeeded')
        self.assertEqual(job['response'], OUTCOME_UNKNOWN)
        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(self.states(), ['outcome-unknown'])
        self.assertEqual(self.pending(), {})
        again = self.say('승인')
        self.assertEqual(len(self.provider.calls), 1, 'an unknown outcome must not be retried')

    def test_a_missing_write_grant_parks_and_the_resumed_work_previews_once(self):
        self.registry.transition(self.OWNER, CALENDAR_WRITE_SPEC.connector_id, ConnectorState.DISCONNECTED)
        job = self.say('내일 오후 3시에 치과 일정 잡아줘')
        self.assertEqual(job['status'], 'awaiting_connection')
        self.assertEqual(self.drafts(), {})
        self.connect(self.OWNER)
        self.service.resume_connector_work(CALENDAR_WRITE_SPEC.connector_id, self.OWNER,
                                           (CALENDAR_WRITE_SCOPE,))
        self.assertTrue(self.service.run_one())
        self.assertFalse(self.service.run_one())
        resumed = self.store.job(job['id'])
        self.assertEqual(resumed['status'], 'succeeded')
        self.assertIn(PREVIEW_HEADER, resumed['response'])
        self.assertEqual(self.states(), ['awaiting-approval'])
        self.assertEqual(self.provider.calls, [])


class CorrectionCancelRestartTests(ConversationTestCase):
    def test_a_correction_redrafts_and_the_first_draft_is_never_executed(self):
        self.say('내일 오후 3시에 치과 일정 잡아줘')
        job = self.say('아니 4시로')
        self.assertIn('16:00 – 17:00', job['response'])
        self.assertIn(PREVIEW_HEADER, job['response'])
        job = self.say('제목은 치과 검진으로')
        self.assertIn('제목: 치과 검진', job['response'])
        self.assertIn('16:00 – 17:00', job['response'])
        job = self.say('2시간으로')
        self.assertIn('16:00 – 18:00', job['response'])
        self.say('승인')
        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(self.provider.calls[0]['summary'], '치과 검진')
        self.assertEqual(self.provider.calls[0]['end'], '2026-09-23T18:00:00+09:00')
        self.assertEqual(self.states(), ['awaiting-approval', 'awaiting-approval', 'awaiting-approval', 'completed'])

    def test_an_english_correction_works_the_same_way(self):
        self.say('schedule a meeting with the vendor tomorrow at 3pm')
        job = self.say('no, make it 4pm')
        self.assertIn('16:00 – 17:00', job['response'])
        self.say('yes')
        self.assertEqual(self.provider.calls[0]['start'], '2026-09-23T16:00:00+09:00')

    def test_cancel_creates_nothing_and_a_later_approval_has_nothing_to_approve(self):
        self.say('내일 오후 3시에 치과 일정 잡아줘')
        job = self.say('취소')
        self.assertEqual(job['response'], CANCELLED)
        self.assertEqual(self.pending(), {})
        job = self.say('승인')
        self.assertEqual(job['status'], 'failed')
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.states(), ['awaiting-approval'])

    def test_english_cancel_and_the_bare_no(self):
        for word in ('never mind', 'no'):
            with self.subTest(word=word):
                self.say('schedule a meeting with the vendor tomorrow at 3pm')
                self.assertEqual(self.say(word)['response'], CANCELLED)
        self.assertEqual(self.provider.calls, [])

    def test_a_new_request_replaces_the_pending_draft_and_says_so(self):
        self.say('내일 오후 3시에 치과 일정 잡아줘')
        job = self.say('금요일 오전 10시 팀 회의 일정 잡아줘')
        self.assertTrue(job['response'].startswith(REPLACED_NOTICE))
        self.assertIn('제목: 팀 회의', job['response'])
        self.say('승인')
        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(self.provider.calls[0]['summary'], '팀 회의')

    def test_a_topic_change_drops_the_draft_says_so_and_routes_normally(self):
        self.say('내일 오후 3시에 치과 일정 잡아줘')
        job = self.say('메모 목록')
        self.assertTrue(job['response'].startswith(DROPPED_NOTICE))
        self.assertIn('저장된 메모가 없습니다', job['response'])
        self.assertEqual(self.pending(), {})
        # An unrelated question while collecting is not swallowed as a title.
        self.say('add a calendar event for friday')
        job = self.say('오늘 날씨 어때?')
        self.assertEqual(job['status'], 'failed')
        self.assertIn(MODEL_ROUTE_ERROR, job['error'])
        self.assertEqual(self.pending(), {})
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.states(), ['awaiting-approval'])

    def test_a_cue_free_unrelated_message_drops_the_draft_and_says_so(self):
        """The other drop path, which nothing asserted.

        `test_a_topic_change_...` uses '메모 목록', which carries a note cue and
        so takes the *other-intent* branch. A cue-free utterance takes the
        continuation-not-claimed branch instead, and removing its notice left
        the whole 1180-test suite green. The owner has to be told their
        pending draft is gone, or their next "승인" is a surprise.
        """
        self.say('내일 오후 3시에 치과 일정 잡아줘')
        job = self.say('/notes')
        self.assertTrue(job['response'].startswith(DROPPED_NOTICE), job['response'])
        self.assertEqual(self.pending(), {})
        self.assertEqual(self.provider.calls, [])

    def test_a_cue_free_drop_is_announced_even_when_the_reroute_fails(self):
        """`job['error']` is internal; the owner reads the assistant message."""
        self.say('내일 오후 3시에 치과 일정 잡아줘')
        job = self.say('오늘 날씨 어때?')
        self.assertEqual(job['status'], 'failed')
        with self.store.db() as db:
            last = db.execute("SELECT content FROM messages WHERE role='assistant' "
                              "ORDER BY created DESC LIMIT 1").fetchone()
        self.assertTrue(str(last[0]).startswith(DROPPED_NOTICE), last[0])
        self.assertEqual(self.pending(), {})

    def test_restart_after_cancel_starts_clean(self):
        self.say('내일 오후 3시에 치과 일정 잡아줘')
        self.say('취소')
        job = self.say('내일 오후 5시에 치과 일정 잡아줘')
        self.assertFalse(job['response'].startswith(REPLACED_NOTICE))
        self.assertIn('17:00 – 18:00', job['response'])
        self.say('승인')
        self.assertEqual([call['start'] for call in self.provider.calls], ['2026-09-23T17:00:00+09:00'])

    def test_an_ambiguous_utterance_still_clarifies_and_keeps_the_draft(self):
        self.say('내일 오후 3시에 치과 일정 잡아줘')
        job = self.say('내일 회의 일정 잡고 작업공간에 저장한 자료도 찾아줘')
        self.assertIn('아무 작업도 실행하지 않았습니다', job['response'])
        self.assertIsNotNone(self.pending())
        self.assertEqual(self.provider.calls, [])


class ModelAuthorityTests(unittest.TestCase):
    def test_a_model_suggestion_still_cannot_select_calendar_create(self):
        from personal_agent.conversation_handoff import INTENT_AMBIGUOUS, INTENT_CALENDAR_CREATE, IntentClassifier
        decision = IntentClassifier().classify('내일 회의 일정 잡고 작업공간에 저장한 자료도 찾아줘',
                                               model_suggestion={'intent': INTENT_CALENDAR_CREATE})
        self.assertEqual(decision.intent, INTENT_AMBIGUOUS)
        self.assertEqual(decision.model_suggestion['reason'], 'consequential-intent')


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
