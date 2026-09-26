"""SEC-SEARCH-01 #655: model-chosen multi-provider web search.

Evidence class: deterministic unit tests with an injected fake HTTP opener
shaped after the Bing RSS feed, the Naver Open API and the Brave Search API
responses, a fake public wire for the Capabilities path and a temporary owner
store.  No live provider, key or network is used.
"""
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from personal_agent.agent_runtime import Capabilities, action_definitions, classify_failure, evidence_summary
from personal_agent.bounded_execution import ExecutionResult
from personal_agent.local_tools import LocalTools
from personal_agent.manifests import runtime_packages
from personal_agent.portable_state import export_owner_state
from personal_agent.providers import ModelAdapter, ProviderError
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.search_providers import (BRAVE_TOKEN, CONFIG_KEY, NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, BingRssProvider,
                                             BraveProvider, NaverProvider, ProviderRegistry, SearchProviderError,
                                             SearchProviderSettings, search_arguments)
from personal_agent.subscription_engines import SubscriptionEngines

NAVER_ID = 'naver-id-fixture-0001'
NAVER_SECRET = 'naver-secret-fixture-0001'
BRAVE_KEY = 'brave-token-fixture-0001'
CFG = {'provider': 'compatible', 'endpoint': 'http://127.0.0.1:9999', 'model': 'fixture'}

BING_RSS = b'''<?xml version="1.0"?><rss><channel><item><title>Leaders and differences</title>
<link>https://example.org/leaders</link><description>When leaders make a difference.</description></item>
<item><title>ftp result</title><link>ftp://example.org/no</link><description>skipped</description></item>
<item><title>Second</title><link>http://example.org/second</link><description>d2</description></item></channel></rss>'''
NAVER_WEB = {'items': [{'title': '<b>리더</b>는 언제 차이를 만들어내는가 &amp; 후기', 'link': 'https://blog.example.kr/leaders',
                        'description': '<b>리더십</b> 책 후기'},
                       {'title': 'javascript link', 'link': 'javascript:alert(1)', 'description': 'skipped'}]}
NAVER_BOOK = {'items': [{'title': '리더는 언제 <b>차이</b>를 만들어내는가', 'link': 'https://search.shopping.naver.com/book/1',
                         'author': '홍길동', 'publisher': '출판사', 'pubdate': '20240101', 'isbn': '9788900000000',
                         'description': '리더십에 관한 책'}]}
BRAVE = {'web': {'results': [{'title': 'Brave result', 'url': 'https://example.com/brave', 'description': 'From Brave'},
                             {'title': 'no url'}]}}


class Opener:
    """The fake wire: records each request's URL and headers, answers per host."""

    def __init__(self, status=200):
        self.requests, self.status = [], status

    def open(self, request, timeout=None):
        self.requests.append({'url': request.full_url, 'headers': dict(request.header_items())})
        if self.status != 200:
            raise HTTPError(request.full_url, self.status, 'refused', {}, io.BytesIO(b'{"error":"secret-body"}'))
        host, path = urlsplit(request.full_url).hostname, urlsplit(request.full_url).path
        if host == 'www.bing.com':
            body = BING_RSS
        elif host == 'openapi.naver.com':
            body = json.dumps(NAVER_BOOK if path.endswith('book.json') else NAVER_WEB).encode()
        elif host == 'api.search.brave.com':
            body = json.dumps(BRAVE).encode()
        else:
            raise AssertionError('unexpected destination ' + request.full_url)
        return io.BytesIO(body)


def registry(opener=None, **config):
    return ProviderRegistry.from_config(config, opener=opener or Opener())


def all_keys(**extra):
    return {NAVER_CLIENT_ID: NAVER_ID, NAVER_CLIENT_SECRET: NAVER_SECRET, BRAVE_TOKEN: BRAVE_KEY, **extra}


def query_of(url):
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


