"""Replaceable web-search providers behind one model-facing tool (SEC-SEARCH-01 #655).

The model calls ``web_search(query, provider?, locale?)``.  Which providers
exist is the owner's Settings decision (a provider is listed exactly when its
key is saved; Bing RSS needs none).  Which of them a call uses is the
model's decision, passed as ``provider``; when it is omitted the owner's
configured default is used.  Nothing here chooses a provider from the
query's language, script or subject: that would be scenario code the
Secretary Agency Contract forbids.

Adopt / Adapt / Build: the official Naver Open API and Brave Search API are
called over stdlib ``urllib`` (no new dependency).  The Bing RSS read moved
here from ``LocalTools.search`` unchanged.  AgentOS owns only the key slots,
the availability list, result normalization and the typed failures.

Secrets: keys travel only in request headers built here; they never enter a
result payload, an exception text, a log line or Evidence (``ProviderError``
texts are fixed strings).  The slots are redacted by the service's
provenance redactor and are absent from the portable owner-state export,
which never includes the secret file.
"""
import json
import re
import time
import xml.etree.ElementTree as ET
from html import unescape
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener

from .providers import NoRedirect, ProviderError

#: Secret slots in the owner's local secret store (``QuickStore.secret``).
NAVER_CLIENT_ID = 'search_key:naver_client_id'
NAVER_CLIENT_SECRET = 'search_key:naver_client_secret'
BRAVE_TOKEN = 'search_key:brave'
SECRET_SLOTS = (NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, BRAVE_TOKEN)
#: Config row: ``{'default': <option id>, 'keys': {<provider id>: {'saved_at': ...}}}``.
CONFIG_KEY = 'search_providers'
DEFAULT_PROVIDER = 'bing'

MAX_RESPONSE_BYTES = 1_000_000
SEARCH_TIMEOUT_SECONDS = 15
RESULT_LIMIT = 5
USER_AGENT = 'Mozilla/5.0 (compatible; AgentOS/0.1 personal search)'
#: A BCP 47-shaped tag such as ``ko``, ``ko-KR`` or ``en_US``; nothing longer
#: may ride along a lookup from a private context.
LOCALE_PATTERN = re.compile(r'[A-Za-z]{2,3}(?:[-_][A-Za-z]{2})?')
SEARCH_SCOPE = 'Search snippets only; full pages have not been read.'
SEARCH_FAILED_TEXT = '웹 검색 결과를 가져오지 못했습니다. 잠시 후 다시 요청하세요.'
PROVIDER_UNAVAILABLE_TEXT = '선택한 검색 제공자는 설정되어 있지 않습니다. 사용할 수 있는 제공자 중에서 고르세요.'
PROVIDER_AUTH_TEXT = '검색 제공자가 저장된 키를 거부했습니다. 설정에서 키를 확인하세요.'
PROVIDER_RATE_LIMITED_TEXT = '검색 제공자의 요청 한도에 도달했습니다. 다른 제공자를 쓰거나 잠시 후 다시 요청하세요.'
_TAGS = re.compile(r'<[^>]+>')


class SearchProviderError(ProviderError):
    """A typed provider failure the loop can react to (``code`` is stable).

    ``provider_auth`` (401/403: the owner's key was refused),
    ``provider_rate_limited`` (429) and ``provider_unavailable`` (the model
    named a provider the owner has not configured).  ``classify_failure``
    treats a coded error as permanent for this call: re-plan (another
    provider or query), never the same call again.
    """
    def __init__(self, message, code, status=None):
        super().__init__(message, status)
        self.code = code


def _text(value, limit):
    """Plain text from a provider field: tags removed, entities decoded, bounded."""
    if not isinstance(value, str):
        return ''
    return unescape(_TAGS.sub('', value)).strip()[:limit]


def _public_http_url(value):
    return isinstance(value, str) and urlsplit(value).scheme in ('https', 'http')


