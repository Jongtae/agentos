"""SEC-EVAL-01 (#660): no decision/runtime branch on a named site, provider or request category.

Contract: ``docs/secretary-agency-contract.en.md`` "Probe scenarios and the
no-scenario-code rule" and completion-rule item 5.  Evidence class: static
structural check (stdlib ``ast``); it proves what the scanned source contains,
not how a live model behaves.

What is inspected.  Only string literals in positions where they steer
control flow:

- ``comparison``: an operand of ``==``/``!=``/``in``/``not in``/``is``,
  including a literal collection or a module/class constant it names;
- ``match-call``: an argument (or constant receiver) of a string-matching call
  such as ``startswith``, ``find``, ``re.search`` or a dict ``get``;
- ``match``: a ``case`` value or mapping key of a ``match`` statement;
- ``dispatch-key``: a key of a dict literal that is subscripted or ``get``-ed,
  directly or through the name it is bound to;
- ``match-table``: an element of a string collection (or ``re.compile``
  pattern) bound to a name in any scope - module, class or function - that
  the module reads, or iterated inline by a ``for``/comprehension: the shape
  of a cue list consumed by a matcher.

Message text is excluded by construction: an owner-facing Korean or English
sentence passed to a reply, a tool description or an error is not in any of
those positions, so it is never read.  ``test_guard_catches_a_planted_scenario_branch``
proves both directions on a planted module.

The registry and adapter modules that must name providers are allowlisted
as whole modules (``ALLOWED_MODULES``); the provider-id enum offered to the
model is built at run time from that registry, so it has no literal here.

Anything else the scan finds must be listed in ``CLASSIFIED``, keyed by
``(module, literal)`` with its classification and reason, so every exception
is reviewable in one place.  A new hit fails; a listed entry that no longer
exists fails too, so the list cannot go stale.  ``open-finding`` entries are
pre-existing branches reported by #660 and deliberately left unfixed here;
#672 resolved the three it reported, so none is listed now.
"""
import ast
import re
import tempfile
import textwrap
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'src' / 'personal_agent'

#: Decision and runtime modules.  ``decision*.py`` is globbed; ``preparations.py``
#: is scanned once it exists (SEC-ATTN-01 #659); ``orchestrator.py`` is the
#: ORCH-01 (#710) orchestration step and its worker catalogue; ``owner_model.py`` the
#: #805 owner-model upkeep; ``skills.py`` the #961 skill-supply glue.
SCANNED_MODULES = ('agent_runtime.py', 'conversation_handoff.py', 'current_context.py', 'browser_session.py',
                   'browser_worker.py', 'browser_jar.py',
                   'preparations.py', 'local_tools.py', 'quickstart_service.py', 'orchestrator.py', 'owner_model.py',
                   # SKILL-SUPPLY-02 (#961): the skill-supply glue stays free of site/category branches;
                   # skill content is data in packages, not scanned (#960 section 8).
                   'skills.py',
                   # API-READ-01 (#1216): the authenticated API call and its response provenance.
                   'api_requests.py')

#: Modules whose job is to name providers.  Not scanned.
ALLOWED_MODULES = {
    'search_providers.py': 'provider registry and adapters (#655, #678): implements the connected AI\'s native search '
                           '(per owner-configured API route), Brave and the Bing RSS opt-in by name; the model-facing '
                           'provider enum is built from this registry at run time',
}

#: Sites and providers from the probes and common Korean commerce/search hosts.
SITE_TOKENS = ('kyobo', 'coupang', 'yes24', 'aladin', 'naver', 'daum', 'kakao', 'google', 'bing', 'brave',
               '11st', 'gmarket', 'baemin', 'yogiyo')
#: Request categories the probes exercise.
CATEGORY_TOKENS = ('lunch', 'book', 'cart', '점심', '책', '장바구니')