class ProviderParsing(unittest.TestCase):
    def test_bing_rss_parses_as_before_and_carries_its_provider(self):
        opener = Opener()
        rows = BingRssProvider().search('leaders', opener=opener)
        self.assertEqual(rows, [{'title': 'Leaders and differences', 'url': 'https://example.org/leaders',
                                 'snippet': 'When leaders make a difference.', 'provider': 'bing'},
                                {'title': 'Second', 'url': 'http://example.org/second', 'snippet': 'd2', 'provider': 'bing'}])
        self.assertEqual(query_of(opener.requests[0]['url']), {'format': 'rss', 'q': 'leaders'})
        self.assertNotIn('X-Naver-Client-Id', opener.requests[0]['headers'])

    def test_bing_market_comes_only_from_the_model_locale_never_from_the_script(self):
        for query in ('leaders', '리더는 언제 차이를 만들어내는가'):
            with self.subTest(query=query):
                opener = Opener()
                BingRssProvider().search(query, opener=opener)
                self.assertEqual(query_of(opener.requests[0]['url']), {'format': 'rss', 'q': query})
                opener = Opener()
                BingRssProvider().search(query, locale='ko-KR', opener=opener)
                sent = query_of(opener.requests[0]['url'])
                self.assertEqual((sent['mkt'], sent['setlang']), ('ko-KR', 'ko'))

    def test_naver_web_strips_tags_and_entities_and_sends_its_headers(self):
        opener = Opener()
        rows = NaverProvider(NAVER_ID, NAVER_SECRET).search('리더', opener=opener)
        self.assertEqual(rows, [{'title': '리더는 언제 차이를 만들어내는가 & 후기', 'url': 'https://blog.example.kr/leaders',
                                 'snippet': '리더십 책 후기', 'provider': 'naver'}])
        request = opener.requests[0]
        self.assertTrue(request['url'].startswith('https://openapi.naver.com/v1/search/webkr.json?'))
        self.assertEqual(query_of(request['url']), {'query': '리더', 'display': '5', 'start': '1', 'sort': 'sim'})
        self.assertEqual((request['headers']['X-naver-client-id'], request['headers']['X-naver-client-secret']),
                         (NAVER_ID, NAVER_SECRET))

    def test_naver_book_kind_uses_the_book_endpoint_and_folds_bibliographic_fields(self):
        opener = Opener()
        rows = NaverProvider(NAVER_ID, NAVER_SECRET).search('리더', kind='book', opener=opener)
        self.assertTrue(opener.requests[0]['url'].startswith('https://openapi.naver.com/v1/search/book.json?'))
        self.assertEqual(rows[0]['title'], '리더는 언제 차이를 만들어내는가')
        self.assertEqual(rows[0]['snippet'], '홍길동 · 출판사 · 20240101 · ISBN 9788900000000\n리더십에 관한 책')
        self.assertEqual(rows[0]['provider'], 'naver')

    def test_brave_parses_web_results_and_sends_locale_as_country_and_language(self):
        opener = Opener()
        rows = BraveProvider(BRAVE_KEY).search('leaders', locale='en-US', opener=opener)
        self.assertEqual(rows, [{'title': 'Brave result', 'url': 'https://example.com/brave', 'snippet': 'From Brave',
                                 'provider': 'brave'}])
        request = opener.requests[0]
        self.assertEqual(query_of(request['url']), {'q': 'leaders', 'count': '5', 'search_lang': 'en', 'country': 'US'})
        self.assertEqual(request['headers']['X-subscription-token'], BRAVE_KEY)
        self.assertEqual(request['headers']['Accept'], 'application/json')

    def test_http_401_and_429_are_typed_failures_without_the_body_or_key(self):
        for status, code in ((401, 'provider_auth'), (403, 'provider_auth'), (429, 'provider_rate_limited')):
            with self.subTest(status=status):
                with self.assertRaises(SearchProviderError) as failed:
                    BraveProvider(BRAVE_KEY).search('x', opener=Opener(status=status))
                self.assertEqual((failed.exception.code, failed.exception.status), (code, status))
                self.assertNotIn(BRAVE_KEY, str(failed.exception))
                self.assertNotIn('secret-body', str(failed.exception))
                # The loop re-plans (another provider or query), never the same call.
                self.assertEqual(classify_failure(failed.exception, 'web_search'), (code, 'permanent', 'none'))

    def test_other_http_statuses_stay_untyped_provider_errors(self):
        with self.assertRaises(ProviderError) as failed:
            NaverProvider(NAVER_ID, NAVER_SECRET).search('x', opener=Opener(status=503))
        self.assertNotIsInstance(failed.exception, SearchProviderError)
        self.assertEqual(failed.exception.status, 503)
        self.assertEqual(classify_failure(failed.exception, 'web_search')[0], 'transient_failure')


