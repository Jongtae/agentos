"""Per-Work information-use audit (EGRESS-OPEN-01 / #826).

Owner decision (2026-09-28, #826): owner-private reads and web search may run
in the same Work.  In exchange, every Work shows which owner information it
used and where that information went.

The audit is a *view*, derived only from records AgentOS already keeps for
the Work.  It adds no store:

* ``turn_provenance`` (#570): what each attempt sent, to which worker, route
  and model; the owner-model sections it carried (``owner_information``,
  recorded at send time as references: profile keys, current-context refs,
  prepared-answer refs, spliced sources) and how many earlier conversation
  turns were included;
* ``tool_events``: every tool call AgentOS executed or relayed, and every web
  search the CLI reported (``scope: cli-native``), with the redacted Evidence
  summaries ``agent_runtime.evidence_summary`` wrote;
* ``work_decisions``: the Judgment AI calls linked to the Work (#794).

Vocabulary follows W3C PROV loosely: ``used`` is the owner information the
Work's activity used, ``sent_to`` the agents and destinations it went to,
``results`` what came back (``wasGeneratedBy``).  It is AgentOS's own record,
never a model's claim.  Only references and short labels are shown - keys,
refs, paths, titles, counts, queries - never payloads; a secret redactor is
applied to every label before it leaves this module.
"""
import json
from datetime import datetime, timezone

#: Evidence class of every audit this module returns.
EVIDENCE_CLASS = 'observed AgentOS records (turn_provenance, tool_events, work_decisions); not model claims'
#: Bounds of what one audit shows.
MAX_ITEMS = 20
LABEL_CHARS = 120
QUERY_CHARS = 200

#: #918 slice (a): the owner's undo of a direct memory save, recorded on the Work as its own event.
MEMORY_UNDO_ACTION = 'memory_undo'
#: Owner-private reads, by host action, and the category their items belong to.
READ_CATEGORIES = {
    'list_memory': 'memory', 'search_memory': 'memory', 'save_memory': 'memory', MEMORY_UNDO_ACTION: 'memory',
    'calendar_query': 'calendar', 'calendar_draft_create': 'calendar', 'calendar_draft_update': 'calendar',
    'calendar_draft_cancel': 'calendar',
    'find_files': 'files', 'read_file': 'files', 'list_roots': 'files',
    'list_notes': 'notes', 'save_note': 'notes',
    'propose_current_state': 'current_context',
    'settings_read': 'settings',
    # #826 review: an earlier Work's audit read into this Work is itself owner information used here.
    'information_use': 'records',
    'browser_open': 'browser', 'browser_read': 'browser', 'browser_find': 'browser', 'browser_click': 'browser',
    'browser_type': 'browser', 'browser_sign_in': 'browser',
    # ATTN-WAIT-01 (#839): an item AgentOS reminded the owner of on the waiting draft.
    'attention_surface': 'attention',
}
#: Public destinations AgentOS or the CLI sent a lookup to.
LOOKUP_ACTIONS = frozenset({'web_search', 'bounded_public_research', 'weather', 'public_page_read'})
#: Korean names of the categories, in the order the section shows them.
CATEGORY_NAMES = {
    'profile': '프로필', 'memory': '기억', 'calendar': '캘린더', 'files': '파일',
    'current_context': '현재 상황', 'notes': '메모', 'browser': '로그인한 브라우저 페이지',
    'settings': '설정', 'spliced': '요청에 붙인 자료', 'prepared': '준비해 둔 답변',
    'records': '이전 답변의 사용 기록', 'attention': '기다리는 동안 알린 것',
}
#: Turn-provenance events that are not tools the worker called.
_NOT_TOOLS = frozenset({'model', 'subscription_engine', 'orchestrator'})


def _text(value, limit=LABEL_CHARS):
    return ' '.join(str(value or '').split())[:limit]


def _json_after_legend(text):
    """The compact JSON body a rendered section carries after its legend line, or {}."""
    body = str(text or '').split('\n', 1)
    if len(body) < 2:
        return {}
    try:
        # #942: a line may follow the JSON (the browser sign-ins); only the JSON is read.
        data, _end = json.JSONDecoder().raw_decode(body[1].lstrip())
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def profile_keys(text):
    """The ``profile.*`` keys of a rendered profile snapshot (``key: value (saved ...)`` lines)."""
    keys = []
    for line in str(text or '').splitlines():
        key, sep, _rest = line.partition(':')
        key = key.strip()
        if sep and key and ' ' not in key and key not in keys:
            keys.append(key[:80])
    return keys[:40]


