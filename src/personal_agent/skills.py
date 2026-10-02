"""SKILL-SUPPLY-02 (#961): optional, pinned skill knowledge over the existing package lifecycle.

Decision record: ``docs/skill-prep-01-interface-decision.en.md`` (#960).  A
skill is versioned know-how (an Agent Skills ``SKILL.md`` plus packaged text
resources), carried by an ordinary ``PluginRegistry`` declaration with no
tools and no roles.  It is never a tool, a permission or an executor:

* the owner's switch (``store.config('skills')``) is off by default; off, no
  Work gets a catalogue, a loader or a skill tool (``SkillLibrary.binding``);
* a Work captures the catalogue once (``SkillBinding``): the exact skill
  revisions (content digests) it may load, so a revision never changes
  under a running Work;
* a skill this Work loaded that is no longer current (switch off, package
  disabled, removed or updated) refuses every later tool call of the Work
  (``SkillBinding.check_current``), not only the next load; content changed
  on disk is refused at its next read (``SkillLibrary.read``);
* acquisition fetches one exact GitHub commit, stages and inspects the bytes,
  and installs only instruction/resource skills with a recognised licence.
  Scripts, hooks and executables are never run, and a skill that needs them
  is refused rather than stripped (``SkillError`` ``unsupported``).

Parsing adopts PyYAML's ``SafeLoader`` (no tag construction) with duplicate
keys refused; containment follows Microsoft Agent Framework's
``FileSkillsSource`` rules (resolved path inside the root, no link below it,
re-checked on every read).  ``allowed-tools`` is kept as metadata, never a grant.
"""
import hashlib
import io
import json
import re
import shutil
import tarfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from .manifests import validate_package

#: Agent Skills frontmatter fields (agentskills.io specification).
SPEC_FIELDS = frozenset({'name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools'})
NAME = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')
DIGEST = re.compile(r'^[0-9a-f]{64}$')
COMMIT = re.compile(r'^[0-9a-f]{40}$')
#: #960 section 6 bounds.  A load or resource read is one ordinary Work tool attempt.
MAX_FILE_BYTES = 256 * 1024
MAX_FILES = 200
MAX_PACKAGE_BYTES = 4 * 1024 * 1024
MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024
MAX_BODY_BYTES = 32 * 1024
MAX_BODY_LINES = 500
MAX_RESOURCE_BYTES = 64 * 1024
CATALOGUE_ENTRIES = 32
CATALOGUE_BYTES = 8 * 1024
MAX_LOADS = 3
MAX_RESOURCE_READS = 8
#: Files whose presence means the skill needs execution AgentOS does not offer.
EXECUTABLE_DIRS = frozenset({'scripts', 'hooks', 'bin'})
EXECUTABLE_SUFFIXES = frozenset({'.py', '.sh', '.bash', '.zsh', '.js', '.mjs', '.cjs', '.ts', '.rb', '.pl', '.ps1',
                                 '.exe', '.bat', '.cmd', '.so', '.dylib', '.dll', '.jar', '.wasm'})
#: Resource files the worker may read as text.
TEXT_SUFFIXES = frozenset({'.md', '.txt', '.json', '.yaml', '.yml', '.csv', '.xml', '.html'})
#: Compatibility statuses a skill may be enabled with (#960 section 5).
ENABLE_STATUSES = frozenset({'supported_as_is', 'adapted'})
#: Licences accepted for an external skill: SPDX ids, and the opening words of a licence file.
SPDX_LICENCES = frozenset({'AGPL-3.0-only', 'Apache-2.0', 'MIT', 'BSD-2-Clause', 'BSD-3-Clause', 'ISC', 'MPL-2.0', 'CC0-1.0', 'CC-BY-4.0'})
LICENCE_TEXTS = (('Apache-2.0', ('apache license', 'version 2.0')), ('MIT', ('mit license',)),
                 ('MIT', ('permission is hereby granted, free of charge',)), ('MPL-2.0', ('mozilla public license', '2.0')),
                 ('BSD-3-Clause', ('redistribution and use in source and binary forms', 'neither the name')),
                 ('BSD-2-Clause', ('redistribution and use in source and binary forms',)), ('ISC', ('isc license',)))