class RegistryRules(unittest.TestCase):
    def test_only_keyed_providers_are_listed_and_bing_always_is(self):
        self.assertEqual([row['id'] for row in registry().options()], ['bing'])
        self.assertEqual([row['id'] for row in registry(**{BRAVE_TOKEN: BRAVE_KEY}).options()], ['bing', 'brave'])
        # Naver needs both values; one alone lists nothing.
        self.assertEqual([row['id'] for row in registry(**{NAVER_CLIENT_ID: NAVER_ID}).options()], ['bing'])
        self.assertEqual([row['id'] for row in registry(**all_keys()).options()], ['bing', 'naver', 'naver-book', 'brave'])

    def test_missing_key_means_absent_from_the_list_and_a_typed_failure_if_named_anyway(self):
        with self.assertRaises(SearchProviderError) as failed:
            registry().search('x', provider='brave')
        self.assertEqual(failed.exception.code, 'provider_unavailable')

    def test_the_owner_default_is_used_when_the_model_omits_provider(self):
        opener = Opener()
        result = registry(opener, default='brave', **all_keys()).search('leaders')
        self.assertEqual(result['provider'], 'brave')
        self.assertEqual(urlsplit(opener.requests[0]['url']).hostname, 'api.search.brave.com')

    def test_a_default_whose_key_was_removed_falls_back_to_bing(self):
        self.assertEqual(registry(default='naver').default(), 'bing')
        self.assertEqual(registry(default='naver', **all_keys()).default(), 'naver')

    def test_the_model_choice_is_honored_regardless_of_the_query_language(self):
        # No language, script or category rule: a Korean query goes where the
        # model says (or to the default), and so does an English one.
        for query, provider, host in (('리더는 언제 차이를 만들어내는가', None, 'www.bing.com'),
                                      ('리더는 언제 차이를 만들어내는가', 'naver-book', 'openapi.naver.com'),
                                      ('when do leaders make a difference', 'naver', 'openapi.naver.com'),
                                      ('when do leaders make a difference', 'brave', 'api.search.brave.com'),
                                      ('리더', 'brave', 'api.search.brave.com')):
            with self.subTest(query=query, provider=provider):
                opener = Opener()
                result = registry(opener, **all_keys()).search(query, provider=provider)
                self.assertEqual(urlsplit(opener.requests[0]['url']).hostname, host)
                self.assertEqual(result['provider'], provider or 'bing')
                self.assertTrue(all(row['provider'] == (provider or 'bing').split('-')[0] for row in result['results']))

    def test_provider_id_with_a_separate_kind_resolves_to_the_option(self):
        reg = registry(**all_keys())
        self.assertEqual(reg.resolve('naver', 'book')[1], 'book')
        self.assertEqual(reg.resolve('naver-book')[1], 'book')
        with self.assertRaises(SearchProviderError):
            reg.resolve('brave', 'book')

    def test_result_payload_is_normalized_with_provider_and_selectors(self):
        result = registry(**all_keys()).search('leaders', provider='naver-book', locale='ko-KR')
        self.assertEqual((result['tool'], result['provider'], result['kind'], result['locale']), ('web_search', 'naver-book', 'book', 'ko-KR'))
        self.assertEqual(set(result['results'][0]), {'title', 'url', 'snippet', 'provider'})
        self.assertEqual(result['sources'], [result['results'][0]['url']])


