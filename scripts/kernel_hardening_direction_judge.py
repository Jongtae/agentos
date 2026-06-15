#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "agentos-hardening-direction-judge.v1"


@dataclass(frozen=True)
class SourceSnapshot:
    prd: str
    tasks: str
    roadmap: str
    ledger_lines: list[str]
    git_status: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def git_status(root: Path) -> str:
    proc = subprocess.run(
        ["git", "status", "--short", "--branch"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.stdout.strip()


def load_snapshot(root: Path) -> SourceSnapshot:
    ledger = root / "docs" / "issue-branch-ledger.jsonl"
    lines = ledger.read_text(encoding="utf-8").splitlines() if ledger.exists() else []
    return SourceSnapshot(
        prd=read_text(root / "PRD.md"),
        tasks=read_text(root / "TASKS.md"),
        roadmap=read_text(root / "docs" / "next-roadmap.md"),
        ledger_lines=lines,
        git_status=git_status(root),
    )


def current_task(tasks: str) -> str:
    match = re.search(r"Current task:\n\n- `([^`]+)`", tasks)
    return match.group(1) if match else "unknown"


def recent_task_ids(lines: list[str], limit: int = 6) -> list[str]:
    ids: list[str] = []
    for line in reversed(lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        task_id = payload.get("task_id")
        if task_id and payload.get("action") == "start":
            ids.append(str(task_id))
        if len(ids) >= limit:
            break
    return list(reversed(ids))


def contains_all(text: str, needles: list[str]) -> bool:
    lower = text.lower()
    return all(needle.lower() in lower for needle in needles)


def judge(root: Path) -> dict:
    snapshot = load_snapshot(root)
    task = current_task(snapshot.tasks)
    recent_ids = recent_task_ids(snapshot.ledger_lines)
    combined = "\n".join([snapshot.prd, snapshot.tasks, snapshot.roadmap])

    phase2_closed = "Phase 2 closeout recorded" in snapshot.roadmap
    hardening_active = "Five-minute hardening is active" in snapshot.tasks
    vm_blocker_explicit = "VM/ISO proof remains an explicit blocker" in snapshot.tasks
    runtime_first = contains_all(
        combined,
        ["managed agent runtime", "OS-native capabilities", "narrate", "recovery"],
    )
    cleanup_policy = contains_all(
        combined,
        ["cleanup_temp_artifacts.py", "cleanup_build_artifacts.py"],
    )
    later_tracks = _later_tracks(snapshot.roadmap)
    hardening_recent = [task_id for task_id in recent_ids if task_id in {"P2-24", "P2-25", "P2-26"}]

    risks: list[dict] = []
    if phase2_closed and hardening_active and len(hardening_recent) >= 2:
        risks.append(
            {
                "id": "stable-phase-repeat",
                "reason": "Recent lifecycle work is concentrated on hardening-loop maintenance after Phase 2 closeout.",
                "recovery_action": "Use a roadmap-direction judge before each autonomous pass chooses more repetition.",
            }
        )
    if not vm_blocker_explicit:
        risks.append(
            {
                "id": "implicit-vm-proof",
                "reason": "VM/ISO proof must remain explicit until observed.",
                "recovery_action": "Record VM/ISO proof as a blocker or run the VM proof flow.",
            }
        )
    if not runtime_first:
        risks.append(
            {
                "id": "runtime-direction-unclear",
                "reason": "Runtime-first completion language is missing or diluted.",
                "recovery_action": "Refresh PRD/TASKS/roadmap around managed runtime completion.",
            }
        )
    if not cleanup_policy:
        risks.append(
            {
                "id": "cleanup-policy-missing",
                "reason": "Autonomous loop does not clearly preserve temp/build cleanup policy.",
                "recovery_action": "Keep cleanup checks in every signoff-sensitive hardening pass.",
            }
        )

    blockers = []
    if "live Gmail OAuth" in snapshot.roadmap or "Gmail OAuth" in snapshot.tasks:
        blockers.append(
            {
                "id": "live-gmail-oauth",
                "reason": "Live Gmail proof requires explicit tester credentials.",
                "recovery_action": "Keep fixture/live-missing smokes automated; run live read-only proof only with provided credentials.",
            }
        )
    if "VM/ISO proof remains an explicit blocker" in snapshot.tasks:
        blockers.append(
            {
                "id": "vm-iso-proof",
                "reason": "VM/ISO proof is not complete until an observed VM run is recorded.",
                "recovery_action": "Open a VM proof issue only when a VM run can be observed, or keep the blocker explicit.",
            }
        )

    next_forward_candidates = _next_forward_candidates(snapshot, later_tracks)

    if any(risk["id"] in {"runtime-direction-unclear", "cleanup-policy-missing", "implicit-vm-proof"} for risk in risks):
        verdict = "reject"
    elif risks:
        verdict = "accept_with_risk"
    else:
        verdict = "accept"

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "reason": _reason(verdict, risks, phase2_closed),
        "current_task": task,
        "git_status": snapshot.git_status,
        "phase_focus": {
            "phase2_closeout_recorded": phase2_closed,
            "hardening_loop_active": hardening_active,
            "recent_task_ids": recent_ids,
        },
        "protected_runtime_paths": [
            "setup status and adapter recovery",
            "prompt intent classification and bounded dispatch",
            "activity narration and user-owned records",
            "Gmail read-only setup/live-missing recovery",
            "ISO/build smoke and artifact cleanup",
        ],
        "completion_tracks": later_tracks,
        "risks": risks,
        "next_forward_candidates": next_forward_candidates,
        "blockers": blockers,
        "proof": {
            "runtime_first_language_present": runtime_first,
            "cleanup_policy_present": cleanup_policy,
            "vm_iso_blocker_explicit": vm_blocker_explicit,
        },
    }


def _later_tracks(roadmap: str) -> list[dict]:
    tracks: list[dict] = []
    in_section = False
    for raw_line in roadmap.splitlines():
        line = raw_line.strip()
        if line == "## Later Tracks":
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section and line.startswith("- "):
            tracks.append({"name": line[2:], "status": "open"})
    return tracks


def _next_forward_candidates(snapshot: SourceSnapshot, later_tracks: list[dict]) -> list[dict]:
    candidates = []
    if "roadmap direction judge" not in snapshot.tasks.lower():
        candidates.append(
            {
                "id": "direction-judge-loop-gate",
                "title": "Gate autonomous hardening through roadmap direction judge output",
                "safe_without_external_state": True,
                "advances": ["OS-native runtime defaults", "runtime proof truthfulness"],
            }
        )
    track_names = " ".join(track["name"] for track in later_tracks).lower()
    if "calendar read-only" in track_names and "fixture-backed contract" not in snapshot.tasks.lower():
        candidates.append(
            {
                "id": "calendar-readonly-contract",
                "title": "Define a read-only Calendar capability contract and fixture smoke",
                "safe_without_external_state": True,
                "advances": ["capability ownership", "mediation cost reduction"],
            }
        )
    if "vm/iso proof" in track_names:
        candidates.append(
            {
                "id": "vm-proof-runbook-smoke",
                "title": "Add VM/ISO proof runbook preflight smoke without claiming observed boot proof",
                "safe_without_external_state": True,
                "advances": ["runtime proof truthfulness", "OS-native runtime defaults"],
            }
        )
    if "live gmail oauth" in track_names:
        candidates.append(
            {
                "id": "gmail-live-manual-acceptance",
                "title": "Add live Gmail read-only manual acceptance checklist and blocker capture",
                "safe_without_external_state": True,
                "advances": ["capability ownership", "runtime proof truthfulness"],
            }
        )
    return candidates


def _reason(verdict: str, risks: list[dict], phase2_closed: bool) -> str:
    if verdict == "reject":
        return "The hardening loop is missing a required direction, blocker, or cleanup invariant."
    if verdict == "accept_with_risk":
        if phase2_closed:
            return "The loop is useful, but Phase 2 is closed and recent work risks becoming validation-only repetition."
        return "The loop is useful, but open risks should steer the next safe lifecycle issue."
    return "The loop is aligned with the active roadmap and no direction drift was detected."


def main() -> int:
    parser = argparse.ArgumentParser(description="Judge whether autonomous hardening is advancing AgentOS completion.")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-on-reject", action="store_true")
    args = parser.parse_args()

    payload = judge(Path(args.root).resolve())
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(json.dumps(payload, ensure_ascii=True))
    if args.fail_on_reject and payload["verdict"] == "reject":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