#: The reviewed skills shipped with AgentOS, under one reserved package id.
BUNDLED_PACKAGE = 'agentos'
BUNDLED_ROOT = Path(__file__).with_name('bundled_skills')
#: The owner's switch: ``{"enabled": bool}``; absent means off.
SETTINGS_KEY = 'skills'
#: The one supported acquisition source (#960 section 6): a GitHub folder at one commit.
GITHUB_TREE = re.compile(r'^(?:https://)?github\.com/([A-Za-z0-9][A-Za-z0-9_.-]*)/([A-Za-z0-9_.-]+)/tree/([A-Za-z0-9_.-]+)/'
                         r'([A-Za-z0-9_./-]+?)/?$')

REVOKED_TEXT = ('이 작업이 읽은 스킬({skill})이 작업 중에 꺼지거나 바뀌어 이 작업은 더 진행하지 않았어요. '
                '같은 요청을 다시 보내면 지금 설정으로 새로 시작해요.')
UNAVAILABLE_TEXT = '이 작업에서 쓸 수 있는 스킬 목록에 없는 스킬이에요. 스킬 없이 진행하세요.'


class SkillError(ValueError):
    """A skill refusal with a stable ``code`` (#960 section 5 vocabulary)."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


# -- format ------------------------------------------------------------------------------

_LOADER = []


def _loader():
    """``SafeLoader`` that refuses a duplicate key and any alias; PyYAML is imported only when a skill is parsed.

    Aliases are refused because a few nested ones expand into billions of
    items (review P2): frontmatter never needs them.
    """
    if not _LOADER:
        import yaml

        class Loader(yaml.SafeLoader):
            def compose_node(self, parent, index):
                if self.check_event(yaml.events.AliasEvent):
                    raise yaml.composer.ComposerError(None, None, 'aliases are not allowed', self.peek_event().start_mark)
                return super().compose_node(parent, index)

        def mapping(loader, node, deep=False):
            keys = [loader.construct_object(key, deep=deep) for key, _value in node.value]
            if len(keys) != len(set(map(repr, keys))):
                raise yaml.constructor.ConstructorError(None, None, 'duplicate key', node.start_mark)
            return yaml.SafeLoader.construct_mapping(loader, node, deep)

        Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
        _LOADER.append((yaml, Loader))
    return _LOADER[0]


def parse_frontmatter(text):
    """``(frontmatter, body)`` of a ``SKILL.md``, or ``SkillError('invalid_package')``."""
    text = text.replace('\r\n', '\n')
    if not text.startswith('---\n'):
        raise SkillError('SKILL.md에 머리말(frontmatter)이 없어요.', 'invalid_package')
    head, sep, body = text[4:].partition('\n---')
    if not sep or (body and body[0] != '\n'):
        raise SkillError('SKILL.md 머리말이 닫히지 않았어요.', 'invalid_package')
    yaml, loader = _loader()
    try:
        data = yaml.load(head, Loader=loader)  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError:
        raise SkillError('SKILL.md 머리말을 읽을 수 없어요(형식 오류, 중복 키, 별칭 또는 허용하지 않는 태그).', 'invalid_package') from None
    if not isinstance(data, dict):
        raise SkillError('SKILL.md 머리말이 키-값 목록이 아니에요.', 'invalid_package')
    return data, body[1:]


def tree_digest(files):
    """The content digest of one skill: sha256 of its sorted ``{relative path: sha256}`` map."""
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def _walk(root):
    """``{relative path: bytes}`` of every file under ``root``; links and oversize refused."""
    root = Path(root)
    real = root.resolve()
    if root.is_symlink() or not root.is_dir():
        raise SkillError('스킬 폴더를 찾을 수 없어요.', 'invalid_package')
    files, total = {}, 0
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise SkillError(f'스킬 안에 링크({rel})가 있어 받지 않았어요.', 'invalid_package')
        if not path.resolve().is_relative_to(real):
            raise SkillError(f'스킬 밖을 가리키는 경로({rel})가 있어요.', 'invalid_package')
        if path.is_dir():
            continue
        if not path.is_file():
            raise SkillError(f'일반 파일이 아닌 항목({rel})이 있어요.', 'invalid_package')
        size = path.stat().st_size
        total += size
        if size > MAX_FILE_BYTES or total > MAX_PACKAGE_BYTES or len(files) >= MAX_FILES:
            raise SkillError('스킬 파일이 너무 크거나 많아요.', 'invalid_package')
        files[rel] = path.read_bytes()
    return files


def _licence(frontmatter, files):
    """``(label, recognised)`` of a skill's licence; a referenced file must be packaged."""
    declared = frontmatter.get('license')
    if declared is not None and not isinstance(declared, str):
        return '', False
    declared = (declared or '').strip()
    if declared in SPDX_LICENCES:
        return declared, True
    named = [rel for rel in files if '/' not in rel and rel.upper().startswith(('LICENSE', 'LICENCE', 'COPYING'))]
    # A declared non-SPDX licence counts only when it points to the packaged file (review P3):
    # "Proprietary" is not overridden by words that happen to appear in a LICENSE file.
    if declared:
        named = [rel for rel in named if rel.lower() in declared.lower()]
    for rel in named:
        head = files[rel][:4000].decode('utf-8', 'replace').lower()
        for spdx, words in LICENCE_TEXTS:
            if all(word in head for word in words):
                return f'{spdx} ({rel})', True
    return declared[:80], False


