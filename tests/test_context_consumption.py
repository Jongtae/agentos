"""CONTEXT-STATE-01 / #627: the snapshot is consumed in real tool inputs on both routes.

One changed-boundary integration, parameterized over the direct-API binding
and the CLI binding: real Telegram ingress (``AgentService.ingest_update``) ->
the owner store -> the snapshot in the actual route input -> a scripted
worker that reads ONLY what the route handed it -> the real broker
(``Capabilities.execute``; the CLI through its MCP facade) -> a fake network
that records every outbound plan.  If the snapshot were not wired into the
route input, the scripted worker would have nothing to choose from and the
assertions on the outbound plan would fail.

Fakes: model transport, CLI engine, Telegram transport, network.  Evidence
class: automated synthetic/fixture only.  No live model, Telegram, device
location or weather/search provider is contacted, and none is claimed.
"""
import json
import tempfile
import time
import unittest
from pathlib import Path

from personal_agent.agent_runtime import (CURRENT_CONTEXT_HEADING, Capabilities, ToolError, lookup_sources, run_agent)
from personal_agent.bounded_execution import AgentOSMcpTools, ExecutionResult, profile_actions
from personal_agent.memory_service import MemoryService
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.subscription_engines import SubscriptionEngines
from test_agency_loop import CFG, Script, call, finish, judgments

CHAT = 4242
GENERATION = 'g1'
SEOUL_POINT = {'latitude': 37.566512, 'longitude': 126.978031, 'horizontal_accuracy': 10}
ADMITTED = {'tool': 'weather', 'latitude': 37.57, 'longitude': 126.98}
PASSPORT = 'M12345678'


def snapshot_in(text):
    """The current-context snapshot a worker can read from its input, or None."""
    if not text or CURRENT_CONTEXT_HEADING not in text:
        return None
    section = text.split(CURRENT_CONTEXT_HEADING + '\n', 1)[1]
    return json.loads(section.split('\n')[1])


def lunch_or_weather(snapshot, request):
    """The scripted worker's choices, made only from the snapshot it was given."""
    if snapshot is None:
        return []
    anchors = {item['ref']: item['label'] for item in snapshot.get('anchors', [])}
    if '재택' in request:
        home = next(ref for ref in anchors if ref.endswith('.home'))
        return [('propose_current_state', {'predicate': 'work_mode', 'value': 'remote', 'place_ref': home,
                                           'until': 'today'})]
    if '점심' in request:
        mode = next(item for item in snapshot.get('hypotheses', []) if item['predicate'] == 'work_mode')
        query = anchors[mode['place_ref']] + ' 점심 맛집'
        if '여권' in request:
            # The worker copies the owner's saved private value into its query.
            return [('save_note', {'content': '여권번호 ' + PASSPORT}), ('web_search', {'query': query + ' ' + PASSPORT})]
        return [('web_search', {'query': query})]
    if '비' in request or '날씨' in request:
        here = next(item['ref'] for item in snapshot.get('locations', []) if item['kind'].endswith('position_report'))
        return [('weather', {'location_ref': here})]
    return []


class _Network:
    def __init__(self):
        self.plans = []

    def execute(self, plan):
        self.plans.append(dict(plan))
        if plan['tool'] == 'weather':
            return {'tool': 'weather', 'location': {'name': plan.get('city'), 'latitude': plan.get('latitude'),
                                                    'longitude': plan.get('longitude')},
                    'retrieved_at': 1, 'sources': ['https://open-meteo.com/'],
                    'forecast': {'current': {'time': '2026-09-27T12:00', 'temperature_2m': 21,
                                             'apparent_temperature': 21, 'precipitation': 1.2, 'wind_speed_10m': 5},
                                 'current_units': {'temperature_2m': '°C', 'apparent_temperature': '°C',
                                                   'precipitation': 'mm', 'wind_speed_10m': 'km/h'},
                                 'timezone': 'Asia/Seoul'}}
        return {'query': plan.get('query'), 'retrieved_at': 1, 'sources': ['https://example.org/'],
                'results': [{'title': 'lunch', 'url': 'https://example.org/', 'snippet': 'public snippet'}]}