_ASCII = [token for token in (*SITE_TOKENS, *CATEGORY_TOKENS) if token.isascii()]
_HANGUL = [token for token in CATEGORY_TOKENS if not token.isascii()]
#: A token starts a word: ``kyobo`` in ``kyobobook.co.kr``, ``google`` in
#: ``google-calendar``, but not ``bing`` in ``combining`` or ``책`` in ``정책``.
TOKEN_PATTERN = re.compile('|'.join([rf'(?<![a-z0-9]){re.escape(token)}' for token in _ASCII] +
                                    [rf'(?<![가-힣]){re.escape(token)}' for token in _HANGUL]))

#: Methods and functions whose string arguments are match patterns.
MATCH_CALLS = frozenset({'startswith', 'endswith', 'find', 'rfind', 'index', 'rindex', 'count', 'search', 'match',
                         'fullmatch', 'findall', 'finditer', 'compile', 'fnmatch', 'get', '__contains__'})
_COLLECTION_CALLS = frozenset({'frozenset', 'set', 'tuple', 'list'})

#: Every scan hit outside the allowed modules, reviewed once.
#: ``allowed``: not a scenario branch.  ``open-finding``: a pre-existing
#: request-category rule reported by #660 for an owner decision; not fixed here.
CLASSIFIED = {
    ('local_tools.py', 'metadata.google.internal'): (
        'allowed', 'SSRF denylist of cloud metadata hosts (DENIED_PUBLIC_HOSTS); a security boundary that refuses '
                   'every request to that host, not a site the model may choose'),
    ('quickstart_service.py', 'google-drive-read'): (
        'allowed', 'connector registry identity of the owner-connected Drive capability (read grant/handoff); '
                   'capability dispatch by connector id, not a site or provider chosen for a request'),
    ('quickstart_service.py', 'google-gmail-read'): (
        'allowed', 'connector registry identity of the owner-connected Gmail capability'),
    ('quickstart_service.py', 'google-calendar'): (
        'allowed', 'connector registry identity of the owner-connected Calendar capability'),
    ('quickstart_service.py', 'google-calendar-write'): (
        'allowed', 'connector registry identity of the owner-connected Calendar write grant'),
    # #672 removed the three open findings #660 listed here ("book" in
    # _CALENDAR_VERBS, "google it" in _RESEARCH_CUES, "google drive" in
    # AgentService.requests_drive_access); calendar create and Drive read are
    # now the DecisionEngine's capability-need judgment, research the loop's.
}


def scenario_tokens(text):
    """The site/provider/category tokens a literal names (case-insensitive)."""
    return sorted({match.group(0) for match in TOKEN_PATTERN.finditer(str(text).casefold())})


def _strings(node, constants=None):
    """String literals a node denotes: a constant, a literal collection, a
    ``frozenset(...)``/``re.compile(...)`` over one, or a constant it names."""
    constants = constants or {}
    if isinstance(node, ast.Constant):
        return [node.value] if isinstance(node.value, str) else []
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return [value for element in node.elts for value in _strings(element, constants)]
    if isinstance(node, ast.Call) and node.args:
        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, 'id', None)
        if name in _COLLECTION_CALLS or name == 'compile':
            return _strings(node.args[0], constants)
    if isinstance(node, ast.Name):
        return constants.get(node.id, [])
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in ('self', 'cls'):
        return constants.get(node.attr, [])
    return []


def _bound_names(target):
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Attribute):
        return [target.attr]
    return []


