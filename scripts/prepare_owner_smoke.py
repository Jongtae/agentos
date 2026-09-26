#!/usr/bin/env python3
"""Owner smoke helpers; neither starts AgentOS nor calls a provider.

Default: create NEW synthetic smoke folders and print commands.
``record-probe``: print (and save) a redacted evidence record of one Work
from an existing local store (SEC-EVAL-01 #660).
"""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]

NOTE = """# Launch review
This is synthetic test data, not a real project.
Decision: publish the local preview after the owner smoke test.
Owner: Demo User. Deadline: 2030-01-15.
Open question: does the saved result remain available after restart?
"""


def prepare(root: Path, port: int, environ: dict[str, str]) -> dict:
    if not 1024 <= port <= 65535:
        raise ValueError("Choose an unprivileged port between 1024 and 65535.")
    names = [key for key, value in environ.items() if value and (
        key == "AGENTOS_DATA" or key.startswith("AGENTOS_DRIVE_")
        or key in ("AGENTOS_ISOLATED_ENGINE_URL", "AGENTOS_PUBLIC_ACCESS_TOKEN"))]
    if names:
        raise ValueError("Use a clean shell without inherited AgentOS integration/state settings; no values were read from files.")
    root = Path(os.path.abspath(root.expanduser()))
    # No parents=True or exist_ok=True: never reuse/overwrite another installation.
    root.mkdir(mode=0o700)
    for name in ("state", "reference", "workspace"):
        (root / name).mkdir(mode=0o700)
    note = root / "reference" / "launch.md"
    with note.open("x", encoding="utf-8") as stream:
        stream.write(NOTE)
    note.chmod(0o600)
    command = shlex.join(["agentos", "start", "--host", "127.0.0.1", "--port", str(port), "--data", str(root / "state")])
    return {"root": str(root), "state": str(root / "state"),
            "reference": str(root / "reference"), "workspace": str(root / "workspace"),
            "start_command": command, "restart_command": command,
            "evidence": "synthetic_setup_only", "service_started": False,
            "provider_calls": 0, "private_data_copied": False,
            "limitations": "Not an OS sandbox or live-model test. Do not import private data or enable automatic memory writes."}


# --- SEC-EVAL-01 (#660): probe evidence records ------------------------------
#
# Reads one Work's durable rows (``jobs``, ``tool_events``, ``turn_provenance``)
# and renders what the SEC-LOOP-01 loop recorded: the owner's request, each
# tool call with provider/action and the alternative it was, the ``finish``
# claim with its cited refs, the goal judgment, the final outcome and the
# owner report.  Redaction reuses the existing passes: ``recorded_arguments``
# (typed browser text), ``redact_private_values`` (values this Work saved
# privately), ``redact_known_secrets`` (stored secret values and credential
# shapes) and ``AgentService._redact_reason`` (bearer tokens, home paths).
# Keys that name session or credential material are dropped outright.

PROBES = ("A", "B", "C", "D")
RECORD_SCHEMA = "secretary-01-probe/1"
EVIDENCE_CLASS = "owner-installation-record"
STATEMENT = ("Redacted extract of one Work from the owner's local AgentOS store. It shows what AgentOS recorded for "
             "that run: tool events, the completion claim, the goal judgment, the outcome and the owner report. "
             "External state it cites (a cart page, a reminder, sources) is as observed by AgentOS's own tools on "
             "that run. One run, not a repeated-trial measure; a fixture or this record's shape alone is not "
             "live evidence.")
#: Detail keys never copied into a record, whatever their value.
DROPPED_KEY = re.compile(r"cookie|storage|session|password|passwd|secret|token|authorization|credential|api_?key",
                         re.IGNORECASE)
