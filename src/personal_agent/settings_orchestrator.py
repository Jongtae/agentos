"""Policy-owned, conversation-first settings lifecycle changes.

This deliberately supports only the reviewed capability lifecycle.  It never
accepts credentials, OAuth artifacts, arbitrary setting names, or a provider
endpoint.  HTTP, Telegram, and the local companion view call this same object.
"""
import hashlib
import json
import re
import secrets
import time

from .capabilities import CATALOGUE, CapabilityRegistry


class SettingsError(ValueError):
    """A fail-closed settings request error safe to show to an owner."""


class SettingsOrchestrator:
    TTL_SECONDS = 10 * 60
    _CATEGORY = {
        "connections": {"google-drive-read", "google-calendar-create"},
        "runtime": {"isolated-runtime-placeholder"},
        "assistant": {"builtin-mcp-read"},
    }
    _ACTIONS = {"pause": "paused", "disconnect": "disconnected", "resume": "enabled"}

    def __init__(self, store, now=time.time):
        self.store, self.now = store, now
        self.registry = CapabilityRegistry(store)

    def _drafts(self):
        rows = self.store.config("settings_change_drafts", {})
        return rows if isinstance(rows, dict) else {}

    def _put_drafts(self, rows):
        self.store.put("settings_change_drafts", rows)

    @staticmethod
    def _digest(change):
        return hashlib.sha256(json.dumps(change, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _catalogue(capability_id):
        return next((item for item in CATALOGUE if item["id"] == capability_id), None)

    def _redacted_capability(self, row):
        return {
            "id": row["id"], "kind": row["kind"], "state": row["state"],
            "declared_scopes": list(row["scopes"]),
            "health": "ready" if row["state"] == "enabled" else "attention" if row["state"] in ("error", "auth-required") else "inactive",
            "recovery": self._recovery_label(row["id"], row["state"]),
        }

    @staticmethod
    def _recovery_label(capability_id, state):
        if state == "auth-required": return "로컬 Connections에서 다시 인증"
        if state == "disconnected": return "로컬 Connections에서 다시 연결"
        if state == "paused": return "검토된 연결 다시 시작 초안"
        if state == "error": return "Runtime & recovery 진단"
        return "현재 상태 확인"

    def read(self, owner, category=None):
        if not isinstance(owner, str) or not owner:
            raise SettingsError("설정 소유자를 확인하세요.")
        if category is not None and category not in self._CATEGORY:
            raise SettingsError("검토된 설정 범주를 선택하세요.")
        rows = [self._redacted_capability(item) for item in self.registry.list()
                if category is None or item["id"] in self._CATEGORY[category]]
        audit = self.store.config("settings_audit", [])
        activity = [{key: item[key] for key in ("at", "target", "before", "after", "terminal", "error_class") if key in item}
                    for item in audit[-20:] if isinstance(item, dict) and item.get("terminal") != "drafted"] if isinstance(audit, list) else []
        return {"state": "read", "category": category or "all", "capabilities": rows,
                "manual_sections": [
                    {"id":"assistant", "label":"Assistant", "description":"선택한 assistant와 기본 동작"},
                    {"id":"connections", "label":"Connections", "description":"검토된 연결 상태와 lifecycle"},
                    {"id":"data-privacy", "label":"Data & privacy", "description":"개인 공간과 export/restore 경계"},
                    {"id":"activity", "label":"Approvals & activity", "description":"redacted settings activity와 recovery"},
                    {"id":"runtime", "label":"Runtime & recovery", "description":"local runtime health와 recovery"},
                ], "activity": activity}

    def _intent(self, intent):
        if not isinstance(intent, str):
            raise SettingsError("검토된 설정 요청을 구체적으로 말해 주세요.")
        value = intent.strip().lower()
        # Keep the language vocabulary intentionally small.  Do not infer an
        # action from a bare yes/no, a model proposal, or an arbitrary name.
        action = next((name for name in self._ACTIONS if re.search(rf"\b{name}\b", value)), None)
        if not action:
            if "일시 정지" in intent: action = "pause"
            elif "연결 해제" in intent: action = "disconnect"
            elif "다시 시작" in intent or "재개" in intent: action = "resume"
        capability = None
        for ident, words in {
            "google-drive-read": ("drive", "드라이브"),
            "google-calendar-create": ("calendar", "캘린더", "일정"),
            "builtin-mcp-read": ("mcp",),
        }.items():
            if any(word in value for word in words): capability = ident; break
        if not action or not capability:
            raise SettingsError("변경할 검토된 연결과 pause, disconnect, resume 중 하나를 정확히 요청하세요.")
        return capability, action

    def _preview(self, row):
        return {key: row[key] for key in ("id", "target", "action", "before", "after", "effect", "recovery", "digest", "expires_at", "state")}

    def _audit(self, row, terminal, error_class=None):
        audit = self.store.config("settings_audit", [])
        audit = audit if isinstance(audit, list) else []
        event = {"at": self.now(), "draft_ref": row["id"], "target": row["target"],
                 "before": row["before"], "after": row["after"], "terminal": terminal}
        if error_class: event["error_class"] = error_class
        self.store.put("settings_audit", [*audit, event][-100:])

    def draft(self, owner, channel, intent):
        if not isinstance(owner, str) or not owner or not isinstance(channel, str) or not channel:
            raise SettingsError("설정 요청의 소유자와 채널을 확인하세요.")
        target, action = self._intent(intent)
        current = next(item for item in self.registry.list() if item["id"] == target)
        if action == "resume" and set(current.get("grant", [])) != set(current["scopes"]):
            raise SettingsError("이미 승인된 검토 capability만 다시 시작할 수 있습니다. 로컬 Connections에서 다시 연결하세요.")
        if action in ("pause", "disconnect") and current["state"] != "enabled":
            raise SettingsError("현재 enable된 검토 capability만 이 변경을 초안으로 만들 수 있습니다.")
        change = {"target": target, "action": action, "before": current["state"], "after": self._ACTIONS[action],
                  "effect": f"{target} 상태를 {self._ACTIONS[action]}로 변경", "recovery": self._recovery_label(target, self._ACTIONS[action])}
        ident = secrets.token_urlsafe(9)
        row = {"id": ident, "owner": owner, "channel": channel, **change, "digest": self._digest(change),
               "created_at": self.now(), "expires_at": self.now() + self.TTL_SECONDS, "state": "awaiting-confirmation"}
        rows = self._drafts(); rows[ident] = row; self._put_drafts(rows)
        self._audit(row, "drafted")
        return {"state": "awaiting-confirmation", "preview": self._preview(row),
                "response": f"변경 초안 {ident}을 만들었습니다. Confirm {ident}로 한 번만 확인하세요."}

    def _owned(self, owner, channel, draft_id):
        row = self._drafts().get(draft_id)
        if not row or row.get("owner") != owner or row.get("channel") != channel:
            raise SettingsError("확인할 설정 초안을 찾지 못했습니다.")
        return row

    def confirm(self, owner, channel, draft_id, digest):
        if not isinstance(draft_id, str) or not isinstance(digest, str):
            raise SettingsError("초안 ID와 정확한 확인 정보를 제공하세요.")
        row = self._owned(owner, channel, draft_id)
        if not secrets.compare_digest(row.get("digest", ""), digest):
            raise SettingsError("설정 초안 확인 정보가 일치하지 않습니다.")
        if row["state"] == "applied": return {"state": "applied", "result": row["result"], "idempotent": True}
        if row["state"] != "awaiting-confirmation": raise SettingsError("이 설정 초안은 더 이상 확인할 수 없습니다.")
        if self.now() > row["expires_at"]:
            row["state"] = "expired"; rows = self._drafts(); rows[draft_id] = row; self._put_drafts(rows); self._audit(row, "expired", "expired")
            raise SettingsError("설정 초안이 만료되었습니다. 새 초안을 만드세요.")
        current = next(item for item in self.registry.list() if item["id"] == row["target"])
        if current["state"] != row["before"]:
            row["state"] = "failed"; rows = self._drafts(); rows[draft_id] = row; self._put_drafts(rows); self._audit(row, "failed", "stale-state")
            raise SettingsError("설정 상태가 바뀌었습니다. 새 초안을 확인하세요.")
        try:
            scopes = tuple(current["scopes"]) if row["after"] == "enabled" else ()
            applied = self.registry.transition(row["target"], row["after"], scopes)
        except ValueError as exc:
            row["state"] = "failed"; rows = self._drafts(); rows[draft_id] = row; self._put_drafts(rows); self._audit(row, "failed", "lifecycle-rejected")
            raise SettingsError("검토된 lifecycle 변경을 적용하지 못했습니다. 복구 경로를 확인하세요.") from exc
        row["state"] = "applied"; row["result"] = {"target": applied["id"], "state": applied["state"], "recovery": row["recovery"]}
        rows = self._drafts(); rows[draft_id] = row; self._put_drafts(rows); self._audit(row, "applied")
        return {"state": "applied", "result": row["result"], "idempotent": False}

    def cancel(self, owner, channel, draft_id):
        row = self._owned(owner, channel, draft_id)
        if row["state"] == "canceled": return {"state": "canceled", "idempotent": True}
        if row["state"] != "awaiting-confirmation": raise SettingsError("이 설정 초안은 취소할 수 없습니다.")
        row["state"] = "canceled"; rows = self._drafts(); rows[draft_id] = row; self._put_drafts(rows); self._audit(row, "canceled")
        return {"state": "canceled", "idempotent": False}

    def recovery(self, owner, subject):
        if not isinstance(owner, str) or not owner or not isinstance(subject, str):
            raise SettingsError("복구할 검토 capability를 선택하세요.")
        item = next((row for row in self.registry.list() if row["id"] == subject), None)
        if not item: raise SettingsError("복구할 검토 capability를 선택하세요.")
        return {"state": "recovery", "target": item["id"], "action": self._recovery_label(item["id"], item["state"])}

    def handle_text(self, owner, channel, text):
        if not isinstance(text, str): raise SettingsError("설정 요청을 확인하세요.")
        value = text.strip()
        match = re.fullmatch(r"(?:confirm|확인)\s+([A-Za-z0-9_-]+)", value, re.I)
        if match:
            row = self._owned(owner, channel, match.group(1))
            return self.confirm(owner, channel, row["id"], row["digest"])
        match = re.fullmatch(r"(?:cancel|취소)\s+([A-Za-z0-9_-]+)", value, re.I)
        if match: return self.cancel(owner, channel, match.group(1))
        if value.lower() in ("settings", "/settings", "무엇이 연결되어 있어?", "무엇을 바꿀 수 있어?") or "상태 보여" in value:
            return self.read(owner)
        if "어떻게 복구" in value:
            target, _ = self._intent(value + " resume")
            return self.recovery(owner, target)
        return self.draft(owner, channel, value)