def result_row(title, url, snippet, provider):
    return {'title': title, 'url': url, 'snippet': snippet, 'provider': provider}


def default_opener():
    return build_opener(NoRedirect())


def fetch(url, headers, opener=None, timeout=SEARCH_TIMEOUT_SECONDS):
    """One bounded GET; the body as bytes.

    Redirects are not followed, the body is capped, and an HTTP status becomes
    a typed failure without the upstream body or the request headers.
    """
    request = Request(url, headers={'User-Agent': USER_AGENT, **headers})
    try:
        with (opener or default_opener()).open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        status = int(getattr(exc, 'code', 0) or 0)
        if status in (401, 403):
            raise SearchProviderError(PROVIDER_AUTH_TEXT, 'provider_auth', status) from None
        if status == 429:
            raise SearchProviderError(PROVIDER_RATE_LIMITED_TEXT, 'provider_rate_limited', status) from None
        raise ProviderError(SEARCH_FAILED_TEXT, status) from None
    except OSError:
        raise ProviderError(SEARCH_FAILED_TEXT) from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ProviderError(SEARCH_FAILED_TEXT)
    return raw


def _json(raw):
    try:
        data = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        raise ProviderError(SEARCH_FAILED_TEXT) from None
    if not isinstance(data, dict):
        raise ProviderError(SEARCH_FAILED_TEXT)
    return data


def split_locale(locale):
    """``(language, region)`` of a validated locale tag; empty parts when absent."""
    if not locale:
        return '', ''
    parts = re.split('[-_]', locale, maxsplit=1)
    return parts[0].lower(), (parts[1].upper() if len(parts) > 1 else '')


class BingRssProvider:
    """The keyless Bing RSS read, as it was in ``LocalTools.search``."""
    id = 'bing'
    label = 'Bing web search (RSS, no key)'
    kinds = ('web',)
    destination = 'www.bing.com'

    def search(self, query, *, kind='web', locale=None, limit=RESULT_LIMIT, opener=None):
        language, region = split_locale(locale)
        if language:
            market = f'{language}-{region}' if region else language
        else:
            # The pre-#655 request default of this keyless provider, kept
            # unchanged: it sets Bing's market for the query, not which
            # provider answers.  A model that wants another market passes
            # ``locale``.
            korean = bool(re.search('[가-힣]', query))
            market, language = ('ko-KR', 'ko') if korean else ('en-US', 'en')
        url = 'https://www.bing.com/search?' + urlencode({'format': 'rss', 'q': query, 'mkt': market, 'setlang': language})
        raw = fetch(url, {}, opener)
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            raise ProviderError(SEARCH_FAILED_TEXT) from None
        results = []
        for item in root.findall('./channel/item')[:limit]:
            link = item.findtext('link', '')
            if not _public_http_url(link):
                continue
            results.append(result_row(item.findtext('title', '')[:300], link, item.findtext('description', '')[:1800], self.id))
        # Bing's RSS titles are localized and often omit the exact query
        # token.  Returning its bounded result set is more reliable than
        # silently discarding valid results with a second text filter.  An
        # empty feed is a failed read, as before.
        if not results:
            raise ProviderError(SEARCH_FAILED_TEXT)
        return results