class _ConsumptionCase:
    """Shared journeys; ``ApiRoute`` and ``CliRoute`` bind them to one route each."""
    ROUTE = None
    CONFIG = {'provider': 'compatible', 'endpoint': 'http://127.0.0.1:9999', 'model': 'fixture'}

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'state')
        self.now = float(int(time.time()))
        self.network, self.model_calls, self.telegram_calls = _Network(), [], []
        self.worker_inputs, self.results, self.claims = [], [], []
        self.before_dispatch = None
        self.update_id, self.message_id = 100, 500

        def telegram(url, body=None, headers=None, timeout=60):
            self.telegram_calls.append(url.rsplit('/', 1)[-1])
            return {'ok': True, 'result': {'message_id': 9000 + len(self.telegram_calls)}}

        self.service = AgentService(self.store, adapter=ModelAdapter(self._model), telegram_transport=telegram,
                                    subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/cli',
                                                                             clock=lambda: 1),
                                    execution_adapter=self)
        self.service.local_tools = self.network
        self.service.context_observations.clock = lambda: self.now
        self.store.secret('telegram_token', 'bot-token-value-1234')
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': GENERATION, 'cursor': 0})
        if self.ROUTE == 'cli':
            self.service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        else:
            self.store.put('model', self.CONFIG)
            self.store.put('model_test', {'ok': True, 'tools_ok': True, 'time': 9999999999,
                                          'fingerprint': self.service.model_fingerprint(self.CONFIG)})
        memory = MemoryService(self.store, private_read_sink=MemoryService.NO_EGRESS_GUARD)
        memory.remember_profile('local-owner', 'settings', 'profile.place.home', '합정')
        memory.remember_profile('local-owner', 'settings', 'profile.place.work', '판교')

    # --- the two bindings ---------------------------------------------------

    def _model(self, url, body, headers):
        """Direct-API worker: reads the snapshot from its system text only."""
        messages = body['messages']
        self.model_calls.append(messages)
        tail = list(messages)
        nudged = False
        while tail and tail[-1]['role'] == 'system' and len(tail) > 1:
            tail.pop()
            nudged = True
        if tail[-1]['role'] == 'tool' and nudged:
            # A failed path earned a "try another path" turn (#657): this
            # worker has none, so it records what it saw and answers.
            self.results.extend(json.loads(m['content']) for m in tail[-1:])
            return {'choices': [{'message': {'content': 'done'}}]}
        if messages[-1]['role'] == 'tool':
            batch = []
            for message in reversed(messages):
                if message['role'] != 'tool':
                    break
                batch.insert(0, json.loads(message['content']))
            if messages[-1]['tool_call_id'] == 'finish':
                # The claim was refused (for example: internal state only).
                self.claims.append(batch[-1])
                return {'choices': [{'message': {'content': 'done'}}]}
            self.results.extend(batch)
            # #657: a tool-using turn ends with a completion claim citing the
            # loop's result refs; a result that failed is not cited.
            refs = [item['ref'] for item in batch if 'ref' in item and 'error' not in item]
            return {'choices': [{'message': {'content': None, 'tool_calls': [
                {'id': 'finish', 'type': 'function', 'function': {'name': 'finish', 'arguments': json.dumps(
                    {'status': 'done' if refs else 'partial', 'evidence_refs': refs, 'summary': 'done'})}}]}}]}
        if messages[-1]['role'] == 'system':
            return {'choices': [{'message': {'content': 'done'}}]}
        system = messages[0]['content']
        self.worker_inputs.append({'text': system, 'tools': [t['function']['name'] for t in body.get('tools', [])]})
        calls = lunch_or_weather(snapshot_in(system), messages[-1]['content'])
        if self.before_dispatch:
            self.before_dispatch()
        if not calls:
            return {'choices': [{'message': {'content': 'done'}}]}
        return {'choices': [{'message': {'content': None, 'tool_calls': [
            {'id': f'c{index}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}
            for index, (name, args) in enumerate(calls)]}}]}

    def execute(self, engine, prompt, tools, **kwargs):
        """CLI worker: reads the snapshot from the prompt it was actually sent."""
        context = kwargs.get('context') or {}
        self.worker_inputs.append({'text': prompt, 'tools': [t['name'] for t in tools.definitions()],
                                   'context': context})
        self.assertEqual(snapshot_in(prompt), json.loads(context['current_context'].split('\n')[1])
                         if context.get('current_context') else None, 'the prompt carries the context section')
        calls = lunch_or_weather(snapshot_in(prompt), context.get('request', prompt))
        if self.before_dispatch:
            self.before_dispatch()
        for name, args in calls:
            try:
                self.results.append(tools.call(name, args))
            except ToolError as exc:
                self.results.append({'error': str(exc), 'code': exc.code})
        return ExecutionResult('done', engine, 0)

    # --- helpers -----------------------------------------------------------

    def enable(self):
        self.service.set_current_context({'enabled': True, 'timezone': 'Asia/Seoul'})

    def share_live_location(self, point=SEOUL_POINT, edit=False):
        self.update_id += 1
        message = {'message_id': self.message_id, 'from': {'id': CHAT}, 'chat': {'id': CHAT, 'type': 'private'},
                   'date': int(self.now) - (60 if edit else 0), 'location': {**point, 'live_period': 3600}}
        if edit:
            message['edit_date'] = int(self.now)
        self.service.ingest_update({'update_id': self.update_id, ('edited_message' if edit else 'message'): message},
                                   GENERATION)

    def turn(self, text):
        self.message_id += 1
        job = self.store.enqueue(text, f'k{self.message_id}')
        self.assertTrue(self.service.run_one())
        return job

    def outbound(self, tool):
        return [plan for plan in self.network.plans if plan['tool'] == tool]

    def memories(self):
        return sorted((row['memory_key'], row['content']) for row in self.store.memories('local-owner'))

    # --- journeys -----------------------------------------------------------

    def test_location_updates_alone_invoke_no_model_lookup_work_or_reply(self):
        """CT-08/CT-13: a location tick is data, not a request."""
        self.enable()
        self.message_id += 1
        for _ in range(20):
            self.now += 30
            self.share_live_location(edit=self.update_id > 100)
        self.assertEqual((self.model_calls, self.network.plans, self.worker_inputs), ([], [], []))
        self.assertEqual(self.store.jobs(), [])
        self.assertNotIn('sendMessage', self.telegram_calls)

    def test_here_weather_uses_the_fresh_shared_location_through_the_broker(self):
        """CT-13/CT-14/CT-17: the ref from the actual route input resolves to admitted coordinates."""
        self.enable()
        self.message_id += 1
        self.share_live_location()
        job = self.turn('여기 비 와?')
        self.assertEqual(self.outbound('weather'), [ADMITTED], 'rounded coordinates from the admitted source only')
        [result] = self.results
        self.assertEqual(result['location_source']['kind'], 'live_position_report')
        self.assertIn('not verified GPS', result['location_source']['basis'])
        self.assertEqual(result['sent'], {'latitude': 37.57, 'longitude': 126.98}, 'checked payload = sent payload')
        self.assertNotIn('location_ref', json.dumps(self.network.plans), 'the opaque ref never leaves')
        record = self.store.turn_provenance(job)
        self.assertIn('owner-current-context', record['prompt_withheld'], 'the record keeps size/digest only')
        self.assertNotIn('37.57', json.dumps(record))

    def test_a_stale_location_is_not_presented_as_current(self):
        """CT-12: an old point is last-known; the broker refuses it for "here"."""
        self.enable()
        self.message_id += 1
        self.share_live_location()
        self.now += 16 * 60
        self.turn('여기 날씨 어때?')
        self.assertEqual(self.outbound('weather'), [])
        self.assertEqual(self.results[-1]['code'], 'location_stale')
        self.assertIn('물어보세요', self.results[-1]['error'], 'the loop can ask the owner once')

    def test_pause_between_snapshot_and_dispatch_stops_the_lookup(self):
        """CT-16: the ref was in the input; the owner paused before the call ran."""
        self.enable()
        self.message_id += 1
        self.share_live_location()
        self.before_dispatch = lambda: self.service.set_current_context({'enabled': False})
        self.turn('여기 비 와?')
        self.assertEqual(self.outbound('weather'), [])
        self.assertEqual(self.results[-1]['code'], 'context_paused')

    def test_clear_revokes_a_ref_from_an_earlier_snapshot(self):
        self.enable()
        self.message_id += 1
        self.share_live_location()
        self.before_dispatch = lambda: self.service.set_current_context({'clear': True})
        self.turn('여기 비 와?')
        self.assertEqual(self.outbound('weather'), [])
        self.assertEqual(self.results[-1]['code'], 'location_ref_unknown')

    def test_work_from_home_today_steers_lunch_without_touching_profile(self):
        """CT-10/CT-14: the temporary exception picks the home anchor; profile.* is unchanged."""
        self.enable()
        before = self.memories()
        self.turn('오늘 재택이야')
        self.assertTrue(self.results[-1]['recorded'], self.results[-1])
        self.assertIn('propose_current_state', self.worker_inputs[-1]['tools'])
        self.turn('점심 먹을 데 찾아줘')
        self.assertEqual([plan['query'] for plan in self.outbound('web_search')], ['합정 점심 맛집'])
        self.assertEqual(self.memories(), before, 'the work anchor is still 판교; nothing new was remembered')
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM memory_candidates').fetchone()[0], 0)

    def test_a_saved_private_value_never_reaches_the_wire(self):
        """CT-15 (pilot): the admitted place goes out; the value saved in this Work does not."""
        self.enable()
        self.turn('오늘 재택이야')
        self.turn('여권번호 저장하고 점심 먹을 데 찾아줘')
        [plan] = self.outbound('web_search')
        self.assertIn('합정', plan['query'])
        self.assertNotIn(PASSPORT, json.dumps(self.network.plans))

    def test_context_off_is_the_old_text_flow(self):
        """CT-18: no section, no proposal tool, no lookup from context."""
        self.message_id += 1
        self.share_live_location()
        self.turn('여기 비 와?')
        self.assertIsNone(snapshot_in(self.worker_inputs[-1]['text']))
        self.assertNotIn(CURRENT_CONTEXT_HEADING, self.worker_inputs[-1]['text'])
        self.assertNotIn('propose_current_state', self.worker_inputs[-1]['tools'])
        self.assertEqual(self.network.plans, [])


class ApiRoute(_ConsumptionCase, unittest.TestCase):
    ROUTE = 'api'


class CliRoute(_ConsumptionCase, unittest.TestCase):
    ROUTE = 'cli'


class BridgeProcessResolution(unittest.TestCase):
    """The CLI's MCP bridge builds its broker from the store alone (``mcp_bridge.serve``)."""

    def test_a_bridge_built_broker_resolves_the_same_ref_from_the_store(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / 'state')
        service = AgentService(store)
        store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': GENERATION, 'cursor': 0})
        service.set_current_context({'enabled': True})
        now = int(time.time()) + 1  # after the enable cutoff
        service.ingest_update({'update_id': 1, 'message': {'message_id': 7, 'from': {'id': CHAT}, 'date': now,
                                                           'chat': {'id': CHAT, 'type': 'private'},
                                                           'location': dict(SEOUL_POINT)}}, GENERATION)
        # An unsolicited pin is a place reference: usable as a place, never "here".
        ref = 'obs:' + service.current_state.observations.usable()[0]['id']
        job = store.enqueue('그 장소 날씨', 'k1')
        with store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job,))
        network = _Network()
        caps = Capabilities(store, None, {}, '', job, lambda *a: None, network=network, document_access=False,
                            allowed_tools=set(profile_actions(AgentOSMcpTools.PROFILE)),
                            lookup_sources=lambda: lookup_sources(store, job))
        result = AgentOSMcpTools(caps).call('weather', {'location_ref': ref})
        self.assertEqual(network.plans, [ADMITTED])
        self.assertEqual(result['location_source']['kind'], 'place_reference')
        self.assertEqual(result['sent'], {'latitude': 37.57, 'longitude': 126.98}, 'checked payload = sent payload')
        with self.assertRaises(ToolError) as unknown:
            AgentOSMcpTools(caps).call('weather', {'location_ref': 'obs:unknown'})
        self.assertEqual(unknown.exception.code, 'location_ref_unknown')
        # The bridge's own proposal path validates against the same store.
        refused = AgentOSMcpTools(caps).call('propose_current_state', {'predicate': 'work_mode', 'value': 'remote',
                                                                       'source': 'state:x'})
        self.assertEqual((refused['recorded'], refused['reason']), (False, 'unsupported_source'))
        self.assertEqual(len(network.plans), 1)


