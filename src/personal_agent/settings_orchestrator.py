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

OWNER-SETTINGS-01 #814: with the owning service supplied, the same object also
reads and changes a few owner settings that already exist in the service -
current context (on/off, time zone), the Judgment AI (mode, model) and the
Main AI (route, model) - through the service's own setters only.  A change is
a digest-bound draft; nothing applies until the owner confirms it (Telegram
button, ``/settings 확인 <id>`` in the same conversation, or the HTTP
``confirm``).  Values are fixed-choice or a validated time zone; a credential,
key, token or endpoint is never accepted (those stay in Settings).
"""
import hashlib
import hmac
import json
import re
import threading
import time
import uuid


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


#: #814: owner-visible names of the categories and settings the conversation may read/change.
CATEGORY_LABELS = {"connections": "외부 연결", "current_context": "현재 맥락", "judgment_ai": "판단 AI", "main_ai": "기본 AI"}
SETTINGS = {"current_context": ("enabled", "timezone"), "judgment_ai": ("mode", "model"), "main_ai": ("route", "model")}
SETTING_LABELS = {"enabled": "사용", "timezone": "시간대", "mode": "방식", "model": "모델", "route": "경로"}
VALUE_LABELS = {"on": "켜짐", "off": "꺼짐", "follow_main": "기본 AI 따라가기", "explicit": "따로 지정"}
JUDGMENT_MODE_LABELS = {"off": "사용 안 함"}
UNKNOWN_SETTING_MESSAGE = ("대화로 바꿀 수 있는 설정이 아닙니다. 현재 맥락(enabled, timezone), 판단 AI(mode, model), "
                           "기본 AI(route, model)만 바꿀 수 있습니다. API 키, 토큰, 로그인, 엔드포인트는 설정 화면에서 직접 입력하세요.")
CREDENTIAL_VALUE_MESSAGE = ("자격 증명처럼 보이는 값은 대화로 설정하지 않습니다. API 키, 토큰, 로그인은 설정 화면에서 직접 입력하세요. "
                            "아무것도 바꾸지 않았습니다.")
UNAVAILABLE_MESSAGE = "이 설정의 현재 상태를 확인하지 못해 바꾸지 않았습니다. 설정 화면에서 확인하세요."
MAX_VALUE_CHARS = 200
MAX_REASON_CHARS = 300


class SettingsOrchestrator:
    TTL_SECONDS = 10 * 60
    _CATEGORIES = ("connections",)

    def __init__(self, store, now=time.time, connections=None, service=None):
        self.store, self.now = store, now
        # A callable returning owner-visible connection rows derived from the
        # authoritative boundaries.  With none supplied there are no
        # connections to report, never a guessed one.
        self.connections = connections or (lambda: [])
        # #814: the owning service whose existing setters are the only mutation
        # path for the owner settings below; None offers only ``connections``.
        self.service = service
        if service is not None:
            self._CATEGORIES = ("connections", *SETTINGS)
        # One confirmation moves a draft out of awaiting at a time (exactly once).
        self._confirming = threading.Lock()

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
        return "\n".join(f"{row['service']} · {row['state_label']}"
                         + ("" if row["state"] == "connected" else f" · {row['next_action']}") for row in rows)

    def read(self, owner, category=None):
        if not isinstance(owner, str) or not owner:
            raise SettingsError("설정 소유자를 확인하세요.")
        if category is not None and category not in self._CATEGORIES:
            raise SettingsError("검토된 설정 범주를 선택하세요.")
        rows = self._rows() if category in (None, "connections") else []
        result = {"state": "read", "category": category or "all", "connections": rows,
                  "response": self._summary(rows), "activity": self._activity()}
        if self.service is None:
            return result
        # #814: the owner settings, redacted: values, labels and allowed choices only.
        settings = {name: self._snapshot(name) for name in SETTINGS if category in (None, name)}
        lines = [self._category_line(name, row) for name, row in settings.items()]
        if category in (None, "connections"):
            lines.append(f"{CATEGORY_LABELS['connections']}:\n{result['response']}" if category is None else result["response"])
        return {**result, "settings": settings, "response": "\n".join(lines)}

    # -- #814 owner settings ------------------------------------------------------
    def _snapshot(self, category):
        """``{setting: {value, value_label, label, options}}`` of one category, or ``{unavailable}``."""
        try:
            return getattr(self, "_" + category)()
        except Exception:
            return {"unavailable": UNAVAILABLE_MESSAGE}

    @staticmethod
    def _options(values, labels=None):
        return [{"value": value, "label": (labels or {}).get(value) or VALUE_LABELS.get(value) or value} for value in values]

    @staticmethod
    def _row(setting, value, value_label, options, **extra):
        return {"label": SETTING_LABELS[setting], "value": value, "value_label": value_label, "options": options, **extra}

    def _current_context(self):
        settings = self.service.context_observations.settings()
        enabled = "on" if settings.get("enabled") else "off"
        zone = settings.get("timezone") or ""
        return {"enabled": self._row("enabled", enabled, VALUE_LABELS[enabled], self._options(("on", "off"))),
                "timezone": self._row("timezone", zone, zone or "설정 안 함(이 컴퓨터의 시간대)", None,
                                      format="IANA 시간대 이름(예: Asia/Seoul)")}

    def _model_lists(self):
        rows = self.store.config("decision_model_lists", {})
        return rows if isinstance(rows, dict) else {}

    def _judgment_ai(self):
        from .decision_routes import ROUTE_NAMES, known_models
        status = self.service.decision_routes.status()
        active, mode = status.get("active") or {}, status.get("mode")
        route = active.get("engine") if active.get("transport") == "subscription_cli" else (
            active.get("provider") if active.get("transport") == "direct_api" else "")
        model = active.get("requested_model") or ""
        models = known_models(route, self._model_lists()) if route else []
        return {"mode": self._row("mode", mode, JUDGMENT_MODE_LABELS.get(mode) or VALUE_LABELS.get(mode, mode or "-"),
                                  self._options(("follow_main", "off"), JUDGMENT_MODE_LABELS)),
                "model": self._row("model", model, model or "기본 모델", self._options(models),
                                   route=ROUTE_NAMES.get(route, route or "-"),
                                   note="모델을 바꾸면 기본 AI 따라가기 대신 따로 지정됩니다." if mode == "follow_main" else ""),
                "effective": (status.get("effective") or {}).get("text") or ""}

    @staticmethod
    def _ready_route(row):
        """A Main AI route already connected and checked: the only switch targets (#814)."""
        if (row.get("check") or {}).get("state") != "ok":
            return False
        if row.get("kind") == "subscription":
            return bool(row.get("installed")) and (row.get("login") or {}).get("state") != "signed-out"
        return bool((row.get("key") or {}).get("saved"))

    def _main_ai(self):
        from .decision_routes import known_models
        from .main_ai import API_ROUTES, SUBSCRIPTION_ROUTES
        status = self.service.main_ai.status()
        current, routes = status.get("current") or "", status.get("routes") or []
        names = {row["id"]: row["name"] for row in routes}
        options = [{"value": row["id"], "label": row["name"], "destination": row.get("destination") or ""}
                   for row in routes if self._ready_route(row)]
        row = next((item for item in routes if item["id"] == current), {})
        model = row.get("model") or ""
        selectable = (current in SUBSCRIPTION_ROUTES and row.get("model_selectable")) or current in API_ROUTES
        models = known_models(current, self._model_lists()) if selectable else []
        return {"route": self._row("route", current, names.get(current) or ("기타 연결" if current else "없음"), options,
                                   note="기본 AI를 바꾸면 이후 작업 내용이 새 경로의 목적지로 전송됩니다. 항상 확인 후 적용합니다."),
                "model": self._row("model", model, model or "기본 모델", self._options(models))}

    @staticmethod
    def _category_line(category, row):
        if row.get("unavailable"):
            return f"{CATEGORY_LABELS[category]} · {row['unavailable']}"
        parts = [f"{item['label']}: {item['value_label']}" for item in row.values() if isinstance(item, dict)]
        line = f"{CATEGORY_LABELS[category]} · " + " · ".join(parts)
        return line + (f" ({row['effective']})" if row.get("effective") else "")

    def _normalized(self, category, setting, value):
        """The canonical allowed value, or a fail-closed ``SettingsError`` (#814)."""
        if category == "connections":
            raise SettingsError(RETIRED_CONTROL_MESSAGE)
        if category not in SETTINGS or setting not in SETTINGS[category] or self.service is None:
            raise SettingsError(UNKNOWN_SETTING_MESSAGE)
        if isinstance(value, bool) and (category, setting) == ("current_context", "enabled"):
            value = "on" if value else "off"
        if not isinstance(value, str) or len(value) > MAX_VALUE_CHARS:
            raise SettingsError("바꿀 값을 짧은 글자로 주세요. 아무것도 바꾸지 않았습니다.")
        value = value.strip()
        from .current_context import redact_known_secrets
        if redact_known_secrets(self.store, value) != value:
            raise SettingsError(CREDENTIAL_VALUE_MESSAGE)
        row = self._snapshot(category)
        if row.get("unavailable"):
            raise SettingsError(row["unavailable"])
        if (category, setting) == ("current_context", "timezone"):
            from .context_observations import valid_timezone
            try:
                return valid_timezone(value), row
            except ValueError as exc:
                raise SettingsError(f"{exc} 아무것도 바꾸지 않았습니다.") from None
        allowed = [option["value"] for option in row[setting]["options"] or ()]
        if value not in allowed:
            listed = ", ".join(allowed) or "지금은 없음"
            raise SettingsError(f"{CATEGORY_LABELS[category]} {SETTING_LABELS[setting]}은(는) 다음 중 하나만 고를 수 있습니다: "
                                f"{listed}. 아무것도 바꾸지 않았습니다.")
        return value, row

    def _describe(self, category, setting, value, row):
        options = {option["value"]: option["label"] for option in row[setting].get("options") or ()}
        return options.get(value) or VALUE_LABELS.get(value) or value or "설정 안 함"

    @staticmethod
    def _digest(row):
        body = {key: row.get(key) for key in ("id", "owner", "channel", "category", "setting", "before", "after", "expires_at")}
        return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def propose(self, owner, channel, category, setting, value, reason=None, work_id=None):
        """A digest-bound draft of one owner setting change; applies nothing (#814)."""
        if not isinstance(owner, str) or not owner or not isinstance(channel, str) or not channel:
            raise SettingsError("설정 요청의 소유자와 채널을 확인하세요.")
        after, row = self._normalized(category, setting, value)
        before = row[setting]["value"]
        if after == before:
            raise SettingsError(f"{CATEGORY_LABELS[category]} {SETTING_LABELS[setting]}은(는) 이미 "
                                f"{self._describe(category, setting, after, row)}입니다. 바꿀 것이 없습니다.")
        summary = (f"{CATEGORY_LABELS[category]} {SETTING_LABELS[setting]}: {self._describe(category, setting, before, row)}"
                   f" → {self._describe(category, setting, after, row)}")
        note = row[setting].get("note") or ""
        if (category, setting) == ("main_ai", "route"):
            destination = next((option.get("destination") for option in row["route"]["options"] if option["value"] == after), "")
            note = f"이후 작업 내용이 {destination}(으)로 전송됩니다." if destination else note
        reason = reason.strip()[:MAX_REASON_CHARS] if isinstance(reason, str) else ""
        from .current_context import redact_known_secrets
        now = self.now()
        draft = {"id": uuid.uuid4().hex[:12], "owner": owner, "channel": channel, "category": category, "setting": setting,
                 "target": f"{category}.{setting}", "before": before, "after": after, "effect": summary, "note": note,
                 "reason": redact_known_secrets(self.store, reason), "work_id": work_id if isinstance(work_id, str) else None,
                 "created_at": now, "expires_at": now + self.TTL_SECONDS, "state": "awaiting-confirmation"}
        draft["digest"] = self._digest(draft)
        with self._confirming:
            rows = self._drafts()
            rows[draft["id"]] = draft
            self._put_drafts(rows)
        self._audit(draft, "drafted")
        return {"state": "awaiting-confirmation", "draft_id": draft["id"], "digest": draft["digest"],
                "category": category, "setting": setting, "before": before, "after": after, "summary": summary,
                "note": note, "expires_at": draft["expires_at"], "requires_owner_confirmation": True, "applied": False,
                "response": summary + (f"\n{note}" if note else "") + "\n확인해야 적용됩니다. 아직 아무것도 바꾸지 않았습니다."}

    def _apply(self, row):
        category, setting, after = row["category"], row["setting"], row["after"]
        if category == "current_context":
            self.service.set_current_context({"enabled": after == "on"} if setting == "enabled" else {"timezone": after})
        elif (category, setting) == ("judgment_ai", "mode"):
            self.service.activate_decision_route({"transport": after})
        elif category == "judgment_ai":
            active = self.service.decision_routes.status().get("active") or {}
            if active.get("transport") == "subscription_cli":
                self.service.activate_decision_route({"transport": "subscription_cli", "engine": active.get("engine"),
                                                      "model_policy": "explicit", "model": after})
            else:
                self.service.activate_decision_route({"transport": "direct_api", "model": after})
        elif setting == "route":
            self.service.activate_main_ai({"route": after})
        else:
            self.service.activate_main_ai({"route": self.service.main_ai.current(), "model": after})

    def _settle(self, draft_id, state, terminal, error_class=None):
        rows = self._drafts()
        row = rows.get(draft_id)
        if row:
            row["state"] = state
            rows[draft_id] = row
            self._put_drafts(rows)
            if terminal:
                self._audit(row, terminal, error_class)
        return row

    def _confirm_owner_setting(self, row, digest):
        """Apply one awaiting draft exactly once, after re-checking it is still current (#814)."""
        with self._confirming:
            row = self._drafts().get(row["id"]) or row
            if row.get("state") == "applied":
                raise SettingsError("이미 적용한 설정 초안입니다.")
            if row.get("state") != "awaiting-confirmation":
                raise SettingsError("이 설정 초안은 더 이상 확인할 수 없습니다. 필요하면 다시 요청하세요.")
            if not hmac.compare_digest(str(row.get("digest") or ""), digest) or self._digest(row) != row.get("digest"):
                raise SettingsError("확인 정보가 이 설정 초안과 맞지 않아 적용하지 않았습니다.")
            if self.now() > float(row.get("expires_at") or 0):
                self._settle(row["id"], "expired", "expired")
                raise SettingsError("설정 초안이 만료되어 적용하지 않았습니다. 필요하면 다시 요청하세요.")
            self._settle(row["id"], "applying", None)
        try:
            after, current = self._normalized(row["category"], row["setting"], row["after"])
            if after != row["after"] or current[row["setting"]]["value"] != row["before"]:
                raise SettingsError("초안을 만든 뒤 설정이 바뀌었거나 이 값을 더 이상 고를 수 없어 적용하지 않았습니다. 다시 요청하세요.")
            self._apply(row)
        except Exception as exc:
            self._settle(row["id"], "failed", "failed", type(exc).__name__)
            message = str(exc) if isinstance(exc, ValueError) and str(exc) else "설정을 적용하지 못했습니다."
            raise SettingsError(message) from None
        self._settle(row["id"], "applied", "applied")
        return {"state": "applied", "draft_id": row["id"], "target": row["target"], "before": row["before"],
                "after": row["after"], "response": f"{row['effect']}(으)로 바꿨습니다."}

    def pending_for_work(self, work_id):
        """This Work's drafts still awaiting the owner, oldest first (#814)."""
        now = self.now()
        rows = [row for row in self._drafts().values() if isinstance(row, dict) and row.get("work_id") == work_id
                and row.get("state") == "awaiting-confirmation" and float(row.get("expires_at") or 0) >= now]
        return sorted(rows, key=lambda row: (row.get("created_at") or 0, row["id"]))

    @staticmethod
    def drafts_digest(rows):
        """The fingerprint of exactly these drafts (ids and digests) a confirmation message offers (#814)."""
        body = [[row["id"], row.get("digest")] for row in rows]
        return hashlib.sha256(json.dumps(body).encode()).hexdigest()

    @staticmethod
    def confirmation_text(rows):
        lines = ["대화에서 요청한 설정 변경입니다. 적용을 누르기 전에는 아무것도 바뀌지 않습니다."]
        for row in rows:
            lines.append(f"- {row['effect']}" + (f" ({row['note']})" if row.get("note") else ""))
            if row.get("reason"):
                lines.append(f"  이유: {row['reason']}")
        return "\n".join(lines)

    def work_tools(self, owner, channel, work_id, telegram=False):
        """``settings_read`` / ``settings_change`` bound to one Work (#814).

        A change is only a draft bound to this conversation; the model gets
        no digest and no way to confirm.  The owner confirms in the same
        conversation: the Telegram button, or ``/settings 확인 <id>``.
        """
        def call(action, args):
            args = args if isinstance(args, dict) else {}
            if action == "settings_read":
                category = args.get("category") or None
                result = self.read(owner, category)
                return {key: result[key] for key in ("category", "settings", "connections", "response") if key in result}
            draft = self.propose(owner, channel, args.get("category"), args.get("setting"), args.get("value"),
                                 args.get("reason"), work_id)
            minutes = self.TTL_SECONDS // 60
            how = (f"Telegram으로 보내는 확인 메시지의 적용 버튼을 누르면 적용됩니다({minutes}분 안에)." if telegram else
                   f"이 대화에 /settings 확인 {draft['draft_id']} 를 보내면 적용됩니다({minutes}분 안에). "
                   f"취소는 /settings 취소 {draft['draft_id']} 입니다.")
            return {**{key: value for key, value in draft.items() if key not in ("digest", "response", "expires_at")},
                    "next_step": f"{draft['summary']} 변경은 소유자 확인을 기다립니다. {how} 확인 전에는 아무것도 바뀌지 않았습니다."}
        return call

    def _audit(self, row, terminal, error_class=None):
        audit = self.store.config("settings_audit", [])
        audit = audit if isinstance(audit, list) else []
        event = {"at": self.now(), "draft_ref": row["id"], "target": row.get("target"),
                 "before": row.get("before"), "after": row.get("after"), "terminal": terminal}
        if error_class: event["error_class"] = error_class
        self.store.put("settings_audit", [*audit, event][-100:])

    def draft(self, owner, channel, intent):
        """No lifecycle draft exists any more: say so and change nothing.

        #814: a structured ``{category, setting, value}`` intent drafts one
        owner setting change (``propose``); free text is still not parsed.
        """
        if not isinstance(owner, str) or not owner or not isinstance(channel, str) or not channel:
            raise SettingsError("설정 요청의 소유자와 채널을 확인하세요.")
        if isinstance(intent, dict) and self.service is not None:
            return self.propose(owner, channel, intent.get("category"), intent.get("setting"), intent.get("value"),
                                intent.get("reason"))
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
        if row.get("category") in SETTINGS and self.service is not None:
            return self._confirm_owner_setting(row, digest)
        if row.get("state") == "awaiting-confirmation":
            row["state"] = "failed"
            rows = self._drafts(); rows[draft_id] = row; self._put_drafts(rows)
            self._audit(row, "failed", "retired-control")
        raise SettingsError(RETIRED_CONTROL_MESSAGE)

    def cancel(self, owner, channel, draft_id):
        with self._confirming:
            row = self._owned(owner, channel, draft_id)
            if row["state"] == "canceled": return {"state": "canceled", "idempotent": True}
            if row["state"] != "awaiting-confirmation": raise SettingsError("이 설정 초안은 취소할 수 없습니다.")
            row["state"] = "canceled"; rows = self._drafts(); rows[draft_id] = row; self._put_drafts(rows); self._audit(row, "canceled")
        return {"state": "canceled", "idempotent": False, "response": "설정 변경을 취소했습니다. 아무것도 바꾸지 않았습니다."}

    def recovery(self, owner, subject):
        if not isinstance(owner, str) or not owner or not isinstance(subject, str):
            raise SettingsError("복구할 연결을 선택하세요.")
        rows = {str(row.get("id")): row for row in self.connections() or [] if isinstance(row, dict)}
        row = rows.get(subject)
        if not row:
            raise SettingsError("복구할 연결을 선택하세요.")
        return {"state": "recovery", "target": subject, "action": next_action(row)}

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
            # Every row already carries its one truthful next action; no
            # keyword table guesses which service the owner meant.
            return self.read(owner)
        return self.draft(owner, channel, value)