def inspect_skill(root):
    """The inspected record of one skill folder: identity, statuses and file digests.

    Never runs or imports anything from the folder.  ``invalid_package`` is
    raised for a malformed or hostile folder; anything AgentOS could hold but
    not use is a status in ``status``.
    """
    root = Path(root)
    files = _walk(root)
    if 'SKILL.md' not in files:
        raise SkillError('SKILL.md가 없어요.', 'invalid_package')
    try:
        text = files['SKILL.md'].decode('utf-8')
    except UnicodeDecodeError:
        raise SkillError('SKILL.md가 UTF-8 글자가 아니에요.', 'invalid_package') from None
    frontmatter, body = parse_frontmatter(text)
    name = frontmatter.get('name')
    if not isinstance(name, str) or len(name) > 64 or not NAME.match(name) or name != root.name:
        raise SkillError('스킬 이름은 폴더 이름과 같은 소문자·숫자·하이픈(64자 이하)이어야 해요.', 'invalid_package')
    description = frontmatter.get('description')
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        raise SkillError('스킬 설명은 1~1024자여야 해요.', 'invalid_package')
    compatibility = frontmatter.get('compatibility', '')
    if not isinstance(compatibility, str) or len(compatibility) > 500:
        raise SkillError('compatibility는 500자 이하 글자여야 해요.', 'invalid_package')
    metadata = frontmatter.get('metadata', {})
    if not isinstance(metadata, dict):
        raise SkillError('metadata는 키-값 목록이어야 해요.', 'invalid_package')
    status, notes = set(), []
    executable = sorted(rel for rel, data in files.items()
                        if any(part.lower() in EXECUTABLE_DIRS for part in rel.split('/')[:-1])
                        or Path(rel).suffix.lower() in EXECUTABLE_SUFFIXES or data.startswith(b'#!'))
    if executable:
        status.add('scripts_or_hooks_required')
        notes.append('실행 파일: ' + ', '.join(executable[:5]))
    extra = sorted(set(frontmatter) - SPEC_FIELDS)
    if extra:
        status.add('adapted')
        notes.append('표준 밖 머리말(메타데이터로만 보관): ' + ', '.join(map(str, extra[:5])))
    allowed_tools = frontmatter.get('allowed-tools') or ''
    if not isinstance(allowed_tools, str):
        raise SkillError('allowed-tools는 글자여야 해요.', 'invalid_package')
    allowed_tools = allowed_tools.split()
    licence, recognised = _licence(frontmatter, files)
    if not recognised:
        status.add('licence_unknown')
    if len(body.encode()) > MAX_BODY_BYTES or body.count('\n') > MAX_BODY_LINES:
        raise SkillError(f'SKILL.md 본문이 너무 길어요({MAX_BODY_LINES}줄, {MAX_BODY_BYTES // 1024}KB 이하).', 'invalid_package')
    digests = {rel: hashlib.sha256(data).hexdigest() for rel, data in files.items()}
    return {'name': name, 'description': ' '.join(description.split()), 'compatibility': compatibility.strip(),
            'licence': licence, 'allowed_tools': allowed_tools[:32],
            'status': sorted(status) or ['supported_as_is'], 'notes': notes,
            'files': digests, 'digest': tree_digest(digests)}


# -- source adapter: one GitHub folder at one commit --------------------------------------