def last_tool(body):
    """The last tool result a model turn was shown (a loop nudge may follow it)."""
    return json.loads(next(m for m in reversed(body['messages']) if m['role'] == 'tool')['content'])


class LoopCompletion(unittest.TestCase):
    """SEC-LOOP-01 (#657) meets #627: refs, internal state and repeat keys in ``run_agent``."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'state')
        self.service = AgentService(self.store)
        self.now = float(int(time.time()) + 1)
        self.service.context_observations.clock = lambda: self.now
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': GENERATION, 'cursor': 0})
        self.service.set_current_context({'enabled': True, 'timezone': 'Asia/Seoul'})
        self.update_id = 0
        self.network, self.events = _Network(), []

    def share(self, edit=False):
        self.update_id += 1
        message = {'message_id': 7, 'from': {'id': CHAT}, 'chat': {'id': CHAT, 'type': 'private'},
                   'date': int(self.now) - (30 if edit else 0), 'location': {**SEOUL_POINT, 'live_period': 3600}}
        if edit:
            message['edit_date'] = int(self.now)
        self.service.ingest_update({'update_id': self.update_id,
                                    ('edited_message' if edit else 'message'): message}, GENERATION)
        return 'obs:' + self.service.current_state.observations.usable()[0]['id']

    def loop(self, text, *script, answer=True):
        job = self.store.enqueue(text, f'k{len(self.events)}')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running', created=? WHERE id=?", (self.now, job))
        transport = Script(*script)
        caps = Capabilities(self.store, ModelAdapter(transport), CFG, '', job,
                            lambda tool, status, detail: self.events.append((tool, status, detail)),
                            network=self.network, lookup_sources=lambda: lookup_sources(self.store, job),
                            judgments=judgments(answer), current_context=self.service.current_state)
        result = run_agent(caps.adapter, CFG, '',
                           [{'role': 'user', 'content': text}], '', caps, caps.record)
        return result, transport

    def test_a_weather_ref_result_carries_the_loop_ref_and_can_be_cited(self):
        ref = self.share()
        result, transport = self.loop('여기 비 와?', {'tool_calls': [call('w1', 'weather', location_ref=ref)]},
                                     finish('f1', 'w1'), answer=True)
        tool = last_tool(transport.bodies[1])
        self.assertEqual(tool['ref'], 'w1', 'the loop call id, not the location ref')
        self.assertEqual(tool['location_source']['ref'], ref)
        self.assertEqual(result.outcome, 'succeeded')

    def test_a_proposal_is_neither_failure_nor_goal_evidence(self):
        # Only internal state ran: a plain answer concludes like conversation.
        result, transport = self.loop('오늘 재택이야', {'tool_calls': [call('p1', 'propose_current_state',
                                                                     predicate='work_mode', value='remote')]},
                                     {'content': '오늘은 재택으로 기억해 둘게요.'})
        tool = last_tool(transport.bodies[1])
        self.assertEqual(tool['ref'], 'p1')
        self.assertTrue(tool['recorded'])
        self.assertTrue(tool['state_ref'].startswith('state:'))
        self.assertEqual(result.outcome, 'succeeded')
        self.assertEqual(len(transport.bodies), 2, 'no completion check for internal bookkeeping')
        # A done claim resting only on a proposal has no goal evidence.
        result, transport = self.loop('오늘 재택이야 2', {'tool_calls': [call('p2', 'propose_current_state',
                                                                       predicate='work_mode', value='office')]},
                                     finish('f2', 'p2'), {'content': '알겠어요.'})
        rejected = last_tool(transport.bodies[2])
        self.assertEqual(rejected['code'], 'no_evidence')
        self.assertEqual(result.outcome, 'succeeded', 'then answered as conversation, not a failure')

    def test_the_same_ref_is_a_repeat_only_while_its_source_revision_is_unchanged(self):
        ref = self.share()
        weather = lambda ident: {'tool_calls': [call(ident, 'weather', location_ref=ref)]}  # noqa: E731

        def moved(body):
            self.now += 60
            self.share(edit=True)
            return weather('w3')
        result, transport = self.loop('여기 비 와?', weather('w1'), weather('w2'), moved,
                                     finish('f1', 'w1', 'w3'))
        second = last_tool(transport.bodies[2])
        self.assertEqual(second['code'], 'duplicate_call', 'unchanged source: a repeat')
        third = last_tool(transport.bodies[3])
        self.assertEqual(third['ref'], 'w3', 'a new live point: a new path that runs')
        self.assertEqual(len([plan for plan in self.network.plans if plan['tool'] == 'weather']), 2)


if __name__ == '__main__':
    unittest.main()