class NaverProvider:
    """Naver Open API: web documents and books (``X-Naver-Client-Id/Secret``)."""
    id = 'naver'
    label = 'Naver Open API (Korean web portal)'
    kinds = ('web', 'book')
    kind_labels = {'web': 'Naver web documents', 'book': 'Naver book catalogue (title, author, publisher, ISBN)'}
    destination = 'openapi.naver.com'
    endpoints = {'web': 'https://openapi.naver.com/v1/search/webkr.json',
                 'book': 'https://openapi.naver.com/v1/search/book.json'}

    def __init__(self, client_id, client_secret):
        self._client_id, self._client_secret = client_id, client_secret

    def search(self, query, *, kind='web', locale=None, limit=RESULT_LIMIT, opener=None):
        del locale  # the API has no locale parameter; the argument is accepted and ignored
        url = self.endpoints[kind] + '?' + urlencode({'query': query, 'display': limit, 'start': 1, 'sort': 'sim'})
        data = _json(fetch(url, {'X-Naver-Client-Id': self._client_id, 'X-Naver-Client-Secret': self._client_secret}, opener))
        results = []
        for item in (data.get('items') or [])[:limit]:
            if not isinstance(item, dict) or not _public_http_url(item.get('link')):
                continue
            snippet = _text(item.get('description'), 1500)
            if kind == 'book':
                meta = ' · '.join(part for part in (_text(item.get('author'), 200), _text(item.get('publisher'), 200),
                                                    _text(item.get('pubdate'), 20), ('ISBN ' + _text(item.get('isbn'), 40)) if item.get('isbn') else '') if part)
                snippet = (meta + ('\n' if meta and snippet else '') + snippet)[:1800]
            results.append(result_row(_text(item.get('title'), 300), item['link'], snippet, self.id))
        return results


class BraveProvider:
    """Brave Search API web search (``X-Subscription-Token``)."""
    id = 'brave'
    label = 'Brave Search API (global web index)'
    kinds = ('web',)
    destination = 'api.search.brave.com'
    endpoint = 'https://api.search.brave.com/res/v1/web/search'

    def __init__(self, token):
        self._token = token

    def search(self, query, *, kind='web', locale=None, limit=RESULT_LIMIT, opener=None):
        params = {'q': query, 'count': limit}
        language, region = split_locale(locale)
        if language:
            params['search_lang'] = language
        if region:
            params['country'] = region
        data = _json(fetch(self.endpoint + '?' + urlencode(params),
                           {'X-Subscription-Token': self._token, 'Accept': 'application/json'}, opener))
        web = data.get('web') if isinstance(data.get('web'), dict) else {}
        results = []
        for item in (web.get('results') or [])[:limit]:
            if not isinstance(item, dict) or not _public_http_url(item.get('url')):
                continue
            results.append(result_row(_text(item.get('title'), 300), item['url'], _text(item.get('description'), 1800), self.id))
        return results


def option_id(provider_id, kind):
    return provider_id if kind == 'web' else f'{provider_id}-{kind}'


