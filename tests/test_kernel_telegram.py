from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from unittest.mock import patch

from kernel.capability_substrate import (
    TELEGRAM_LIVE_LOOP_SCHEMA,
    TELEGRAM_REPLY_SCHEMA,
    TELEGRAM_WEB_EXECUTION_SCHEMA,
    TELEGRAM_PROOF_SCHEMA,
    TELEGRAM_ROUTING_SCHEMA,
    TELEGRAM_STATUS_SCHEMA,
    _build_telegram_config,
    build_telegram_reply_surface_report,
    build_telegram_web_execution_report,
    build_telegram_request_routing_contract,
    build_telegram_proof_baseline_report,
    build_telegram_status_report,
    build_telegram_live_loop_report,
    is_telegram_chat_allowed,
)
from scripts.kernel_telegram_contract import validate_payload as validate_telegram_contract
from scripts.kernel_telegram_reply_surface import validate_payload as validate_telegram_reply
from scripts.kernel_telegram_routing_contract import validate_payload as validate_telegram_routing
from scripts.kernel_telegram_status import validate_payload as validate_telegram_status
from scripts.kernel_telegram_proof_baseline import validate_payload as validate_telegram_proof
from scripts.kernel_telegram_live_loop import validate_payload as validate_telegram_live_loop
from scripts.kernel_telegram_setup import (
    TELEGRAM_SETUP_SCHEMA,
    build_telegram_setup_report,
    serve_telegram_setup_page,
    validate_payload as validate_telegram_setup,
)
from scripts.kernel_telegram_webhookd import WEBHOOK_SCHEMA, build_webhook_payload


ROOT_DIR = Path(__file__).resolve().parents[1]