def scan_source(source, module):
    """``[(module, line, kind, literal, tokens)]`` for one module's source."""
    tree = ast.parse(source)
    # String collections and patterns are collected from every scope (module,
    # class and function bodies, #660 review); a name bound more than once
    # keeps every literal it was bound to, so the guard over-reports rather
    # than misses a shadowed cue list.  A single string is resolved only from
    # module/class constants: a local variable assigned one value and compared
    # to another (`provider = 'x'` then `provider == y`) is a value, not a table.
    top_level = {id(statement) for scope in [tree, *[node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]]
                 for statement in scope.body}
    constants = {}      # bound name -> string literals it holds
    collections = {}    # bound name -> [(line, literals)] of a string collection or pattern
    dicts = {}          # any bound name -> [(line, key)] of a dict literal's string keys
    for statement in ast.walk(tree):
        if isinstance(statement, ast.Assign):
            targets, value = statement.targets, statement.value
        elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
            targets, value = [statement.target], statement.value
        else:
            continue
        literals = _strings(value)
        single = isinstance(value, ast.Constant)
        if not literals or (single and id(statement) not in top_level):
            continue
        for target in targets:
            for name in _bound_names(target):
                constants.setdefault(name, []).extend(literals)
                if not single:
                    collections.setdefault(name, []).append((statement.lineno, literals))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Dict):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            keys = [(key.lineno, key.value) for key in node.value.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)]
            for target in targets:
                for name in _bound_names(target):
                    dicts.setdefault(name, []).extend(keys)

    hits = []

    def add(line, kind, values):
        for value in values:
            tokens = scenario_tokens(value)
            if tokens:
                hits.append((module, line, kind, value, tokens))

    loaded = set()
    dispatched = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            loaded.add(node.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            loaded.add(node.attr)
        if isinstance(node, ast.Compare):
            for operand in (node.left, *node.comparators):
                add(node.lineno, 'comparison', _strings(operand, constants))
        elif isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name)):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            if name in MATCH_CALLS:
                for argument in (*node.args, *(keyword.value for keyword in node.keywords)):
                    add(node.lineno, 'match-call', _strings(argument, constants))
                if isinstance(node.func, ast.Attribute):
                    add(node.lineno, 'match-call', _strings(node.func.value, constants))
                    if name == 'get':
                        receiver = node.func.value
                        if isinstance(receiver, ast.Dict):
                            add(node.lineno, 'dispatch-key', _strings(ast.Tuple(elts=[k for k in receiver.keys if k], ctx=ast.Load())))
                        dispatched.update(_bound_names(receiver))
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
            if isinstance(node.value, ast.Dict):
                add(node.lineno, 'dispatch-key', [key.value for key in node.value.keys
                                                  if isinstance(key, ast.Constant) and isinstance(key.value, str)])
            dispatched.update(_bound_names(node.value))
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)) and isinstance(
                node.iter, (ast.Tuple, ast.List, ast.Set, ast.Call)):
            # An inline cue list iterated by a matcher: `any(c in text for c in ('a', 'b'))`.
            add(getattr(node, 'lineno', None) or node.iter.lineno, 'match-table', _strings(node.iter))
        elif isinstance(node, ast.Match):
            for case in node.cases:
                for pattern in ast.walk(case.pattern):
                    if isinstance(pattern, ast.MatchValue):
                        add(pattern.lineno, 'match', _strings(pattern.value))
                    elif isinstance(pattern, ast.MatchMapping):
                        for key in pattern.keys:
                            add(pattern.lineno, 'match', _strings(key))
    for name in dispatched & set(dicts):
        for line, key in dicts[name]:
            add(line, 'dispatch-key', [key])
    for name, bindings in collections.items():
        if name in loaded:
            for line, literals in bindings:
                add(line, 'match-table', literals)
    return hits


def scanned_paths(root=SRC):
    names = [*SCANNED_MODULES, *sorted(path.name for path in root.glob('decision*.py'))]
    return [root / name for name in dict.fromkeys(names) if (root / name).is_file()]


def scan(paths):
    hits = []
    for path in paths:
        hits.extend(scan_source(path.read_text(encoding='utf-8'), path.name))
    return hits