#: turn_provenance fields a record keeps (no prompt envelope, no instructions).
PROVENANCE_FIELDS = ("route", "provider", "requested_model", "reported_model", "status", "goal", "build")
TEXT_FIELDS_OMITTED = "[omitted: {chars} chars, sha256 {digest}]"
#: Tool arguments that select a path rather than carry what was asked; kept
#: readable under --omit-text so the record still shows which path ran.
SELECTOR_ARGUMENTS = frozenset({"provider", "locale", "kind", "mode", "effect", "target", "predicate",
                                "location_ref", "status"})
#: Evidence keys whose string values are structure (ids, refs, action and
#: provider names, states, kinds, typed reasons); kept under --omit-text.
#: Every other string in evidence (titles, text, snippets, names, URLs) is
#: free text: a URL keeps its scheme and host, the rest is length and digest.
STRUCTURAL_EVIDENCE_KEYS = frozenset({"id", "ref", "state_ref", "draft_id", "agent_id", "root_id", "state", "status",
                                      "provider", "locale", "kind", "predicate", "action", "composed_by", "qualifiers",
                                      "freshness", "reason", "refused_because", "supersedes", "superseded", "model",
                                      "retrieved_at"})


def _import_runtime():
    try:
        import personal_agent  # noqa: F401
    except ImportError:
        sys.path.insert(0, str(ROOT / "src"))
    from personal_agent.agent_runtime import recorded_arguments, REDACTED_ARGUMENTS
    from personal_agent.browser_session import redact_private_values
    from personal_agent.conversation_projection import (REPORT_NEXT_LABEL, REPORT_QUESTION_LABEL,
                                                        REPORT_STATED_FAILED_LABEL, REPORT_UNKNOWN_LABEL,
                                                        TERMINAL_UNFINISHED_LABEL)
    from personal_agent.current_context import redact_known_secrets
    from personal_agent.quickstart_service import AgentService
    from personal_agent.quickstart_store import QuickStore
    return {"recorded_arguments": recorded_arguments, "REDACTED_ARGUMENTS": REDACTED_ARGUMENTS,
            "redact_private_values": redact_private_values, "redact_known_secrets": redact_known_secrets,
            "redact_reason": AgentService._redact_reason, "QuickStore": QuickStore,
            "labels": {"failed_steps": TERMINAL_UNFINISHED_LABEL, "failed_stated": REPORT_STATED_FAILED_LABEL,
                       "unknown": REPORT_UNKNOWN_LABEL, "question": REPORT_QUESTION_LABEL,
                       "next": REPORT_NEXT_LABEL}}


def _open_store(runtime, data: Path):
    data = Path(os.path.abspath(Path(data).expanduser()))
    # QuickStore creates a missing installation; a record reads an existing one only.
    if not (data / "private" / "quickstart.db").is_file():
        raise FileNotFoundError("No AgentOS store in the given data folder.")
    return runtime["QuickStore"](data)


def _work_private_values(store, job_id):
    """Values this Work wrote to a private store (the #605 exclusion set of
    ``agent_runtime.lookup_sources``: Memory candidates and notes)."""
    values = []
    with store.db() as db:
        values.extend(row["content"] for row in db.execute(
            "SELECT content FROM memory_candidates WHERE work_key=?", (store._work_binding(job_id),)))
        for row in db.execute("SELECT id,content FROM notes"):
            if row["id"] == job_id or row["id"] == hashlib.sha256((job_id + str(row["content"])).encode()).hexdigest():
                values.append(row["content"])
    return [value for value in values if isinstance(value, str) and value.strip()]