class _WebHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/plain":
            body = b"hello from agentos"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/app":
            body = (
                b"<html><head>"
                + (b"<script>console.log('x')</script>" * 9)
                + b"</head><body><h1>app shell</h1></body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class _TelegramApiHandler(BaseHTTPRequestHandler):
    sent_payloads: list[dict] = []
    updates: list[dict] = []
    get_me_ok: bool = True
    get_updates_conflict_once: bool = False
    delete_webhook_count: int = 0

    def do_GET(self) -> None:  # noqa: N802
        if "/getMe" in self.path:
            body = json.dumps(
                {
                    "ok": self.__class__.get_me_ok,
                    "result": {"id": 42, "is_bot": True, "username": "agentos_test_bot"} if self.__class__.get_me_ok else {},
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if "/deleteWebhook" in self.path:
            self.__class__.delete_webhook_count += 1
            body = json.dumps({"ok": True, "result": True}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if "/getUpdates" not in self.path:
            self.send_response(404)
            self.end_headers()
            return
        if self.__class__.get_updates_conflict_once:
            self.__class__.get_updates_conflict_once = False
            body = json.dumps({"ok": False, "description": "Conflict: webhook is active"}).encode("utf-8")
            self.send_response(409)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = json.dumps({"ok": True, "result": self.__class__.updates}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = {}
        self.__class__.sent_payloads.append({"path": self.path, "payload": payload})
        body = json.dumps({"ok": True, "result": {"message_id": 1}}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class TelegramCapabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        _TelegramApiHandler.sent_payloads = []
        _TelegramApiHandler.updates = []
        _TelegramApiHandler.get_me_ok = True
        _TelegramApiHandler.get_updates_conflict_once = False
        _TelegramApiHandler.delete_webhook_count = 0

    def test_allowed_chat_policy_default_and_explicit_policy(self) -> None:
        self.assertTrue(is_telegram_chat_allowed("123", []))
        self.assertTrue(is_telegram_chat_allowed("123", ["123", "456"]))
        self.assertFalse(is_telegram_chat_allowed("123", ["456"]))

    def test_polling_defaults_are_clamped_from_spec_and_env(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            spec = workspace / "spec.yaml"
            spec.write_text(
                "telegram:\n  polling:\n    interval_sec: 15\n",
                encoding="utf-8",
            )

            env_file = workspace / "env"
            env_file.write_text("", encoding="utf-8")
            with patch.dict(os.environ, {"AGENTOS_ENV_FILE": str(env_file)}, clear=False):
                os.environ.pop("AGENTOS_TELEGRAM_POLL_INTERVAL_SEC", None)
                default_from_spec = _build_telegram_config(workspace)
                self.assertEqual(default_from_spec["polling_interval_sec"], 15)
                self.assertEqual(default_from_spec["polling_interval_source"], "spec")

            with patch.dict(
                os.environ,
                {
                    "AGENTOS_ENV_FILE": str(env_file),
                    "AGENTOS_TELEGRAM_POLL_INTERVAL_SEC": "9",
                },
                clear=False,
            ):
                from_spec = _build_telegram_config(workspace)
                self.assertEqual(from_spec["polling_interval_sec"], 9)
                self.assertEqual(from_spec["polling_interval_source"], "env:AGENTOS_TELEGRAM_POLL_INTERVAL_SEC")

    def test_status_and_proof_reports_write_latest_artifacts_and_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            status_payload = build_telegram_status_report(workspace)
            routing_payload = build_telegram_request_routing_contract(
                workspace,
                message_text="search agentos and summarize",
                chat_id="1001",
                request_id="req-123",
            )
            with patch("kernel.capability_substrate.build_web_access_report") as mock_web_access:
                mock_web_access.return_value = {
                    "schema_version": "agentos-web-access.v1",
                    "capability": "web_access",
                    "native_handled": True,
                    "escalated_handled": False,
                    "unsupported_or_deferred": False,
                    "proof": {
                        "ok": True,
                        "selected_path": "native_fetch_parse",
                        "text_preview": "search results preview",
                        "content_type": "text/plain",
                    },
                    "document_class": "text",
                    "artifacts": {},
                }
                proof_payload = build_telegram_proof_baseline_report(
                    workspace,
                    message_text="search agentos and summarize",
                    chat_id="1001",
                    request_id="req-123",
                    reply_sent=True,
                )

            status_path = Path(status_payload["artifacts"]["latest_telegram_status_manifest_json"])
            routing_path = Path(routing_payload["artifacts"]["latest_telegram_request_routing_manifest_json"])
            proof_path = Path(proof_payload["artifacts"]["latest_telegram_proof_baseline_manifest_json"])
            self.assertTrue(status_path.exists())
            self.assertTrue(routing_path.exists())
            self.assertTrue(proof_path.exists())
            self.assertIn("latest_telegram_status_manifest_json", proof_payload["artifacts"])
            self.assertIn("latest_telegram_ingress_contract_manifest_json", proof_payload["artifacts"])
            self.assertIn("latest_telegram_request_routing_manifest_json", proof_payload["artifacts"])
            self.assertIn("latest_telegram_web_execution_manifest_json", proof_payload["artifacts"])

            status_manifest = json.loads(status_path.read_text(encoding="utf-8"))
            routing_manifest = json.loads(routing_path.read_text(encoding="utf-8"))
            proof_manifest = json.loads(proof_path.read_text(encoding="utf-8"))
            self.assertEqual(status_manifest["schema_version"], TELEGRAM_STATUS_SCHEMA)
            self.assertEqual(status_manifest["capability"], "telegram_status")
            self.assertEqual(routing_manifest["schema_version"], TELEGRAM_ROUTING_SCHEMA)
            self.assertEqual(routing_manifest["capability"], "telegram_request_routing_contract")
            self.assertEqual(proof_manifest["schema_version"], TELEGRAM_PROOF_SCHEMA)
            self.assertEqual(proof_manifest["capability"], "telegram_proof_baseline")
            self.assertEqual(validate_telegram_status(status_manifest), [])
            self.assertEqual(validate_telegram_routing(routing_manifest), [])
            self.assertEqual(validate_telegram_proof(proof_manifest), [])
            self.assertTrue(proof_manifest["summary"]["telegram_ingress_received"])
            self.assertEqual(proof_manifest["summary"]["telegram_request_id"], "req-123")
            self.assertTrue(proof_manifest["summary"]["telegram_request_routed"])
            self.assertTrue(proof_manifest["summary"]["telegram_web_execution_ok"])
            self.assertTrue(proof_manifest["summary"]["telegram_reply_ready"])
            self.assertFalse(proof_manifest["summary"]["telegram_reply_sent"])

    def test_live_loop_polls_routes_sends_and_persists_offset(self) -> None:
        web_server = ThreadingHTTPServer(("127.0.0.1", 0), _WebHandler)
        web_thread = threading.Thread(target=web_server.serve_forever, daemon=True)
        web_thread.start()
        telegram_server = ThreadingHTTPServer(("127.0.0.1", 0), _TelegramApiHandler)
        telegram_thread = threading.Thread(target=telegram_server.serve_forever, daemon=True)
        telegram_thread.start()
        try:
            with tempfile.TemporaryDirectory() as td:
                workspace = Path(td) / "workspace"
                workspace.mkdir(parents=True, exist_ok=True)
                message_url = f"http://127.0.0.1:{web_server.server_port}/plain"
                _TelegramApiHandler.updates = [
                    {
                        "update_id": 77,
                        "message": {
                            "message_id": 5,
                            "date": 1,
                            "chat": {"id": 1001},
                            "text": message_url,
                        },
                    }
                ]
                with patch.dict(
                    os.environ,
                    {
                        "AGENTOS_TELEGRAM_BOT_TOKEN": "live-loop-secret",
                        "AGENTOS_TELEGRAM_API_BASE_URL": f"http://127.0.0.1:{telegram_server.server_port}",
                        "AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS": "1001",
                    },
                    clear=False,
                ):
                    payload = build_telegram_live_loop_report(workspace, once=True, send_reply=True)

                self.assertEqual(payload["schema_version"], TELEGRAM_LIVE_LOOP_SCHEMA)
                self.assertTrue(payload["telegram_polling_attempted"])
                self.assertTrue(payload["telegram_live_update_received"])
                self.assertTrue(payload["telegram_live_message_routed"])
                self.assertTrue(payload["telegram_live_search_success"])
                self.assertTrue(payload["telegram_reply_sent"])
                self.assertTrue(payload["telegram_update_offset_persisted"])
                self.assertEqual(payload["summary"]["failure_class"], "")
                self.assertEqual(validate_telegram_live_loop(payload), [])
                rendered = json.dumps(payload, ensure_ascii=True)
                self.assertNotIn("live-loop-secret", rendered)
                self.assertEqual(len(_TelegramApiHandler.sent_payloads), 1)
                self.assertEqual(_TelegramApiHandler.sent_payloads[0]["path"], "/botlive-loop-secret/sendMessage")
                self.assertEqual(_TelegramApiHandler.sent_payloads[0]["payload"]["chat_id"], "1001")
                offset_path = workspace / "artifacts" / "capability-substrate" / "latest-telegram-live-loop-offset.json"
                self.assertEqual(json.loads(offset_path.read_text(encoding="utf-8"))["last_update_id"], "77")
        finally:
            web_server.shutdown()
            web_server.server_close()
            web_thread.join(timeout=1)
            telegram_server.shutdown()
            telegram_server.server_close()
            telegram_thread.join(timeout=1)

    def test_live_loop_preserves_webhook_conflict_without_deleting_webhook(self) -> None:
        web_server = ThreadingHTTPServer(("127.0.0.1", 0), _WebHandler)
        web_thread = threading.Thread(target=web_server.serve_forever, daemon=True)
        web_thread.start()
        telegram_server = ThreadingHTTPServer(("127.0.0.1", 0), _TelegramApiHandler)
        telegram_thread = threading.Thread(target=telegram_server.serve_forever, daemon=True)
        telegram_thread.start()
        try:
            with tempfile.TemporaryDirectory() as td:
                workspace = Path(td) / "workspace"
                workspace.mkdir(parents=True, exist_ok=True)
                _TelegramApiHandler.get_updates_conflict_once = True
                _TelegramApiHandler.updates = [
                    {
                        "update_id": 89,
                        "message": {
                            "message_id": 7,
                            "date": 1,
                            "chat": {"id": 1001},
                            "text": f"http://127.0.0.1:{web_server.server_port}/plain",
                        },
                    }
                ]
                with patch.dict(
                    os.environ,
                    {
                        "AGENTOS_TELEGRAM_BOT_TOKEN": "conflict-secret",
                        "AGENTOS_TELEGRAM_API_BASE_URL": f"http://127.0.0.1:{telegram_server.server_port}",
                        "AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS": "1001",
                    },
                    clear=False,
                ):
                    payload = build_telegram_live_loop_report(workspace, once=True, send_reply=True)

                self.assertFalse(payload["proof"]["ok"], payload)
                self.assertTrue(payload["transport"]["poll_conflict_detected"])
                self.assertTrue(payload["transport"]["webhook_active"])
                self.assertFalse(payload["transport"]["webhook_clear_attempted"])
                self.assertEqual(_TelegramApiHandler.delete_webhook_count, 0)
                self.assertEqual(payload["summary"]["failure_class"], "telegram_webhook_active")
                self.assertFalse(payload["telegram_reply_sent"])
                self.assertNotIn("conflict-secret", json.dumps(payload, ensure_ascii=True))
        finally:
            web_server.shutdown()
            web_server.server_close()
            web_thread.join(timeout=1)
            telegram_server.shutdown()
            telegram_server.server_close()
            telegram_thread.join(timeout=1)

    def test_live_loop_webhook_transport_does_not_poll(self) -> None:
        telegram_server = ThreadingHTTPServer(("127.0.0.1", 0), _TelegramApiHandler)
        telegram_thread = threading.Thread(target=telegram_server.serve_forever, daemon=True)
        telegram_thread.start()
        try:
            with tempfile.TemporaryDirectory() as td:
                workspace = Path(td) / "workspace"
                workspace.mkdir(parents=True, exist_ok=True)
                with patch.dict(
                    os.environ,
                    {
                        "AGENTOS_TELEGRAM_BOT_TOKEN": "webhook-secret",
                        "AGENTOS_TELEGRAM_API_BASE_URL": f"http://127.0.0.1:{telegram_server.server_port}",
                        "AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS": "1001",
                        "AGENTOS_TELEGRAM_TRANSPORT": "webhook",
                    },
                    clear=False,
                ):
                    payload = build_telegram_live_loop_report(workspace, once=True, send_reply=True)

                self.assertFalse(payload["proof"]["ok"], payload)
                self.assertEqual(payload["transport"]["mode"], "webhook")
                self.assertFalse(payload["telegram_polling_attempted"])
                self.assertEqual(payload["summary"]["failure_class"], "telegram_webhook_transport_active")
                self.assertEqual(_TelegramApiHandler.delete_webhook_count, 0)
        finally:
            telegram_server.shutdown()
            telegram_server.server_close()
            telegram_thread.join(timeout=1)

    def test_live_loop_rejects_disallowed_chat_without_send(self) -> None:
        telegram_server = ThreadingHTTPServer(("127.0.0.1", 0), _TelegramApiHandler)
        telegram_thread = threading.Thread(target=telegram_server.serve_forever, daemon=True)
        telegram_thread.start()
        try:
            with tempfile.TemporaryDirectory() as td:
                workspace = Path(td) / "workspace"
                workspace.mkdir(parents=True, exist_ok=True)
                _TelegramApiHandler.updates = [
                    {
                        "update_id": 88,
                        "message": {
                            "message_id": 6,
                            "date": 1,
                            "chat": {"id": 2002},
                            "text": "https://example.com",
                        },
                    }
                ]
                with patch.dict(
                    os.environ,
                    {
                        "AGENTOS_TELEGRAM_BOT_TOKEN": "reject-secret",
                        "AGENTOS_TELEGRAM_API_BASE_URL": f"http://127.0.0.1:{telegram_server.server_port}",
                        "AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS": "1001",
                    },
                    clear=False,
                ):
                    payload = build_telegram_live_loop_report(workspace, once=True, send_reply=True)

                self.assertTrue(payload["telegram_polling_attempted"])
                self.assertTrue(payload["telegram_live_update_received"])
                self.assertTrue(payload["telegram_chat_rejected"])
                self.assertFalse(payload["telegram_live_message_routed"])
                self.assertFalse(payload["telegram_reply_sent"])
                self.assertEqual(payload["summary"]["failure_class"], "telegram_chat_rejected")
                self.assertEqual(_TelegramApiHandler.sent_payloads, [])
        finally:
            telegram_server.shutdown()
            telegram_server.server_close()
            telegram_thread.join(timeout=1)

    def test_telegram_setup_validates_token_extracts_chat_and_writes_env(self) -> None:
        telegram_server = ThreadingHTTPServer(("127.0.0.1", 0), _TelegramApiHandler)
        telegram_thread = threading.Thread(target=telegram_server.serve_forever, daemon=True)
        telegram_thread.start()
        try:
            with tempfile.TemporaryDirectory() as td:
                workspace = Path(td) / "workspace"
                workspace.mkdir(parents=True, exist_ok=True)
                env_file = Path(td) / "agentos.env"
                _TelegramApiHandler.updates = [
                    {
                        "update_id": 100,
                        "message": {
                            "message_id": 7,
                            "chat": {"id": 1001},
                            "text": "/start",
                        },
                    }
                ]
                payload = build_telegram_setup_report(
                    workspace,
                    env_file=env_file,
                    token="setup-secret-token",
                    api_base_url=f"http://127.0.0.1:{telegram_server.server_port}",
                )

                self.assertEqual(payload["schema_version"], TELEGRAM_SETUP_SCHEMA)
                self.assertTrue(payload["get_me_ok"])
                self.assertTrue(payload["chat_id_auto_detected"])
                self.assertEqual(payload["chat_id"], "1001")
                self.assertTrue(payload["env_written"])
                self.assertTrue(payload["proof"]["ok"])
                self.assertEqual(_TelegramApiHandler.delete_webhook_count, 1)
                self.assertEqual(validate_telegram_setup(payload), [])
                rendered = json.dumps(payload, ensure_ascii=True)
                self.assertNotIn("setup-secret-token", rendered)
                env_text = env_file.read_text(encoding="utf-8")
                self.assertIn('AGENTOS_TELEGRAM_BOT_TOKEN="setup-secret-token"', env_text)
                self.assertIn('AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS="1001"', env_text)
                self.assertEqual(_TelegramApiHandler.delete_webhook_count, 1)
        finally:
            telegram_server.shutdown()
            telegram_server.server_close()
            telegram_thread.join(timeout=1)

    def test_telegram_setup_preserves_active_webhook_during_chat_lookup(self) -> None:
        telegram_server = ThreadingHTTPServer(("127.0.0.1", 0), _TelegramApiHandler)
        telegram_thread = threading.Thread(target=telegram_server.serve_forever, daemon=True)
        telegram_thread.start()
        try:
            with tempfile.TemporaryDirectory() as td:
                workspace = Path(td) / "workspace"
                workspace.mkdir(parents=True, exist_ok=True)
                env_file = Path(td) / "agentos.env"
                _TelegramApiHandler.get_updates_conflict_once = True
                payload = build_telegram_setup_report(
                    workspace,
                    env_file=env_file,
                    token="setup-secret-token",
                    api_base_url=f"http://127.0.0.1:{telegram_server.server_port}",
                )

                self.assertTrue(payload["get_me_ok"])
                self.assertFalse(payload["chat_id_auto_detected"])
                self.assertFalse(payload["env_written"])
                self.assertFalse(payload["proof"]["ok"])
                self.assertTrue(payload["transport"]["poll_conflict_detected"])
                self.assertTrue(payload["transport"]["webhook_active"])
                self.assertEqual(payload["summary"]["failure_class"], "telegram_webhook_active_chat_id_lookup_blocked")
                self.assertEqual(_TelegramApiHandler.delete_webhook_count, 0)
                self.assertEqual(validate_telegram_setup(payload), [])
        finally:
            telegram_server.shutdown()
            telegram_server.server_close()
            telegram_thread.join(timeout=1)

    def test_telegram_setup_manual_chat_fallback_and_invalid_token(self) -> None:
        telegram_server = ThreadingHTTPServer(("127.0.0.1", 0), _TelegramApiHandler)
        telegram_thread = threading.Thread(target=telegram_server.serve_forever, daemon=True)
        telegram_thread.start()
        try:
            with tempfile.TemporaryDirectory() as td:
                workspace = Path(td) / "workspace"
                workspace.mkdir(parents=True, exist_ok=True)
                env_file = Path(td) / "agentos.env"
                _TelegramApiHandler.updates = []
                manual_payload = build_telegram_setup_report(
                    workspace,
                    env_file=env_file,
                    token="manual-secret",
                    chat_id="2002",
                    api_base_url=f"http://127.0.0.1:{telegram_server.server_port}",
                )
                self.assertTrue(manual_payload["get_me_ok"])
                self.assertFalse(manual_payload["chat_id_auto_attempted"])
                self.assertEqual(manual_payload["chat_id"], "2002")
                self.assertTrue(manual_payload["env_written"])
                self.assertEqual(_TelegramApiHandler.delete_webhook_count, 1)

                _TelegramApiHandler.get_me_ok = False
                invalid_payload = build_telegram_setup_report(
                    workspace,
                    env_file=Path(td) / "invalid.env",
                    token="bad-secret",
                    chat_id="2002",
                    api_base_url=f"http://127.0.0.1:{telegram_server.server_port}",
                )
                self.assertFalse(invalid_payload["get_me_ok"])
                self.assertFalse(invalid_payload["proof"]["ok"])
                self.assertEqual(invalid_payload["summary"]["failure_class"], "telegram_token_invalid")
        finally:
            telegram_server.shutdown()
            telegram_server.server_close()
            telegram_thread.join(timeout=1)

    def test_telegram_setup_page_accepts_token_and_writes_env(self) -> None:
        telegram_server = ThreadingHTTPServer(("127.0.0.1", 0), _TelegramApiHandler)
        telegram_thread = threading.Thread(target=telegram_server.serve_forever, daemon=True)
        telegram_thread.start()
        try:
            with tempfile.TemporaryDirectory() as td:
                workspace = Path(td) / "workspace"
                workspace.mkdir(parents=True, exist_ok=True)
                env_file = Path(td) / "agentos.env"
                url_file = Path(td) / "setup-url"
                result: dict = {}
                _TelegramApiHandler.updates = [
                    {
                        "update_id": 101,
                        "message": {
                            "message_id": 8,
                            "chat": {"id": 3003},
                            "text": "/start",
                        },
                    }
                ]

                def run_server() -> None:
                    result.update(
                        serve_telegram_setup_page(
                            workspace,
                            env_file=env_file,
                            host="127.0.0.1",
                            display_host="198.51.100.12",
                            port=0,
                            api_base_url=f"http://127.0.0.1:{telegram_server.server_port}",
                            timeout_sec=10,
                            url_file=url_file,
                        )
                    )

                server_thread = threading.Thread(target=run_server, daemon=True)
                server_thread.start()
                for _ in range(100):
                    if url_file.exists():
                        break
                    time.sleep(0.05)
                setup_url = url_file.read_text(encoding="utf-8").strip()
                self.assertIn("198.51.100.12", setup_url)
                encoded = urllib_parse.urlencode({"token": "setup-page-secret", "chat_id": ""}).encode("utf-8")
                req = urllib_request.Request(
                    setup_url.replace("198.51.100.12", "127.0.0.1"),
                    data=encoded,
                    method="POST",
                )
                with urllib_request.urlopen(req, timeout=5) as response:
                    body = response.read().decode("utf-8", errors="replace")
                server_thread.join(timeout=5)

                self.assertIn("Telegram is connected", body)
                self.assertIn("Bridged", body)
                self.assertIn("Mac host browser", body)
                self.assertTrue(result["completed"], result)
                self.assertEqual(result["telegram_setup"]["chat_id"], "3003")
                env_text = env_file.read_text(encoding="utf-8")
                self.assertIn('AGENTOS_TELEGRAM_BOT_TOKEN="setup-page-secret"', env_text)
                self.assertIn('AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS="3003"', env_text)
                self.assertIn('AGENTOS_TELEGRAM_TRANSPORT="polling"', env_text)
                self.assertNotIn("setup-page-secret", json.dumps(result, ensure_ascii=True))
        finally:
            telegram_server.shutdown()
            telegram_server.server_close()
            telegram_thread.join(timeout=1)

    def test_telegram_setup_page_reuses_captured_token_for_manual_chat_retry(self) -> None:
        telegram_server = ThreadingHTTPServer(("127.0.0.1", 0), _TelegramApiHandler)
        telegram_thread = threading.Thread(target=telegram_server.serve_forever, daemon=True)
        telegram_thread.start()
        try:
            with tempfile.TemporaryDirectory() as td:
                workspace = Path(td) / "workspace"
                workspace.mkdir(parents=True, exist_ok=True)
                env_file = Path(td) / "agentos.env"
                url_file = Path(td) / "setup-url"
                result: dict = {}
                _TelegramApiHandler.updates = []

                def run_server() -> None:
                    result.update(
                        serve_telegram_setup_page(
                            workspace,
                            env_file=env_file,
                            host="127.0.0.1",
                            display_host="127.0.0.1",
                            port=0,
                            api_base_url=f"http://127.0.0.1:{telegram_server.server_port}",
                            timeout_sec=10,
                            url_file=url_file,
                        )
                    )

                server_thread = threading.Thread(target=run_server, daemon=True)
                server_thread.start()
                for _ in range(100):
                    if url_file.exists():
                        break
                    time.sleep(0.05)
                setup_url = url_file.read_text(encoding="utf-8").strip()

                first = urllib_parse.urlencode({"token": "retry-secret", "chat_id": ""}).encode("utf-8")
                req = urllib_request.Request(setup_url, data=first, method="POST")
                with urllib_request.urlopen(req, timeout=5) as response:
                    first_body = response.read().decode("utf-8", errors="replace")
                self.assertIn("Token captured", first_body)

                second = urllib_parse.urlencode({"token": "", "chat_id": "4444"}).encode("utf-8")
                req = urllib_request.Request(setup_url, data=second, method="POST")
                with urllib_request.urlopen(req, timeout=5) as response:
                    second_body = response.read().decode("utf-8", errors="replace")
                server_thread.join(timeout=5)

                self.assertIn("Telegram is connected", second_body)
                self.assertTrue(result["completed"], result)
                self.assertEqual(result["telegram_setup"]["chat_id"], "4444")
                env_text = env_file.read_text(encoding="utf-8")
                self.assertIn('AGENTOS_TELEGRAM_BOT_TOKEN="retry-secret"', env_text)
                self.assertIn('AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS="4444"', env_text)
                self.assertNotIn("retry-secret", json.dumps(result, ensure_ascii=True))
        finally:
            telegram_server.shutdown()
            telegram_server.server_close()
            telegram_thread.join(timeout=1)

    def test_routing_contract_normalizes_search_fetch_and_chat_policy(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "spec.yaml").write_text(
                "telegram:\n  allowed_chat_ids:\n    - \"1001\"\n",
                encoding="utf-8",
            )
            search_payload = build_telegram_request_routing_contract(
                workspace,
                message_text="search agentos roadmap",
                chat_id="1001",
                request_id="req-search",
            )
            self.assertEqual(search_payload["selected_intent"], "search_query")
            self.assertEqual(search_payload["selected_path"], "internal_web_access")
            self.assertTrue(search_payload["telegram_chat_allowed"])
            self.assertTrue(search_payload["telegram_request_routed"])

            fetch_payload = build_telegram_request_routing_contract(
                workspace,
                message_text="https://example.com/releases",
                chat_id="1001",
                request_id="req-fetch",
            )
            self.assertEqual(fetch_payload["selected_intent"], "fetch_page")
            self.assertEqual(fetch_payload["request"]["command_input"]["url"], "https://example.com/releases")

            blocked_payload = build_telegram_request_routing_contract(
                workspace,
                message_text="search hidden",
                chat_id="2002",
                request_id="req-blocked",
            )
            self.assertFalse(blocked_payload["telegram_chat_allowed"])
            self.assertFalse(blocked_payload["telegram_request_routed"])
            self.assertFalse(blocked_payload["proof"]["ok"])

    def test_web_execution_report_happy_path_fetch_uses_internal_web_access(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _WebHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as td:
                workspace = Path(td) / "workspace"
                workspace.mkdir(parents=True, exist_ok=True)
                url = f"http://127.0.0.1:{server.server_port}/plain"
                routing = build_telegram_request_routing_contract(
                    workspace,
                    message_text=url,
                    chat_id="1001",
                    request_id="exec-fetch",
                )
                execution = build_telegram_web_execution_report(
                    workspace,
                    routing_report=routing,
                )

                self.assertEqual(execution["schema_version"], TELEGRAM_WEB_EXECUTION_SCHEMA)
                self.assertEqual(execution["capability"], "telegram_web_execution")
                self.assertEqual(execution["selected_intent"], "fetch_page")
                self.assertEqual(execution["selected_path"], "internal_web_access")
                self.assertTrue(execution["native_handled"])
                self.assertFalse(execution["browser_escalation_used"])
                self.assertTrue(execution["execution_artifacts"]["web_access"]["native_handled"])
                self.assertIn("latest_telegram_web_execution_manifest_json", execution["artifacts"])
                self.assertTrue(execution["proof"]["ok"])
                self.assertEqual(execution["proof"]["document_class"], "text")
                self.assertIn("hello from agentos", execution["execution_artifacts"]["web_access"]["proof"]["text_preview"])
        finally:
            server.shutdown()
            server.server_close()

    def test_web_execution_report_marks_browser_escalation_fallback_signal(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _WebHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as td:
                workspace = Path(td) / "workspace"
                workspace.mkdir(parents=True, exist_ok=True)
                url = f"http://127.0.0.1:{server.server_port}/app"
                routing = build_telegram_request_routing_contract(
                    workspace,
                    message_text=url,
                    chat_id="1001",
                    request_id="exec-escalation",
                )
                execution = build_telegram_web_execution_report(
                    workspace,
                    routing_report=routing,
                )

                self.assertTrue(execution["browser_escalation_used"])
                self.assertTrue(execution["browser_escalation_allowed"])
                self.assertTrue(execution["browser_escalation_required"])
                self.assertFalse(execution["native_handled"])
                self.assertEqual(execution["proof"]["ok"], False)
                self.assertEqual(
                    execution["proof"]["reason"],
                    "browser_escalation_required:interactive_or_js_heavy",
                )
                self.assertEqual(execution["proof"]["browser_escalation_reason"], "interactive_or_js_heavy")
                self.assertIn("execution_artifacts", execution)
                self.assertEqual(execution["execution_artifacts"]["web_access"]["escalated_handled"], True)
        finally:
            server.shutdown()
            server.server_close()

    def test_web_execution_report_supports_search_query_via_web_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            routing = build_telegram_request_routing_contract(
                workspace,
                message_text="agentos roadmap",
                chat_id="1001",
                request_id="exec-search",
            )
            with patch("kernel.capability_substrate.build_web_access_report") as mock_web_access:
                mock_web_access.return_value = {
                    "schema_version": "agentos-web-access.v1",
                    "capability": "web_access",
                    "native_handled": True,
                    "escalated_handled": False,
                    "unsupported_or_deferred": False,
                    "proof": {
                        "ok": True,
                        "selected_path": "native_fetch_parse",
                        "text_preview": "search results preview",
                        "content_type": "text/html",
                    },
                    "document_class": "text",
                    "artifacts": {},
                }
                execution = build_telegram_web_execution_report(
                    workspace,
                    routing_report=routing,
                )

                self.assertTrue(execution["telegram_request_routed"])
                self.assertTrue(execution["native_handled"])
                self.assertEqual(mock_web_access.call_count, 1)
                called_args = mock_web_access.call_args.args
                self.assertIn("duckduckgo.com/html/?q=", str(called_args[1]))
                self.assertEqual(execution["proof"]["execution_selected"], True)
                self.assertTrue(execution["proof"]["ok"])
                self.assertFalse(execution["browser_escalation_used"])

    def test_greeting_routes_to_direct_reply_without_duckduckgo(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            routing = build_telegram_request_routing_contract(
                workspace,
                message_text="hi",
                chat_id="1001",
                request_id="hello",
            )
            self.assertEqual(routing["selected_intent"], "direct_reply")
            self.assertEqual(routing["selected_path"], "direct_agentos_reply")

            with patch("kernel.capability_substrate.build_web_access_report") as mock_web_access:
                reply = build_telegram_reply_surface_report(
                    workspace,
                    message_text="hi",
                    chat_id="1001",
                    request_id="hello",
                )

            self.assertEqual(mock_web_access.call_count, 0)
            self.assertTrue(reply["reply_ready"])
            self.assertIn("AgentOS is online", reply["reply_text"])
            self.assertNotIn("DuckDuckGo", reply["reply_text"])

    def test_reply_surface_renders_and_sends_operator_reply(self) -> None:
        web_server = ThreadingHTTPServer(("127.0.0.1", 0), _WebHandler)
        web_thread = threading.Thread(target=web_server.serve_forever, daemon=True)
        web_thread.start()
        api_server = ThreadingHTTPServer(("127.0.0.1", 0), _TelegramApiHandler)
        api_thread = threading.Thread(target=api_server.serve_forever, daemon=True)
        api_thread.start()
        _TelegramApiHandler.sent_payloads = []
        try:
            with tempfile.TemporaryDirectory() as td:
                workspace = Path(td) / "workspace"
                workspace.mkdir(parents=True, exist_ok=True)
                env_file = workspace / "agentos.env"
                env_file.write_text(
                    "\n".join(
                        [
                            "AGENTOS_TELEGRAM_BOT_TOKEN=test-token",
                            f"AGENTOS_TELEGRAM_API_BASE_URL=http://127.0.0.1:{api_server.server_port}",
                        ]
                    )
                    + "\n",
                    encoding="utf-8",
                )
                url = f"http://127.0.0.1:{web_server.server_port}/plain"
                with patch.dict(os.environ, {"AGENTOS_ENV_FILE": str(env_file)}, clear=False):
                    reply = build_telegram_reply_surface_report(
                        workspace,
                        message_text=url,
                        chat_id="1001",
                        request_id="reply-send",
                        send_reply=True,
                    )

                self.assertEqual(reply["schema_version"], TELEGRAM_REPLY_SCHEMA)
                self.assertTrue(reply["reply_ready"])
                self.assertTrue(reply["reply_sent"])
                self.assertEqual(reply["reply_mode"], "send_message")
                self.assertTrue(reply["proof"]["send_ok"])
                self.assertIn("AgentOS page fetch result", reply["reply_text"])
                self.assertEqual(len(_TelegramApiHandler.sent_payloads), 1)
                sent = _TelegramApiHandler.sent_payloads[0]
                self.assertEqual(sent["path"], "/bottest-token/sendMessage")
                self.assertEqual(sent["payload"]["chat_id"], "1001")
                self.assertIn("Source:", sent["payload"]["text"])
                self.assertEqual(validate_telegram_reply(reply), [])
        finally:
            web_server.shutdown()
            web_server.server_close()
            web_thread.join(timeout=1)
            api_server.shutdown()
            api_server.server_close()
            api_thread.join(timeout=1)

    def test_webhook_payload_routes_update_and_sends_reply(self) -> None:
        api_server = ThreadingHTTPServer(("127.0.0.1", 0), _TelegramApiHandler)
        api_thread = threading.Thread(target=api_server.serve_forever, daemon=True)
        api_thread.start()
        _TelegramApiHandler.sent_payloads = []
        try:
            with tempfile.TemporaryDirectory() as td:
                workspace = Path(td) / "workspace"
                workspace.mkdir(parents=True, exist_ok=True)
                env_file = workspace / "agentos.env"
                env_file.write_text(
                    "\n".join(
                        [
                            "AGENTOS_TELEGRAM_BOT_TOKEN=test-token",
                            "AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS=1001",
                            "AGENTOS_TELEGRAM_TRANSPORT=webhook",
                            f"AGENTOS_TELEGRAM_API_BASE_URL=http://127.0.0.1:{api_server.server_port}",
                        ]
                    )
                    + "\n",
                    encoding="utf-8",
                )
                update = {
                    "update_id": 9001,
                    "message": {
                        "message_id": 77,
                        "date": 1,
                        "chat": {"id": 1001},
                        "text": "hi",
                    },
                }
                with patch.dict(os.environ, {"AGENTOS_ENV_FILE": str(env_file)}, clear=False):
                    payload = build_webhook_payload(workspace, update, send_reply=True)

                self.assertEqual(payload["schema_version"], WEBHOOK_SCHEMA)
                self.assertTrue(payload["proof"]["ok"], payload)
                self.assertTrue(payload["telegram_webhook_update_received"])
                self.assertTrue(payload["telegram_webhook_message_routed"])
                self.assertFalse(payload["telegram_webhook_search_success"])
                self.assertEqual(payload["intent_dispatch"]["intent"], "greeting")
                self.assertFalse(payload["intent_dispatch"]["web_search_used"])
                self.assertTrue(payload["telegram_reply_sent"])
                self.assertEqual(payload["summary"]["failure_class"], "")
                self.assertEqual(len(_TelegramApiHandler.sent_payloads), 1)
                sent = _TelegramApiHandler.sent_payloads[0]
                self.assertEqual(sent["path"], "/bottest-token/sendMessage")
                self.assertEqual(sent["payload"]["chat_id"], "1001")
                self.assertIn("AgentOS is online", sent["payload"]["text"])
                rendered = json.dumps(payload, ensure_ascii=True)
                self.assertNotIn("test-token", rendered)
        finally:
            api_server.shutdown()
            api_server.server_close()
            api_thread.join(timeout=1)

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            spec = workspace / "spec.yaml"
            spec.write_text(
                "telegram:\n  polling:\n    enabled: false\n",
                encoding="utf-8",
            )
            out = Path(td) / "telegram-status.json"
            subprocess.run(
                ["python3", str(ROOT_DIR / "scripts" / "kernel_telegram_status.py"), "--workspace", str(workspace), "--output", str(out)],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
            result = subprocess.run(
                ["python3", str(ROOT_DIR / "scripts" / "kernel_telegram_status.py"), "--validate", str(out), "--json"],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(result.stdout), {"ok": True, "errors": [], "schema_version": TELEGRAM_STATUS_SCHEMA})

            contract_out = Path(td) / "telegram-contract.json"
            subprocess.run(
                ["python3", str(ROOT_DIR / "scripts" / "kernel_telegram_contract.py"), "--workspace", str(workspace), "--output", str(contract_out)],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
            contract_payload = json.loads(contract_out.read_text(encoding="utf-8"))
            self.assertEqual(validate_telegram_contract(contract_payload), [])

            routing_out = Path(td) / "telegram-routing.json"
            subprocess.run(
                [
                    "python3",
                    str(ROOT_DIR / "scripts" / "kernel_telegram_routing_contract.py"),
                    "--workspace",
                    str(workspace),
                    "--message-text",
                    "search agentos",
                    "--request-id",
                    "req-cli",
                    "--output",
                    str(routing_out),
                ],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
            routing_payload = json.loads(routing_out.read_text(encoding="utf-8"))
            self.assertEqual(validate_telegram_routing(routing_payload), [])

            proof_out = Path(td) / "telegram-proof.json"
            subprocess.run(
                [
                    "python3",
                    str(ROOT_DIR / "scripts" / "kernel_telegram_proof_baseline.py"),
                    "--workspace",
                    str(workspace),
                    "--message-text",
                    "",
                    "--chat-id",
                    "1001",
                    "--request-id",
                    "req-proof",
                    "--reply-sent",
                    "--output",
                    str(proof_out),
                ],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
            proof_payload = json.loads(proof_out.read_text(encoding="utf-8"))
            self.assertEqual(validate_telegram_proof(proof_payload), [])
            self.assertEqual(proof_payload["summary"]["telegram_request_id"], "req-proof")
            self.assertFalse(proof_payload["summary"]["telegram_reply_ready"])
            self.assertFalse(proof_payload["summary"]["telegram_reply_sent"])


if __name__ == "__main__":
    unittest.main()
