"""PRESENCE-WEB-IA-01 (#562): exact retained items instead of a records browser.

The local web no longer has a generic 내 기록 destination.  A conversation
turn links to the exact items its own Work recorded, and a link opens one
item through ``GET /api/personal-space/items/<kind>/<id>``.  These tests walk
the shipped HTTP handler and worker (the same harness as the J6 owner-path
tests) and check:

- which items a turn links to comes from typed records only - the note a
  Work stored under its own id, a save_memory event that committed Memory, a
  MemoryCandidate bound to the Work, the Work's own saved results - never
  from the request or answer text;
- one item is returned alone, and a MemoryCandidate is returned as a
  candidate only while it is pending, never as remembered Memory;
- opening an item is a read: it changes no stored data and calls no model;
- removing the browsing page deleted nothing, and the existing type-bound
  delete and candidate decision paths still work from an item link.

**Evidence class: local, offline, fixture-transport integration.**  The only
injected seam is the outbound model transport.  No live provider, Telegram
or browser is exercised here; browser rendering is covered separately by the
fixture-backed Playwright run recorded in the PR.
"""
import json
import unittest
from http.cookiejar import CookieJar
from urllib.request import HTTPCookieProcessor, build_opener

from test_pa1_memory_candidate_owner_path import (CANDIDATE_CONTENT, CANDIDATE_KEY,
                                                   _OwnerSurface)


def counts(store):
    with store.db() as db:
        return {table: db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                for table in ('notes', 'memories', 'memory_candidates', 'memory_approvals',
                              'workspace_results', 'jobs', 'tool_events')}