#: #942: the line ``current_context_text`` adds after the JSON, and how many sites it may name.
BROWSER_SIGNINS_PREFIX = 'Browser sign-ins'


def browser_signin_claims(text):
    """The sites a rendered context's browser sign-ins line named (#943 review), as claims."""
    claims = []
    for line in str(text or '').splitlines():
        if not line.startswith(BROWSER_SIGNINS_PREFIX) or ':' not in line:
            continue
        for item in line.split(':', 1)[1].split(', '):
            site = item.split(' (', 1)[0].strip()
            if site and len(claims) < 20:
                shared = ' (공유받은 로그인)' if "shared with you" in item else ''
                claims.append({'ref': f'browser:{_text(site, 60)}', 'label': f'로그인한 사이트: {_text(site, 60)}{shared}'})
    return claims


def context_claims(text):
    """Refs and short labels of a rendered current-context snapshot (#627, #804)."""
    body = _json_after_legend(text)
    claims = browser_signin_claims(text)
    if body.get('local_time') or body.get('as_of'):
        # #804: every turn carries the clock, with the zone when one is known.
        claims.append({'ref': 'clock', 'label': f"현재 시각 ({_text(body.get('timezone') or 'unknown', 40)})"})
    for item in body.get('hypotheses') or ():
        if isinstance(item, dict):
            claims.append({'ref': _text(item.get('ref'), 60), 'label': _text(item.get('predicate'), 60)})
    for item in body.get('locations') or ():
        if isinstance(item, dict):
            label = item.get('label') or item.get('kind') or 'location'
            claims.append({'ref': _text(item.get('ref'), 60), 'label': f'위치: {_text(label, 60)}'})
    for item in body.get('anchors') or ():
        if isinstance(item, dict):
            claims.append({'ref': _text(item.get('ref'), 60), 'label': f"장소: {_text(item.get('label'), 60)}"})
    return claims[:MAX_ITEMS]


def prepared_refs(text):
    """Refs of the prepared answers a turn carried (#659)."""
    return [_text(item.get('ref'), 60) for item in _json_after_legend(text).get('items') or ()
            if isinstance(item, dict) and item.get('ref')][:MAX_ITEMS]


def section_references(profile=None, current_context=None, prepared=None, spliced=()):
    """What the owner-model sections of a turn referred to: keys, refs and labels, never values.

    Recorded on the Work's ``turn_provenance`` at send time
    (``owner_information``), so the audit reads what was sent, not what the
    stores hold later.
    """
    return {'profile_keys': profile_keys(profile), 'current_context': context_claims(current_context),
            'prepared': prepared_refs(prepared),
            'spliced': [{key: _text(value) for key, value in item.items() if key in ('kind', 'ref', 'label')}
                        for item in spliced or () if isinstance(item, dict)][:MAX_ITEMS]}