class NoScenarioCodeTests(unittest.TestCase):
    def test_decision_and_runtime_code_names_no_site_provider_or_category(self):
        hits = scan(scanned_paths())
        found = {(module, literal) for module, _line, _kind, literal, _tokens in hits}
        unclassified = sorted({(module, line, kind, literal) for module, line, kind, literal, _tokens in hits
                               if (module, literal) not in CLASSIFIED})
        self.assertEqual(unclassified, [], 'decision/runtime code branches on a named site, provider or request '
                                           'category; make the model choose instead, or classify the literal in '
                                           'CLASSIFIED with a reviewable reason')
        stale = sorted(set(CLASSIFIED) - found)
        self.assertEqual(stale, [], 'a CLASSIFIED entry no longer occurs; remove it')

    def test_scope_is_the_decision_and_runtime_modules(self):
        names = {path.name for path in scanned_paths()}
        for required in ('agent_runtime.py', 'conversation_handoff.py', 'current_context.py', 'browser_session.py',
                         'browser_worker.py', 'browser_jar.py',
                         'local_tools.py', 'quickstart_service.py', 'decision.py', 'decision_adapters.py',
                         'decision_routes.py', 'orchestrator.py'):
            self.assertIn(required, names)
        self.assertFalse(names & set(ALLOWED_MODULES))
        for module in ALLOWED_MODULES:
            self.assertTrue((SRC / module).is_file(), module)
        self.assertLessEqual({classification for classification, _reason in CLASSIFIED.values()},
                             {'allowed', 'open-finding'})

    def test_tokens_start_words(self):
        self.assertEqual(scenario_tokens('https://www.kyobobook.co.kr/cart'), ['cart', 'kyobo'])
        self.assertEqual(scenario_tokens('google-calendar'), ['google'])
        self.assertEqual(scenario_tokens('점심 뭐 먹지'), ['점심'])
        self.assertEqual(scenario_tokens('책 사줘'), ['책'])
        for harmless in ('combining', 'notebook', '정책', 'Descartes', 'provider'):
            self.assertEqual(scenario_tokens(harmless), [], harmless)

    def test_guard_catches_a_planted_scenario_branch(self):
        planted = textwrap.dedent('''
            import re
            _LUNCH_CUES = ('점심', 'lunch')
            _HOST = re.compile(r'coupang\\.com')
            HANDLERS = {'yes24': object, 'web': object}
            NOTICE = '장바구니에 담았습니다.'

            def plan(url, provider, text, site, reply):
                if 'kyobobook' in url:
                    return 'direct'
                if provider == 'naver':
                    provider = 'brave'
                if url.startswith('https://www.aladin.co.kr'):
                    return None
                if any(cue in text for cue in _LUNCH_CUES):
                    return 'menu'
                if _HOST.search(url):
                    return 'shop'
                if re.search(r'장바구니', text):
                    return 'cart'
                match site:
                    case '11st':
                        return 'mall'
                handler = HANDLERS[site]
                route = {'baemin': 1}.get(site)
                # A cue list bound inside the function, then consumed by a matcher.
                cues = ('kyobo', '점심 메뉴')
                if any(c in text for c in cues):
                    return 'local'
                # A cue list iterated inline.
                if any(word in text for word in ('gmarket', 'yogiyo')):
                    return 'inline'
                # Message text is not a branch condition and is never read.
                reply('책을 찾았습니다. 점심 추천도 준비할게요.', notice=NOTICE)
                description = 'Search Naver, Brave or Bing; add the book to the cart.'
                return handler, route, description
        ''')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'planted_runtime.py'
            path.write_text(planted, encoding='utf-8')
            hits = scan([path])
        by_literal = {}
        for _module, _line, kind, literal, _tokens in hits:
            by_literal.setdefault(literal, set()).add(kind)
        self.assertIn('comparison', by_literal['kyobobook'])
        self.assertIn('comparison', by_literal['naver'])
        self.assertIn('https://www.aladin.co.kr', by_literal)
        self.assertIn('match-table', by_literal['점심'])
        self.assertIn('match-table', by_literal['lunch'])
        self.assertIn('coupang\\.com', by_literal)
        self.assertIn('match-call', by_literal['장바구니'])
        self.assertIn('match', by_literal['11st'])
        self.assertIn('dispatch-key', by_literal['yes24'])
        self.assertIn('dispatch-key', by_literal['baemin'])
        self.assertIn('match-table', by_literal['kyobo'])
        self.assertIn('match-table', by_literal['점심 메뉴'])
        self.assertIn('match-table', by_literal['gmarket'])
        self.assertIn('match-table', by_literal['yogiyo'])
        # Owner-facing message text and a tool description are not conditions.
        for message in ('장바구니에 담았습니다.', '책을 찾았습니다. 점심 추천도 준비할게요.',
                        'Search Naver, Brave or Bing; add the book to the cart.'):
            self.assertNotIn(message, by_literal)
        # 'brave' is assigned, not compared: a value, not a branch.
        self.assertNotIn('brave', by_literal)
        # A planted branch is unclassified, so the main assertion would fail on it.
        self.assertTrue(all((path.name, literal) not in CLASSIFIED for literal in by_literal))



