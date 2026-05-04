from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "agentos-vm-integrated-proof-foundation.v1"
LAYOUT_DIRNAME = "vm-integrated-proof-foundations"
CORRELATION_KEYS = ("session_id", "request_id", "approval_id", "trace_id", "run_id", "boot_id")
ESCALATION_KEYS = ("escalation_reason", "intake_escalation_reason")
ESCALATION_LIST_KEYS = ("escalation_reasons",)
EXPECTED_PRIMARY_PATH = "Continue to AgentOS -> AgentOS Welcome -> AgentOS Setup -> ai>"
EXPECTED_INSTALLED_PATH = "Installed AgentOS Boot -> AgentOS Setup -> AgentOS Managed Session -> ai>"
EXPECTED_RECOVERY_PATH = "AgentOS Recovery -> Return to AgentOS -> ai>"

REFERENCE_FILES = [
    Path(__file__).resolve().parents[2] / "docs" / "reference" / "appliance-boot-signoff-pack-v1.md",
    Path(__file__).resolve().parents[2] / "docs" / "reference" / "capability-proof-surfaces-v1.md",
    Path(__file__).resolve().parents[2] / "docs" / "reference" / "intake-runtime-vocabulary-v1.md",
    Path(__file__).resolve().parents[2] / "docs" / "reference" / "service-governance-model-v1.md",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def _load_json(path: str) -> dict:
    if not path:
        return {}
    target = Path(path)
    if not target.exists():
        return {}
    return json.loads(target.read_text(encoding="utf-8"))


def _runtime_summary_ok(payload: dict) -> bool:
    summary = payload.get("summary") or {}
    schema = str(payload.get("schema_version", ""))
    if schema == "agentos-appliance-boot-signoff-pack.v1":
        return bool(
            summary.get("ok") is True
            and summary.get("expected_primary_path") == EXPECTED_PRIMARY_PATH
            and summary.get("expected_installed_path") == EXPECTED_INSTALLED_PATH
            and summary.get("expected_recovery_path") == EXPECTED_RECOVERY_PATH
        )
    if schema == "agentos-welcome-first-vm-proof-pack.v1":
        return bool(summary.get("ok") is True and summary.get("expected_path") == EXPECTED_PRIMARY_PATH)
    return bool(summary.get("ok") is True)


def _capability_summary_ok(payload: dict) -> bool:
    if payload.get("schema_version") != "agentos-capability-proof-surface.v1":
        return False
    summary = payload.get("summary") or {}
    return "document_native_handled" in summary and "intake_native_items" in summary


def _intake_summary_ok(payload: dict) -> bool:
    if payload.get("schema_version") != "agentos-intake-surface.v1":
        return False
    summary = payload.get("summary") or {}
    return bool(summary.get("ok") is True and "total_items" in summary)


def _service_permission_summary_ok(payload: dict) -> bool:
    schema = str(payload.get("schema_version", ""))
    if schema == "agentos-service-governance.v1":
        summary = payload.get("summary") or {}
        inventory = payload.get("inventory") or []
        return bool(inventory and "mandatory_broker_units" in summary and "approval_gated_units" in summary)
    summary = payload.get("summary") or {}
    return bool(summary.get("ok") is True)


def _collect_escalation_reasons(payload: object, bucket: set[str]) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in ESCALATION_KEYS and str(value).strip():
                bucket.add(str(value).strip())
            elif key in ESCALATION_LIST_KEYS and isinstance(value, list):
                for item in value:
                    if str(item).strip():
                        bucket.add(str(item).strip())
            _collect_escalation_reasons(value, bucket)
    elif isinstance(payload, list):
        for item in payload:
            _collect_escalation_reasons(item, bucket)


def _collect_correlation_evidence(payload: object, findings: list[dict], *, source: str, trail: str = "root") -> None:
    if isinstance(payload, dict):
        evidence = {}
        for key in CORRELATION_KEYS:
            value = str(payload.get(key, "")).strip()
            if value:
                evidence[key] = value
        if evidence:
            findings.append({"source": source, "path": trail, "evidence": evidence})
        for key, value in payload.items():
            child_trail = f"{trail}.{key}"
            _collect_correlation_evidence(value, findings, source=source, trail=child_trail)
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            _collect_correlation_evidence(item, findings, source=source, trail=f"{trail}[{index}]")


def _dedupe_correlation(findings: list[dict]) -> list[dict]:
    seen: set[tuple[str, str, tuple[tuple[str, str], ...]]] = set()
    unique: list[dict] = []
    for item in findings:
        evidence = item.get("evidence") or {}
        marker = (
            str(item.get("source", "")),
            str(item.get("path", "")),
            tuple(sorted((str(key), str(value)) for key, value in evidence.items())),
        )
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(item)
    return unique


def _combined_correlation_summary(findings: list[dict]) -> dict:
    combined = {key: [] for key in CORRELATION_KEYS}
    for item in findings:
        evidence = item.get("evidence") or {}
        for key in CORRELATION_KEYS:
            value = str(evidence.get(key, "")).strip()
            if value and value not in combined[key]:
                combined[key].append(value)
    return {
        "present": any(combined[key] for key in CORRELATION_KEYS),
        "counts": {key: len(values) for key, values in combined.items()},
        "values": combined,
    }


def build_markdown(*, label: str, manifest: dict, copied_references: list[str]) -> str:
    summary = manifest["summary"]
    artifacts = manifest["artifacts"]
    lines = [
        "# AgentOS VM Integrated Proof Foundation",
        "",
        f"Run label: `{label}`",
        f"Generated at: `{manifest['generated_at_utc']}`",
        "",
        "## Aggregated inputs",
        "",
        f"1. Runtime proof: `{artifacts['runtime_proof_json']}`",
        f"2. Capability proof: `{artifacts['capability_proof_json']}`",
        f"3. Intake proof: `{artifacts['intake_proof_json']}`",
        f"4. Service/permission proof: `{artifacts['service_permission_proof_json']}`",
        "",
        "## Foundation summary",
        "",
        f"- Runtime proof ok: `{summary['runtime_proof_ok']}`",
        f"- Capability proof ok: `{summary['capability_proof_ok']}`",
        f"- Intake proof ok: `{summary['intake_proof_ok']}`",
        f"- Service/permission proof ok: `{summary['service_permission_proof_ok']}`",
        f"- Escalation reasons captured: `{summary['escalation_reasons']}`",
        f"- Correlation evidence present: `{summary['correlation_evidence_present']}`",
        f"- Correlation evidence count: `{summary['correlation_evidence_count']}`",
        f"- Integrated proof ready: `{summary['ok']}`",
        "",
        "## Included references",
        "",
    ]
    lines.extend(f"- `{Path(path).name}`" for path in copied_references)
    return "\n".join(lines) + "\n"


def build_vm_integrated_proof_foundation(
    *,
    report_dir: str,
    snapshot_label: str,
    runtime_proof: str,
    capability_proof: str,
    intake_proof: str,
    service_permission_proof: str,
) -> dict:
    root = resolve_root(report_dir)
    run_dir = root / f"vm-integrated-proof-foundation-{snapshot_label or 'current'}"
    run_dir.mkdir(parents=True, exist_ok=True)

    runtime_payload = _load_json(runtime_proof)
    capability_payload = _load_json(capability_proof)
    intake_payload = _load_json(intake_proof)
    service_permission_payload = _load_json(service_permission_proof)

    references_dir = run_dir / "references"
    references_dir.mkdir(parents=True, exist_ok=True)
    copied_references: list[str] = []
    for ref in REFERENCE_FILES:
        if ref.exists():
            destination = references_dir / ref.name
            shutil.copyfile(ref, destination)
            copied_references.append(str(destination))

    escalation_reasons: set[str] = set()
    _collect_escalation_reasons(capability_payload, escalation_reasons)
    _collect_escalation_reasons(intake_payload, escalation_reasons)
    _collect_escalation_reasons(service_permission_payload, escalation_reasons)

    correlation_findings: list[dict] = []
    _collect_correlation_evidence(runtime_payload, correlation_findings, source="runtime_proof")
    _collect_correlation_evidence(capability_payload, correlation_findings, source="capability_proof")
    _collect_correlation_evidence(intake_payload, correlation_findings, source="intake_proof")
    _collect_correlation_evidence(service_permission_payload, correlation_findings, source="service_permission_proof")
    correlation_findings = _dedupe_correlation(correlation_findings)
    correlation_summary = _combined_correlation_summary(correlation_findings)

    summary = {
        "ok": False,
        "runtime_proof_ok": _runtime_summary_ok(runtime_payload),
        "capability_proof_ok": _capability_summary_ok(capability_payload),
        "intake_proof_ok": _intake_summary_ok(intake_payload),
        "service_permission_proof_ok": _service_permission_summary_ok(service_permission_payload),
        "escalation_reasons": sorted(escalation_reasons),
        "escalation_count": len(escalation_reasons),
        "correlation_evidence_present": bool(correlation_summary["present"]),
        "correlation_evidence_count": len(correlation_findings),
        "reference_count": len(copied_references),
    }
    summary["ok"] = all(
        [
            summary["runtime_proof_ok"],
            summary["capability_proof_ok"],
            summary["intake_proof_ok"],
            summary["service_permission_proof_ok"],
            summary["correlation_evidence_present"],
        ]
    )

    markdown = run_dir / "vm-integrated-proof-foundation.md"
    manifest = run_dir / "vm-integrated-proof-foundation.json"
    latest = root / "latest-vm-integrated-proof-foundation.json"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "run_label": snapshot_label or "current",
        "run_root": str(root),
        "run_dir": str(run_dir),
        "references": copied_references,
        "artifacts": {
            "vm_integrated_proof_foundation_markdown": str(markdown),
            "vm_integrated_proof_foundation_json": str(manifest),
            "latest_vm_integrated_proof_foundation_json": str(latest),
            "runtime_proof_json": str(runtime_proof),
            "capability_proof_json": str(capability_proof),
            "intake_proof_json": str(intake_proof),
            "service_permission_proof_json": str(service_permission_proof),
        },
        "components": {
            "runtime_proof": runtime_payload,
            "capability_proof": capability_payload,
            "intake_proof": intake_payload,
            "service_permission_proof": service_permission_payload,
        },
        "evidence": {
            "escalation_reasons": sorted(escalation_reasons),
            "correlation_evidence": correlation_findings,
            "combined_correlation": correlation_summary,
        },
        "summary": summary,
    }
    markdown.write_text(
        build_markdown(label=snapshot_label or "current", manifest=payload, copied_references=copied_references),
        encoding="utf-8",
    )
    manifest.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_vm_integrated_proof_foundation(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    summary = payload.get("summary") or {}
    for key in (
        "runtime_proof_ok",
        "capability_proof_ok",
        "intake_proof_ok",
        "service_permission_proof_ok",
        "correlation_evidence_present",
        "ok",
    ):
        if summary.get(key) is not True:
            errors.append(f"summary.{key} must be true")
    evidence = payload.get("evidence") or {}
    if not isinstance(evidence.get("escalation_reasons", []), list):
        errors.append("evidence.escalation_reasons must be a list")
    if not isinstance(evidence.get("correlation_evidence", []), list) or not evidence.get("correlation_evidence"):
        errors.append("evidence.correlation_evidence must be a non-empty list")
    combined = evidence.get("combined_correlation") or {}
    if combined.get("present") is not True:
        errors.append("evidence.combined_correlation.present must be true")
    return errors