def _event_items(action, evidence):
    """Short labels of the owner items one successful read or write event shows."""
    evidence = evidence if isinstance(evidence, dict) else {}
    if action == 'list_memory':
        keys = [_text(key, 80) for key in evidence.get('memory_keys') or ()]
        return keys or [f"기억 {int(evidence.get('memory_count') or 0)}개"]
    if action == 'search_memory':
        query = _text(' '.join(evidence.get('query_terms') or ()), 80)
        refs = []
        for item in evidence.get('memory_refs') or ():
            if not isinstance(item, dict):
                continue
            saved = item.get('saved_at')
            if not saved and item.get('created') is not None:
                try:
                    saved = datetime.fromtimestamp(float(item['created']), timezone.utc).isoformat(timespec='seconds')
                except (TypeError, ValueError, OverflowError, OSError):
                    saved = None
            label = _text(item.get('memory_key'), 80)
            if saved:
                label += f" (saved { _text(saved, 25) }"
                if item.get('work_ref'):
                    label += f", {_text(item.get('work_ref'), 60)}"
                label += ')'
            refs.append(label)
        keys = [_text(key, 80) for key in evidence.get('memory_keys') or ()]
        return [f"기억 검색: {query} → {', '.join(refs or keys) if refs or keys else '일치 없음'}"]
    if action == 'save_memory':
        key = _text(evidence.get('memory_key'), 80)
        # #918 slice (a): the owner's worker saved it at once (undo offered); a third party's stays a proposal.
        state = ('바로 저장' if evidence.get('auto_saved') else '저장') if evidence.get('saved') else '제안'
        return [f'{key} ({state})' if key else state]
    if action == MEMORY_UNDO_ACTION:
        key = _text(evidence.get('memory_key'), 80)
        state = '되돌림 · 이전 값 복원' if evidence.get('restored_id') else '되돌림'
        return [f'{key} ({state})' if key else state]
    if action == 'calendar_query':
        events = [f"{_text(row.get('title'), 60)} ({_text(row.get('start'), 25)})".strip()
                  for row in evidence.get('events') or () if isinstance(row, dict)]
        return events or [f"일정 {int(evidence.get('event_count') or 0)}개"]
    if action.startswith('calendar_draft_'):
        return [f"일정 초안 {_text(evidence.get('draft_id'), 40)}"]
    if action == 'find_files':
        files = [_text(row.get('path')) for row in evidence.get('files') or () if isinstance(row, dict)]
        return files or [f"일치하는 파일 {int(evidence.get('file_count') or 0)}개"]
    if action == 'read_file':
        return [_text(evidence.get('path'))]
    if action == 'list_roots':
        roots = [f'폴더: {_text(name, 60)}' for name in evidence.get('roots') or ()]
        return roots or [f"연결 폴더 {int(evidence.get('root_count') or 0)}개"]
    if action == 'list_notes':
        return [f"메모 {int(evidence.get('note_count') or 0)}개"]
    if action == 'save_note':
        return ['메모 저장']
    if action == 'propose_current_state':
        return [f"상태 제안: {_text(evidence.get('predicate'), 60)}"]
    if action == 'settings_read':
        return [f"설정 {_text(evidence.get('category'), 40)}"]
    if action == 'attention_surface':
        return [f"{_text(evidence.get('label'))} ({_text(evidence.get('ref'), 60)})"]
    if action == 'information_use':
        names = ', '.join(CATEGORY_NAMES.get(name, name) for name in evidence.get('categories') or ())
        lookups = int(evidence.get('lookup_count') or 0)
        detail = ', '.join(part for part in (names, f'웹 조회 {lookups}건' if lookups else '') if part)
        return [f"작업 {_text(evidence.get('work_id'), 12)}" + (f' ({detail})' if detail else '')]
    if action.startswith('browser_'):
        return [_text(evidence.get('title') or evidence.get('url'))]
    return []


def _lookup(action, trace, evidence):
    """One public lookup: where it went and what was sent, as the records show it."""
    evidence = evidence if isinstance(evidence, dict) else {}
    queries = [_text(query, QUERY_CHARS) for query in evidence.get('search_queries') or () if query]
    sent = evidence.get('sent') if isinstance(evidence.get('sent'), dict) else {}
    arguments = trace.get('arguments') if isinstance(trace.get('arguments'), dict) else {}
    # What AgentOS sent (``sent``, stored secrets already dropped) is the record when there is one;
    # otherwise the call's starting arguments (the subscription /search preflight records its query
    # at the top level of its running event).
    for source in ((sent,) if sent else (arguments, trace)):
        for key in ('query', 'city', 'url'):
            value = source.get(key)
            if isinstance(value, str) and value.strip() and _text(value, QUERY_CHARS) not in queries:
                queries.append(_text(value, QUERY_CHARS))
    by = evidence.get('provider') or (arguments.get('provider') if isinstance(arguments.get('provider'), str) else '')
    native = trace.get('scope') == 'cli-native'
    return {'tool': action, 'by': _text(by or (trace.get('engine') if native else 'AgentOS'), 60),
            'cli_own_search': native, 'queries': queries[:5], 'status': 'succeeded',
            'result_count': int(evidence.get('result_count') or 0), 'sources': [_text(url, 200) for url in evidence.get('sources') or ()][:5]}


def _result_label(action, evidence):
    evidence = evidence if isinstance(evidence, dict) else {}
    if action in LOOKUP_ACTIONS:
        count = int(evidence.get('result_count') or 0)
        sources = evidence.get('sources') or ()
        return f'결과 {count}개' + (f', 출처 {len(sources)}개' if sources else '')
    items = _event_items(action, evidence)
    return ', '.join(items[:3]) if items else '완료'


