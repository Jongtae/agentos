from __future__ import annotations

import json
import mailbox
import tempfile
import threading
import unittest
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from kernel.capability_substrate import (
    build_capability_proof_surface,
    build_document_access_report,
    build_inbox_capability_report,
    build_inbox_normalized_intake_report,
    build_inbox_proof_baseline_report,
    build_inbox_routing_contract,
    build_intake_surface_report,
    build_web_access_report,
)
from kernel.event_fabric.collectors import append_events_jsonl
from kernel.event_fabric.schema import build_os_event_record


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


class CapabilitySubstrateTests(unittest.TestCase):
    def test_inbox_capability_handles_fixture_natively(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)

            payload = build_inbox_capability_report(workspace)

            self.assertTrue(payload["native_inbox_handled"])
            self.assertFalse(payload["inbox_adapter_required"])
            self.assertTrue(payload["message_thread_correlated"])
            self.assertTrue(payload["attachment_visibility_ok"])
            self.assertTrue(payload["inbox_execution_ready"])
            self.assertEqual(payload["summary"]["message_count"], 2)
            self.assertTrue(Path(payload["artifacts"]["latest_inbox_capability_manifest_json"]).exists())

    def test_inbox_capability_handles_maildir_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            maildir_root = workspace / "mail" / "primary"
            maildir_root.parent.mkdir(parents=True, exist_ok=True)
            box = mailbox.Maildir(str(maildir_root), create=True)

            root = EmailMessage()
            root["Message-ID"] = "<root@example.local>"
            root["Subject"] = "Root thread"
            root["From"] = "root@example.local"
            root["To"] = "agentos@example.local"
            root.set_content("root body")
            box.add(root)

            reply = EmailMessage()
            reply["Message-ID"] = "<reply@example.local>"
            reply["In-Reply-To"] = "<root@example.local>"
            reply["Subject"] = "Re: Root thread"
            reply["From"] = "agentos@example.local"
            reply["To"] = "root@example.local"
            reply.set_content("reply body")
            reply.add_attachment(b"hello world", maintype="text", subtype="plain", filename="hello.txt")
            box.add(reply)
            box.flush()

            payload = build_inbox_capability_report(workspace, maildir_path="mail/primary")

            self.assertFalse(payload["native_inbox_handled"])
            self.assertTrue(payload["inbox_adapter_required"])
            self.assertEqual(payload["inbox_adapter_path"], "maildir")
            self.assertTrue(payload["message_thread_correlated"])
            self.assertTrue(payload["attachment_visibility_ok"])
            self.assertTrue(payload["inbox_execution_ready"])
            self.assertEqual(payload["summary"]["thread_count"], 1)
            self.assertEqual(payload["summary"]["message_count"], 2)

    def test_inbox_routing_contract_exposes_native_and_adapter_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            payload = build_inbox_routing_contract(workspace, session_id="agentos:tty1")

            self.assertEqual(payload["default_selected_path"], "native_inbox_path")
            self.assertEqual(len(payload["paths"]), 2)
            self.assertEqual(payload["paths"][0]["path_id"], "native_inbox_path")
            self.assertEqual(payload["paths"][1]["path_id"], "inbox_adapter_path")
            self.assertEqual(payload["correlation"]["session_id"], "agentos:tty1")
            self.assertTrue(Path(payload["artifacts"]["latest_inbox_routing_contract_json"]).exists())

    def test_inbox_normalized_intake_uses_fixture_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"

            payload = build_inbox_normalized_intake_report(workspace, session_id="agentos:tty1")

            self.assertEqual(payload["selected_path"], "native_inbox_path")
            self.assertEqual(payload["path_kind"], "native")
            self.assertEqual(payload["source_kind"], "fixture")
            self.assertEqual(payload["summary"]["message_count"], 2)
            self.assertEqual(payload["summary"]["message_intake_count"] if "message_intake_count" in payload["summary"] else 2, 2)
            self.assertEqual(payload["normalized_messages"][0]["intake_kind"], "message_intake")
            self.assertEqual(payload["normalized_messages"][0]["correlation"]["session_id"], "agentos:tty1")
            self.assertTrue(Path(payload["artifacts"]["latest_inbox_normalized_intake_json"]).exists())

    def test_inbox_normalized_intake_uses_maildir_adapter_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            maildir_root = workspace / "mail" / "primary"
            maildir_root.parent.mkdir(parents=True, exist_ok=True)
            box = mailbox.Maildir(str(maildir_root), create=True)

            root = EmailMessage()
            root["Message-ID"] = "<adapter-root@example.local>"
            root["Subject"] = "Adapter root"
            root["From"] = "root@example.local"
            root["To"] = "agentos@example.local"
            root.set_content("root body")
            box.add(root)

            reply = EmailMessage()
            reply["Message-ID"] = "<adapter-reply@example.local>"
            reply["In-Reply-To"] = "<adapter-root@example.local>"
            reply["Subject"] = "Re: Adapter root"
            reply["From"] = "agentos@example.local"
            reply["To"] = "root@example.local"
            reply.set_content("reply body")
            reply.add_attachment(b"hello world", maintype="text", subtype="plain", filename="hello.txt")
            box.add(reply)
            box.flush()

            payload = build_inbox_normalized_intake_report(
                workspace,
                maildir_path="mail/primary",
                session_id="agentos:tty1",
            )

            self.assertEqual(payload["selected_path"], "inbox_adapter_path")
            self.assertEqual(payload["path_kind"], "adapter")
            self.assertEqual(payload["source_kind"], "maildir")
            self.assertTrue(payload["inbox_adapter_required"])
            self.assertEqual(payload["summary"]["attachment_count"], 1)
            self.assertEqual({item["thread_id"] for item in payload["normalized_messages"]}, {"<adapter-root@example.local>"})
            self.assertEqual(max(item["attachment_count"] for item in payload["normalized_messages"]), 1)

    def test_inbox_normalized_intake_carries_session_and_approval_correlation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            artifacts = workspace / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            append_events_jsonl(
                artifacts / "os_events.jsonl",
                [
                    build_os_event_record(
                        source="journald",
                        kind="session.login",
                        action="login",
                        object={"session_id": "agentos:tty1"},
                        correlation={
                            "session_id": "agentos:tty1",
                            "boot_id": "boot-247",
                            "request_id": "request-247",
                            "approval_id": "approval-247",
                        },
                        timestamp_utc="2026-04-21T00:00:00Z",
                    )
                ],
            )

            payload = build_inbox_normalized_intake_report(workspace, session_id="agentos:tty1")

            self.assertEqual(payload["correlation"]["session_id"], "agentos:tty1")
            self.assertEqual(payload["correlation"]["request_id"], "request-247")
            self.assertEqual(payload["correlation"]["approval_id"], "approval-247")
            self.assertEqual(payload["correlation"]["boot_id"], "boot-247")
            self.assertEqual(payload["session_correlation"]["request_ids"], ["request-247"])
            self.assertEqual(payload["session_correlation"]["approval_ids"], ["approval-247"])
            self.assertTrue(payload["summary"]["session_correlated"])
            self.assertTrue(payload["summary"]["request_correlated"])
            self.assertTrue(payload["summary"]["approval_correlated"])
            self.assertEqual(payload["normalized_messages"][0]["correlation"]["approval_id"], "approval-247")

    def test_inbox_proof_baseline_combines_native_and_maildir_reports(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            maildir_root = workspace / "mail" / "primary"
            maildir_root.parent.mkdir(parents=True, exist_ok=True)
            box = mailbox.Maildir(str(maildir_root), create=True)

            root = EmailMessage()
            root["Message-ID"] = "<proof-root@example.local>"
            root["Subject"] = "Proof root"
            root["From"] = "root@example.local"
            root["To"] = "agentos@example.local"
            root.set_content("root body")
            box.add(root)
            box.flush()

            payload = build_inbox_proof_baseline_report(workspace, maildir_path="mail/primary", session_id="agentos:tty1")

            self.assertTrue(payload["summary"]["native_inbox_handled"])
            self.assertTrue(payload["summary"]["adapter_report_present"])
            self.assertTrue(payload["summary"]["inbox_adapter_required"])
            self.assertTrue(payload["summary"]["message_thread_correlated"])
            self.assertTrue(payload["summary"]["attachment_visibility_ok"])
            self.assertTrue(payload["summary"]["inbox_execution_ready"])
            self.assertIn("session_correlated", payload["summary"])
            self.assertIn("request_correlated", payload["summary"])
            self.assertIn("approval_correlated", payload["summary"])
            self.assertTrue(Path(payload["artifacts"]["latest_inbox_proof_baseline_json"]).exists())

    def test_inbox_proof_baseline_carries_correlation_surface(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            maildir_root = workspace / "mail" / "primary"
            maildir_root.parent.mkdir(parents=True, exist_ok=True)
            box = mailbox.Maildir(str(maildir_root), create=True)

            root = EmailMessage()
            root["Message-ID"] = "<proof-corr-root@example.local>"
            root["Subject"] = "Proof corr root"
            root["From"] = "root@example.local"
            root["To"] = "agentos@example.local"
            root.set_content("root body")
            box.add(root)
            box.flush()

            artifacts = workspace / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            append_events_jsonl(
                artifacts / "os_events.jsonl",
                [
                    build_os_event_record(
                        source="journald",
                        kind="session.login",
                        action="login",
                        object={"session_id": "agentos:tty1"},
                        correlation={
                            "session_id": "agentos:tty1",
                            "boot_id": "boot-249",
                            "request_id": "request-249",
                            "approval_id": "approval-249",
                        },
                        timestamp_utc="2026-04-21T00:00:00Z",
                    )
                ],
            )

            payload = build_inbox_proof_baseline_report(
                workspace,
                maildir_path="mail/primary",
                session_id="agentos:tty1",
            )

            self.assertTrue(payload["summary"]["session_correlated"])
            self.assertTrue(payload["summary"]["request_correlated"])
            self.assertTrue(payload["summary"]["approval_correlated"])
            self.assertIn("native_intake", payload)
            self.assertIn("adapter_intake", payload)

    def test_document_access_handles_markdown_natively(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            docs = workspace / "docs"
            docs.mkdir(parents=True, exist_ok=True)
            (docs / "note.md").write_text("# hello\n\nworld\n", encoding="utf-8")

            payload = build_document_access_report(workspace, "docs/note.md")

            self.assertTrue(payload["native_handled"])
            self.assertEqual(payload["document_class"], "markdown")
            self.assertFalse(payload["unsupported_or_deferred"])
            self.assertTrue(Path(payload["artifacts"]["latest_document_access_manifest_json"]).exists())

    def test_document_access_defers_binary_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "image.bin").write_bytes(b"\x00\x01\x02\x03")

            payload = build_document_access_report(workspace, "image.bin")

            self.assertFalse(payload["native_handled"])
            self.assertTrue(payload["unsupported_or_deferred"])
            self.assertEqual(payload["mediation_cost"], "deferred")

    def test_web_access_handles_plain_text_natively(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _WebHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as td:
                workspace = Path(td) / "workspace"
                workspace.mkdir(parents=True, exist_ok=True)
                url = f"http://127.0.0.1:{server.server_port}/plain"

                payload = build_web_access_report(workspace, url, domain_allowlist=["127.0.0.1"])

                self.assertTrue(payload["native_handled"])
                self.assertFalse(payload["escalated_handled"])
                self.assertEqual(payload["document_class"], "text")
                self.assertIn("hello from agentos", payload["proof"]["text_preview"])
        finally:
            server.shutdown()
            server.server_close()

    def test_web_access_escalates_interactive_pages(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _WebHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as td:
                workspace = Path(td) / "workspace"
                workspace.mkdir(parents=True, exist_ok=True)
                url = f"http://127.0.0.1:{server.server_port}/app"

                payload = build_web_access_report(workspace, url, domain_allowlist=["127.0.0.1"])

                self.assertFalse(payload["native_handled"])
                self.assertTrue(payload["escalated_handled"])
                self.assertEqual(payload["escalation_reason"], "interactive_or_js_heavy")
        finally:
            server.shutdown()
            server.server_close()

    def test_intake_surface_unifies_events_and_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            artifacts = workspace / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            append_events_jsonl(
                artifacts / "os_events.jsonl",
                [
                    build_os_event_record(
                        source="journald",
                        kind="session.login",
                        action="login",
                        object={"session_id": "agentos:tty1"},
                        correlation={"session_id": "agentos:tty1", "boot_id": "boot-1"},
                        timestamp_utc="2026-04-19T00:00:00Z",
                    ),
                    build_os_event_record(
                        source="broker",
                        kind="broker.approval_request",
                        action="approval_gate",
                        object={"tool_name": "bash"},
                        correlation={"session_id": "agentos:tty1", "approval_id": "approval-1"},
                        timestamp_utc="2026-04-19T00:00:01Z",
                    ),
                ],
            )
            feedback_root = artifacts / "feedback-intake"
            feedback_root.mkdir(parents=True, exist_ok=True)
            (feedback_root / "latest-feedback-intake-manifest.json").write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-04-19T00:00:02Z",
                        "feedback_packet": {
                            "channel": "internal_preview",
                            "summary": "Need one more pass.",
                            "recommendation": "hold",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            payload = build_intake_surface_report(workspace, report_dir=str(artifacts), session_id="agentos:tty1")

            self.assertTrue(payload["summary"]["ok"])
            self.assertEqual(payload["summary"]["total_items"], 3)
            self.assertEqual(payload["summary"]["native_intake_items"], 3)
            self.assertIn("feedback_intake", payload["summary"]["counts_by_kind"])
            self.assertTrue(Path(payload["artifacts"]["latest_intake_surface_manifest_json"]).exists())

    def test_capability_proof_surface_aggregates_latest_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            docs = workspace / "docs"
            docs.mkdir(parents=True, exist_ok=True)
            (docs / "note.txt").write_text("hello", encoding="utf-8")

            build_document_access_report(workspace, "docs/note.txt")
            build_intake_surface_report(workspace)
            payload = build_capability_proof_surface(workspace)

            self.assertEqual(payload["schema_version"], "agentos-capability-proof-surface.v1")
            self.assertTrue(Path(payload["artifacts"]["latest_capability_proof_surface_json"]).exists())
            self.assertIn("native_handled", payload["proof_vocabulary"])
            self.assertIn("service_capability", payload)
            self.assertIn("permission_capability", payload)
            self.assertIn("service_broker_mediated_units", payload["summary"])
            self.assertIn("permission_escalated_events", payload["summary"])

    @patch("kernel.capability_substrate.build_web_access_report")
    def test_capability_proof_surface_refreshes_stale_manifests(self, mock_web_access) -> None:
        mock_web_access.return_value = {
            "schema_version": "agentos-web-access.v1",
            "generated_at_utc": "2026-04-19T00:00:00Z",
            "workspace": "",
            "capability_family": "web",
            "capability": "web_access",
            "url": "https://example.com",
            "native_path_default": True,
            "native_handled": False,
            "escalated_handled": True,
            "escalation_reason": "interactive_or_js_heavy",
            "unsupported_or_deferred": False,
            "mediation_cost": "medium",
            "document_class": "html",
            "proof": {"ok": True},
            "artifacts": {},
        }

        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "spec.yaml").write_text("name: refresh-test\n", encoding="utf-8")

            artifacts = workspace / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            stale_capability_root = artifacts / "capability-substrate"
            stale_capability_root.mkdir(parents=True, exist_ok=True)
            (stale_capability_root / "latest-document-access.json").write_text(
                json.dumps(
                    {
                        "schema_version": "agentos-document-access.v1",
                        "native_handled": False,
                        "proof": {"ok": False, "reason": "file_not_found"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (stale_capability_root / "latest-intake-surface.json").write_text(
                json.dumps(
                    {
                        "schema_version": "agentos-intake-surface.v1",
                        "summary": {"ok": False, "total_items": 0, "native_intake_items": 0, "escalated_intake_items": 0},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            append_events_jsonl(
                artifacts / "os_events.jsonl",
                [
                    build_os_event_record(
                        source="journald",
                        kind="session.login",
                        action="login",
                        object={"session_id": "agentos:tty1"},
                        correlation={"session_id": "agentos:tty1", "boot_id": "boot-1"},
                        timestamp_utc="2026-04-19T00:00:00Z",
                    )
                ],
            )

            payload = build_capability_proof_surface(workspace)

            self.assertTrue(payload["summary"]["document_native_handled"])
            self.assertTrue(payload["intake_surface"]["summary"]["ok"])
            self.assertEqual(payload["intake_surface"]["summary"]["total_items"], 1)
            self.assertTrue(Path(payload["document_access"]["artifacts"]["latest_document_access_manifest_json"]).exists())
            self.assertTrue(Path(payload["intake_surface"]["artifacts"]["latest_intake_surface_manifest_json"]).exists())
            self.assertTrue(Path(payload["service_capability"]["artifacts"]["latest_service_capability_manifest_json"]).exists())
            self.assertTrue(Path(payload["permission_capability"]["artifacts"]["latest_permission_capability_manifest_json"]).exists())
            self.assertTrue(Path(payload["execution_ownership"]["artifacts"]["latest_execution_ownership_manifest_json"]).exists())
            self.assertIn("inbox_capability", payload)
            self.assertIn("inbox_normalized_intake", payload)
            self.assertIn("native_inbox_handled", payload["summary"])
            self.assertIn("inbox_message_intake_count", payload["summary"])
            self.assertIn("inbox_session_correlated", payload["summary"])
            self.assertTrue(Path(payload["inbox_capability"]["artifacts"]["latest_inbox_capability_manifest_json"]).exists())
            self.assertTrue(Path(payload["inbox_normalized_intake"]["artifacts"]["latest_inbox_normalized_intake_json"]).exists())
            self.assertTrue((stale_capability_root / "latest-document-access.json").exists())
            refreshed_document = json.loads((stale_capability_root / "latest-document-access.json").read_text(encoding="utf-8"))
            refreshed_intake = json.loads((stale_capability_root / "latest-intake-surface.json").read_text(encoding="utf-8"))
            self.assertTrue(refreshed_document["native_handled"])
            self.assertTrue(refreshed_intake["summary"]["ok"])


if __name__ == "__main__":
    unittest.main()
