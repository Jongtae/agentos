from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from kernel.event_fabric.policy_evidence import policy_evidence_report
from scripts.kernel_policy_enforced_pilot import DEFAULT_POLICY_TARGET, NEXT_POLICY_TARGET, _report as enforced_report
from scripts.kernel_policy_readiness import build_readiness_report
from scripts.kernel_policy_shadow_report import build_shadow_report

POLICY_MATURITY_SCHEMA_VERSION = "agentos-policy-maturity.v1"
POLICY_LADDER = ["shadow", "advisory", "guarded_enforce", "enforced_default"]
POLICY_TARGET_ORDER = [
    "fs_workspace_boundary",
    "network_allowlist",
    "destructive_action_approval",
]
BASELINE_CURRENT_LEVEL = {
    "fs_workspace_boundary": "guarded_enforce",
    "network_allowlist": "guarded_enforce",
    "destructive_action_approval": "advisory",
}
BASELINE_NEXT_LEVEL = {
    "fs_workspace_boundary": "enforced_default",
    "network_allowlist": "enforced_default",
    "destructive_action_approval": "guarded_enforce",
}


def _normalize_comparison_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized or "unknown"


def _readiness_bonus(readiness: dict, policy_target: str) -> int:
    ready = bool(readiness.get("ready_for_enforced_pilot", False))
    status = str(readiness.get("overall_status", "")).strip().lower()
    configured_target = str((readiness.get("enforced_pilot") or {}).get("policy_target", "")).strip()
    bonus = 0
    if ready:
        bonus += 20
    if status == "pass":
        bonus += 10
    elif status == "warn":
        bonus += 5
    if configured_target == policy_target:
        bonus += 10
    return bonus


def _shadow_bonus(policy_item: dict) -> int:
    comparison = policy_item.get("comparison", {}) or {}
    aligned = bool(comparison.get("aligned", False))
    delta = abs(int(comparison.get("delta", 0) or 0))
    if aligned:
        return 35
    return max(5, 20 - min(delta * 5, 15))


def _enforcement_bonus(enforced_status: dict, policy_target: str) -> int:
    effective_enabled = bool(enforced_status.get("effective_enabled", False))
    configured_enabled = bool(enforced_status.get("configured_enabled", False))
    configured_target = str(enforced_status.get("policy_target", "")).strip()
    if configured_target != policy_target:
        return 5 if configured_enabled else 0
    if effective_enabled:
        return 35
    if configured_enabled:
        return 20
    return 10


def _tracking(policy_item: dict) -> tuple[dict, dict]:
    comparison = policy_item.get("comparison", {}) or {}
    delta = int(comparison.get("delta", 0) or 0)
    aligned = bool(comparison.get("aligned", False))
    shadow_count = int(policy_item.get("shadow_detected_count", 0) or 0)
    userspace_count = int(policy_item.get("user_space_blocked_count", 0) or 0)
    false_positive_count = max(0, delta)
    false_deny_count = max(0, -delta)
    false_positive = {
        "count": false_positive_count,
        "status": "none" if false_positive_count == 0 else "attention_required",
        "summary": (
            "shadow detection is aligned with user-space evidence"
            if aligned or false_positive_count == 0
            else "shadow detection exceeds user-space evidence and may need tighter filters"
        ),
        "shadow_detected_count": shadow_count,
        "user_space_blocked_count": userspace_count,
    }
    false_deny = {
        "count": false_deny_count,
        "status": "none" if false_deny_count == 0 else "attention_required",
        "summary": (
            "user-space evidence is aligned with shadow detection"
            if aligned or false_deny_count == 0
            else "user-space blocking exceeds shadow detection and may indicate missing kernel-path coverage"
        ),
        "shadow_detected_count": shadow_count,
        "user_space_blocked_count": userspace_count,
    }
    return false_positive, false_deny


def _ladder_recommendation(readiness_score: int, current_level: str) -> str:
    if readiness_score >= 90 and current_level != "enforced_default":
        return "promote"
    if readiness_score >= 70:
        return "monitor"
    return "stabilize"