class ExactRetainedItems(_OwnerSurface):
    def task(self, job_id):
        return next(task for task in self.web('/api/tasks')['tasks'] if task['id'] == job_id)

    def item(self, kind, item_id):
        return self.web(f'/api/personal-space/items/{kind}/{item_id}')['item']

    def note_turn(self, text):
        # The deterministic note path stores the note under the Work's own id.
        return self.ask('/note ' + text)

    def test_a_turn_links_only_the_note_it_saved_and_the_link_opens_only_that_note(self):
        first = self.note_turn('우유 사기')
        second = self.note_turn('치과 예약 확인')
        self.assertEqual(self.task(first)['retained'],
                         [{'kind': 'note', 'id': first, 'label': None, 'available': True}])
        self.assertEqual([row['id'] for row in self.task(second)['retained']], [second])

        opened = self.web(f'/api/personal-space/items/note/{first}')
        self.assertEqual(opened, {'item': {'kind': 'note', 'id': first, 'content': '우유 사기',
                                            'created': opened['item']['created'], 'work_id': first}})
        self.assertNotIn('치과', json.dumps(opened, ensure_ascii=False))

    def test_a_note_saved_by_the_save_note_tool_resolves_to_its_work(self):
        self.model_plan = [('save_note', json.dumps({'content': '우유 사기'}, ensure_ascii=False))]
        self.model_text = '저장했어요.'
        job = self.ask('우유 사야 한다는 걸 저장해 줘')
        self.model_plan = []
        [link] = self.task(job)['retained']
        self.assertEqual(link['kind'], 'note')
        self.assertNotEqual(link['id'], job)
        opened = self.item('note', link['id'])
        self.assertEqual((opened['content'], opened['work_id']), ('우유 사기', job))

    def test_a_turn_that_asked_for_nothing_to_be_kept_links_nothing(self):
        job = self.ask('오늘 날씨 이야기만 해 줘')
        self.assertEqual(self.task(job)['retained'], [])

    def test_opening_an_item_is_a_read_that_changes_nothing_and_calls_no_model(self):
        job = self.note_turn('우유 사기')
        self.pending_candidate()
        candidate = self.candidates()['candidates'][0]['id']
        before, calls = counts(self.store), len(self.calls)
        for kind, item_id in (('note', job), ('candidate', candidate)):
            self.item(kind, item_id)
        self.assertEqual(counts(self.store), before)
        self.assertEqual(len(self.calls), calls)

    def test_a_candidate_is_linked_as_a_candidate_and_never_as_memory_until_accepted(self):
        job = self.pending_candidate()
        [link] = self.task(job)['retained']
        self.assertEqual((link['kind'], link['label'], link['available']), ('candidate', CANDIDATE_KEY, True))
        opened = self.item('candidate', link['id'])
        self.assertEqual((opened['kind'], opened['state'], opened['content']), ('candidate', 'pending', CANDIDATE_CONTENT))
        self.assertEqual(opened['work_id'], job)
        # A candidate id is not a Memory id: nothing is remembered yet.
        self.assertEqual(self.refused(f"/api/personal-space/items/memory/{link['id']}")[0], 404)

        # The link carries what the existing two-step decision needs.
        inspected = self.act(operation='inspect', id=opened['id'], work_ref=opened['work_ref'])
        issued = self.act(operation='request-approval', id=opened['id'], work_ref=opened['work_ref'],
                          content_digest=inspected['content_digest'])
        saved = self.act(operation='accept', id=opened['id'], work_ref=opened['work_ref'],
                         content_digest=inspected['content_digest'], approval_token=issued['approval_token'])

        # After the decision the same turn links the Memory it became, and the
        # candidate link is gone rather than shown as remembered.
        self.assertEqual(self.task(job)['retained'],
                         [{'kind': 'memory', 'id': saved['id'], 'label': CANDIDATE_KEY, 'available': True}])
        self.assertEqual(self.refused(f"/api/personal-space/items/candidate/{opened['id']}")[0], 404)
        self.assertEqual(self.item('memory', saved['id'])['content'], CANDIDATE_CONTENT)

    def test_committed_memory_is_linked_and_its_deletion_is_said_not_hidden(self):
        self.model_plan = [('save_memory', json.dumps({'memory_key': 'meeting-time', 'content': '오전 회의를 선호합니다'},
                                                      ensure_ascii=False))]
        self.model_text = '기억했습니다.'
        job = self.ask('내 회의 시간 선호를 기억해 줘: 오전이 좋아')
        self.model_plan = []
        [link] = self.task(job)['retained']
        self.assertEqual((link['kind'], link['label'], link['available']), ('memory', 'meeting-time', True))
        self.assertEqual(self.item('memory', link['id'])['work_id'], job)

        # The existing type-bound delete, from the item.
        self.assertTrue(self.web('/api/personal-space/memories/' + link['id'], method='DELETE')['deleted'])
        self.assertEqual(self.task(job)['retained'][0]['available'], False)
        self.assertEqual(self.refused(f"/api/personal-space/items/memory/{link['id']}")[0], 404)

    def test_a_saved_result_opens_alone_with_its_project(self):
        done = self.ask('회의 준비 목록 정리해 줘')
        other = self.ask('여행 준비 목록 정리해 줘')
        workspace = self.web('/api/workspaces', {'title': '회의 프로젝트'})
        elsewhere = self.web('/api/workspaces', {'title': '여행 프로젝트'})
        self.web(f"/api/workspaces/{workspace['id']}/save-result", {'job_id': done})
        self.web(f"/api/workspaces/{elsewhere['id']}/save-result", {'job_id': other})
        [artifact] = self.task(done)['artifacts']
        opened = self.item('artifact', artifact['id'])
        self.assertEqual((opened['workspace_id'], opened['workspace_title'], opened['job_id'], opened['work_id']),
                         (workspace['id'], '회의 프로젝트', done, done))
        self.assertNotIn('여행', json.dumps(opened, ensure_ascii=False))
        # Deleting the result keeps its Work and project.
        self.web('/api/personal-space/results/' + artifact['id'], method='DELETE')
        self.assertEqual(self.task(done)['artifacts'], [])
        self.assertEqual(self.web(f"/api/workspaces/{workspace['id']}")['title'], '회의 프로젝트')

    def test_the_item_route_refuses_anonymous_unknown_and_malformed_requests(self):
        job = self.note_turn('우유 사기')
        anonymous = build_opener(HTTPCookieProcessor(CookieJar()))
        self.assertEqual(self.refused(f'/api/personal-space/items/note/{job}', opener=anonymous)[0], 401)
        self.assertEqual(self.refused(f'/api/personal-space/items/context/{job}')[0], 400)
        self.assertEqual(self.refused('/api/personal-space/items/note/does-not-exist')[0], 404)
        self.assertEqual(self.refused(f'/api/personal-space/items/note/{job}/extra')[0], 404)
        # A kind is not interchangeable: a note id is not a saved result.
        self.assertEqual(self.refused(f'/api/personal-space/items/artifact/{job}')[0], 404)


class LinksComeFromTypedDataOnly(unittest.TestCase):
    """The browser decides nothing from wording: links are typed Work data."""

    APP = (__import__('pathlib').Path(__file__).resolve().parents[1] / 'src/personal_agent/web/app.js').read_text()

    def test_the_link_helper_reads_only_retained_and_artifact_records(self):
        start = self.APP.index('function retainedLinks(')
        body = self.APP[start:self.APP.index('return rows;}', start)]
        for field in ('response', 'title', 'request', 'message', 'content', 'RegExp', '.match(', '.test('):
            self.assertNotIn(field, body)
        self.assertIn('task?.retained', body)
        self.assertIn('task?.artifacts', body)

    def test_the_trace_renders_links_through_the_helper(self):
        render = self.APP[self.APP.index('function renderTasks(){'):self.APP.index('function itemTitle(item){')]
        self.assertIn('for(const link of retainedLinks(task))', render)
        self.assertIn('itemLink(link.kind,link.id', render)
        self.assertNotIn("navigate('records')", self.APP)


if __name__ == '__main__':
    unittest.main()
