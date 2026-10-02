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
a digest-bound draft; nothing applies until the owner confirms it (the
적용 button on Telegram or the web, a plain yes typed in the same conversation
judged by the DecisionEngine - OWNER-SETTINGS-02 #855 - or the HTTP
``confirm``).  No command is ever shown to the owner (#855).  Values are fixed-choice or a validated time zone; a credential,
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
CATEGORY_LABELS = {"connections": "외부 연결", "current_context": "현재 맥락", "judgment_ai": "판단 AI", "main_ai": "기본 AI",
                   "owner_model": "알아 두기", "family": "가족 비서", "skills": "스킬"}
SETTINGS = {"current_context": ("enabled", "timezone"), "judgment_ai": ("mode", "model"), "main_ai": ("route", "model"),
            # #805 owner-model upkeep: its pause switch and rolling 24-hour call cap.
            "owner_model": ("enabled", "daily_calls"),
            # #912: a family member's own agent, created by asking the assistant (FAMILY-02 #897).
            # #934: the owner shares (and stops sharing) one signed-in site with one of them.
            "family": ("add", "share_site", "unshare_site"),
            # #961: optional skill know-how: the switch, adding one pinned GitHub skill, removing one.
            "skills": ("enabled", "add", "remove")}
SETTING_LABELS = {"enabled": "사용", "timezone": "시간대", "mode": "방식", "model": "모델", "route": "경로",
                  "daily_calls": "하루 판단 횟수", "add": "새로 만들기", "share_site": "로그인 공유", "unshare_site": "공유 그만",
                  "remove": "빼기"}
#: #934: the value of a share is "<family assistant>|<site>"; a stop may name the site alone.
FAMILY_SHARE_SETTINGS = frozenset({("family", "share_site"), ("family", "unshare_site")})
FAMILY_SHARE_NOTE = "비밀번호는 넘기지 않고 지금 로그인된 세션만 전달해요. 내 세션이 갱신되면 따라가고, 결제는 계정 주인만 할 수 있어요."
VALUE_LABELS = {"on": "켜짐", "off": "꺼짐", "follow_main": "기본 AI 따라가기", "explicit": "따로 지정"}
JUDGMENT_MODE_LABELS = {"off": "사용 안 함"}
UNKNOWN_SETTING_MESSAGE = ("대화로 바꿀 수 있는 설정이 아닙니다. 현재 맥락(enabled, timezone), 판단 AI(mode, model), "
                           "기본 AI(route, model), 알아 두기(enabled, daily_calls), 가족 비서(add, share_site, unshare_site), 스킬(enabled, add, remove)만 바꿀 수 있습니다. API 키, 토큰, 로그인, 엔드포인트는 설정 화면에서 직접 입력하세요.")
CREDENTIAL_VALUE_MESSAGE = ("자격 증명처럼 보이는 값은 대화로 설정하지 않습니다. API 키, 토큰, 로그인은 설정 화면에서 직접 입력하세요. "
                            "아무것도 바꾸지 않았습니다.")
UNAVAILABLE_MESSAGE = "이 설정의 현재 상태를 확인하지 못해 바꾸지 않았습니다. 설정 화면에서 확인하세요."
MAX_VALUE_CHARS = 200
MAX_REASON_CHARS = 300
#: #814 review: settings whose setter probes or qualifies an AI (seconds to minutes).
#: With a follow-up channel they are applied off the caller's thread, one at a time.
SLOW_SETTINGS = frozenset({("judgment_ai", "model"), ("main_ai", "route"), ("main_ai", "model"),
                           # #961: adding a skill downloads and inspects one pinned GitHub folder.
                           ("skills", "add")})
#: #961: what adding a skill does, shown with the draft.
SKILL_ADD_NOTE = ("확인하면 고정된 커밋에서 그 폴더만 받아 라이선스와 내용을 확인한 뒤 추가해요(브랜치 이름은 이 초안을 만들 때 "
                  "GitHub에 물어 커밋으로 고정했어요). 스크립트·훅은 실행하지 않고, 라이선스를 확인할 수 없거나 실행 파일이 "
                  "필요한 스킬은 추가하지 않아요. 스킬은 방법 안내일 뿐 권한이 아니에요.")
#: How long a confirmation waits for another apply of the same category (#814 review).
APPLY_WAIT_SECONDS = 5
#: #814 review: a draft left ``applying`` by a restart: its setter may or may not have committed.
IN_DOUBT_MESSAGE = ("설정 변경이 적용 중에 중단되어 적용됐는지 확인하지 못했어요. 현재 값을 확인해 주세요. "
                    "필요하면 다시 요청하세요: {effect}")
#: #814 review P1: text confirmation needs a message the owner typed, not one AgentOS ran.
NOT_OWNER_TYPED_MESSAGE = ("설정 변경은 소유자가 직접 보낸 메시지나 확인 버튼으로만 확인하거나 취소할 수 있습니다. "
                           "아무것도 바꾸지 않았습니다.")
BUSY_MESSAGE = "다른 설정을 적용하는 중입니다. 끝난 뒤 다시 확인하세요. 아직 아무것도 바꾸지 않았습니다."
STALE_MESSAGE = "초안을 만든 뒤 설정이 바뀌었거나 이 값을 더 이상 고를 수 없어 적용하지 않았습니다. 다시 요청하세요."
WORKER_START_MESSAGE = "설정을 적용하는 작업을 시작하지 못했습니다. 아무것도 바꾸지 않았습니다."
FOLLOW_REQUESTED_MESSAGE = "판단 AI를 기본 AI 따라가기로 요청했어요. 확인이 끝나면 적용돼요."
#: #912: the family setup runs in the background; its link and outcome follow on Telegram.
FAMILY_REQUESTED_MESSAGE = "가족 비서를 만드는 중이에요. 준비되면 가족에게 보낼 설정 링크를 여기로 보내 드릴게요."


def canonical_timezone(name):
    """The IANA spelling of a zone ``valid_timezone`` accepted (#814 review): ``asia/seoul`` -> ``Asia/Seoul``."""
    from zoneinfo import available_timezones
    if not name:
        return name
    return next((zone for zone in sorted(available_timezones()) if zone.lower() == name.lower()), name)


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
        # One confirmation moves a draft out of awaiting at a time (exactly once);
        # every read-modify-write of the draft rows holds it (re-entrant).
        self._confirming = threading.RLock()
        # #814 review P2-3: slow applies run in order on one background worker.
        self._queue, self._worker_running = [], False
        self.thread = None
        # #814 review: one compare-and-apply per category at a time (the stale ``before``
        # check and the setter under one lock, handed to the off-thread apply).
        self._category_locks = {name: threading.Lock() for name in SETTINGS}
        # Drafts this process is applying; any other ``applying`` draft is in doubt.
        self._in_flight = set()

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
        self.reconcile()
        rows = self._rows() if category in (None, "connections") else []
        result = {"state": "read", "category": category or "all", "connections": rows,
                  "response": self._summary(rows), "activity": self._activity()}
        if self.service is None:
            return result
        # #814: the owner settings, redacted: values, labels and allowed choices only.
        settings = {name: self._snapshot(name) for name in SETTINGS if category in (None, name)}
        lines = [self._category_line(name, row) for name, row in settings.items()]
        lines += [IN_DOUBT_MESSAGE.format(effect=row["effect"]) for row in self.in_doubt()
                  if category in (None, row.get("category"))]
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

    def _owner_model(self):
        from .owner_model import MAX_DAILY_CALLS
        settings = self.service.owner_model.settings()
        enabled = "on" if settings.get("enabled") else "off"
        cap = str(settings.get("daily_calls"))
        return {"enabled": self._row("enabled", enabled, VALUE_LABELS[enabled], self._options(("on", "off"))),
                "daily_calls": self._row("daily_calls", cap, f"{cap}회", None,
                                         format=f"0~{MAX_DAILY_CALLS} 사이의 정수(24시간 동안 판단 AI 호출 수)")}

    def _family(self):
        """#912: the family members' agents on this Mac; ``add`` takes the new one's display name.

        #934: ``share_site`` / ``unshare_site`` carry the current shares (names
        only) and, for the model to match the owner's words against, the
        sites the owner is signed in to and the family assistants' names.
        """
        from . import family_share
        # #957: every other instance on this Mac (the owner's main one included), never this one, each with
        # its bot's display name and the state its own store reports.
        others = family_share.instances(own=self.store.root)
        assistants = {name: {**row, "state_label": family_share.STATE_LABELS.get(row.get("state"), "")}
                      for name, row in others.items()}
        shares = family_share.listing(self.store, others)
        shared = ", ".join(f"{row['label']}: {row['site']}" + ("" if row["delivered"] else " (전달 대기)") for row in shares) or "없음"
        signed_in = self._signed_in_sites()
        family = ", ".join(family_share.describe(name, row) for name, row in others.items() if not row.get("main")) or "없음"
        return {"add": self._row("add", "", family, None,
                                 format="새 가족 비서의 텔레그램 이름(예: 아내 비서)",
                                 note="내 AI 구독을 함께 쓰는 가족 전용 비서를 만들고, 가족에게 보낼 설정 링크를 텔레그램으로 드립니다."),
                "share_site": self._row("share_site", "", shared, None, format="비서 이름|사이트 주소(예: <비서 이름>|example.com)",
                                        note=FAMILY_SHARE_NOTE, assistants=assistants, signed_in_sites=signed_in,
                                        shared=[{"instance": row["instance"], "site": row["site"]} for row in shares],
                                        received_sites=sorted(family_share.received(self.store))),
                "unshare_site": self._row("unshare_site", "", shared, None,
                                          format="사이트 주소, 또는 비서 이름|사이트 주소(예: example.com)",
                                          shared=[{"instance": row["instance"], "site": row["site"]} for row in shares])}

    def _skills(self):
        """#961: the switch, and the installed skills for ``add`` / ``remove`` (names and pinned sources only)."""
        status = self.service.skills_status()
        enabled = "on" if status.get("enabled") else "off"
        rows = status.get("skills") or []
        listed = ", ".join(f"{row['skill']} ({row['source']}{'' if row.get('enabled') else ', 꺼짐'})" for row in rows) or "없음"
        removable = [row["skill"].split("/", 1)[1] for row in rows if not row["skill"].startswith("agentos/")]
        return {"enabled": self._row("enabled", enabled, VALUE_LABELS[enabled], self._options(("on", "off"))),
                "add": self._row("add", "", listed, None, format="GitHub 스킬 폴더 주소(예: github.com/<owner>/<repo>/tree/<브랜치 또는 커밋>/<폴더>)",
                                 note=SKILL_ADD_NOTE),
                "remove": self._row("remove", "", ", ".join(removable) or "없음", None, format="설치된 스킬 이름",
                                    installed=removable)}

    def _signed_in_sites(self):
        """The sites the owner's browser is signed in to, names only, from the profile's non-blocking view."""
        profile = getattr(self.service, "browser_profile", None)
        view = getattr(profile, "_jar_view", None)
        if not callable(view):
            return []
        try:
            _state, sessions = view()
        except Exception:
            return []
        return [row["site"] for row in sessions if isinstance(row, dict) and row.get("site")]

    @staticmethod
    def _share_value(setting, value, row):
        """``"<instance>|<site>"`` for a share or a stop (#934), resolved and normalized, or ``SettingsError``."""
        from . import family_share
        # Without a "|" the value is the site: a stop may name it alone; a share still needs the assistant.
        who, _sep, where = value.rpartition("|")
        try:
            site = family_share.normalize_site(where)
        except ValueError as exc:
            raise SettingsError(str(exc)) from None
        shared = row[setting].get("shared") or []
        if setting == "unshare_site" and not who.strip():
            holders = [item["instance"] for item in shared if item["site"] == site]
            if not holders:
                raise SettingsError(f"{site} 로그인 세션은 공유하고 있지 않아요. 바꿀 것이 없어요.")
            if len(holders) > 1:
                raise SettingsError(f"{site}은(는) 여러 비서({', '.join(holders)})와 공유 중이에요. 어느 비서인지 이름을 주세요.")
            return f"{holders[0]}|{site}"
        if setting == "share_site" and site in (row["share_site"].get("received_sites") or ()):
            # Review P1-1: a session received from the owner is not this instance's to pass on.
            raise SettingsError(family_share.NOT_YOURS_TEXT.format(site=site))
        try:
            instance = family_share.resolve_instance(who, row["share_site"].get("assistants") or {})
        except ValueError as exc:
            raise SettingsError(str(exc)) from None
        already = any(item["instance"] == instance and item["site"] == site for item in shared)
        if setting == "share_site" and already:
            raise SettingsError(f"{instance} 비서와 {site} 로그인 세션을 이미 공유하고 있어요. 바꿀 것이 없어요.")
        if setting == "unshare_site" and not already:
            raise SettingsError(f"{instance} 비서와 {site} 로그인 세션을 공유하고 있지 않아요. 바꿀 것이 없어요.")
        return f"{instance}|{site}"

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
        if not isinstance(category, str) or not isinstance(setting, str):
            raise SettingsError(UNKNOWN_SETTING_MESSAGE)
        if category == "connections":
            raise SettingsError(RETIRED_CONTROL_MESSAGE)
        if category not in SETTINGS or setting not in SETTINGS[category] or self.service is None:
            raise SettingsError(UNKNOWN_SETTING_MESSAGE)
        if isinstance(value, bool) and setting == "enabled":
            value = "on" if value else "off"
        if isinstance(value, int) and not isinstance(value, bool) and setting == "daily_calls":
            value = str(value)
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
                return valid_timezone(canonical_timezone(value)), row
            except ValueError as exc:
                raise SettingsError(f"{exc} 아무것도 바꾸지 않았습니다.") from None
        if (category, setting) == ("family", "add"):
            # A display name only: letters and spaces, 1-64 characters, no control characters.
            name = " ".join(value.split())
            if not name or len(name) > 64 or any(ord(char) < 32 for char in value):
                raise SettingsError("가족 비서 이름을 1~64자로 주세요. 아무것도 만들지 않았습니다.")
            # SKILL-MANAGE-01 (#962): a repeated request never makes a second assistant of the same name.
            # Only an already paired one blocks; an unfinished setup is reused by the setter itself.
            from . import family_share
            same = [(instance, item) for instance, item in (row["share_site"].get("assistants") or {}).items()
                    if " ".join(str(item.get("name") or "").split()).lower() == name.lower() and item.get("state") == "paired"]
            if same:
                listed = ", ".join(family_share.describe(instance, item) for instance, item in same)
                raise SettingsError(f"'{name}' 비서는 이미 있어요: {listed}. 새로 만들지 않았어요. "
                                    "다른 가족의 비서라면 다른 이름으로 다시 요청해 주세요.")
            return name, row
        if (category, setting) in FAMILY_SHARE_SETTINGS:
            return self._share_value(setting, value, row), row
        if (category, setting) in (("skills", "add"), ("skills", "remove")):
            from .skills import SkillError
            try:
                return self.service.skill_setting_value(setting, value), row
            except SkillError as exc:
                raise SettingsError(f"{exc} 아무것도 바꾸지 않았습니다.") from None
        if setting == "daily_calls":
            from .owner_model import MAX_DAILY_CALLS
            if not value.isascii() or not value.isdigit() or not 0 <= int(value) <= MAX_DAILY_CALLS:
                raise SettingsError(f"하루 판단 횟수는 0~{MAX_DAILY_CALLS} 사이의 정수로 주세요. 아무것도 바꾸지 않았습니다.")
            return str(int(value)), row
        allowed = [option["value"] for option in row[setting]["options"] or ()]
        if value not in allowed:
            listed = ", ".join(allowed) or "지금은 없음"
            raise SettingsError(f"{CATEGORY_LABELS[category]} {SETTING_LABELS[setting]}은(는) 다음 중 하나만 고를 수 있습니다: "
                                f"{listed}. 아무것도 바꾸지 않았습니다.")
        return value, row

    def _describe(self, category, setting, value, row):
        options = {option["value"]: option["label"] for option in row[setting].get("options") or ()}
        if setting == "daily_calls":
            return f"{value}회"
        return options.get(value) or VALUE_LABELS.get(value) or value or "설정 안 함"

    @staticmethod
    def _digest(row):
        body = {key: row.get(key) for key in ("id", "owner", "channel", "category", "setting", "before", "after", "expires_at")}
        return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def propose(self, owner, channel, category, setting, value, reason=None, work_id=None):
        """A digest-bound draft of one owner setting change; applies nothing (#814)."""
        if not isinstance(owner, str) or not owner or not isinstance(channel, str) or not channel:
            raise SettingsError("설정 요청의 소유자와 채널을 확인하세요.")
        if reason is not None and not isinstance(reason, str):
            raise SettingsError("변경 이유는 짧은 글자로 주세요. 아무것도 바꾸지 않았습니다.")
        after, row = self._normalized(category, setting, value)
        before = row[setting]["value"]
        if after == before:
            raise SettingsError(f"{CATEGORY_LABELS[category]} {SETTING_LABELS[setting]}은(는) 이미 "
                                f"{self._describe(category, setting, after, row)}입니다. 바꿀 것이 없습니다.")
        if (category, setting) == ("family", "add"):
            summary = f"가족 비서 '{after}'를 만듭니다"
        elif (category, setting) == ("skills", "add"):
            from .skills import parse_source
            source = parse_source(after)
            name = source["path"].rstrip("/").split("/")[-1]
            replacing = any(row["skill"].split("/", 1)[-1] == name and not row["skill"].startswith("agentos/")
                            for row in self.service.skills_status().get("skills") or ())
            summary = (f"스킬을 {'이 버전으로 바꿉니다' if replacing else '추가합니다'}: {source['repo']}의 {source['path']} "
                       f"(커밋 {source['revision'][:7]})")
        elif (category, setting) == ("skills", "remove"):
            summary = f"스킬 '{after}'를 뺍니다"
        elif (category, setting) in FAMILY_SHARE_SETTINGS:
            from . import family_share
            instance, _sep, site = after.partition("|")
            label = family_share.names(row["share_site"].get("assistants") or {}).get(instance, instance)
            summary = (f"'{label}' 비서에 {site} 로그인 세션을 공유합니다" if setting == "share_site"
                       else f"'{label}' 비서의 {site} 로그인 공유를 그만둡니다")
        else:
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
        """Run the service's own setter; ``applied``, or ``requested`` when it only queued the change."""
        category, setting, after = row["category"], row["setting"], row["after"]
        if category == "current_context":
            self.service.set_current_context({"enabled": after == "on"} if setting == "enabled" else {"timezone": after})
        elif (category, setting) in FAMILY_SHARE_SETTINGS:
            # #934: the push (or the revocation) runs now over loopback; the receipt's text is the answer.
            instance, _sep, site = after.partition("|")
            receipt = (self.service.share_site(instance, site) if setting == "share_site"
                       else self.service.unshare_site(instance, site))
            self.__dict__.setdefault("_apply_text", {})[row["id"]] = (receipt or {}).get("response")
        elif category == "family":
            # #912: runs in the background; the link, then the outcome, follow in the confirming conversation.
            notify = self.__dict__.get("_family_notify", {}).pop(row["id"], None)
            self.service.start_family_setup(after, notify=notify)
            return "requested"
        elif category == "skills":
            # #961: the service's own setters; adding returns the installed identity as the answer.
            receipt = self.service.apply_skill_setting(setting, after)
            self.__dict__.setdefault("_apply_text", {})[row["id"]] = (receipt or {}).get("response")
        elif category == "owner_model":
            self.service.owner_model_request({"operation": "set", **({"enabled": after == "on"} if setting == "enabled"
                                                                      else {"daily_calls": int(after)})})
        elif (category, setting) == ("judgment_ai", "mode"):
            self.service.activate_decision_route({"transport": after})
            # #814 review P2-1: following the Main AI queues a background qualification
            # (#685/#760); the Judgment AI changes only when it passes.
            if after == "follow_main":
                return "requested"
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
        return "applied"

    def _settle(self, draft_id, state, terminal, error_class=None, **fields):
        with self._confirming:
            rows = self._drafts()
            row = rows.get(draft_id)
            if row:
                row.update(state=state, **fields)
                rows[draft_id] = row
                self._put_drafts(rows)
                if terminal:
                    self._audit(row, terminal, error_class)
            return row

    def reconcile(self):
        """#814 review: a draft ``applying`` that this process is not applying was cut off (a restart).

        Its setter may or may not have committed, so it is settled ``unknown``
        (audited ``interrupted``), never ``applied`` or ``failed``, and never
        re-applied; ``read`` tells the owner to check the current value.  Run
        at service start, on every read and before every confirm.
        """
        with self._confirming:
            for row in list(self._drafts().values()):
                if isinstance(row, dict) and row.get("state") == "applying" and row.get("id") not in self._in_flight:
                    self._settle(row["id"], "unknown", "unknown", "interrupted", settled_at=self.now())

    def in_doubt(self, within=24 * 3600):
        """Drafts whose outcome a restart left unknown in the last day, oldest first."""
        now = self.now()
        rows = [row for row in self._drafts().values() if isinstance(row, dict) and row.get("state") == "unknown"
                and now - float(row.get("settled_at") or 0) <= within]
        return sorted(rows, key=lambda row: row.get("settled_at") or 0)

    def _finish(self, row):
        """Apply one checked draft and settle it; the owner-facing result, or ``SettingsError``."""
        try:
            outcome = self._apply(row)
        except Exception as exc:
            self._settle(row["id"], "failed", "failed", type(exc).__name__)
            message = str(exc) if isinstance(exc, ValueError) and str(exc) else "설정을 적용하지 못했습니다."
            raise SettingsError(message) from None
        self._settle(row["id"], outcome, outcome)
        response = ((FAMILY_REQUESTED_MESSAGE if row.get("category") == "family" else FOLLOW_REQUESTED_MESSAGE)
                    if outcome == "requested" else f"{row['effect']}(으)로 바꿨습니다.")
        # #934: a share's receipt says what was delivered (names and counts); it replaces the generic line.
        response = self.__dict__.get("_apply_text", {}).pop(row["id"], None) or response
        return {"state": outcome, "draft_id": row["id"], "target": row["target"], "before": row["before"],
                "after": row["after"], "response": response}

    def _admit(self, row, digest):
        """Check one draft is still confirmable and move it to ``applying``, in flight (exactly once)."""
        with self._confirming:
            row = self._drafts().get(row["id"]) or row
            if row.get("state") in ("applied", "requested"):
                raise SettingsError("이미 적용한 설정 초안입니다.")
            if row.get("state") == "unknown":
                raise SettingsError(IN_DOUBT_MESSAGE.format(effect=row["effect"]))
            if row.get("state") != "awaiting-confirmation":
                raise SettingsError("이 설정 초안은 더 이상 확인할 수 없습니다. 필요하면 다시 요청하세요.")
            if not hmac.compare_digest(str(row.get("digest") or ""), digest) or self._digest(row) != row.get("digest"):
                raise SettingsError("확인 정보가 이 설정 초안과 맞지 않아 적용하지 않았습니다.")
            if self.now() > float(row.get("expires_at") or 0):
                self._settle(row["id"], "expired", "expired")
                raise SettingsError("설정 초안이 만료되어 적용하지 않았습니다. 필요하면 다시 요청하세요.")
            row = self._settle(row["id"], "applying", None, applying_at=self.now())
            self._in_flight.add(row["id"])
            return row

    def _checked_apply(self, row):
        """Compare-and-apply (#814 review): re-check ``before``, then the setter.  The caller holds the category lock."""
        try:
            try:
                after, current = self._normalized(row["category"], row["setting"], row["after"])
                if after != row["after"] or current[row["setting"]]["value"] != row["before"]:
                    raise SettingsError(STALE_MESSAGE)
            except Exception as exc:
                self._settle(row["id"], "failed", "failed", type(exc).__name__)
                message = str(exc) if isinstance(exc, ValueError) and str(exc) else "설정을 적용하지 못했습니다."
                raise SettingsError(message) from None
            return self._finish(row)
        finally:
            with self._confirming:
                self._in_flight.discard(row["id"])

    def _worker(self):
        """The one background worker: queued slow drafts, in order, each compare-and-apply under its category lock."""
        while True:
            with self._confirming:
                if not self._queue:
                    self._worker_running = False
                    return
                row, notify = self._queue.pop(0)
            with self._category_locks[row["category"]]:
                try:
                    text = self._checked_apply(row)["response"]
                except Exception as exc:
                    text = f"{row['effect']} 변경을 적용하지 못했습니다: {exc if isinstance(exc, SettingsError) else '오류'}"
            try:
                notify(text)
            except Exception:
                pass

    def _enqueue(self, row, notify):
        """Queue one admitted slow draft on the background worker; start it when idle."""
        with self._confirming:
            self._queue.append((row, notify))
            start = not self._worker_running
            self._worker_running = True
        if start:
            thread = threading.Thread(target=self._worker, daemon=True, name="agentos-settings-apply")
            try:
                thread.start()
            except Exception:
                # #814 review P3: nothing ran; every queued draft fails and nothing stays in flight.
                with self._confirming:
                    items, self._queue, self._worker_running = self._queue, [], False
                    for item, _notify in items:
                        self._in_flight.discard(item["id"])
                        self._settle(item["id"], "failed", "failed", "worker-start")
                raise SettingsError(WORKER_START_MESSAGE) from None
            self.thread = thread
        return {"state": "applying", "draft_id": row["id"], "target": row["target"], "before": row["before"],
                "after": row["after"],
                "response": f"{row['effect']} 변경을 확인하고 있어요. 끝나면 결과를 알려드릴게요."}

    def _confirm_owner_setting(self, row, digest, notify=None):
        """Apply one awaiting draft exactly once, after re-checking it is still current (#814).

        With ``notify`` (a follow-up to the confirming conversation) a slow
        setter is queued on the one background worker and ``notify`` gets its
        result; the caller is answered at once.  Otherwise the stale check and
        the setter run here under the category lock.
        """
        if notify is not None and (row.get("category"), row.get("setting")) in SLOW_SETTINGS:
            return self._enqueue(self._admit(row, digest), notify)
        if row.get("category") == "family":
            # #913 review P2-1: the family setup's link and outcome go to the conversation that confirmed it.
            self.__dict__.setdefault("_family_notify", {})[row.get("id")] = notify
        category_lock = self._category_locks.get(row.get("category"))
        if category_lock is None or not category_lock.acquire(timeout=APPLY_WAIT_SECONDS):
            raise SettingsError(BUSY_MESSAGE)
        try:
            return self._checked_apply(self._admit(row, digest))
        finally:
            category_lock.release()

    def pending_drafts(self):
        """Every draft still awaiting the owner (not expired), oldest first."""
        now = self.now()
        rows = [row for row in self._drafts().values() if isinstance(row, dict)
                and row.get("state") == "awaiting-confirmation" and float(row.get("expires_at") or 0) >= now]
        return sorted(rows, key=lambda row: (row.get("created_at") or 0, row["id"]))

    def pending_for_conversation(self, owner, channel):
        """This conversation's drafts still awaiting the owner, oldest first (#855)."""
        return [row for row in self.pending_drafts() if row.get("owner") == owner and row.get("channel") == channel]

    def settle_pending(self, owner, channel, rows, apply, notify=None):
        """Confirm (``apply``) or cancel every offered draft of one conversation; one owner-facing result (#855).

        The same path as the 적용 / 바꾸지 않음 buttons: each draft goes through
        ``confirm`` (digest, TTL, stale check, audit) or ``cancel``.
        """
        lines, states = [], []
        for row in rows:
            try:
                result = (self.confirm(owner, channel, row["id"], row.get("digest", ""), notify) if apply
                          else self.cancel(owner, channel, row["id"]))
                states.append(result.get("state"))
                lines.append(result.get("response") or "처리했습니다.")
            except SettingsError as exc:
                states.append("failed")
                lines.append(f"{row['effect']}: {exc}")
        return {"state": states[0] if len(states) == 1 else ("mixed" if len(set(states)) > 1 else states[0]),
                "drafts": [row["id"] for row in rows], "response": "\n".join(lines)}

    def pending_for_work(self, work_id):
        """This Work's drafts still awaiting the owner, oldest first (#814)."""
        return [row for row in self.pending_drafts() if row.get("work_id") == work_id]

    @staticmethod
    def drafts_digest(rows):
        """The fingerprint of exactly these drafts (ids and digests) a confirmation message offers (#814)."""
        body = [[row["id"], row.get("digest")] for row in rows]
        return hashlib.sha256(json.dumps(body).encode()).hexdigest()

    @staticmethod
    def confirmation_text(rows):
        lines = ["대화에서 요청한 설정 변경입니다. 적용을 누르거나 대화에서 그렇게 하라고 답하기 전에는 아무것도 바뀌지 않습니다."]
        for row in rows:
            lines.append(f"- {row['effect']}" + (f" ({row['note']})" if row.get("note") else ""))
            if row.get("reason"):
                lines.append(f"  이유: {row['reason']}")
        return "\n".join(lines)

    def work_tools(self, owner, channel, work_id, telegram=False):
        """``settings_read`` / ``settings_change`` bound to one Work (#814).

        A change is only a draft bound to this conversation; the model gets
        no digest and no way to confirm.  The owner confirms in the same
        conversation: the 적용 button, or a plain yes (#855).  ``telegram`` is
        kept for callers; the wording no longer differs by channel.
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
            how = (f"소유자에게 이 대화에서 확인을 요청합니다: 적용 버튼을 누르거나 그렇게 하라고 답하면 적용되고, "
                   f"아니라고 답하면 취소됩니다({minutes}분 안에).")
            return {**{key: value for key, value in draft.items() if key not in ("digest", "response", "expires_at")},
                    "next_step": f"{draft['summary']} 변경은 소유자 확인을 기다립니다. {how} 확인 전에는 아무것도 바뀌지 않았습니다."}
        return call

    def _audit(self, row, terminal, error_class=None):
        with self._confirming:
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

    def confirm(self, owner, channel, draft_id, digest, notify=None):
        """A draft made by the retired control plane can never apply."""
        if not isinstance(draft_id, str) or not isinstance(digest, str):
            raise SettingsError("초안 ID와 정확한 확인 정보를 제공하세요.")
        row = self._owned(owner, channel, draft_id)
        if row.get("category") in SETTINGS and self.service is not None:
            self.reconcile()
            return self._confirm_owner_setting(row, digest, notify)
        with self._confirming:
            row = self._drafts().get(draft_id) or row
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

    def handle_text(self, owner, channel, text, owner_typed=True, notify=None):
        """``owner_typed`` (#814 review P1): False for a message AgentOS ran on the owner's
        behalf (a preparation goal, a continuation, a retry); it can never confirm or cancel.

        The ``확인 <id>`` / ``취소 <id>`` forms are kept for compatibility only;
        they are never shown to the owner (#855)."""
        if not isinstance(text, str): raise SettingsError("설정 요청을 확인하세요.")
        value = text.strip()
        match = re.fullmatch(r"(?:confirm|확인)\s+([A-Za-z0-9_-]+)", value, re.I)
        if match:
            if owner_typed is not True: raise SettingsError(NOT_OWNER_TYPED_MESSAGE)
            row = self._owned(owner, channel, match.group(1))
            return self.confirm(owner, channel, row["id"], row.get("digest", ""), notify)
        match = re.fullmatch(r"(?:cancel|취소)\s+([A-Za-z0-9_-]+)", value, re.I)
        if match:
            if owner_typed is not True: raise SettingsError(NOT_OWNER_TYPED_MESSAGE)
            return self.cancel(owner, channel, match.group(1))
        if value.lower() in ("settings", "/settings", "무엇이 연결되어 있어?", "무엇을 바꿀 수 있어?") or "상태 보여" in value:
            return self.read(owner)
        if "어떻게 복구" in value:
            # Every row already carries its one truthful next action; no
            # keyword table guesses which service the owner meant.
            return self.read(owner)
        return self.draft(owner, channel, value)