def _redactor(runtime, store, job_id, omit_text):
    private = _work_private_values(store, job_id)
    roots = sorted({str(store.root), str(Path(store.root).resolve())}, key=len, reverse=True)

    def text(value, free=False):
        if value is None:
            return None
        value = str(value)
        try:
            value, _count = runtime["redact_private_values"](value, private)
            value = runtime["redact_known_secrets"](store, value)
        except Exception:
            return "[redacted]"
        for root in roots:
            if len(root) > 1:
                value = value.replace(root, "[AgentOS data]")
        value = runtime["redact_reason"](value) or ""
        if free and omit_text:
            return _omitted(value)
        return value

    def tree(value, free=False):
        if isinstance(value, dict):
            return {str(key): tree(item, free) for key, item in value.items() if not DROPPED_KEY.search(str(key))}
        if isinstance(value, (list, tuple)):
            return [tree(item, free) for item in value]
        if isinstance(value, str):
            return text(value, free)
        return value

    def evidence(value, key=None):
        """An evidence tree: under --omit-text every string outside a
        structural key is free text (#660 review P1)."""
        if isinstance(value, dict):
            return {str(name): evidence(item, str(name)) for name, item in value.items()
                    if not DROPPED_KEY.search(str(name))}
        if isinstance(value, (list, tuple)):
            return [evidence(item, key) for item in value]
        if isinstance(value, str):
            return text(value, key not in STRUCTURAL_EVIDENCE_KEYS)
        return value
    return text, tree, evidence


def _omitted(value):
    """Length and digest of free text; an http(s) URL keeps scheme and host."""
    marker = TEXT_FIELDS_OMITTED.format(chars=len(value), digest=hashlib.sha256(value.encode()).hexdigest()[:16])
    try:
        parts = urlsplit(value)
    except ValueError:
        return marker
    if parts.scheme in ("http", "https") and parts.hostname and " " not in value:
        rest = value[len(f"{parts.scheme}://{parts.netloc}"):]
        host = f"{parts.scheme}://{parts.hostname}"
        if not rest or rest == "/":
            return host + rest
        return host + "/" + TEXT_FIELDS_OMITTED.format(chars=len(rest), digest=hashlib.sha256(rest.encode()).hexdigest()[:16])
    return marker


def _detail(raw):
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _report_sections(owner_cause, labels, text):
    sections = {key: [] for key in labels}
    for line in str(owner_cause or "").splitlines():
        line = line.strip()
        for key, label in labels.items():
            if line.startswith(label):
                sections[key].append(text(line[len(label):].strip(" —"), True))
                break
    return {key: value for key, value in sections.items() if value}


def _select_work(store, work):
    if work == "latest":
        rows = store.jobs()
        return rows[0] if rows else None
    return store.job(work)