class LocalToolsPlan(unittest.TestCase):
    def test_execute_passes_provider_kind_and_locale_through(self):
        opener = Opener()
        tools = LocalTools(providers=registry(opener, **all_keys()))
        result = tools.execute({'tool': 'web_search', 'query': ' leaders ', 'provider': 'brave', 'locale': 'ko-KR'})
        self.assertEqual(result['provider'], 'brave')
        self.assertEqual(query_of(opener.requests[0]['url']), {'q': 'leaders', 'count': '5', 'search_lang': 'ko', 'country': 'KR'})

    def test_a_plan_without_selectors_uses_the_default_and_a_bad_locale_is_refused(self):
        opener = Opener()
        tools = LocalTools(providers=registry(opener, default='naver', **all_keys()))
        self.assertEqual(tools.execute({'tool': 'web_search', 'query': 'x'})['provider'], 'naver')
        with self.assertRaises(ValueError):
            tools.execute({'tool': 'web_search', 'query': 'x', 'locale': 'ko-KR; drop table'})
        with self.assertRaises(ValueError):
            tools.search('')

    def test_without_a_registry_only_bing_exists(self):
        self.assertEqual([row['id'] for row in LocalTools().providers.options()], ['bing'])


class ToolSchema(unittest.TestCase):
    def setUp(self):
        self.tools = {tool['id']: tool for package in runtime_packages([]) for tool in package['tools']}

    def definition(self, reg=None):
        rows = action_definitions(self.tools, {'web_search'}, search_providers=reg)
        return rows[0]['function']

    def test_enum_is_exactly_the_configured_options_and_the_text_names_them_without_a_preference(self):
        function = self.definition(registry(**all_keys()))
        self.assertEqual(function['parameters']['properties']['provider']['enum'], ['bing', 'naver', 'naver-book', 'brave'])
        self.assertEqual(function['parameters']['required'], ['query'])
        self.assertIn('locale', function['parameters']['properties'])
        for option in ('bing = Bing web search', 'naver-book = Naver book catalogue', 'brave = Brave Search API'):
            self.assertIn(option, function['description'])
        self.assertIn('When provider is omitted, bing is used.', function['description'])
        for steer in ('prefer', 'Korean quer', 'best for'):
            self.assertNotIn(steer, function['description'])

    def test_bounded_research_carries_the_same_provider_enum_and_text(self):
        rows = action_definitions(self.tools, {'bounded_public_research', 'web_search'}, search_providers=registry(**all_keys()))
        research, search = (next(r['function'] for r in rows if r['function']['name'] == name)
                            for name in ('bounded_public_research', 'web_search'))
        self.assertEqual(research['parameters']['properties']['provider'], search['parameters']['properties']['provider'])
        self.assertIn('locale', research['parameters']['properties'])
        self.assertEqual(research['parameters']['required'], ['mode', 'query'])
        self.assertTrue(research['description'].endswith(search['description'][search['description'].index(' Providers configured'):]))

    def test_enum_shrinks_with_the_keys_and_is_absent_without_a_registry(self):
        self.assertEqual(self.definition(registry())['parameters']['properties']['provider']['enum'], ['bing'])
        self.assertNotIn('enum', self.definition()['parameters']['properties']['provider'])

    def test_capabilities_definitions_use_the_network_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = QuickStore(Path(tmp) / 'data')
            store.secret(BRAVE_TOKEN, BRAVE_KEY)
            caps = Capabilities(store, None, {}, '', 'job', lambda *e: None,
                                network=LocalTools(providers=ProviderRegistry.from_store(store)))
            spec = next(d['function'] for d in caps.definitions() if d['function']['name'] == 'web_search')
            self.assertEqual(spec['parameters']['properties']['provider']['enum'], ['bing', 'brave'])
            # A key saved later is offered on the next listing without a restart.
            store.secret(NAVER_CLIENT_ID, NAVER_ID); store.secret(NAVER_CLIENT_SECRET, NAVER_SECRET)
            spec = next(d['function'] for d in caps.definitions() if d['function']['name'] == 'web_search')
            self.assertEqual(spec['parameters']['properties']['provider']['enum'], ['bing', 'naver', 'naver-book', 'brave'])


class Wire:
    """A fake public transport that records the exact outbound plan."""

    def __init__(self):
        self.plans = []

    def execute(self, plan):
        self.plans.append(dict(plan))
        if plan['tool'] == 'public_page_read':
            return {'tool': 'public_page_read', 'url': plan['url'], 'content': 'Model A costs 100 USD.', 'sources': [plan['url']], 'retrieved_at': 1}
        return {'tool': 'web_search', 'query': plan['query'], 'provider': plan.get('provider', 'bing'), 'kind': 'web',
                'locale': plan.get('locale', ''), 'retrieved_at': 1,
                'results': [{'title': 't', 'url': 'https://example.org/', 'snippet': 's', 'provider': plan.get('provider', 'bing')}],
                'sources': ['https://example.org/']}


