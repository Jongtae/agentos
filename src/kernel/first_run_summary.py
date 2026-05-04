from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from kernel.capability_substrate import (
    build_capability_proof_surface,
    build_document_access_report,
    build_web_access_report,
)

FIRST_RUN_SUMMARY_SCHEMA = "agentos-first-run-summary.v1"
DEFAULT_DOCUMENT_PATH = "documents/agentos-first-run.md"
DEFAULT_WEB_URL = "https://example.com"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _first_run_artifact_path(workspace: Path) -> Path:
    path = workspace / "artifacts" / "repo-free-first-run" / "latest-first-run-summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def ensure_first_run_document(workspace_dir: str | Path, document_path: str = DEFAULT_DOCUMENT_PATH) -> str:
    workspace = Path(workspace_dir).resolve()
    target = workspace / document_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(
            "# AgentOS First Run\n\n"
            "This document proves repo-free native document handling on the installed AgentOS surface.\n"
            "\n"
            "- runtime: Codex-managed AgentOS session\n"
            "- capability goal: document + web + summary\n",
            encoding="utf-8",
        )
    return str(target.relative_to(workspace))


def build_first_run_summary_report(
    workspace_dir: str | Path,
    *,
    document_path: str = DEFAULT_DOCUMENT_PATH,
    web_url: str = DEFAULT_WEB_URL,
    domain_allowlist: list[str] | None = None,
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    document_rel_path = ensure_first_run_document(workspace, document_path)
    document_access = build_document_access_report(workspace, document_rel_path, write_manifest=True)
    web_access = build_web_access_report(
        workspace,
        web_url,
        domain_allowlist=domain_allowlist or ["example.com"],
        write_manifest=True,
    )
    capability_proof = build_capability_proof_surface(workspace)

    summary_text = (
        "Repo-free first-run flow: "
        f"document={'native' if document_access.get('native_handled') else 'deferred'}, "
        f"web={'native' if web_access.get('native_handled') else ('escalated' if web_access.get('escalated_handled') else 'deferred')}, "
        f"proof_document={capability_proof.get('summary', {}).get('document_native_handled', False)}, "
        f"proof_web={capability_proof.get('summary', {}).get('web_native_handled', False) or capability_proof.get('summary', {}).get('web_escalated_handled', False)}."
    )

    payload = {
        "schema_version": FIRST_RUN_SUMMARY_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "document_access": document_access,
        "web_access": web_access,
        "capability_proof": capability_proof,
        "summary": {
            "document_path": document_rel_path,
            "web_url": web_url,
            "document_native_handled": bool(document_access.get("native_handled", False)),
            "web_handled": bool(web_access.get("native_handled", False) or web_access.get("escalated_handled", False)),
            "capability_proof_ready": bool(
                document_access.get("native_handled", False)
                and (web_access.get("native_handled", False) or web_access.get("escalated_handled", False))
            ),
            "summary_text": summary_text,
        },
        "artifacts": {},
    }

    if write_manifest:
        manifest = _first_run_artifact_path(workspace)
        manifest.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
        payload["artifacts"]["latest_first_run_summary_manifest_json"] = str(manifest)

    return payload