def record_probe(data: Path, work: str, probe: str, recorded_at: datetime.datetime | None = None,
                 head: str | None = None, omit_text: bool = False) -> dict:
    """The redacted evidence record of one Work, for probe ``probe``.

    ``recorded_at`` (timezone-aware; default now) names the record in UTC.
    """
    if probe not in PROBES:
        raise ValueError("Probe must be one of A, B, C, D.")
    if head is not None and not re.fullmatch(r"[0-9a-f]{7,40}", head):
        raise ValueError("--head must be a git commit id.")
    recorded_at = recorded_at or datetime.datetime.now(datetime.timezone.utc)
    if not isinstance(recorded_at, datetime.datetime) or recorded_at.tzinfo is None:
        raise ValueError("recorded_at must be a timezone-aware datetime.")
    recorded_at = recorded_at.astimezone(datetime.timezone.utc)
    runtime = _import_runtime()
    store = _open_store(runtime, data)
    job = _select_work(store, work)
    if not job:
        raise LookupError("No Work with that id in this store.")
    job_id = job["id"]
    text, tree, evidence_tree = _redactor(runtime, store, job_id, omit_text)
    with store.db() as db:
        events = [dict(row) for row in db.execute(
            "SELECT tool,status,detail,created FROM tool_events WHERE job_id=? ORDER BY id", (job_id,))]
    calls, order, rejections, conclusions, stops, others, models = {}, [], [], [], [], [], []
    for event in events:
        tool, status, detail = event["tool"], event["status"], _detail(event["detail"])
        if tool == "model":
            if status == "responded":
                model = {"model": detail.get("model"), "requested_model": detail.get("requested_model")}
                if model not in models:
                    models.append(model)
            elif status == "claim_rejected":
                rejections.append({"call_id": detail.get("call_id"), "code": detail.get("code"),
                                   "evidence_refs": detail.get("evidence_refs")})
            elif status == "concluded":
                conclusions.append(detail)
            elif status == "stopped":
                stops.append({"code": detail.get("code")})
            continue
        call_id = detail.get("call_id")
        if not call_id:
            others.append({"tool": tool, "status": status})
            continue
        scope = detail.get("scope") or "main"
        key = (scope, call_id, detail.get("attempt"))
        if key not in calls:
            calls[key] = {"call_id": call_id, "tool": tool}
            if scope != "main":
                calls[key]["scope"] = scope
            order.append(key)
        row = calls[key]
        if detail.get("host_action"):
            row["host_action"] = detail["host_action"]
        if status == "running":
            action = detail.get("host_action") or tool
            arguments = detail.get("arguments") if isinstance(detail.get("arguments"), dict) else {}
            field = runtime["REDACTED_ARGUMENTS"].get(action)
            if field and not str(arguments.get(field, "")).startswith("[가림"):
                arguments = runtime["recorded_arguments"](action, arguments)
            row["arguments"] = {str(key): tree(value, key not in SELECTOR_ARGUMENTS)
                                for key, value in arguments.items() if not DROPPED_KEY.search(str(key))}
            for selector in ("provider", "locale"):
                if arguments.get(selector):
                    row[selector] = arguments[selector]
            if detail.get("alternative"):
                row["alternative"] = detail["alternative"]
        else:
            row["status"] = status
            if isinstance(detail.get("evidence"), dict):
                evidence = evidence_tree(detail["evidence"])
                row["evidence"] = evidence
                if evidence.get("provider"):
                    row["provider"] = evidence["provider"]
            for field in ("code", "retry", "requires"):
                if detail.get(field):
                    row[field] = detail[field]
            if detail.get("error"):
                row["error"] = text(detail["error"], True)
    tool_calls = [calls[key] for key in order]
    main = next((row for row in reversed(conclusions) if row.get("scope", "main") == "main"), None)
    claim = (main or {}).get("claim")
    finish = None
    if isinstance(claim, dict):
        by_id = {row["call_id"]: row for row in tool_calls if "scope" not in row}
        finish = {"status": claim.get("status"), "evidence_refs": claim.get("evidence_refs") or [],
                  "cited": [{key: by_id[ref].get(key) for key in ("call_id", "tool", "host_action", "provider",
                                                                     "status", "evidence") if key in by_id[ref]}
                            for ref in claim.get("evidence_refs") or [] if ref in by_id]}
    outcome = job.get("status")
    provenance = store.turn_provenance(job_id) or {}
    cited_ok = finish is not None and all(row.get("status") == "succeeded" for row in finish["cited"]) \
        and len(finish["cited"]) == len(finish["evidence_refs"])
    judged_done = finish is not None and finish["status"] == "done" and (main or {}).get("judgment") == "yes"
    record = {
        "record": RECORD_SCHEMA, "probe": probe, "date": recorded_at.date().isoformat(),
        "recorded_at": recorded_at.strftime("%Y-%m-%dT%H%MZ"), "evidence_class": EVIDENCE_CLASS,
        "statement": STATEMENT, "head": head,
        "work": {"id": job_id, "channel": job.get("channel"), "created": job.get("created")},
        "requested": text(job.get("message"), True),
        "models": models,
        "tool_calls": tool_calls,
        "alternatives_tried": (main or {}).get("alternatives_tried"),
        "nudges": (main or {}).get("nudges"),
        "claim_rejections": rejections,
        "finish": finish,
        "goal_judgment": (main or {}).get("judgment"),
        "final_outcome": outcome,
        "report": {"reply": text(job.get("response"), True), "observed": text(job.get("owner_verified"), True),
                   **_report_sections(job.get("owner_cause"), runtime["labels"], text),
                   "error": text(job.get("error"), True)},
        "goal_summary": provenance.get("goal"),
        "provenance": tree({key: provenance[key] for key in PROVENANCE_FIELDS
                            if key != "goal" and provenance.get(key) is not None}),
        "other_events": others,
        "stops": stops,
        "checks": {
            "succeeded_iff_judged_done_claim": (outcome == "succeeded") == judged_done or not tool_calls,
            "cited_refs_all_succeeded": cited_ok if finish and finish["status"] == "done" else None,
            "repeat_paths_refused": sum(1 for row in tool_calls if row.get("code") == "repeat_path"),
        },
        "redaction": ["typed browser text and proposed state values as length placeholders",
                      "values this Work saved to Memory candidates or notes",
                      "stored secret values and credential-shaped tokens", "bearer tokens and home paths",
                      "keys naming cookies, storage, sessions, passwords, secrets, tokens or credentials"]
                     + (["free text (request, queries, reply, report, errors, evidence titles, text and URL paths) "
                         "replaced by length and digest; URLs keep scheme and host (--omit-text)"] if omit_text else []),
    }
    return record


