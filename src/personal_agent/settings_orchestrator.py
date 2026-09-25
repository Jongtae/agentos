"""Conversation-first settings read model over the authoritative connections.

PRESENCE-SETTINGS-01 #506 retired the legacy ``CapabilityRegistry`` as a
Settings control plane.  That registry had no production execution caller:
pausing or disconnecting ``google-drive-read`` there changed a config row
while the real connector credential and execution path stayed usable, so the
owner could be told a capability was stopped while AgentOS could still call it.

This object therefore reads connection state only from the authoritative
boundaries the owning service supplies (Telegram pairing, ``ConnectorRegistry``
status for Gmail/Calendar, the Drive OAuth handoff), and it offers no lifecycle
mutation whose backend would not actually change the represented authority.
It never accepts credentials, OAuth artifacts, arbitrary setting names, or a
provider endpoint.  HTTP, Telegram, and the local companion view call this same
object.

Historical ``capability_registry`` rows, ``retired_capability_evidence`` and
the redacted ``settings_audit`` stay in the store untouched as evidence; they
are not read as current authority.
"""
import re
import time


class SettingsError(ValueError):
    """A fail-closed settings request error safe to show to an owner."""


# Owner-visible words for the connection contract states.  An unknown value is
# reported as needing a check rather than guessed as connected.
STATE_LABELS = {
    "connected": "연결됨",
    "disconnected": "연결 안 됨",
    "reauth_required": "다시 인증 필요",
    "blocked": "차단됨",
    "pending": "확인 필요",
}
UNKNOWN_STATE_LABEL = "확인 필요"

# The words an owner may use for each service in a recovery question.  This is
# a literal lookup over already-declared services, not an intent judgment.
_SERVICE_WORDS = {
    "telegram": ("telegram", "텔레그램"),
    "google-gmail-read": ("gmail", "메일", "지메일"),
    "google-calendar": ("calendar", "캘린더", "일정"),
    "google-calendar-write": ("calendar", "캘린더", "일정"),
    "google-drive-read": ("drive", "드라이브"),
}

RETIRED_CONTROL_MESSAGE = (
    "연결을 일시 정지하거나 해제하는 기능은 대화에서 제공하지 않습니다. "
    "설정 > 외부 연결에서 서비스별 현재 상태와 실제로 가능한 작업을 확인하세요."
)


def state_label(state):
    return STATE_LABELS.get(state, UNKNOWN_STATE_LABEL)


def next_action(row):
    """The one truthful owner action for a connection row, as plain text."""
    state = row.get("state")
    if state == "blocked":
        return "현재 정책으로 사용할 수 없습니다."
    if row.get("id") == "telegram":
        if state == "connected":
            return "추가로 할 일이 없습니다. 해제는 설정 > 외부 연결에서 합니다."
        if state == "pending":
            return "Telegram에서 연결 링크를 열어 소유자 계정을 연결하세요."
        return "설정 > 외부 연결에서 봇 토큰으로 연결하세요."
    if not row.get("connectable"):
        if state == "connected":
            return "추가로 할 일이 없습니다."
        return row.get("connect_hint") or "이 설치에서는 여기서 연결을 시작할 수 없습니다."
    if state == "connected":
        return "추가로 할 일이 없습니다. 권한을 새로 받으려면 설정 > 외부 연결에서 다시 연결하세요."
    if state == "reauth_required":
        return "설정 > 외부 연결에서 다시 연결하세요."
    if state == "disconnected":
        return "설정 > 외부 연결에서 연결하세요."
    return "설정 > 외부 연결에서 상태를 확인하세요."