def build_policy_maturity_report(
    workspace: str,
    *,
    policy_dir: str = "artifacts/kernel-policy",
    parser_cmd: str = "apparmor_parser",
) -> dict:
    workspace_path = Path(workspace).resolve()
    shadow = build_shadow_report(workspace=str(workspace_path))
    readiness = build_readiness_report(workspace=str(workspace_path), policy_dir=policy_dir, parser_cmd=parser_cmd)
    evidence = policy_evidence_report(workspace_path)

    enforced_by_target: dict[str, dict] = {}
    for target in POLICY_TARGET_ORDER:
        effective_target = target if target in {DEFAULT_POLICY_TARGET, NEXT_POLICY_TARGET, "network_allowlist"} else DEFAULT_POLICY_TARGET
        enforced_by_target[target] = enforced_report(
            action="status",
            workspace_dir=workspace_path,
            config={
                "enabled": True,
                "policy_target": effective_target,
                "updated_at_utc": "",
            },
            mechanism={
                "type": "apparmor",
                "ready_for_enforced_pilot": bool(readiness.get("ready_for_enforced_pilot", False)),
                "policy_dir": str((workspace_path / policy_dir).resolve()) if not Path(policy_dir).is_absolute() else str(Path(policy_dir).resolve()),
                "profile_exists": True,
                "parser_available": True,
            },
        )

    shadow_targets = {item.get("policy_target", ""): item for item in shadow.get("policy_targets", [])}
    evidence_targets = {item.get("policy_target", ""): item for item in evidence.get("policy_targets", [])}

    targets: list[dict] = []
    for target in POLICY_TARGET_ORDER:
        shadow_item = shadow_targets.get(target, {"comparison": {"aligned": False, "delta": 0, "status": "unknown"}})
        evidence_item = evidence_targets.get(target, {})
        readiness_score = min(
            100,
            _shadow_bonus(shadow_item)
            + _readiness_bonus(readiness, target)
            + _enforcement_bonus(enforced_by_target[target], target),
        )
        false_positive, false_deny = _tracking(shadow_item)
        current_level = BASELINE_CURRENT_LEVEL[target]
        next_level = BASELINE_NEXT_LEVEL[target]
        targets.append(
            {
                "policy_target": target,
                "current_level": current_level,
                "next_level": next_level,
                "readiness_score": readiness_score,
                "recommendation": _ladder_recommendation(readiness_score, current_level),
                "comparison_status": _normalize_comparison_status((shadow_item.get("comparison") or {}).get("status", "")),
                "readiness_inputs": {
                    "shadow_aligned": bool((shadow_item.get("comparison") or {}).get("aligned", False)),
                    "shadow_delta": int((shadow_item.get("comparison") or {}).get("delta", 0) or 0),
                    "readiness_overall_status": readiness.get("overall_status", "unknown"),
                    "ready_for_enforced_pilot": bool(readiness.get("ready_for_enforced_pilot", False)),
                    "evidence_status": str(evidence_item.get("status", "")) or "unknown",
                    "enforced_effective_enabled": bool(enforced_by_target[target].get("effective_enabled", False)),
                },
                "false_positive_tracking": false_positive,
                "false_deny_tracking": false_deny,
            }
        )

    level_counts = {level: 0 for level in POLICY_LADDER}
    for item in targets:
        level_counts[item["current_level"]] += 1

    return {
        "ok": True,
        "exit_code": 0,
        "schema_version": POLICY_MATURITY_SCHEMA_VERSION,
        "workspace": str(workspace_path),
        "ladder": POLICY_LADDER,
        "targets": targets,
        "summary": {
            "policy_target_count": len(targets),
            "level_counts": level_counts,
            "average_readiness_score": round(sum(item["readiness_score"] for item in targets) / len(targets), 2),
            "promotion_candidates": [item["policy_target"] for item in targets if item["recommendation"] == "promote"],
            "stabilization_candidates": [item["policy_target"] for item in targets if item["recommendation"] == "stabilize"],
        },
        "readiness_baseline": {
            "overall_status": readiness.get("overall_status", "unknown"),
            "operator_state": readiness.get("operator_state", "unknown"),
            "ready_for_enforced_pilot": bool(readiness.get("ready_for_enforced_pilot", False)),
        },
    }