#: C16 amendment (#974): skill content may carry domain and site know-how, so core code must
#: treat every skill alike.  A string literal anywhere in core that names one skill (exactly,
#: or as a path to it) would let core special-case that skill's content.
SKILL_ROOT = SRC / 'bundled_skills'


def skill_names():
    """The bundled skills' names: the skills core could most easily special-case."""
    return sorted(path.name for path in SKILL_ROOT.iterdir() if (path / 'SKILL.md').is_file())


def skill_name_literals(paths, names):
    """``(module, line, literal)`` of each string literal that names one of ``names``, anywhere in it.

    Bounded by word characters and hyphens, so ``personal-agentos-skills`` (a User-Agent) does not
    name ``agentos-skills``.  Installed skills are runtime data and cannot be scanned statically.
    """
    hits = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                literal = node.value
                if any(re.search(rf'(?<![\w-]){re.escape(name)}(?![\w-])', literal) for name in names):
                    hits.append((path.name, node.lineno, literal))
    return hits


class CoreNamesNoSkill(unittest.TestCase):
    """#974: know-how lives in skill content; core code never names a particular skill."""

    def test_no_core_module_names_a_skill(self):
        names = skill_names()
        self.assertTrue(names, 'the bundled skills exist')
        self.assertEqual(skill_name_literals(sorted(SRC.rglob('*.py')), names), [])

    def test_guard_catches_a_planted_skill_branch(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'planted.py'
            path.write_text(textwrap.dedent("""
                SPECIAL = 'bundled_skills/agentos-management/SKILL.md'
                HINT = 'For settings, first skill_load agentos/agentos-management.'
                def pick(entry):
                    if entry['name'] == 'agentos-management':
                        return 'special'
                    return 'personal-agentos-skills'  # a substring is not a name
            """))
            hits = skill_name_literals([path], ['agentos-management', 'agentos-skills'])
        self.assertEqual(sorted(literal for _module, _line, literal in hits),
                         ['For settings, first skill_load agentos/agentos-management.', 'agentos-management',
                          'bundled_skills/agentos-management/SKILL.md'])


#: #974 review: only the skill-supply glue reads skill files; core never opens one on its own.
SKILL_FILE_LITERALS = ('SKILL.md', 'bundled_skills')
SKILL_FILE_NAMES = ('BUNDLED_ROOT',)


def skill_file_references(paths):
    hits = []
    for path in paths:
        if path.name == 'skills.py':
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'), filename=str(path))):
            text = (node.value if isinstance(node, ast.Constant) and isinstance(node.value, str)
                    else node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute)
                    else node.name if isinstance(node, ast.alias) else None)
            if text is not None and (any(item in text for item in SKILL_FILE_LITERALS) if isinstance(node, ast.Constant)
                                     else text in SKILL_FILE_NAMES):
                hits.append((path.name, node.lineno, text))
    return hits