def work_information_use(store, job_id, redact=None):
    """The information-use audit of one Work, or None when the Work does not exist.

    ``redact`` (the service's stored-secret pass) is applied to every label.
    """
    job = store.job(job_id) if isinstance(job_id, str) and job_id else None
    if not job:
        return None
    clean = redact if callable(redact) else (lambda text: text)
    def label(value, limit=LABEL_CHARS):
        try:
            return _text(clean(_text(value, limit * 2)), limit)
        except Exception:
            return '[가림]'
    record = store.turn_provenance(job_id) if callable(getattr(store, 'turn_provenance', None)) else None
    record = record if isinstance(record, dict) else {}
    sections = record.get('owner_information') if isinstance(record.get('owner_information'), dict) else {}
    used = {}
    def add(category, items):
        rows = used.setdefault(category, [])
        for item in items:
            text = label(item)
            if text and text not in rows and len(rows) < MAX_ITEMS:
                rows.append(text)
    add('profile', sections.get('profile_keys') or ())
    add('current_context', [row.get('label') for row in sections.get('current_context') or () if isinstance(row, dict)])
    add('prepared', sections.get('prepared') or ())
    add('spliced', [f"{row.get('kind')}: {row.get('label') or row.get('ref')}" for row in sections.get('spliced') or ()
                    if isinstance(row, dict)])
    photo_rows=record.get('photo_inputs') if isinstance(record.get('photo_inputs'),list) else []
    if not photo_rows and isinstance(record.get('photo_input'),dict):photo_rows=[record['photo_input']]
    photo_rows=[row for row in photo_rows if isinstance(row,dict)]
    included_photos=[row for row in photo_rows if row.get('status')=='included-in-request' and row.get('count')]
    if included_photos:
        try:photo_count=min(10,max(1,max(int(row.get('count') or 0) for row in included_photos)))
        except (TypeError,ValueError):photo_count=1
        add('spliced', [f'Telegram 사진 {photo_count}개'])
    lookups, results, started = [], [], {}
    for event in store.task_events(job_id):
        tool, status, trace = event.get('tool'), event.get('status'), event.get('trace') or {}
        if tool in _NOT_TOOLS or not isinstance(trace, dict):
            continue
        action = trace.get('host_action') or tool
        evidence = trace.get('evidence') if isinstance(trace.get('evidence'), dict) else {}
        if action in LOOKUP_ACTIONS and status == 'running':
            # The arguments a lookup started with, for a call that then failed.
            started[(tool, trace.get('call_id'))] = trace
        # #918: an undo is recorded on the Work after it settled (status ``recorded``, never a step).
        if (status == 'succeeded' or (action == MEMORY_UNDO_ACTION and status == 'recorded')) and action in READ_CATEGORIES:
            add(READ_CATEGORIES[action], _event_items(action, evidence))
        if action in LOOKUP_ACTIONS and status in ('succeeded', 'failed'):
            # A succeeded lookup's record is what its Evidence says left (``sent``, the CLI's reported
            # queries); the worker's raw arguments are not shown for it.  A failed lookup was still
            # attempted: its starting event (the worker's arguments, or the /search preflight's query)
            # completes what the terminal event recorded.
            begun = started.pop((tool, trace.get('call_id')), {})
            source = trace if status == 'succeeded' else {**begun, **trace}
            lookup = _lookup(action, source, evidence)
            lookup['status'] = status
            lookup['queries'] = [label(query, QUERY_CHARS) for query in lookup['queries']]
            lookup['by'] = label(lookup['by'], 60)
            lookup['sources'] = [label(url, 200) for url in lookup['sources']]
            lookups.append(lookup)
        if status in ('succeeded', 'failed', 'withheld', 'unavailable', 'denied'):
            results.append({'tool': label(tool, 60), 'status': status,
                            'label': label(_result_label(action, evidence)) if status == 'succeeded'
                            else label(trace.get('code') or trace.get('error') or status, 80)})
    used = [{'category': category, 'name': CATEGORY_NAMES.get(category, category), 'items': items}
            for category, items in sorted(used.items(), key=lambda row: list(CATEGORY_NAMES).index(row[0])
                                          if row[0] in CATEGORY_NAMES else len(CATEGORY_NAMES)) if items]
    workers = [dict(row) for row in record.get('workers') or () if isinstance(row, dict)]
    if not workers and (record.get('engine') or record.get('provider')):
        # A Work recorded before #826 names only its last worker.
        workers = [{'route': record.get('route'), 'engine': record.get('engine'), 'provider': record.get('provider'),
                    'model': record.get('requested_model'), 'own_web_search': bool(record.get('cli_native_tools'))}]
    workers = [{key: (label(value, 80) if isinstance(value, str) else value) for key, value in row.items()} for row in workers]
    if workers and record.get('reported_model'):
        workers[-1]['reported_model'] = label(record['reported_model'], 80)
    judgments = store.work_decisions(job_id)
    judgment_models = sorted({label(row.get('observed_model') or row.get('model') or row.get('engine') or row.get('provider'), 80)
                              for row in judgments} - {''})
    photo_inputs=[{key: (label(value,80) if isinstance(value,str) else value)
                   for key,value in photo.items() if key in ('attempt','source','count','status','route','engine','provider')}
                  for photo in photo_rows]
    sent_to={'workers': workers,
             'judgment_ai': {'calls': len(judgments), 'models': judgment_models},
             'web_search_ran': bool(lookups), 'lookups': lookups[:MAX_ITEMS]}
    if photo_inputs:sent_to['attachments']=photo_inputs
    return {'work_id': job_id, 'recorded': bool(record), 'evidence_class': EVIDENCE_CLASS,
            'used': used,
            'conversation_turns': int(record.get('context_messages') or 0),
            'sent_to': sent_to,
            'results': results[-MAX_ITEMS:]}


