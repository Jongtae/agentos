"""Policy-owned, local-first assistant orchestration for MP1 capabilities.

Adapters are injected and deliberately have no HTTP or channel surface.  This
module is the only boundary allowed to select and invoke them.
"""
import hashlib
import time
import uuid

from .capabilities import CapabilityRegistry


class AssistantRequestError(ValueError):
    pass


class PersonalAssistantOrchestrator:
    def __init__(self, store, *, drive=None, a2a=None, calendar=None, now=time.time):
        self.store, self.drive, self.a2a, self.calendar, self.now = store, drive, a2a, calendar, now
        self.registry = CapabilityRegistry(store)

    def _evidence(self, kind, state, recovery=None, **metadata):
        """Persist only lifecycle metadata; never prompts, secrets, or content."""
        rows = self.store.config('personal_assistant_evidence', [])
        event = {'kind': kind, 'state': state, 'at': self.now()}
        if recovery:
            event['recovery'] = recovery
        event.update({key: value for key, value in metadata.items() if value not in (None, '', [], {})})
        rows.append(event)
        self.store.put('personal_assistant_evidence', rows[-100:])
        return event

    # PA1-CONV-01 / #393 resolving the Drive `.read()` gap carried from
    # REUSE-R1c / #442.  The resolution is that this seam stays unsatisfiable
    # by any shipped class, deliberately, and refuses in the owner's language
    # instead of crashing.  Recording why, because adapting it looks reasonable
    # until the two owner identity types are compared.
    #
    # `DriveWebOAuthHandoff.read_selected(telegram_owner_id, file_id,
    # transport)` cannot be adapted to this seam's `.read(file_id)` without
    # dissolving the gate that makes it safe.  `select_files_for_grant` stores
    # the Picker selection owner only when `isinstance(owner, int)` -- a
    # Telegram chat id -- while `_request` below rejects any orchestrator owner
    # that is not a non-empty `str`.  The two identity spaces cannot intersect,
    # so `assert_selected` would refuse every request this seam could ever
    # make, and the only way to make one pass is to hand it the owner read back
    # out of the very selection record it is checking.  That is the bypass the
    # issue forbids, so the adapter is not written.
    #
    # This is a decision now and a defect later: it becomes one the moment an
    # orchestrator request can carry a Drive identity the Picker gate can
    # actually evaluate, because a refusal would then be hiding a capability
    # the owner had already authorized.  Until then the owner-reachable Drive
    # capability is `AgentService.selected_drive_context`, which holds the chat
    # id the gate needs.  `search` is served here -- the handoff provides it as
    # a deliberate refusal -- so the required shape is named per call site
    # rather than assumed, and an absent one is reported instead of leaving the
    # owner-safe envelope as an AttributeError.
    def _drive_adapter(self, method):
        if self.drive is None:
            raise AssistantRequestError('이 요청 경로에는 Google Drive 어댑터가 연결되어 있지 않습니다. Google Drive 파일은 Telegram 대화에서 Google Drive를 연결하고 Google Picker로 선택해 읽을 수 있습니다.')
        adapter = self.drive.adapter() if hasattr(self.drive, 'adapter') else self.drive
        if not callable(getattr(adapter, method, None)):
            raise AssistantRequestError('연결된 Google Drive 어댑터는 이 동작을 제공하지 않습니다. Google Drive 파일은 Telegram 대화에서 Google Picker로 선택해 읽을 수 있습니다.')
        return adapter

    def _drive_excerpts(self):
        return self.store.config('drive_excerpt_approvals', {})

    def _put_drive_excerpts(self, rows):
        self.store.put('drive_excerpt_approvals', rows)

    @staticmethod
    def _request(value):
        if not isinstance(value, dict) or not isinstance(value.get('message'), str) or not value['message'].strip():
            raise AssistantRequestError('자연어 요청이 필요합니다.')
        owner = value.get('owner_id')
        if not isinstance(owner, str) or not owner:
            raise AssistantRequestError('소유자 식별이 필요합니다.')
        return value['message'].strip(), owner

    @staticmethod
    def classify(message):
        """Classify only a deliberately small, owner-readable MP1 vocabulary.

        The optional structured fields accompanying a channel request are data
        for a selected action, never authority to select it.  A model cannot
        turn an arbitrary request into a delegation or an external action by
        supplying an `intent` value.
        """
        if message.startswith('Drive 검색:'):
            return 'drive-search'
        if message.startswith('A2A 위임:'):
            return 'a2a-delegate'
        if message.startswith('일정 초안:'):
            return 'calendar-create'
        if any(token in message for token in ('내 메모', '개인 공간', '저장한 결과')):
            return 'local'
        return 'unknown'

    def handle(self, value):
        """Classify one owner request and return an owner-safe result envelope.

        Selection comes from the owner's message; only the explicit Korean
        delegation form can invoke an A2A peer.  It avoids treating a model
        suggestion or a channel-supplied action field as authorization.
        """
        message, owner = self._request(value)
        intent = self.classify(message)
        if intent == 'local':
            space = self.store.personal_space()
            evidence = self._evidence('local', 'completed', memory_count=space['memory_count'], result_count=space['result_count'])
            return {'state': 'completed', 'response': '개인 공간의 기억과 저장 결과를 확인했습니다.', 'evidence': evidence}
        if intent == 'drive-search':
            try:
                self.registry.require_enabled('google-drive-read', 'read')
                rows = self._drive_adapter('search').search(value.get('query', message))
                safe = [{'id': row.get('id', ''), 'name': row.get('name', ''), 'mime_type': row.get('mime_type', '')} for row in rows[:20] if isinstance(row, dict)]
                evidence = self._evidence('drive-search', 'completed', result_count=len(safe))
                return {'state': 'completed', 'response': 'Google Drive에서 관련 파일을 찾았습니다.', 'sources': safe, 'evidence': evidence}
            except (ValueError, AssistantRequestError) as exc:
                evidence = self._evidence('drive-search', 'blocked', 'Drive 연결 상태를 확인하거나 다시 연결하세요.')
                return {'state': 'blocked', 'response': str(exc), 'evidence': evidence}
        if intent == 'a2a-delegate':
            try:
                self.registry.require_enabled('compatibility-a2a-peer', 'delegate')
                if self.a2a is None:
                    raise AssistantRequestError('A2A test peer가 연결되지 않았습니다.')
                excerpt = self._approved_drive_excerpt(value.get('drive_excerpt'), owner) if value.get('drive_excerpt') is not None else None
                delegation = self.a2a.delegate({'explicit': True, 'owner': owner, 'prompt': message, **({'context': {'text': excerpt['text']}} if excerpt else {})})
                if excerpt:
                    rows = self._drive_excerpts(); rows[excerpt['id']]['state'] = 'consumed'; self._put_drive_excerpts(rows)
                evidence = self._evidence('a2a-delegate', 'requested', delegation_id=delegation['id'])
                return {'state': 'requested', 'response': '명시한 작업을 호환성 Agent에 위임했습니다.', 'delegation_id': delegation['id'], 'evidence': evidence}
            except (ValueError, AssistantRequestError) as exc:
                evidence = self._evidence('a2a-delegate', 'blocked', '연결 상태를 확인하거나 로컬 답변을 사용하세요.')
                return {'state': 'blocked', 'response': str(exc), 'evidence': evidence}
        if intent == 'calendar-create':
            try:
                self.registry.require_enabled('google-calendar-create', 'calendar.events')
                if self.calendar is None or not isinstance(value.get('event'), dict):
                    raise AssistantRequestError('일정 초안 정보를 확인하세요.')
                draft = self.calendar.draft(value['event'], owner)
                evidence = self._evidence('calendar-draft', 'awaiting-approval', draft_id=draft['id'])
                return {'state': 'awaiting-approval', 'response': '일정 초안을 만들었습니다. 내용을 확인한 뒤 승인하세요.', 'draft': draft, 'evidence': evidence}
            except (ValueError, AssistantRequestError) as exc:
                evidence = self._evidence('calendar-draft', 'blocked', '일정 연결 상태와 초안 정보를 확인하세요.')
                return {'state': 'blocked', 'response': str(exc), 'evidence': evidence}
        evidence = self._evidence('unknown', 'fallback', '요청을 더 구체적으로 설명하거나 사용 가능한 연결을 확인하세요.')
        return {'state': 'fallback', 'response': '이 요청에 사용할 검토된 capability를 찾지 못했습니다.', 'evidence': evidence}

    def draft_drive_excerpt(self, value):
        """Read a bounded local excerpt; it cannot reach a peer before approval."""
        _, owner = self._request(value)
        try:
            self.registry.require_enabled('google-drive-read', 'read')
            file_id, start, length = value.get('file_id'), value.get('start', 0), value.get('length', 4000)
            if not isinstance(file_id, str) or not file_id or not isinstance(start, int) or start < 0 or not isinstance(length, int) or not 1 <= length <= 4000:
                raise AssistantRequestError('선택할 Drive 발췌문 범위를 확인하세요.')
            content = self._drive_adapter('read').read(file_id)
            if isinstance(content, dict): content = content.get('text')
            if not isinstance(content, str):
                raise AssistantRequestError('Drive 파일 내용을 안전하게 읽지 못했습니다.')
            excerpt = content[start:start + length]
            if not excerpt:
                raise AssistantRequestError('선택한 Drive 발췌문이 비어 있습니다.')
            ident = str(uuid.uuid4()); rows = self._drive_excerpts()
            rows[ident] = {'id': ident, 'owner': owner, 'text': excerpt, 'hash': hashlib.sha256(excerpt.encode()).hexdigest(), 'state': 'awaiting-approval'}
            self._put_drive_excerpts(rows)
            evidence = self._evidence('drive-excerpt-draft', 'awaiting-approval', excerpt_id=ident, length=len(excerpt))
            return {'state': 'awaiting-approval', 'excerpt': {'id': ident, 'text': excerpt}, 'evidence': evidence}
        except (ValueError, AssistantRequestError) as exc:
            evidence = self._evidence('drive-excerpt-draft', 'blocked', 'Drive 연결을 다시 인증하거나 발췌 범위를 확인하세요.')
            return {'state': 'blocked', 'response': str(exc), 'evidence': evidence}

    def approve_drive_excerpt(self, value):
        _, owner = self._request(value)
        try:
            self.registry.require_enabled('google-drive-read', 'read')
            ident = value.get('excerpt_id'); rows = self._drive_excerpts(); row = rows.get(ident)
            if not isinstance(ident, str) or not row or row.get('owner') != owner or row.get('state') != 'awaiting-approval':
                raise AssistantRequestError('승인할 Drive 발췌문을 확인하세요.')
            row['approval_id'] = uuid.uuid4().hex; row['state'] = 'approved'; rows[ident] = row; self._put_drive_excerpts(rows)
            evidence = self._evidence('drive-excerpt-approval', 'approved', excerpt_id=ident)
            return {'state': 'approved', 'approval_id': row['approval_id'], 'evidence': evidence}
        except (ValueError, AssistantRequestError) as exc:
            evidence = self._evidence('drive-excerpt-approval', 'blocked', '발췌문을 다시 확인하세요.')
            return {'state': 'blocked', 'response': str(exc), 'evidence': evidence}

    def _approved_drive_excerpt(self, value, owner):
        if not isinstance(value, dict):
            raise AssistantRequestError('외부 Agent에 전달할 승인된 Drive 발췌문이 필요합니다.')
        row = self._drive_excerpts().get(value.get('excerpt_id'))
        if not row or row.get('owner') != owner or row.get('state') != 'approved' or row.get('approval_id') != value.get('approval_id'):
            raise AssistantRequestError('Drive 발췌문 승인이 일치하지 않습니다.')
        return row

    def approve_calendar(self, value):
        """Record a one-time owner approval for a previously previewed draft."""
        _, owner = self._request(value)
        try:
            self.registry.require_enabled('google-calendar-create', 'calendar.events')
            if self.calendar is None or not isinstance(value.get('draft_id'), str):
                raise AssistantRequestError('승인할 일정 초안을 확인하세요.')
            approval = self.calendar.approve(value['draft_id'], owner)
            evidence = self._evidence('calendar-approval', 'approved', draft_id=value['draft_id'])
            return {'state': 'approved', 'approval': approval, 'evidence': evidence}
        except (ValueError, AssistantRequestError) as exc:
            evidence = self._evidence('calendar-approval', 'blocked', '일정 초안을 다시 확인하세요.')
            return {'state': 'blocked', 'response': str(exc), 'evidence': evidence}

    def create_calendar(self, value):
        """Execute only an exact, owner-bound approval through the policy gate."""
        _, owner = self._request(value)
        try:
            self.registry.require_enabled('google-calendar-create', 'calendar.events')
            if self.calendar is None or not isinstance(value.get('draft_id'), str) or not isinstance(value.get('approval_id'), str):
                raise AssistantRequestError('일정 승인 정보를 확인하세요.')
            result = self.calendar.create(value['draft_id'], value['approval_id'], owner)
            evidence = self._evidence('calendar-create', 'completed', draft_id=value['draft_id'], event_id=result['id'])
            return {'state': 'completed', 'result': result, 'evidence': evidence}
        except (ValueError, AssistantRequestError) as exc:
            evidence = self._evidence('calendar-create', 'blocked', '일정 연결 상태를 확인하거나 새 초안을 만드세요.')
            return {'state': 'blocked', 'response': str(exc), 'evidence': evidence}