class CoreReadsNoSkillFiles(unittest.TestCase):
    def test_only_the_skill_supply_glue_refers_to_skill_files(self):
        self.assertEqual(skill_file_references(sorted(SRC.rglob('*.py'))), [])

    def test_guard_catches_a_planted_read(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'planted.py'
            path.write_text("from personal_agent.skills import BUNDLED_ROOT\nTEXT = (BUNDLED_ROOT / 'x' / 'SKILL.md').read_text()\n")
            hits = skill_file_references([path])
        self.assertEqual(sorted(text for _module, _line, text in hits), ['BUNDLED_ROOT', 'BUNDLED_ROOT', 'SKILL.md'])



#: #975 review: installed skills are runtime data, so naming them cannot be enumerated.  Structurally,
#: core may not compare a skill's identity with a string literal, select one by a literal key, or load
#: skill text anywhere but the model's own ``skill_load`` / ``skill_resource`` dispatch.
#: The one allowed literal is the bundled package prefix (bundled versus installed: supply and removal).
ALLOWED_SKILL_LITERALS = frozenset({'agentos/'})
SKILL_COLLECTIONS = frozenset({'entries', 'loaded'})


def _skill_identity(node):
    """Whether ``node`` reads a skill's identity: ``x['skill']``, ``x.get('skill')`` or a binding's entries/loaded."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Subscript) and isinstance(sub.slice, ast.Constant) and sub.slice.value == 'skill':
            return True
        if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == 'get'
                and sub.args and isinstance(sub.args[0], ast.Constant) and sub.args[0].value == 'skill'):
            return True
        if isinstance(sub, ast.Attribute) and sub.attr in SKILL_COLLECTIONS:
            return True
    return False


def _string_literals(node):
    return [sub.value for sub in ast.walk(node) if isinstance(sub, ast.Constant) and isinstance(sub.value, str)]


def skill_selections(paths):
    """``(module, line, literal)`` where core compares, matches or indexes a skill identity by a literal."""
    hits = []
    for path in paths:
        if path.name == 'skills.py':
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'), filename=str(path))):
            literals = []
            if isinstance(node, ast.Compare):
                operands = [node.left, *node.comparators]
                if any(_skill_identity(item) for item in operands):
                    literals = [value for item in operands if not _skill_identity(item) for value in _string_literals(item)]
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in MATCH_CALLS
                  and _skill_identity(node.func.value)):
                literals = [value for arg in node.args for value in _string_literals(arg)]
            elif (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute)
                  and node.value.attr in SKILL_COLLECTIONS):
                literals = _string_literals(node.slice)
            hits += [(path.name, node.lineno, value) for value in literals if value not in ALLOWED_SKILL_LITERALS]
    return hits


def skill_text_loads(paths):
    """``(module, function, line)`` of each call that loads skill text: ``<...skills or binding>.load/resource(...)``."""
    hits = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for function in [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for node in ast.walk(function):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in ('load', 'resource')):
                    continue
                owner = node.func.value
                label = owner.attr if isinstance(owner, ast.Attribute) else owner.id if isinstance(owner, ast.Name) else ''
                if 'skill' in label.lower() or 'binding' in label.lower():
                    hits.append((path.name, function.name, node.lineno))
    return sorted(set(hits))


class CoreSelectsNoSkill(unittest.TestCase):
    """#974/#975: no core special case for any skill, bundled or installed, and one way in for its text."""

    def test_no_skill_identity_is_compared_with_a_literal(self):
        self.assertEqual(skill_selections(sorted(SRC.rglob('*.py'))), [])

    def test_skill_text_is_loaded_only_by_the_model_tool_dispatch(self):
        loads = skill_text_loads(sorted(path for path in SRC.rglob('*.py') if path.name != 'skills.py'))
        self.assertEqual({(module, function) for module, function, _line in loads}, {('agent_runtime.py', 'execute')})

    def test_guards_catch_planted_selections_and_loads(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'planted.py'
            path.write_text(textwrap.dedent("""
                def route(row, binding, request):
                    if row['skill'] == 'internal-comms/internal-comms':
                        pass
                    if row.get('skill', '').startswith('shop-'):
                        pass
                    entry = binding.entries['some-pkg/any-skill']
                    if row['skill'].startswith('agentos/'):
                        pass  # the bundled package prefix: allowed
                    return binding.load('some-pkg/any-skill')
            """))
            selections = sorted(literal for _module, _line, literal in skill_selections([path]))
            loads = skill_text_loads([path])
        self.assertEqual(selections, ['internal-comms/internal-comms', 'shop-', 'some-pkg/any-skill'])
        self.assertEqual([(module, function) for module, function, _line in loads], [('planted.py', 'route')])


if __name__ == '__main__':
    unittest.main()