def record_filename(record: dict) -> str:
    """``secretary-01-probe-<P>-<UTC yyyy-mm-ddTHHMMZ>-<work8>.json``."""
    work8 = re.sub(r"[^0-9A-Za-z]", "", str(record["work"]["id"]))[:8] or "work"
    return f"secretary-01-probe-{record['probe']}-{record['recorded_at']}-{work8}.json"


def write_probe_record(record: dict, out_dir: Path) -> Path:
    """Save under ``record_filename``; exclusive creation, never overwrite a record."""
    out_dir = Path(os.path.abspath(Path(out_dir).expanduser()))
    path = out_dir / record_filename(record)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return path


def record_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="prepare_owner_smoke.py record-probe",
                                     description="Print and save a redacted evidence record of one Work (#660).")
    parser.add_argument("--data", type=Path, default=Path(os.environ.get("AGENTOS_DATA") or Path.home() / ".local/share/agentos"),
                        help="AgentOS data folder (default: AGENTOS_DATA, else ~/.local/share/agentos).")
    parser.add_argument("--work", required=True, help="Work id from 작업 현황, or 'latest'.")
    parser.add_argument("--probe", required=True, choices=PROBES)
    parser.add_argument("--head", help="git commit the installation ran (git rev-parse HEAD).")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "docs" / "evidence")
    parser.add_argument("--omit-text", action="store_true",
                        help="Replace free text (request, queries, reply, report, errors, evidence titles/text/"
                             "URL paths) with its length and digest; structure stays readable.")
    parser.add_argument("--print-only", action="store_true", help="Print without saving a file.")
    args = parser.parse_args(argv)
    try:
        record = record_probe(args.data, args.work, args.probe, None, args.head, args.omit_text)
        path = None if args.print_only else write_probe_record(record, args.out_dir)
    except (OSError, ValueError, LookupError) as exc:
        # Never echo store content, configuration or a raw OS error payload.
        print(json.dumps({"error": type(exc).__name__, "saved": False,
                          "next_action": "Check --data, --work and --probe; an existing record file is never overwritten."}))
        return 2
    print(json.dumps(record, ensure_ascii=False, indent=2))
    if path is not None:
        print(json.dumps({"saved": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name}),
              file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["record-probe"]:
        return record_main(argv[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="New directory; parent must exist. Existing roots are refused.")
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args(argv)
    try:
        result = prepare(args.root, args.port, dict(os.environ))
    except (OSError, ValueError) as exc:
        # Never dump the environment, provider config, or raw OS error payload.
        print(json.dumps({"error": type(exc).__name__, "service_started": False,
                          "next_action": "Use a new root with an existing parent, an unprivileged port, and a clean AgentOS environment."}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