class CapabilitiesPath(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'data')
        self.events = []

    def record(self, tool, status, detail):
        self.events.append((tool, status, detail))

    def test_the_model_provider_and_locale_reach_the_wire_on_the_direct_path(self):
        wire = Wire()
        caps = Capabilities(self.store, None, CFG, '', 'job-1', self.record, network=wire)
        result = caps.execute('web_search', {'query': 'leaders', 'provider': 'naver-book', 'locale': 'ko-KR'})
        self.assertEqual(wire.plans, [{'tool': 'web_search', 'query': 'leaders', 'provider': 'naver-book', 'locale': 'ko-KR'}])
        self.assertEqual(result['provider'], 'naver-book')
        summary = evidence_summary('web_search', result)
        self.assertEqual((summary['provider'], summary['locale'], summary['sources']), ('naver-book', 'ko-KR', ['https://example.org/']))

    def test_the_selectors_ride_along_the_composed_lookup_and_are_recorded_as_sent(self):
        wire = Wire()
        caps = Capabilities(self.store, None, CFG, '', 'job-2', self.record, network=wire,
                            lookup_sources=lambda: {'permitted': ['leaders'], 'excluded': []})
        result = caps.execute('web_search', {'query': 'leaders', 'provider': 'brave', 'locale': 'en-US'})
        self.assertEqual(wire.plans, [{'tool': 'web_search', 'query': 'leaders', 'provider': 'brave', 'locale': 'en-US'}])
        self.assertEqual(result['sent'], {'query': 'leaders', 'provider': 'brave', 'locale': 'en-US'})
        self.assertEqual(result['composed_by'], 'agentos-public-task')

    def test_omitted_selectors_leave_the_plan_unchanged(self):
        wire = Wire()
        caps = Capabilities(self.store, None, CFG, '', 'job-3', self.record, network=wire,
                            lookup_sources=lambda: {'permitted': ['leaders'], 'excluded': []})
        caps.execute('web_search', {'query': 'leaders'})
        self.assertEqual(wire.plans, [{'tool': 'web_search', 'query': 'leaders'}])

    def test_bounded_research_carries_the_model_provider_on_both_routes(self):
        # Codex P1 on PR #666: research made a bare web_search plan, so the
        # model could not choose or switch providers for a comparison.
        for route, resolver in (('direct', None), ('composed', lambda: {'permitted': ['headphones'], 'excluded': []})):
            with self.subTest(route=route):
                wire = Wire()
                caps = Capabilities(self.store, None, CFG, '', f'job-{route}', self.record, network=wire, lookup_sources=resolver)
                result = caps.execute('bounded_public_research', {'mode': 'product_comparison', 'query': 'headphones',
                                                                  'provider': 'brave', 'locale': 'en-US'})
                self.assertEqual(wire.plans[0], {'tool': 'web_search', 'query': 'headphones', 'provider': 'brave', 'locale': 'en-US'})
                self.assertEqual((result['provider'], result['locale']), ('brave', 'en-US'))
                if route == 'composed':
                    self.assertEqual(result['sent'], {'query': 'headphones', 'mode': 'product_comparison', 'provider': 'brave', 'locale': 'en-US'})
                summary = evidence_summary('bounded_public_research', result)
                self.assertEqual((summary['provider'], summary['locale']), ('brave', 'en-US'))
                # Without selectors the plan is bare: the configured default applies, nothing is inferred.
                wire.plans.clear()
                caps.execute('bounded_public_research', {'mode': 'travel_plan', 'query': 'headphones'})
                self.assertEqual(wire.plans[0], {'tool': 'web_search', 'query': 'headphones'})

    def test_bounded_research_default_and_choice_reach_the_configured_provider(self):
        class Pages:
            @staticmethod
            def read(url, approved_urls=None):
                return {'tool': 'public_page_read', 'url': url, 'content': 'Brave result page.', 'sources': [url], 'retrieved_at': 1}
        opener = Opener()
        tools = LocalTools(page_reader=Pages(), providers=registry(opener, default='naver-book', **all_keys()))
        caps = Capabilities(self.store, None, CFG, '', 'job-r', self.record, network=tools)
        result = caps.execute('bounded_public_research', {'mode': 'travel_plan', 'query': 'seoul hotels', 'provider': 'brave'})
        self.assertEqual(urlsplit(opener.requests[0]['url']).hostname, 'api.search.brave.com')
        self.assertEqual(result['provider'], 'brave')
        opener.requests.clear()
        result = caps.execute('bounded_public_research', {'mode': 'product_comparison', 'query': 'leaders'})
        self.assertTrue(opener.requests[0]['url'].startswith('https://openapi.naver.com/v1/search/book.json?'))
        self.assertEqual(result['provider'], 'naver-book')

    def test_selectors_are_bounded_ids_not_free_text(self):
        self.assertEqual(search_arguments({'query': 'x', 'provider': ' naver-book ', 'locale': 'ko-KR'}),
                         {'provider': 'naver-book', 'locale': 'ko-KR'})
        self.assertEqual(search_arguments({'query': 'x', 'provider': '', 'locale': ''}), {})
        for bad in ({'provider': 'naver book'}, {'provider': 'PRIVATE-XYZ'}, {'provider': 'a' * 41}):
            with self.assertRaises(SearchProviderError):
                search_arguments(bad)
        for bad in ({'locale': 'ko-KR M1234567'}, {'locale': 'kor-KOREA'}, {'locale': 'x'}):
            with self.assertRaises(ValueError):
                search_arguments(bad)

    def test_a_provider_failure_is_a_typed_observation_in_the_loop(self):
        from personal_agent.agent_runtime import run_agent

        class Refusing:
            def execute(self, plan):
                raise SearchProviderError('키 거부', 'provider_auth', 401)

        bodies = []

        def transport(url, body, headers=None, timeout=60):
            bodies.append(json.loads(json.dumps(body)))
            if len(bodies) == 1:
                return {'choices': [{'message': {'tool_calls': [{'id': '1', 'function': {'name': 'web_search', 'arguments': json.dumps({'query': 'x', 'provider': 'brave'})}}]}}]}
            return {'choices': [{'message': {'content': '다른 제공자로 다시 찾겠습니다.'}}]}
        caps = Capabilities(self.store, ModelAdapter(transport), CFG, '', 'job-4', self.record, network=Refusing())
        run_agent(caps.adapter, CFG, '', [{'role': 'user', 'content': 'x'}], '', caps, self.record)
        observation = json.loads(bodies[1]['messages'][-1]['content'])
        self.assertEqual((observation['code'], observation['retry']), ('provider_auth', 'permanent'))
        failed = [json.loads(detail) for tool, status, detail in self.events if status == 'failed' and tool != 'model']
        self.assertEqual([row['code'] for row in failed], ['provider_auth'])