class ProviderRegistry:
    """The providers the owner has configured, read at call time.

    ``secret(name)`` returns a stored key or ``''``; ``default()`` returns the
    owner's default option id.  Both are consulted on every call, so a key
    saved in Settings after the service started is offered on the next tool
    listing without a restart, and a removed key drops its provider at once.
    """
    def __init__(self, secret, default=None, opener=None):
        self._secret = secret
        self._default = default if callable(default) else (lambda: default or DEFAULT_PROVIDER)
        self._opener = opener

    @classmethod
    def from_config(cls, config, opener=None):
        """Keys and the default from one plain mapping (tests, fixtures)."""
        config = config if isinstance(config, dict) else {}
        return cls(lambda name: str(config.get(name) or ''), lambda: str(config.get('default') or DEFAULT_PROVIDER), opener)

    @classmethod
    def from_store(cls, store, opener=None):
        """Keys from the owner's secret store, the default from its config row."""
        def default():
            row = store.config(CONFIG_KEY, {}) or {}
            return str(row.get('default') or DEFAULT_PROVIDER) if isinstance(row, dict) else DEFAULT_PROVIDER
        return cls(lambda name: str(store.secret(name) or ''), default, opener)

    def providers(self):
        """Configured providers, Bing first; a provider needs all of its keys."""
        available = [BingRssProvider()]
        client_id, client_secret = self._secret(NAVER_CLIENT_ID), self._secret(NAVER_CLIENT_SECRET)
        if client_id and client_secret:
            available.append(NaverProvider(client_id, client_secret))
        token = self._secret(BRAVE_TOKEN)
        if token:
            available.append(BraveProvider(token))
        return available

    def options(self):
        """Selectable ``provider`` values with what each covers (tool schema, Settings)."""
        rows = []
        for provider in self.providers():
            for kind in provider.kinds:
                label = getattr(provider, 'kind_labels', {}).get(kind, provider.label)
                rows.append({'id': option_id(provider.id, kind), 'provider': provider.id, 'kind': kind,
                             'label': label, 'destination': provider.destination})
        return rows

    def default(self):
        """The owner's default option, or Bing when that option is not configured."""
        ids = {row['id'] for row in self.options()}
        wanted = self._default()
        return wanted if wanted in ids else DEFAULT_PROVIDER

    def resolve(self, provider=None, kind=None):
        """``(provider, kind)`` for a model's ``provider`` argument.

        ``provider`` is an option id (``naver-book``) or a provider id with a
        separate ``kind``; absent means the owner's default.  An unconfigured
        choice is a typed failure, never a silent substitution.
        """
        wanted = str(provider or '').strip() or self.default()
        if kind and kind != 'web':
            wanted = option_id(wanted, kind) if '-' not in wanted else wanted
        for candidate in self.providers():
            for candidate_kind in candidate.kinds:
                if option_id(candidate.id, candidate_kind) == wanted:
                    return candidate, candidate_kind
        raise SearchProviderError(PROVIDER_UNAVAILABLE_TEXT, 'provider_unavailable')

    def search(self, query, *, provider=None, kind=None, locale=None, limit=RESULT_LIMIT):
        chosen, chosen_kind = self.resolve(provider, kind)
        results = chosen.search(query, kind=chosen_kind, locale=locale or None, limit=limit, opener=self._opener)
        return {'tool': 'web_search', 'query': query, 'provider': option_id(chosen.id, chosen_kind), 'kind': chosen_kind,
                'locale': locale or '', 'retrieved_at': time.time(), 'results': results,
                'sources': [row['url'] for row in results], 'scope': SEARCH_SCOPE}


def validate_locale(locale):
    """The locale tag as sent, or ``''``; anything else is refused."""
    if locale is None or locale == '':
        return ''
    if not isinstance(locale, str) or not LOCALE_PATTERN.fullmatch(locale.strip()):
        raise ValueError('locale은 ko-KR 또는 en 같은 언어 태그로 지정하세요.')
    return locale.strip()


def search_arguments(args):
    """The optional ``web_search`` arguments a plan carries through unchanged.

    Only the two model-chosen selectors, each bounded: ``provider`` must be
    a short option id and ``locale`` a language tag.  Nothing else from the
    proposal reaches the wire through this path.
    """
    passed = {}
    provider = args.get('provider') if isinstance(args, dict) else None
    if isinstance(provider, str) and provider.strip():
        provider = provider.strip()
        if len(provider) > 40 or not re.fullmatch(r'[a-z0-9][a-z0-9-]*', provider):
            raise SearchProviderError(PROVIDER_UNAVAILABLE_TEXT, 'provider_unavailable')
        passed['provider'] = provider
    locale = validate_locale(args.get('locale') if isinstance(args, dict) else None)
    if locale:
        passed['locale'] = locale
    return passed


def describe_options(options, default):
    """The tool-description sentence naming the configured providers and the default.

    It says what each covers and which is the default when ``provider`` is
    omitted; it never says which one to prefer.
    """
    listed = '; '.join(f"{row['id']} = {row['label']}" for row in options)
    return f' Providers configured by the owner: {listed}. When provider is omitted, {default} is used.'