def _worker_text(row):
    who = row.get('engine') or row.get('provider') or row.get('route') or '알 수 없는 AI'
    model = row.get('reported_model') or row.get('model') or '기본 모델'
    search = ' · 자체 웹 검색 켜짐' if row.get('own_web_search') else ''
    return f'{who} ({model}){search}'


def render_korean(audit):
    """The compact Korean "이 답변에 쓴 정보" text of one audit."""
    if not audit:
        return '이 작업의 기록을 찾지 못했습니다.'
    lines = ['이 답변에 쓴 정보']
    if not audit.get('recorded'):
        lines.append('- 이 작업에는 보낸 내용 기록이 없습니다(기록 기능 이전 작업일 수 있습니다).')
    for row in audit.get('used') or ():
        lines.append(f"- {row['name']}: {', '.join(row['items'])}")
    turns = audit.get('conversation_turns') or 0
    lines.append(f'- 이전 대화: {turns}개 메시지 포함' if turns else '- 이전 대화: 포함하지 않음')
    if not audit.get('used'):
        lines.append('- 개인 정보: 기록된 사용 없음')
    sent = audit.get('sent_to') or {}
    workers = sent.get('workers') or ()
    lines.append('보낸 곳')
    lines.append('- 작업 AI: ' + ('; '.join(_worker_text(row) for row in workers) if workers else '기록 없음'))
    for photo in sent.get('attachments') or ():
        destination=photo.get('engine') or photo.get('provider') or photo.get('route') or '경로 기록 없음'
        state={'included-in-request':'요청에 포함','staged':'전달 대기','not-sent':'전달하지 않음',
               'unknown':'전달 여부 확인 불가','unsupported':'지원하지 않음','failed':'가져오기 실패'}.get(photo.get('status'),photo.get('status') or '상태 기록 없음')
        lines.append(f"- Telegram 사진 → {destination}: {state}")
    judgment = sent.get('judgment_ai') or {}
    if judgment.get('calls'):
        models = ', '.join(judgment.get('models') or ()) or '판단 AI'
        lines.append(f"- 판단 AI: {judgment['calls']}회 ({models})")
    lookups = sent.get('lookups') or ()
    if lookups:
        for lookup in lookups[:8]:
            queries = ' / '.join(f'"{query}"' for query in lookup.get('queries') or ()) or '검색어 보고 없음'
            who = 'CLI 자체 검색' if lookup.get('cli_own_search') else lookup.get('by') or 'AgentOS'
            failed = ' · 실패' if lookup.get('status') == 'failed' else ''
            lines.append(f"- 웹 조회({who}{failed}): {queries}")
    else:
        lines.append('- 웹 검색: 실행하지 않음')
    results = [row for row in audit.get('results') or () if row.get('status') == 'succeeded']
    if results:
        lines.append('돌아온 결과')
        for row in results[-8:]:
            lines.append(f"- {row['tool']}: {row['label']}")
    return '\n'.join(lines)
