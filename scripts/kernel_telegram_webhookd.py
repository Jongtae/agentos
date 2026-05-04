#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from kernel.capability_substrate import _build_telegram_config
from kernel.capability_substrate import _manifest_path
from kernel.capability_substrate import _utc_now
from kernel.capability_substrate import is_telegram_chat_allowed
from kernel.intent_dispatch import build_intent_dispatch_report


WEBHOOK_SCHEMA = "agentos-telegram-webhookd.v1"
WEBHOOK_MANIFEST = "latest-telegram-webhookd.json"
WEBHOOK_OFFSET = "latest-telegram-webhookd-offset.json"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return str(path)


def _normalize_update(update: dict) -> dict:
    message = update.get("message") if isinstance(update.get("message"), dict) else {}
    if not message and isinstance(update.get("edited_message"), dict):
        message = update.get("edited_message") or {}
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    text = str(message.get("text", "") or "").strip()
    return {
        "update_id": str(update.get("update_id", "")).strip(),
        "message_id": str(message.get("message_id", "")).strip(),
        "chat_id": str(chat.get("id", "")).strip(),
        "text": text,
        "date": message.get("date", ""),
    }


def build_webhook_payload(
    workspace_dir: str | Path,
    update: dict,
    *,
    send_reply: bool = True,
    session_id: str = "",
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    config = _build_telegram_config(workspace)
    normalized = _normalize_update(update if isinstance(update, dict) else {})
    allowed_chat_ids = list(config.get("allowed_chat_ids") or [])
    offset_path = _manifest_path(workspace, WEBHOOK_OFFSET)
    previous_offset = str(_read_json(offset_path).get("last_update_id", "")).strip()
    duplicate = bool(
        previous_offset.isdigit()
        and normalized.get("update_id", "").isdigit()
        and int(normalized["update_id"]) <= int(previous_offset)
    )

    payload = {
        "schema_version": WEBHOOK_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "telegram",
        "capability": "telegram_webhookd",
        "transport": {
            "mode": "webhook",
            "api_base_url": str(config.get("api_base_url", "https://api.telegram.org")).rstrip("/"),
            "bot_token_configured": bool(config.get("bot_token_configured", False)),
            "allowed_chat_configured": bool(allowed_chat_ids),
            "telegram_secret_source": str(config.get("telegram_secret_source", "none")),
        },
        "telegram_webhook_update_received": bool(normalized.get("update_id") and normalized.get("chat_id")),
        "telegram_webhook_duplicate": duplicate,
        "telegram_chat_rejected": False,
        "telegram_webhook_message_routed": False,
        "telegram_webhook_search_success": False,
        "telegram_reply_sent": False,
        "telegram_update_offset_persisted": False,
        "telegram_update": normalized,
        "intent_dispatch": {},
        "research_brief": {},
        "proof": {"ok": False, "reason": "", "session_id": session_id},
        "summary": {},
        "artifacts": {},
    }

    if duplicate:
        payload["proof"]["reason"] = "telegram_webhook_duplicate"
    elif not payload["telegram_webhook_update_received"] or not normalized.get("text"):
        payload["proof"]["reason"] = "telegram_webhook_update_invalid"
    elif not is_telegram_chat_allowed(str(normalized.get("chat_id", "")), allowed_chat_ids):
        payload["telegram_chat_rejected"] = True
        payload["proof"]["reason"] = "telegram_chat_rejected"
    else:
        request_id = f"telegram-webhook-{normalized.get('update_id')}"
        dispatch = build_intent_dispatch_report(
            workspace,
            source="telegram",
            message_text=str(normalized.get("text", "")),
            chat_id=str(normalized.get("chat_id", "")),
            request_id=request_id,
            message_id=str(normalized.get("message_id", "")),
            session_id=session_id,
            send_reply=send_reply,
            write_manifest=write_manifest,
        )
        brief = dict(dispatch.get("research_brief") or {})
        payload["intent_dispatch"] = dispatch
        payload["research_brief"] = brief
        payload["telegram_webhook_message_routed"] = bool(dispatch.get("proof", {}).get("ok", False))
        payload["telegram_webhook_search_success"] = bool(dispatch.get("web_search_used", False) and brief.get("internal_web_query_success", False))
        payload["telegram_reply_sent"] = bool(dispatch.get("telegram_reply_sent", False))
        if not payload["telegram_webhook_message_routed"]:
            payload["proof"]["reason"] = str(dispatch.get("proof", {}).get("reason", "")) or "telegram_message_routing_failure"
        elif dispatch.get("web_search_used", False) and not payload["telegram_webhook_search_success"]:
            payload["proof"]["reason"] = "internal_web_query_failure"
        elif send_reply and not payload["telegram_reply_sent"]:
            payload["proof"]["reason"] = "telegram_send_failure"
        else:
            payload["proof"]["ok"] = True

    if normalized.get("update_id") and write_manifest:
        offset_payload = {
            "schema_version": "agentos-telegram-webhookd-offset.v1",
            "updated_at_utc": _utc_now(),
            "last_update_id": normalized.get("update_id", ""),
        }
        payload["artifacts"]["latest_telegram_webhookd_offset_json"] = _write_json(offset_path, offset_payload)
        payload["telegram_update_offset_persisted"] = offset_path.is_file() and offset_path.stat().st_size > 0

    payload["summary"] = {
        "telegram_webhook_update_received": bool(payload["telegram_webhook_update_received"]),
        "telegram_webhook_message_routed": bool(payload["telegram_webhook_message_routed"]),
        "telegram_webhook_search_success": bool(payload["telegram_webhook_search_success"]),
        "telegram_reply_sent": bool(payload["telegram_reply_sent"]),
        "telegram_update_offset_persisted": bool(payload["telegram_update_offset_persisted"]),
        "failure_class": "" if payload["proof"].get("ok", False) else str(payload["proof"].get("reason", "")),
    }
    if write_manifest:
        payload["artifacts"]["latest_telegram_webhookd_manifest_json"] = _write_json(
            _manifest_path(workspace, WEBHOOK_MANIFEST),
            payload,
        )
    return payload


def serve(
    workspace_dir: str | Path,
    *,
    host: str,
    port: int,
    path: str,
    secret: str,
    send_reply: bool,
    session_id: str,
) -> None:
    workspace = Path(workspace_dir).resolve()
    webhook_path = path if path.startswith("/") else f"/{path}"

    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path in {"/health", "/ready"}:
                self._send_json(200, {"ok": True, "schema_version": WEBHOOK_SCHEMA, "path": webhook_path})
                return
            self._send_json(404, {"ok": False, "reason": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != webhook_path:
                self._send_json(404, {"ok": False, "reason": "not_found"})
                return
            if secret:
                supplied = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
                if supplied != secret:
                    self._send_json(403, {"ok": False, "reason": "telegram_webhook_secret_mismatch"})
                    return
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))
            try:
                update = json.loads(raw.decode("utf-8", errors="replace") or "{}")
            except Exception:
                update = {}
            payload = build_webhook_payload(
                workspace,
                update,
                send_reply=send_reply,
                session_id=session_id,
                write_manifest=True,
            )
            # Telegram should not retry operator-level failures forever. Keep the
            # truthful failure class in the artifact and acknowledge delivery.
            self._send_json(200, {"ok": True, "proof_ok": bool(payload.get("proof", {}).get("ok")), "summary": payload.get("summary", {})})

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(json.dumps({"ok": True, "schema_version": WEBHOOK_SCHEMA, "listening": f"{host}:{port}", "path": webhook_path}, ensure_ascii=True), flush=True)
    server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AgentOS Telegram webhook receiver daemon.")
    parser.add_argument("--workspace", default=os.environ.get("AGENTOS_DEFAULT_WORKSPACE", "/home/ubuntu/agentos-ws"))
    parser.add_argument("--host", default=os.environ.get("AGENTOS_TELEGRAM_WEBHOOK_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("AGENTOS_TELEGRAM_WEBHOOK_PORT", "8790")))
    parser.add_argument("--path", default=os.environ.get("AGENTOS_TELEGRAM_WEBHOOK_PATH", "/telegram/webhook"))
    parser.add_argument("--secret", default=os.environ.get("AGENTOS_TELEGRAM_WEBHOOK_SECRET", ""))
    parser.add_argument("--session-id", default="")
    parser.add_argument("--no-send", action="store_true")
    parser.add_argument("--update-json", default="", help="Process one update JSON file and exit.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.update_json:
        update = json.loads(Path(args.update_json).read_text(encoding="utf-8"))
        payload = build_webhook_payload(
            args.workspace,
            update,
            send_reply=not args.no_send,
            session_id=args.session_id,
        )
        text = json.dumps(payload, ensure_ascii=True)
        if args.json:
            print(text)
        else:
            print(f"telegram webhookd: {'PASS' if payload.get('proof', {}).get('ok') else 'FAIL'}")
        return 0 if payload.get("proof", {}).get("ok", False) else 1

    serve(
        args.workspace,
        host=args.host,
        port=args.port,
        path=args.path,
        secret=args.secret,
        send_reply=not args.no_send,
        session_id=args.session_id,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
