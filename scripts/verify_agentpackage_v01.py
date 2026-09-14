#!/usr/bin/env python3
"""Validate v0.1 design fixtures offline; this does not authorize or execute packages.

The immutable registry contains repository schemas only. Semantic checks establish
consistency of supplied fixture declarations, not authenticated issuer identity,
content integrity, signature validity, or a live enforcement mechanism.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = ROOT / "schemas" / "v0.1"
SCHEMA_NAMESPACE = "https://personal-agentos.dev/schemas/v0.1/"
DIALECT = "https://json-schema.org/draft/2020-12/schema"
CORE_KINDS = {"Owner", "Context", "Memory", "Artifact", "Capability", "Runtime", "Grant", "Work", "Event", "Evidence"}
KINDS = CORE_KINDS | {"ContextSnapshot", "MemoryCandidate", "AgentPackage"}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"duplicate JSON key: {name}")
        result[name] = value
    return result


def _non_json_constant(value: str) -> None:
    raise ValueError(f"non-JSON numeric constant: {value}")


def loads_strict(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_unique_object, parse_constant=_non_json_constant)


def read_json(path: Path) -> Any:
    return loads_strict(path.read_text(encoding="utf-8"))


def _deny_remote(uri: str) -> Resource:
    raise NoSuchResource(ref=uri)


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def load_validators(schema_root: Path = SCHEMA_ROOT) -> dict[str, Draft202012Validator]:
    schemas = {path.name: read_json(path) for path in sorted(schema_root.glob("*.schema.json"))}
    expected = {re.sub(r"([a-z])([A-Z])", r"\1-\2", kind).lower() + ".schema.json" for kind in KINDS}
    if set(schemas) != expected | {"common.schema.json"}:
        raise ValueError("schema inventory must contain the 10 primitives, two boundary records, AgentPackage, and common")
    registry = Registry(retrieve=_deny_remote)
    for name, schema in schemas.items():
        if schema.get("$id") != SCHEMA_NAMESPACE + name or schema.get("$schema") != DIALECT:
            raise ValueError(f"unstable schema identity or dialect: {name}")
        Draft202012Validator.check_schema(schema)
        for node in _walk(schema):
            if node.get("type") == "object" and node.get("additionalProperties") is not False:
                raise ValueError(f"open object in schema: {name}")
            if "$ref" in node and not node["$ref"].startswith(SCHEMA_NAMESPACE):
                raise ValueError(f"non-local schema reference: {name}")
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return {name: Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
            for name, schema in schemas.items()}


def schema_errors(document: dict[str, Any], validator: Draft202012Validator) -> list[str]:
    return [f"{error.json_path}: {error.message}" for error in sorted(
        validator.iter_errors(document), key=lambda error: (str(error.json_path), error.message))]


def _key(ref: dict[str, Any]) -> tuple[str, str, int]:
    return ref["kind"], ref["id"], ref["revision"]


def _refs(value: Any):
    for node in _walk(value):
        if {"kind", "id", "schemaVersion", "revision"} <= node.keys() and "createdAt" not in node:
            yield node


def _stamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _budget_subset(child: dict[str, Any], parent: dict[str, Any]) -> bool:
    return child["currency"] == parent["currency"] and all(
        value <= parent[name] for name, value in child.items() if name != "currency")


def _scope_subset(child: dict[str, Any], parent: dict[str, Any]) -> bool:
    for item in child["resources"]:
        if not any(item["resourceRef"] == other["resourceRef"] and
                   set(item["access"]) <= set(other["access"]) for other in parent["resources"]):
            return False
    for item in child["network"]:
        if not any(item["origin"] == other["origin"] and all(
            set(item[name]) <= set(other[name]) for name in ("paths", "methods", "dataCategories")
        ) for other in parent["network"]):
            return False
    if any(item not in parent["secrets"] for item in child["secrets"]):
        return False
    for name in ("read", "write", "localState"):
        if child["memory"][name] != "none" and child["memory"][name] != parent["memory"][name]:
            return False
    if not set(child["events"]["subscriptions"]) <= set(parent["events"]["subscriptions"]):
        return False
    return child["events"]["background"] == "disabled" or child["events"]["background"] == parent["events"]["background"]


def semantic_errors(records: list[dict[str, Any]], catalog: dict[str, Any]) -> list[str]:
    """Check a closed fixture graph after schema validation; return named rule failures.

    Resource bytes are detached and never fetched. References compare declarations
    of exact revisions and release/content digests; they do not hash whole records.
    """
    errors: list[str] = []

    def fail(rule: str, record: dict[str, Any], message: str) -> None:
        errors.append(f"{rule} {record.get('id', 'fixture')}: {message}")

    index: dict[tuple[str, str, int], dict[str, Any]] = {}
    for record in records:
        if _key(record) in index:
            fail("REF-001", record, "duplicate immutable record identity")
        index[_key(record)] = record
    for item in catalog["resources"]:
        reference = item["ref"]
        if _key(reference) in index:
            fail("REF-001", reference, "duplicate detached Resource identity")
        index[_key(reference)] = {**reference, "ownerRef": item["ownerRef"]}

    def resolve(ref: dict[str, Any] | None) -> dict[str, Any] | None:
        return index.get(_key(ref)) if ref is not None else None

    def owner_key(record: dict[str, Any]) -> tuple[str, str, int] | None:
        if record["kind"] == "Owner":
            return _key(record)
        return _key(record["ownerRef"]) if "ownerRef" in record else None

    def same_work(left: dict[str, Any], right: dict[str, Any]) -> bool:
        return left["workRef"]["id"] == right["workRef"]["id"]

    for record in records:
        for reference in _refs(record):
            target = resolve(reference)
            if target is None:
                fail("REF-001", record, f"unresolved exact reference {reference['id']} revision {reference['revision']}")
                continue
            if reference["kind"] in {"AgentPackage", "Runtime"}:
                if reference["releaseVersion"] != target["releaseVersion"] or reference["digest"] != target["releaseDigest"]:
                    fail("REF-002", record, "release version or detached release digest mismatch")
            elif reference["kind"] == "Resource" and reference["digest"] != target["digest"]:
                fail("REF-002", record, "detached content digest mismatch")
            if owner_key(record) is not None and owner_key(target) is not None and owner_key(record) != owner_key(target):
                fail("OWNER-001", record, "cross-owner reference")

        for name in ("expiresAt", "deadline", "leaseExpiresAt"):
            if record.get(name) is not None and _stamp(record[name]) <= _stamp(record["createdAt"]):
                fail("TIME-001", record, f"{name} must follow creation")
        if record.get("retention", {}).get("expiresAt") and _stamp(record["retention"]["expiresAt"]) <= _stamp(record["createdAt"]):
            fail("TIME-001", record, "retention expiry must follow creation")

    # Link rules operate only when targets exist, so unresolved references fail
    # clearly above rather than crashing the fixture verifier.
    for record in records:
        kind = record["kind"]
        package = resolve(record.get("packageRef"))
        runtime = resolve(record.get("runtimeRef"))
        if package is not None and runtime is not None and runtime["packageRef"] != record["packageRef"]:
            fail("LINK-001", record, "runtime belongs to a different package revision")
        provenance = record["provenance"]
        for field in ("workRef", "packageRef", "runtimeRef"):
            if field in provenance and field in record and provenance[field] != record[field]:
                fail("LINK-001", record, f"provenance {field} disagrees with record")

        if kind == "AgentPackage":
            for field, backlink in (("capabilityRefs", "packageRef"), ("runtimeRefs", "packageRef")):
                for ref in record[field]:
                    target = resolve(ref)
                    if target and _key(target[backlink]) != _key(record):
                        fail("LINK-001", record, "package member has a different package revision")
            if record["healthCheck"]["capabilityRef"] not in record["capabilityRefs"]:
                fail("LINK-001", record, "health check is not a declared capability")
        if kind == "Capability" and package is not None:
            if not set(record["actions"]) <= set(package["requestedActions"]):
                fail("LINK-001", record, "capability action exceeds manifest request")
            if any(ref not in package["runtimeRefs"] for ref in record["runtimeRefs"]):
                fail("LINK-001", record, "capability names undeclared runtime")

        if kind == "Grant":
            if _stamp(record["validFrom"]) >= _stamp(record["expiresAt"]):
                fail("TIME-001", record, "Grant validity interval is empty or reversed")
            if package and (not set(record["actions"]) <= set(package["requestedActions"]) or
                            not _scope_subset(record["scope"], package["requestedScope"]) or
                            not _budget_subset(record["budget"], package["budget"])):
                fail("GRANT-001", record, "Grant exceeds package declaration")
            parent = resolve(record["parentGrantRef"])
            if parent:
                chain, cursor = {_key(record)}, parent
                while cursor:
                    if _key(cursor) in chain:
                        fail("GRANT-002", record, "cyclic Grant delegation")
                        break
                    chain.add(_key(cursor))
                    cursor = resolve(cursor["parentGrantRef"])
                if (not set(record["actions"]) <= set(parent["actions"]) or
                    not _scope_subset(record["scope"], parent["scope"]) or
                    not _budget_subset(record["budget"], parent["budget"]) or
                    any(record[field] != parent[field] for field in ("ownerRef", "workRef", "packageRef", "runtimeRef")) or
                    _stamp(record["validFrom"]) < _stamp(parent["validFrom"]) or
                    _stamp(record["expiresAt"]) > _stamp(parent["expiresAt"])):
                    fail("GRANT-002", record, "delegated Grant is not a subset of its parent")
                if record["state"] == "active" and parent["state"] != "active":
                    fail("GRANT-003", record, "active child of inactive Grant")
            decision = resolve(record["decisionRef"])
            if decision and (decision["recordType"] != "approval" or decision["outcome"] != "approved" or decision["status"] != "sealed" or not same_work(record, decision)):
                fail("GRANT-004", record, "Grant decision is not sealed approval for this Work")
            if record["approvalRef"] is not None:
                decision = resolve(record["approvalRef"])
                if decision and (decision["recordType"] != "approval" or decision["outcome"] != "approved" or decision["recordedBy"] != "owner" or decision["status"] != "sealed" or not same_work(record, decision)):
                    fail("GRANT-004", record, "consequential approval is not owner approval for this Work")

        if kind in {"ContextSnapshot", "Work"}:
            effective = [resolve(ref) for ref in record["effectiveGrantRefs"]]
            for grant in (item for item in effective if item is not None):
                work_id = record["id"] if kind == "Work" else record["workRef"]["id"]
                newer = [item for item in records if item["kind"] == "Grant" and item["id"] == grant["id"] and item["revision"] > grant["revision"]]
                if grant["state"] != "active" or newer or not (_stamp(grant["validFrom"]) <= _stamp(catalog["asOf"]) < _stamp(grant["expiresAt"])):
                    fail("GRANT-003", record, "effective Grant is revoked, stale, expired, or not yet valid")
                if grant["workRef"]["id"] != work_id:
                    fail("WORK-001", record, "effective Grant is bound to different Work")
            if kind == "Work":
                capability = resolve(record["capabilityRef"])
                if capability and (capability["packageRef"] != record["packageRef"] or record["runtimeRef"] not in capability["runtimeRefs"] or not set(record["requestedActions"]) <= set(capability["actions"])):
                    fail("WORK-001", record, "Work capability/runtime/action binding mismatch")
                if record["state"] in {"running", "completionProposed", "completed"}:
                    if not any(grant and set(record["requestedActions"]) <= set(grant["actions"]) and
                               _scope_subset(record["scope"], grant["scope"]) and _budget_subset(record["budget"], grant["budget"]) and
                               record["packageRef"] == grant["packageRef"] and record["runtimeRef"] == grant["runtimeRef"] for grant in effective):
                        fail("WORK-002", record, "no single effective Grant covers the complete Work request")
                    if runtime and (runtime["state"] not in {"enabled", "connected"} or runtime["health"] != "passed"):
                        fail("WORK-003", record, "runtime is not enabled and healthy")
                snapshot = resolve(record["contextSnapshotRef"])
                if snapshot and snapshot["workRef"]["id"] != record["id"]:
                    fail("CONTEXT-001", record, "ContextSnapshot is bound to different Work")
                if record["leaseExpiresAt"] and _stamp(record["leaseExpiresAt"]) > _stamp(record["deadline"]):
                    fail("TIME-001", record, "Work lease exceeds deadline")
                if record["attempt"] > record["recovery"]["maxAttempts"]:
                    fail("WORK-004", record, "attempt exceeds recovery limit")
                if record["state"] == "completed":
                    for ref in record["validationEvidenceRefs"]:
                        evidence = resolve(ref)
                        if evidence and (evidence["recordType"] != "completionValidation" or evidence["status"] != "sealed" or evidence["outcome"] != "passed" or evidence["workRef"]["id"] != record["id"]):
                            fail("EVIDENCE-001", record, "completion requires sealed AgentOS validation for this Work")
            else:
                context = resolve(record["contextRef"])
                if context and (not same_work(record, context) or any(ref not in context["sourceRefs"] for ref in record["sourceRefs"]) or _stamp(record["expiresAt"]) > _stamp(context["expiresAt"])):
                    fail("CONTEXT-001", record, "snapshot expands its Context or Work boundary")

        if kind == "Memory":
            decision = resolve(record["decisionRef"])
            if decision and (decision["recordType"] != "memoryDecision" or decision["outcome"] != "approved" or decision["status"] != "sealed"):
                fail("MEMORY-001", record, "canonical Memory lacks sealed AgentOS/owner decision")
            candidate = resolve(record["acceptedCandidateRef"])
            if candidate and (candidate["state"] != "accepted" or candidate["resultingMemoryRef"] is None or _key(candidate["resultingMemoryRef"]) != _key(record)):
                fail("MEMORY-001", record, "Memory candidate disposition is not reciprocal")
        if kind == "MemoryCandidate" and record["state"] == "accepted":
            memory_record = resolve(record["resultingMemoryRef"])
            if memory_record and (memory_record["acceptedCandidateRef"] is None or _key(memory_record["acceptedCandidateRef"]) != _key(record)):
                fail("MEMORY-001", record, "accepted candidate lacks reciprocal canonical Memory decision")
        if kind == "Evidence" and record["evidenceClass"] != provenance["evidenceClass"]:
            fail("EVIDENCE-002", record, "record/provenance evidence class mismatch")

    transitions = {
        "Work": {"planned": {"ready", "cancelled"}, "ready": {"running", "waitingApproval", "cancelled"}, "running": {"waitingApproval", "completionProposed", "failed", "cancelled"}, "waitingApproval": {"ready", "running", "cancelled"}, "completionProposed": {"completed", "failed"}, "failed": {"ready", "cancelled"}, "completed": set(), "cancelled": set()},
        "Runtime": {"staged": {"installedDisabled", "quarantined"}, "installedDisabled": {"enabled", "connected", "uninstalled"}, "enabled": {"connected", "disabled", "quarantined"}, "connected": {"disabled", "quarantined"}, "disabled": {"enabled", "connected", "uninstalled"}, "quarantined": {"installedDisabled", "uninstalled"}, "uninstalled": set()},
        "Grant": {"active": {"revoked", "expired"}, "revoked": set(), "expired": set()},
        "MemoryCandidate": {"proposed": {"accepted", "rejected", "expired"}, "accepted": set(), "rejected": set(), "expired": set()},
        "Memory": {"active": {"superseded", "deleted"}, "superseded": {"deleted"}, "deleted": set()},
        "Context": {"available": {"expired", "deleted"}, "expired": {"deleted"}, "deleted": set()},
        "Artifact": {"available": {"superseded", "deleted"}, "superseded": {"deleted"}, "deleted": set()},
        "Event": {"received": {"evaluated", "ignored"}, "evaluated": {"consumed", "ignored"}, "consumed": set(), "ignored": set()},
        "Evidence": {"appended": {"sealed"}, "sealed": set()},
    }
    for transition in catalog["transitions"]:
        before, after = resolve(transition["from"]), resolve(transition["to"])
        if before is None or after is None:
            errors.append("TRANSITION-001 fixture: unresolved transition endpoint")
            continue
        state_field = "status" if before["kind"] == "Evidence" else "state"
        allowed = transitions.get(before["kind"], {}).get(before.get(state_field), set())
        if transition["actor"] != "agentos" or before["kind"] != after["kind"] or before["id"] != after["id"] or after["revision"] != before["revision"] + 1 or after.get(state_field) not in allowed:
            fail("TRANSITION-001", after, "invalid state edge, revision, identity, or transition authority")
    return sorted(set(errors))


def load_fixture_bundle(schema_root: Path = SCHEMA_ROOT):
    catalog = read_json(schema_root / "fixtures" / "catalog.json")
    documents = {entry["file"]: read_json(schema_root / "fixtures" / entry["file"]) for entry in catalog["positive"]}
    return catalog, documents


def apply_changes(value: Any, changes: list[dict[str, Any]]) -> Any:
    """Apply fixture-only set/remove operations using explicit JSON-pointer paths."""
    result = deepcopy(value)
    for change in changes:
        parts = [part.replace("~1", "/").replace("~0", "~") for part in change["path"].split("/")[1:]]
        parent = result
        for part in parts[:-1]:
            parent = parent[int(part)] if isinstance(parent, list) else parent[part]
        key = int(parts[-1]) if isinstance(parent, list) else parts[-1]
        if change["op"] == "remove":
            del parent[key]
        elif change["op"] == "set":
            parent[key] = deepcopy(change["value"])
        else:
            raise ValueError("unknown negative-fixture operation")
    return result


def verify(schema_root: Path = SCHEMA_ROOT) -> tuple[list[str], dict[str, int]]:
    validators = load_validators(schema_root)
    catalog, documents = load_fixture_bundle(schema_root)
    failures = []
    for entry in catalog["positive"]:
        failures.extend(f"positive {entry['file']}: {error}" for error in schema_errors(documents[entry["file"]], validators[entry["schema"]]))
    if failures:
        return failures, {"schemas": len(validators), "positive": len(documents), "negative": 0}
    failures.extend(semantic_errors(list(documents.values()), catalog))
    negative_path = schema_root / "fixtures" / "negative" / "cases.json"
    cases = read_json(negative_path) if negative_path.exists() else []
    for case in cases:
        changed = deepcopy(documents)
        changed_catalog = deepcopy(catalog)
        for mutation in case["mutations"]:
            if mutation["file"] == "$catalog":
                changed_catalog = apply_changes(changed_catalog, mutation["changes"])
            else:
                changed[mutation["file"]] = apply_changes(changed[mutation["file"]], mutation["changes"])
        structural = []
        for entry in changed_catalog["positive"]:
            structural.extend(schema_errors(changed[entry["file"]], validators[entry["schema"]]))
        if case["layer"] == "schema":
            if not structural:
                failures.append(f"negative {case['id']}: unexpectedly passes JSON Schema")
        elif structural:
            failures.append(f"negative {case['id']}: semantic fixture is structurally invalid: {structural[0]}")
        else:
            semantic = semantic_errors(list(changed.values()), changed_catalog)
            if not any(error.startswith(case["rule"] + " ") for error in semantic):
                failures.append(f"negative {case['id']}: expected {case['rule']}, got {semantic}")
    return failures, {"schemas": len(validators), "positive": len(documents), "negative": len(cases)}


def main() -> int:
    try:
        failures, counts = verify()
    except (ValueError, KeyError) as error:
        print(f"FAIL: {error}")
        return 1
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(f"AgentPackage v0.1 static fixtures verified: {counts['schemas']} schemas, {counts['positive']} positive, {counts['negative']} negative; no runtime/live-operation evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