class SearchProviderSettings:
    """Owner setup for the providers: key slots and the default (Settings API).

    Key values are written to the secret store and never returned; only a
    ``saved_at`` time is kept in the config row.  Saving or removing a key
    changes which providers the model sees on its next tool listing and
    nothing else: no probe, no switch of the default beyond the fallback to
    Bing when the default's key is removed.
    """
    PROVIDERS = {
        'naver': {'name': 'Naver Open API', 'destination': NaverProvider.destination,
                  'fields': ({'id': 'client_id', 'label': 'Client ID', 'slot': NAVER_CLIENT_ID},
                             {'id': 'client_secret', 'label': 'Client Secret', 'slot': NAVER_CLIENT_SECRET}),
                  'setup': 'developers.naver.com 에서 애플리케이션을 만들고 검색 API를 추가한 뒤 Client ID와 Client Secret을 붙여 넣으세요.'},
        'brave': {'name': 'Brave Search API', 'destination': BraveProvider.destination,
                  'fields': ({'id': 'key', 'label': 'API key', 'slot': BRAVE_TOKEN},),
                  'setup': 'api.search.brave.com 에서 발급한 Subscription Token을 붙여 넣으세요.'},
    }

    def __init__(self, store, lock=None, clock=time.time):
        self.store, self.lock, self.clock = store, lock, clock
        self.registry = ProviderRegistry.from_store(store)

    def _row(self):
        row = self.store.config(CONFIG_KEY, {}) or {}
        row = dict(row) if isinstance(row, dict) else {}
        keys = row.get('keys') if isinstance(row.get('keys'), dict) else {}
        return {'default': str(row.get('default') or DEFAULT_PROVIDER), 'keys': dict(keys)}

    def status(self):
        row = self._row()
        providers = []
        for provider_id, spec in self.PROVIDERS.items():
            saved = all(bool(self.store.secret(field['slot'])) for field in spec['fields'])
            meta = row['keys'].get(provider_id) if isinstance(row['keys'].get(provider_id), dict) else {}
            providers.append({'id': provider_id, 'name': spec['name'], 'destination': spec['destination'], 'setup': spec['setup'],
                              'fields': [{'id': field['id'], 'label': field['label']} for field in spec['fields']],
                              'key': {'saved': saved, 'saved_at': meta.get('saved_at') if saved else None}})
        return {'default': self.registry.default(), 'configured_default': row['default'],
                'options': self.registry.options(), 'providers': providers,
                'keyless': [{'id': BingRssProvider.id, 'name': 'Bing (RSS)', 'destination': BingRssProvider.destination}]}

    def _locked(self):
        from contextlib import nullcontext
        return self.lock if self.lock is not None else nullcontext()

    def save_key(self, body):
        """Store or remove one provider's key material; never returns the values."""
        if not isinstance(body, dict) or body.get('provider') not in self.PROVIDERS:
            raise ValueError('키를 저장할 검색 제공자를 선택하세요.')
        spec = self.PROVIDERS[body['provider']]
        values = {}
        for field in spec['fields']:
            value = body.get(field['id'], '')
            if not isinstance(value, str) or len(value) > 4096 or any(ch.isspace() for ch in value.strip()):
                raise ValueError('키 값을 한 줄 그대로 붙여 넣으세요.')
            values[field['slot']] = value.strip()
        if any(values.values()) and not all(values.values()):
            raise ValueError('이 제공자는 모든 키 값을 함께 저장해야 합니다.')
        with self._locked():
            for slot, value in values.items():
                self.store.secret(slot, value)
            row = self._row()
            if all(values.values()):
                row['keys'][body['provider']] = {'saved_at': self.clock(), 'source': 'owner'}
            else:
                row['keys'].pop(body['provider'], None)
            self.store.put(CONFIG_KEY, row)
        return self.status()

    def set_default(self, body):
        """The option used when the model omits ``provider``; must be configured."""
        wanted = body.get('provider') if isinstance(body, dict) else None
        ids = {row['id'] for row in self.registry.options()}
        if not isinstance(wanted, str) or wanted not in ids:
            raise ValueError('기본 검색 제공자는 설정된 제공자 중에서 고르세요.')
        with self._locked():
            row = self._row()
            row['default'] = wanted
            self.store.put(CONFIG_KEY, row)
        return self.status()