class _GitHubRedirects(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only to the two GitHub hosts over HTTPS (review P3)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith(GITHUB_HOSTS):
            raise urllib.error.URLError('redirect outside GitHub')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


GITHUB_HOSTS = ('https://codeload.github.com/', 'https://api.github.com/')


def http_get(url, limit=MAX_DOWNLOAD_BYTES, timeout=30):
    """Bytes of one HTTPS GET to GitHub, bounded; the default transport."""
    if not url.startswith(GITHUB_HOSTS):
        raise SkillError('스킬은 GitHub에서만 받아요.', 'invalid_source')
    # The commits API answers a ref with only its SHA under this documented media type
    # (the default JSON carries the whole diff).
    accept = 'application/vnd.github.sha' if url.startswith('https://api.github.com/') else 'application/octet-stream'
    request = urllib.request.Request(url, headers={'User-Agent': 'personal-agentos-skills', 'Accept': accept})
    try:
        with urllib.request.build_opener(_GitHubRedirects).open(request, timeout=timeout) as response:
            data = response.read(limit + 1)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise SkillError('GitHub에서 스킬을 받지 못했어요. 잠시 뒤 다시 요청하세요.', 'source_unavailable') from None
    if len(data) > limit:
        raise SkillError('받을 파일이 너무 커요.', 'invalid_package')
    return data


def parse_source(value, transport=http_get):
    """A pinned source from a GitHub folder address; a branch or tag is resolved to its commit now.

    ``https://github.com/<owner>/<repo>/tree/<commit|branch|tag>/<folder>``.
    The result always names one exact 40-hex commit.
    """
    match = GITHUB_TREE.match((value or '').strip())
    if not match:
        raise SkillError('GitHub 스킬 폴더 주소를 주세요(예: https://github.com/<owner>/<repo>/tree/<브랜치 또는 커밋>/<폴더>).',
                         'invalid_source')
    owner, repo, ref, path = match.groups()
    parts = path.split('/')
    if any(part in ('', '.', '..') for part in parts) or not NAME.match(parts[-1]):
        raise SkillError('스킬 폴더 경로를 확인하세요.', 'invalid_source')
    revision = ref.lower() if COMMIT.match(ref.lower()) else None
    if revision is None:
        try:
            revision = transport(f'https://api.github.com/repos/{owner}/{repo}/commits/{ref}',
                                 limit=4096).decode('ascii').strip().lower()
        except (ValueError, AttributeError):
            revision = ''
        if not COMMIT.match(revision):
            raise SkillError('브랜치나 태그의 커밋을 확인하지 못했어요. 커밋 주소로 다시 주세요.', 'source_unavailable')
    return {'kind': 'github', 'repo': f'{owner}/{repo}', 'revision': revision, 'path': path,
            'uri': f'https://github.com/{owner}/{repo}', 'publisher_claim': owner}


def source_address(source):
    return f"{source['uri']}/tree/{source['revision']}/{source['path']}"


def fetch_github(source, dest, transport=http_get):
    """Extract exactly ``source['path']`` of the pinned commit into ``dest``; nothing else is written."""
    data = transport(f"https://codeload.github.com/{source['repo']}/tar.gz/{source['revision']}")
    prefix = source['path'].strip('/') + '/'
    written = count = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
            for member in archive:
                top, _sep, rest = member.name.partition('/')
                if not rest.startswith(prefix) and rest != prefix.rstrip('/'):
                    continue
                rel = rest[len(prefix):]
                if not rel:
                    continue
                parts = rel.split('/')
                if any(part in ('', '.', '..') for part in parts) or rel.startswith('/'):
                    raise SkillError('스킬 안에 허용하지 않는 경로가 있어요.', 'invalid_package')
                if member.isdir():
                    continue
                if not member.isfile():
                    raise SkillError(f'스킬 안에 링크나 특수 파일({rel})이 있어 받지 않았어요.', 'invalid_package')
                written += member.size
                count += 1
                if member.size > MAX_FILE_BYTES or written > MAX_PACKAGE_BYTES or count > MAX_FILES:
                    raise SkillError('스킬 파일이 너무 커요.', 'invalid_package')
                target = Path(dest, *parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
    except (tarfile.TarError, EOFError, OSError):
        raise SkillError('받은 스킬 묶음을 풀 수 없어요.', 'invalid_package') from None
    if not (Path(dest) / 'SKILL.md').is_file():
        raise SkillError('그 커밋의 그 폴더에 SKILL.md가 없어요.', 'invalid_package')
    return Path(dest)


# -- library: the owner's installed and bundled skills -------------------------------------

class SkillLibrary:
    """Skills on this AgentOS: bundled ones plus ``PluginRegistry`` declarations that carry ``skills``.

    Content is stored by digest under ``plugins/skills/<digest>/<name>/`` and
    never rewritten, so a Work pinned to a digest reads exactly those bytes.
    """

    def __init__(self, store, bundled_root=BUNDLED_ROOT, transport=http_get):
        self.store = store
        self.root = Path(store.root) / 'plugins'
        self.content = self.root / 'skills'
        self.bundled_root = Path(bundled_root)
        self.transport = transport

    # The owner's switch.
    def enabled(self):
        try:
            value = self.store.config(SETTINGS_KEY, {})
        except Exception:
            return False
        return isinstance(value, dict) and value.get('enabled') is True

    def set_enabled(self, on):
        current = self.store.config(SETTINGS_KEY, {})
        self.store.put(SETTINGS_KEY, {**(current if isinstance(current, dict) else {}), 'enabled': bool(on)})

    # Declarations.
    def _manifest_path(self, package_id):
        return self.root / f'{package_id}.json'

    def installed(self):
        """Every skill-carrying declaration (enabled or not), validated; an invalid one is skipped."""
        rows = []
        for path in sorted(self.root.glob('*.json')) if self.root.is_dir() else ():
            try:
                manifest = validate_package(json.loads(path.read_text()))
            except (ValueError, OSError):
                continue
            if manifest.get('skills'):
                rows.append(manifest)
        return rows

    def bundled(self):
        """The reviewed skills shipped with this AgentOS, inspected on every call (a few small files)."""
        entries = []
        if not self.bundled_root.is_dir():
            return entries
        for folder in sorted(path for path in self.bundled_root.iterdir() if path.is_dir()):
            try:
                record = inspect_skill(folder)
            except SkillError:
                continue
            if set(record['status']) <= ENABLE_STATUSES:
                entries.append(self._entry(BUNDLED_PACKAGE, record, revision='bundled', licence='AGPL-3.0-only (AgentOS)',
                                           source='AgentOS'))
        return entries

    @staticmethod
    def _entry(package, record, revision, licence, source):
        return {'skill': f"{package}/{record['name']}", 'package': package, 'name': record['name'],
                # One line: a declaration written by hand cannot shape the turn's sections (review P3).
                'description': ' '.join(str(record['description']).split())[:1024], 'digest': record['digest'], 'revision': revision,
                'licence': licence, 'source': source, 'status': list(record.get('status') or ())}

    def _declared(self, manifest):
        source = manifest.get('source') if isinstance(manifest.get('source'), dict) else {}
        return [self._entry(manifest['id'], skill, revision=str(source.get('revision') or ''),
                            licence=str(skill.get('licence') or ''), source=str(source.get('uri') or ''))
                for skill in manifest.get('skills') or ()
                if set(skill.get('status') or ()) <= ENABLE_STATUSES]

    def loadable(self):
        """Every skill a Work may load now, unbounded: empty when the switch is off."""
        if not self.enabled():
            return []
        entries = self.bundled()
        for manifest in self.installed():
            if manifest.get('enabled') is True:
                entries += self._declared(manifest)
        return entries

    def catalogue(self):
        """What a new Work is offered: ``loadable`` bounded (#960 section 6)."""
        bounded, size = [], 0
        for entry in self.loadable()[:CATALOGUE_ENTRIES]:
            size += len(entry['skill']) + len(entry['description']) + 8
            if size > CATALOGUE_BYTES:
                break
            bounded.append(entry)
        return bounded

    def binding(self):
        """This Work's skill binding, or None (off, nothing installed, or an unreadable library)."""
        try:
            entries = self.catalogue()
        except Exception:
            return None
        return SkillBinding(self, entries) if entries else None

    def folder(self, entry):
        if entry['package'] == BUNDLED_PACKAGE:
            return self.bundled_root / entry['name']
        return self.content / entry['digest'] / entry['name']

    def current(self, entry):
        """Whether ``entry`` (one exact revision) is still loadable by a Work: switch, enablement, digest.

        Checked against every loadable skill, not the bounded catalogue, so installing
        more skills never makes a loaded one look withdrawn (review P3).
        """
        try:
            return any(item['skill'] == entry['skill'] and item['digest'] == entry['digest'] for item in self.loadable())
        except Exception:
            return False

    def read(self, entry, rel, limit):
        """Text of one file of a pinned skill: inside its folder, untampered, bounded."""
        folder = self.folder(entry)
        files = _walk(folder)  # links/escapes refused again on every read
        digests = {path: hashlib.sha256(data).hexdigest() for path, data in files.items()}
        if tree_digest(digests) != entry['digest']:
            raise SkillError('스킬 파일이 설치된 내용과 달라 읽지 않았어요.', 'skill_revoked')
        parts = rel.split('/') if isinstance(rel, str) else []
        if not parts or any(part in ('', '.', '..') for part in parts) or rel not in files:
            raise SkillError('스킬 안에 그런 파일이 없어요.', 'skill_unavailable')
        if Path(rel).suffix.lower() not in TEXT_SUFFIXES:
            raise SkillError('스킬의 글자 파일(.md, .txt, .json 등)만 읽을 수 있어요.', 'skill_unavailable')
        data = files[rel]
        text = data[:limit].decode('utf-8', 'replace')
        return text, len(data) > limit, sorted(files)

    # Acquisition (an owner-confirmed settings change; never automatic).
    def install(self, value):
        """Fetch, stage, inspect and install one external skill; returns its declaration."""
        source = parse_source(value, self.transport)
        name = source['path'].rstrip('/').split('/')[-1]
        # Installs run one at a time (the settings category lock); anything left in
        # staging is an interrupted earlier install and never became a declaration.
        shutil.rmtree(self.root / '.staging', ignore_errors=True)
        staging = self.root / '.staging' / uuid.uuid4().hex
        try:
            folder = fetch_github(source, staging / name, self.transport)
            record = inspect_skill(folder)
            blocked = sorted(set(record['status']) - ENABLE_STATUSES)
            if blocked:
                reasons = {'scripts_or_hooks_required': '스크립트나 훅을 실행해야 하는 스킬이에요',
                           'licence_unknown': '라이선스를 확인할 수 없어요'}
                raise SkillError('추가하지 않았어요: ' + ' / '.join(reasons.get(code, code) for code in blocked) + '.',
                                 'unsupported')
            package_id = record['name']
            if package_id == BUNDLED_PACKAGE or package_id in {entry['name'] for entry in self.bundled()}:
                raise SkillError('AgentOS 기본 스킬과 이름이 같아 추가하지 않았어요.', 'identity_collision')
            existing = self._manifest_path(package_id)
            enabled = True
            if existing.exists():
                try:
                    previous = json.loads(existing.read_text())
                except (ValueError, OSError):
                    previous = {}
                same = isinstance(previous.get('source'), dict) and all(
                    previous['source'].get(key) == source[key] for key in ('repo', 'path'))
                if not same:
                    raise SkillError(f"이미 '{package_id}'라는 다른 패키지가 있어 추가하지 않았어요.", 'identity_collision')
                # An update keeps the owner's on/off choice for this package (review P3).
                enabled = previous.get('enabled') is True
            skill = {key: record[key] for key in ('name', 'description', 'digest', 'licence', 'compatibility', 'status', 'files')}
            if record['allowed_tools']:
                skill['allowed_tools'] = record['allowed_tools']  # foreign metadata, never a grant
            try:
                manifest = validate_package({'version': 1, 'id': package_id, 'tools': [], 'roles': [], 'enabled': enabled,
                                             'skills': [skill], 'source': source, 'adaptation': 1,
                                             'installed_at': time.time()})
            except ValueError as exc:
                raise SkillError(f'{exc} 추가하지 않았어요.', 'identity_collision') from None
            target = self.content / record['digest'] / name
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(folder), str(target))
            # Written last and atomically: an interrupted install leaves no declaration.
            temporary = existing.with_suffix('.json.tmp')
            temporary.write_text(json.dumps(manifest, ensure_ascii=False))
            temporary.replace(existing)
            return manifest
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def resolve(self, value):
        """The installed package id an owner's word names (its id or its skill name)."""
        wanted = (value or '').strip().lower()
        for manifest in self.installed():
            if wanted == manifest['id'] or wanted in {skill.get('name') for skill in manifest['skills']}:
                return manifest['id']
        raise SkillError(f"설치된 스킬 중에 '{value}'이(가) 없어요.", 'skill_unavailable')

    def remove(self, package_id):
        """Remove a declaration.  Stored content stays (Work evidence references it by digest)."""
        path = self._manifest_path(self.resolve(package_id))
        path.unlink()

    def summary(self):
        """Owner-readable rows of the installed and bundled skills."""
        rows = [{'skill': entry['skill'], 'source': 'AgentOS 기본', 'enabled': True} for entry in self.bundled()]
        for manifest in self.installed():
            source = manifest.get('source') or {}
            rows.append({'skill': f"{manifest['id']}/{manifest['skills'][0]['name']}", 'enabled': manifest.get('enabled') is True,
                         'source': f"{source.get('repo', '?')}@{str(source.get('revision', ''))[:7]}"})
        return rows


class SkillBinding:
    """One Work's pinned skill catalogue and what it has loaded (#961).

    The host and a CLI bridge process each hold one; the bridge rebuilds it
    from the exact refs the host passed (``refs``/``from_refs``).
    """

    def __init__(self, library, entries):
        self.library = library
        self.entries = {entry['skill']: entry for entry in entries}
        self.loaded = {}
        self.loads = 0
        self.resource_reads = 0

    def refs(self):
        return [f"{skill}@{entry['digest']}" for skill, entry in sorted(self.entries.items())]

    @classmethod
    def from_refs(cls, library, refs):
        """The binding a host handed to a bridge; refs no longer current stay listed and refuse on load."""
        known = {entry['skill']: entry for entry in library.loadable()}
        entries = []
        for ref in refs or ():
            skill, _sep, digest = str(ref).partition('@')
            package, _sep, name = skill.partition('/')
            if not DIGEST.match(digest) or not NAME.match(name) or not package:
                continue
            entry = known.get(skill) if (known.get(skill) or {}).get('digest') == digest else None
            entries.append(entry or {'skill': skill, 'package': package, 'name': name, 'description': '',
                                     'digest': digest, 'revision': '', 'licence': '', 'source': '', 'status': []})
        return cls(library, entries) if entries else None

    def catalogue_text(self):
        return '\n'.join(f"- {skill}: {' '.join(str(entry['description']).split())}" for skill, entry in sorted(self.entries.items()))

    def _entry(self, skill):
        entry = self.entries.get(skill if isinstance(skill, str) else '')
        if entry is None:
            raise SkillError(UNAVAILABLE_TEXT, 'skill_unavailable')
        if not self.library.current(entry):
            raise SkillError(REVOKED_TEXT.format(skill=entry['skill']), 'skill_revoked')
        return entry

    def check_current(self):
        """Refuse when a skill this Work loaded is no longer current (every later tool call)."""
        for skill, entry in sorted(self.loaded.items()):
            if not self.library.current(entry):
                raise SkillError(REVOKED_TEXT.format(skill=skill), 'skill_revoked')

    def identity(self, entry):
        return {'skill': entry['skill'], 'digest': entry['digest'], 'revision': entry['revision'],
                'licence': entry['licence'], 'source': entry['source']}

    def load(self, skill):
        entry = self._entry(skill)
        if skill not in self.loaded and self.loads >= MAX_LOADS:
            raise SkillError(f'한 작업에서 스킬은 {MAX_LOADS}개까지 읽어요.', 'skill_limit')
        text, _cut, files = self.library.read(entry, 'SKILL.md', MAX_FILE_BYTES)
        if skill not in self.loaded:
            self.loads += 1
        self.loaded[skill] = entry
        _frontmatter, body = parse_frontmatter(text)
        return {**self.identity(entry), 'instructions': body.strip()[:MAX_BODY_BYTES],
                'resources': [path for path in files if path != 'SKILL.md' and Path(path).suffix.lower() in TEXT_SUFFIXES][:40],
                'note': '스킬은 방법 안내일 뿐 권한이 아니에요. 요청과 지금 관찰한 결과가 기준이에요.'}

    def resource(self, skill, path):
        entry = self._entry(skill)
        if skill not in self.loaded:
            raise SkillError('먼저 skill_load로 그 스킬을 읽으세요.', 'skill_unavailable')
        if self.resource_reads >= MAX_RESOURCE_READS:
            raise SkillError(f'한 작업에서 스킬 파일은 {MAX_RESOURCE_READS}개까지 읽어요.', 'skill_limit')
        text, cut, _files = self.library.read(entry, path, MAX_RESOURCE_BYTES)
        self.resource_reads += 1
        return {**self.identity(entry), 'path': path, 'content': text, 'truncated': cut}