class SettingsOrchestrator:
    TTL_SECONDS = 10 * 60
    _CATEGORIES = ("connections",)

    def __init__(self, store, now=time.time, connections=None):
        self.store, self.now = store, now
        # A callable returning owner-visible connection rows derived from the
        # authoritative boundaries.  With none supplied there are no
        # connections to report, never a guessed one.
        self.connections = connections or (lambda: [])

    def _drafts(self):
        rows = self.store.config("settings_change_drafts", {})
        return rows if isinstance(rows, dict) else {}

    def _put_drafts(self, rows):
        self.store.put("settings_change_drafts", rows)

    def _rows(self):
        rows = []
        for row in self.connections() or []:
            if not isinstance(row, dict) or not row.get("id"):
                continue
            item = {"id": str(row["id"]), "service": str(row.get("service") or row["id"]),
                    "state": str(row.get("state") or "unknown")}
            item["state_label"] = state_label(item["state"])
            item["next_action"] = next_action(row)
            rows.append(item)
        return rows

    def _activity(self):
        audit = self.store.config("settings_audit", [])
        if not isinstance(audit, list):
            return []
        return [{key: item[key] for key in ("at", "target", "before", "after", "terminal", "error_class") if key in item}
                for item in audit[-20:] if isinstance(item, dict) and item.get("terminal") != "drafted"]

    @staticmethod
    def _summary(rows):
        if not rows:
            return "이 설치에 연결된 외부 서비스가 없습니다."
        return "\n".join(f"{row['service']} · {row['state_label']}" for row in rows)

    def read(self, owner, category=None):
        if not isinstance(owner, str) or not owner:
            raise SettingsError("설정 소유자를 확인하세요.")
        if category is not None and category not in self._CATEGORIES:
            raise SettingsError("검토된 설정 범주를 선택하세요.")
        rows = self._rows()
        return {"state": "read", "category": category or "all", "connections": rows,
                "response": self._summary(rows), "activity": self._activity()}

    def _audit(self, row, terminal, error_class=None):
        audit = self.store.config("settings_audit", [])
        audit = audit if isinstance(audit, list) else []
        event = {"at": self.now(), "draft_ref": row["id"], "target": row.get("target"),
                 "before": row.get("before"), "after": row.get("after"), "terminal": terminal}
        if error_class: event["error_class"] = error_class
        self.store.put("settings_audit", [*audit, event][-100:])

    def draft(self, owner, channel, intent):
        """No lifecycle draft exists any more: say so and change nothing."""
        if not isinstance(owner, str) or not owner or not isinstance(channel, str) or not channel:
            raise SettingsError("설정 요청의 소유자와 채널을 확인하세요.")
        if not isinstance(intent, str):
            raise SettingsError("검토된 설정 요청을 구체적으로 말해 주세요.")
        return {"state": "unsupported", "response": RETIRED_CONTROL_MESSAGE}

    def _owned(self, owner, channel, draft_id):
        row = self._drafts().get(draft_id)
        if not row or row.get("owner") != owner or row.get("channel") != channel:
            raise SettingsError("확인할 설정 초안을 찾지 못했습니다.")
        return row

    def confirm(self, owner, channel, draft_id, digest):
        """A draft made by the retired control plane can never apply."""
        if not isinstance(draft_id, str) or not isinstance(digest, str):
            raise SettingsError("초안 ID와 정확한 확인 정보를 제공하세요.")
        row = self._owned(owner, channel, draft_id)
        if row.get("state") == "awaiting-confirmation":
            row["state"] = "failed"
            rows = self._drafts(); rows[draft_id] = row; self._put_drafts(rows)
            self._audit(row, "failed", "retired-control")
        raise SettingsError(RETIRED_CONTROL_MESSAGE)

    def cancel(self, owner, channel, draft_id):
        row = self._owned(owner, channel, draft_id)
        if row["state"] == "canceled": return {"state": "canceled", "idempotent": True}
        if row["state"] != "awaiting-confirmation": raise SettingsError("이 설정 초안은 취소할 수 없습니다.")
        row["state"] = "canceled"; rows = self._drafts(); rows[draft_id] = row; self._put_drafts(rows); self._audit(row, "canceled")
        return {"state": "canceled", "idempotent": False}

    def recovery(self, owner, subject):
        if not isinstance(owner, str) or not owner or not isinstance(subject, str):
            raise SettingsError("복구할 연결을 선택하세요.")
        rows = {str(row.get("id")): row for row in self.connections() or [] if isinstance(row, dict)}
        row = rows.get(subject)
        if not row:
            raise SettingsError("복구할 연결을 선택하세요.")
        return {"state": "recovery", "target": subject, "action": next_action(row)}

    def _service_in(self, text):
        value = text.lower()
        available = {str(row.get("id")) for row in self.connections() or [] if isinstance(row, dict)}
        for ident, words in _SERVICE_WORDS.items():
            if ident in available and any(word in value for word in words):
                return ident
        return None

    def handle_text(self, owner, channel, text):
        if not isinstance(text, str): raise SettingsError("설정 요청을 확인하세요.")
        value = text.strip()
        match = re.fullmatch(r"(?:confirm|확인)\s+([A-Za-z0-9_-]+)", value, re.I)
        if match:
            row = self._owned(owner, channel, match.group(1))
            return self.confirm(owner, channel, row["id"], row.get("digest", ""))
        match = re.fullmatch(r"(?:cancel|취소)\s+([A-Za-z0-9_-]+)", value, re.I)
        if match: return self.cancel(owner, channel, match.group(1))
        if value.lower() in ("settings", "/settings", "무엇이 연결되어 있어?", "무엇을 바꿀 수 있어?") or "상태 보여" in value:
            return self.read(owner)
        if "어떻게 복구" in value:
            target = self._service_in(value)
            if target:
                return self.recovery(owner, target)
            return self.read(owner)
        return self.draft(owner, channel, value)
