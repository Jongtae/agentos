import tempfile
import unittest
from pathlib import Path

from personal_agent.memory_service import MemoryService, MemoryServiceError
from personal_agent.quickstart_store import QuickStore
from personal_agent.agent_runtime import Capabilities, EFFECT_FREE_READS, recorded_arguments


class MemorySearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(Path(self.temp.name) / 'state')
        self.markers = []
        self.service = MemoryService(self.store, private_read_sink=self.markers.append)

    def test_searches_beyond_first_page_and_returns_owner_scoped_source(self):
        for i in range(55):
            self.store.save_memory(f'profile.preference.{i}', f'일반 항목 {i}', owner_id='owner-a', work_id=f'w{i}')
        expected = self.store.save_memory('profile.store.books', '교보문고에서 책을 삽니다', owner_id='owner-a', work_id='source-work')
        self.store.save_memory('profile.store.books', '다른 사용자의 값', owner_id='owner-b', work_id='other-work')

        result = self.service.search_memories('owner-a', '교보문고 책')

        self.assertEqual([row['id'] for row in result['memories']], [expected['id']])
        self.assertEqual(result['memories'][0]['work_ref'], 'workref:' + self.store._work_binding('source-work'))
        self.assertTrue(result['memories'][0]['created'])
        self.assertTrue(result['egress_guard_armed'])
        self.assertEqual(self.markers[0]['tool'], 'memory_service.search_memories')

    def test_search_ignores_superseded_rows_and_falls_back_to_bounded_literal_match(self):
        self.store.save_memory('profile.preference.food', '초밥을 좋아합니다', owner_id='owner-a', work_id='old')
        current = self.store.save_memory('profile.preference.food', '김밥을 좋아합니다', owner_id='owner-a', work_id='new')
        self.store.memory_search_available = False

        result = self.service.search_memories('owner-a', '김밥')
        empty = self.service.search_memories('owner-a', '초밥')

        self.assertEqual([row['id'] for row in result['memories']], [current['id']])
        self.assertEqual(empty['memories'], [])
        self.assertEqual(result['search_mode'], 'bounded-like')

    def test_search_mode_reports_actual_fallback_after_incompatible_fts_index(self):
        expected = self.store.save_memory('profile.note', '여행 노트를 보관합니다', owner_id='owner-a', work_id='w1')
        with self.store.db() as db:
            db.executescript('''
                DROP TRIGGER IF EXISTS memories_search_ai;
                DROP TRIGGER IF EXISTS memories_search_ad;
                DROP TRIGGER IF EXISTS memories_search_au;
                DROP TABLE memories_search;
                CREATE TABLE memories_search(rowid INTEGER, memory_key TEXT, content TEXT);
            ''')

        result = self.service.search_memories('owner-a', '여행')

        self.assertEqual([row['id'] for row in result['memories']], [expected['id']])
        self.assertEqual(result['search_mode'], 'bounded-like')

    def test_truncated_only_when_an_additional_match_exists(self):
        self.store.save_memory('profile.note.first', '여행 노트 하나', owner_id='owner-a', work_id='w1')
        one = self.service.search_memories('owner-a', '여행', limit=1)
        self.store.save_memory('profile.note.second', '여행 노트 둘', owner_id='owner-a', work_id='w2')
        more = self.service.search_memories('owner-a', '여행', limit=1)

        self.assertFalse(one['truncated'])
        self.assertTrue(more['truncated'])

    def test_memory_search_is_classified_as_effect_free_read(self):
        self.assertIn('search_memory', EFFECT_FREE_READS)

    def test_literal_fallback_keeps_owner_filter_around_multiple_terms(self):
        owner_row = self.store.save_memory('profile.food', '김밥을 좋아합니다', owner_id='owner-a', work_id='a')
        self.store.save_memory('profile.secret', '비밀 위치 정보', owner_id='owner-b', work_id='b')
        self.store.memory_search_available = False

        result = self.service.search_memories('owner-a', '김밥 비밀')

        self.assertEqual([row['id'] for row in result['memories']], [owner_row['id']])

    def test_literal_query_cannot_inject_fts_operators_and_limits_are_checked(self):
        expected = self.store.save_memory('profile.note', '민트초코 아이스크림', owner_id='owner-a', work_id='w1')
        result = self.service.search_memories('owner-a', '민트초코" OR *')
        self.assertEqual([row['id'] for row in result['memories']], [expected['id']])
        with self.assertRaises(MemoryServiceError):
            self.service.search_memories('owner-a', 'x' * 501)
        with self.assertRaises(MemoryServiceError):
            self.service.search_memories('owner-a', 'abc', limit=21)

    def test_two_character_korean_query_is_supported(self):
        expected = self.store.save_memory('profile.place.work', '회사 근처에 구내식당이 있습니다', owner_id='owner-a', work_id='w1')
        result = self.service.search_memories('owner-a', '회사')
        self.assertIn(expected['id'], [row['id'] for row in result['memories']])

    def test_existing_memory_rows_are_indexed_after_index_rebuild(self):
        expected = self.store.save_memory('profile.preference.coffee', '에티오피아 원두를 선호합니다', owner_id='owner-a', work_id='w1')
        with self.store.db() as db:
            db.executescript('''
                DROP TRIGGER IF EXISTS memories_search_ai;
                DROP TRIGGER IF EXISTS memories_search_ad;
                DROP TRIGGER IF EXISTS memories_search_au;
                DROP TABLE IF EXISTS memories_search;
                DROP TABLE IF EXISTS memory_search_meta;
            ''')

        reopened = QuickStore(self.store.root)

        result = reopened.search_memories('owner-a', ['에티오피아'])
        self.assertEqual([row['id'] for row in result], [expected['id']])

    def test_capability_redacts_secrets_from_search_result_and_evidence(self):
        secret = 'MEMORYSECRET987654'
        self.store.save_memory('profile.note.' + secret, '계정 복구 코드 ' + secret, owner_id='local-owner', work_id='source')
        redact = lambda value: value.replace(secret, '[redacted]')
        capabilities = Capabilities(
            self.store, None, {}, '', 'job', lambda *args: None,
            allowed_tools=['search_memory'], secret_redactor=redact,
        )

        result = capabilities.execute('search_memory', {'query': secret})
        serialized = str(result) + str(capabilities.evidence)

        self.assertNotIn(secret, serialized)
        self.assertIn('[redacted]', serialized)
        self.assertEqual(result['memories'][0]['content'], '계정 복구 코드 [redacted]')
        self.assertEqual(result['query_terms'], [])
        recorded = recorded_arguments('search_memory', {'query': secret}, redact)
        self.assertNotIn(secret, str(recorded))


    def test_memory_tools_say_when_and_from_which_request_each_fact_came(self):
        """#794 phase 2: the AI can answer "why do you know that?" from recorded sources."""
        secret = 'MEMORYSECRET987654'
        job = self.store.enqueue(f'내 직장은 판교야 기억해 {secret} sk-abcdefghijklmnop', 'k1', owner_typed=True)
        generated = self.store.enqueue('준비 작업: 점심 후보를 찾아 둔다', 'prep-1')
        sourced = self.store.save_memory('profile.place.work', '판교 카카오뱅크', owner_id='local-owner', work_id=job)
        prepared = self.store.save_memory('profile.preference.lunch', '가벼운 점심', owner_id='local-owner', work_id=generated)
        orphan = self.store.save_memory('profile.preference.food', '가벼운 식사', owner_id='local-owner', work_id='pruned-work')
        capabilities = Capabilities(
            self.store, None, {}, '', 'job', lambda *args: None,
            allowed_tools=['list_memory', 'search_memory'], secret_redactor=lambda value: value.replace(secret, '[redacted]'),
        )

        listed = {row['id']: row for row in capabilities.execute('list_memory', {})['memories']}
        searched = capabilities.execute('search_memory', {'query': '판교'})['memories']

        source = listed[sourced['id']]['source']
        self.assertEqual((source['kind'], source['work_id'], listed[sourced['id']]['source_status']), ('owner_request', job, 'found'))
        self.assertTrue(source['at'] and listed[sourced['id']]['saved_at'])
        self.assertIn('판교', source['text'])
        self.assertEqual(listed[prepared['id']]['source']['kind'], 'agentos_work',
                         'text AgentOS generated is never presented as what the owner said')
        self.assertEqual((listed[orphan['id']]['source'], listed[orphan['id']]['source_status']), (None, 'not_kept'))
        self.assertTrue(listed[orphan['id']]['saved_at'])
        self.assertEqual(searched[0]['source']['work_id'], job)
        serialized = str(listed) + str(searched) + str(capabilities.evidence)
        self.assertNotIn(secret, serialized)
        self.assertNotIn('sk-abcdefghijklmnop', serialized)

    def test_a_failed_source_lookup_is_unknown_not_not_kept(self):
        self.store.save_memory('profile.note', '값', owner_id='local-owner', work_id='w')
        capabilities = Capabilities(self.store, None, {}, '', 'job', lambda *args: None, allowed_tools=['list_memory'])

        def broken(_ids):
            raise RuntimeError('database is locked')
        self.store.memory_sources = broken
        row = capabilities.execute('list_memory', {})['memories'][0]
        self.assertEqual((row['source'], row['source_status']), (None, 'unknown'))

    def test_sources_are_read_not_stored_and_the_index_follows_new_work(self):
        job = self.store.enqueue('출처 요청', 'k2', owner_typed=True)
        saved = self.store.save_memory('profile.note', '값', owner_id='local-owner', work_id=job)
        self.assertEqual(self.store.memory_sources([saved['id'], 'unknown'])[saved['id']]['work_id'], job)
        later = self.store.enqueue('나중 요청', 'k3', owner_typed=True)
        newer = self.store.save_memory('profile.later', '나중 값', owner_id='local-owner', work_id=later)
        self.assertEqual(self.store.memory_sources([newer['id']])[newer['id']]['work_id'], later,
                         'a Work added after the first lookup is indexed incrementally')
        self.assertEqual(self.store.memory_sources([]), {})
        with self.store.db() as db:
            self.assertNotIn(job, str([tuple(row) for row in db.execute('SELECT * FROM memories')]),
                             'the raw Work id is never written to Memory')

if __name__ == '__main__':
    unittest.main()