class _Engine:
    def execute(self, engine, prompt, tools, **_kwargs):
        return ExecutionResult('engine answer', engine, 0)

    def login_status(self, engine_id, binary=None):
        return {'state': 'signed-in'}


class SettingsApi(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / 'state'
        self.service = AgentService(QuickStore(self.root), adapter=ModelAdapter(lambda *a, **k: {}),
                                    subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/cli', clock=lambda: 1),
                                    execution_adapter=_Engine())
        self.store = self.service.store

    def status(self):
        return self.service.settings()['search_providers']

    def test_keys_round_trip_into_the_secret_store_and_are_never_returned(self):
        before = self.status()
        self.assertEqual([row['id'] for row in before['options']], ['bing'])
        self.assertFalse(any(row['key']['saved'] for row in before['providers']))
        self.service.save_search_provider_key({'provider': 'naver', 'client_id': NAVER_ID, 'client_secret': NAVER_SECRET})
        status = self.service.save_search_provider_key({'provider': 'brave', 'key': ' ' + BRAVE_KEY + '\n'})
        self.assertEqual(self.store.secret(NAVER_CLIENT_ID), NAVER_ID)
        self.assertEqual(self.store.secret(NAVER_CLIENT_SECRET), NAVER_SECRET)
        self.assertEqual(self.store.secret(BRAVE_TOKEN), BRAVE_KEY)
        rows = {row['id']: row for row in status['providers']}
        self.assertTrue(rows['naver']['key']['saved'] and rows['brave']['key']['saved'])
        self.assertIsNotNone(rows['naver']['key']['saved_at'])
        self.assertEqual([row['id'] for row in status['options']], ['bing', 'naver', 'naver-book', 'brave'])
        dumped = json.dumps(self.service.settings(), ensure_ascii=False)
        for secret in (NAVER_ID, NAVER_SECRET, BRAVE_KEY, 'fixture-0001'):
            self.assertNotIn(secret, dumped)
        # The live tool list follows the saved keys.
        spec = next(d['function'] for d in Capabilities(self.store, None, {}, '', 'job', lambda *e: None,
                                                        network=self.service.local_tools).definitions()
                    if d['function']['name'] == 'web_search')
        self.assertEqual(spec['parameters']['properties']['provider']['enum'], ['bing', 'naver', 'naver-book', 'brave'])

    def test_removing_a_key_drops_the_provider_and_the_default_falls_back(self):
        self.service.save_search_provider_key({'provider': 'brave', 'key': BRAVE_KEY})
        self.service.set_search_provider_default({'provider': 'brave'})
        self.assertEqual(self.status()['default'], 'brave')
        status = self.service.save_search_provider_key({'provider': 'brave', 'key': ''})
        self.assertEqual(self.store.secret(BRAVE_TOKEN), '')
        self.assertEqual([row['id'] for row in status['options']], ['bing'])
        self.assertEqual((status['default'], status['configured_default']), ('bing', 'brave'))
        self.assertFalse({row['id']: row for row in status['providers']}['brave']['key']['saved'])

    def test_invalid_key_and_default_requests_are_refused(self):
        with self.assertRaises(ValueError):
            self.service.save_search_provider_key({'provider': 'google', 'key': 'x'})
        with self.assertRaises(ValueError):
            self.service.save_search_provider_key({'provider': 'naver', 'client_id': NAVER_ID, 'client_secret': ''})
        with self.assertRaises(ValueError):
            self.service.save_search_provider_key({'provider': 'brave', 'key': 'two words'})
        with self.assertRaises(ValueError):
            self.service.set_search_provider_default({'provider': 'naver'})  # not configured
        self.assertEqual(self.store.secret(NAVER_CLIENT_ID), '')
        self.assertEqual(self.status()['default'], 'bing')

    def test_stored_keys_are_redacted_from_provenance_and_absent_from_the_export(self):
        self.service.save_search_provider_key({'provider': 'naver', 'client_id': NAVER_ID, 'client_secret': NAVER_SECRET})
        self.service.save_search_provider_key({'provider': 'brave', 'key': BRAVE_KEY})
        text = f'sent {NAVER_ID} and {NAVER_SECRET} with {BRAVE_KEY}'
        redacted = self.service._redact_provenance(text)
        for secret in (NAVER_ID, NAVER_SECRET, BRAVE_KEY):
            self.assertNotIn(secret, redacted)
        self.assertIn('[redacted]', redacted)
        archive = export_owner_state(self.root, self.root.with_name('owner-export.tar.gz'))
        with tarfile.open(archive, 'r:gz') as bundle:
            blobs = b''.join(bundle.extractfile(member).read() for member in bundle.getmembers() if member.isfile())
        for secret in (NAVER_ID, NAVER_SECRET, BRAVE_KEY):
            self.assertNotIn(secret.encode(), blobs)
        # The config row keeps only when a key was saved, never the value.
        row = self.store.config(CONFIG_KEY)
        self.assertEqual(set(row['keys']), {'naver', 'brave'})
        self.assertNotIn(BRAVE_KEY, json.dumps(row))

    def test_settings_object_reads_the_store_without_a_service(self):
        settings = SearchProviderSettings(self.store, clock=lambda: 42.0)
        settings.save_key({'provider': 'brave', 'key': BRAVE_KEY})
        self.assertEqual(settings.status()['providers'][1]['key'], {'saved': True, 'saved_at': 42.0})


if __name__ == '__main__':
    unittest.main()
