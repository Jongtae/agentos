#!/usr/bin/env python3
"""Verify canonical internal documents and their historical Korean references."""
from pathlib import Path
import re
import json


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
TRANSLATION_REFERENCES = (
    ("personal-ai-assistant-vision.ko.md", "personal-ai-assistant-vision.en.md"),
    ("master-plan-01-personal-assistant-core.ko.md", "master-plan-01-personal-assistant-core.en.md"),
    ("master-plan-02-proposal.ko.md", "master-plan-02-proposal.en.md"),
    ("d-mp2-01-conversation-settings-contract.ko.md", "d-mp2-01-conversation-settings-contract.en.md"),
    ("d-mp2-02-capability-discovery-contract.ko.md", "d-mp2-02-capability-discovery-contract.en.md"),
    ("d-mp2-03-personal-knowledge-retrieval-contract.ko.md", "d-mp2-03-personal-knowledge-retrieval-contract.en.md"),
    ("mp1-d01-personal-space-contract.ko.md", "mp1-d01-personal-space-contract.en.md"),
    ("mp1-d02-capability-lifecycle.ko.md", "mp1-d02-capability-lifecycle.en.md"),
    ("mp1-d03-drive-contract.ko.md", "mp1-d03-drive-contract.en.md"),
    ("development-governance.ko.md", "development-governance.en.md"),
    ("goal-execution-contract.ko.md", "goal-execution-contract.en.md"),
    ("top-level-specification-completion.ko.md", "top-level-specification-completion.en.md"),
    ("mp1-d04-a2a-delegation-contract.ko.md", "mp1-d04-a2a-delegation-contract.en.md"),
    ("mp1-d05-calendar-contract.ko.md", "mp1-d05-calendar-contract.en.md"),
    ("mp1-d06-react-release-contract.ko.md", "mp1-d06-react-release-contract.en.md"),
    ("mp1-remediation.ko.md", "mp1-remediation.en.md"),
    ("subscription-telegram-stabilization-contract.ko.md", "subscription-telegram-stabilization-contract.en.md"),
    ("operating-deployment-preparation-contract.ko.md", "operating-deployment-preparation-contract.en.md"),
    ("op-02-operating-readiness-remediation-contract.ko.md", "op-02-operating-readiness-remediation-contract.en.md"),
    ("scn-d01-first-live-use-scenarios-contract.ko.md", "scn-d01-first-live-use-scenarios-contract.en.md"),
    ("drive-telegram-web-oauth-contract.ko.md", "drive-telegram-web-oauth-contract.en.md"),
    ("file-workspace-first-experience-contract.ko.md", "file-workspace-first-experience-contract.en.md"),
    ("core-primitives-agentpackage-v0.1.ko.md", "core-primitives-agentpackage-v0.1.en.md"),
    ("web-management-contract.ko.md", "web-management-contract.en.md"),
)
KOREAN_REFERENCE_EXCLUSIONS = {
    "agentos-hub-v2.ko.md", "b3os-design-reference.ko.md", "context-capture-idea.ko.md",
    "first-milestone-report.ko.md", "ux-06-telegram-conversation.ko.md",
    "ux-v1.1-personal-agent-dm.ko.md",
}
PHASE_IDS = ("D-01", "I-01", "D-02", "I-02", "D-03", "I-03", "D-04", "I-04", "D-05", "I-05", "D-06", "I-06")


def links(text):
    return re.findall(r"\[[^]]+\]\(([^)#]+)(?:#[^)]+)?\)", text)


def phase_table_ids(text):
    rows = re.findall(r"^\| [1-6]\. .*\|.*\|.*\|$", text, flags=re.MULTILINE)
    return tuple(re.findall(r"\b[DI]-\d{2}\b", "\n".join(rows)))


def verify_traceability(plan):
    iterations={item["id"]:item for item in plan["iterations"]}
    for ident, item in iterations.items():
        if item.get("kind") != "design":
            continue
        implementation=item.get("implementation_id")
        contract=item.get("contract")
        if not isinstance(implementation,str) or implementation not in iterations or not isinstance(contract,str) or not (DOCS / contract).is_file():
            raise SystemExit(f"design traceability failure: {ident}")
        delivery=iterations[implementation]
        if delivery.get("kind") not in {"implementation", "release"} or delivery.get("design_id") != ident or delivery.get("contract") != contract or not delivery.get("automated_evidence"):
            raise SystemExit(f"implementation traceability failure: {implementation}")
    claims=plan.get("completion_claims", {})
    completed=set(plan.get("history", {}).get("documented_completed_iterations", []))
    for claim_id, claim in claims.items():
        if not isinstance(claim, dict) or claim.get("status") != "development_complete":
            continue
        required=claim.get("required_implementation_ids", [])
        if claim_id != "TOP" and (not isinstance(required, list) or not required or any(ident not in iterations or ident not in completed for ident in required)):
            raise SystemExit(f"completion claim lacks implemented automated evidence: {claim_id}")
        if claim_id != "TOP":
            continue
        required_top = ("TOP-00", "TOP-01", "TOP-02", "TOP-03")
        if (tuple(required) != required_top or any(ident not in iterations for ident in required_top) or
                any(ident not in completed for ident in required_top)):
            raise SystemExit("TOP completion claim lacks every ordered substep")
        requirements = claim.get("requirements")
        if not isinstance(requirements, dict):
            raise SystemExit("TOP completion claim lacks requirement evidence")
        implementation_ids = set(claim.get("implementation_requirement_ids", []))
        owner_ids = set(claim.get("owner_operating_requirement_ids", []))
        decision_ids = set(claim.get("separate_owner_product_decision_ids", []))
        required_implementation_ids = {"CORE-01", "CORE-02", "MP2-01", "STAB-01", "DEPLOY-01", "GOV-01", "STATUS-01"}
        required_owner_ids = {"OWNER-01"}
        required_decision_ids = {"LEGACY-01"}
        if (implementation_ids != required_implementation_ids or owner_ids != required_owner_ids or
                decision_ids != required_decision_ids):
            raise SystemExit("TOP completion claim misclassifies a requirement")
        if (not implementation_ids or not owner_ids or not decision_ids or implementation_ids & owner_ids or
                implementation_ids & decision_ids or owner_ids & decision_ids):
            raise SystemExit("TOP completion claim has invalid requirement ownership")
        if set(requirements) != implementation_ids | owner_ids | decision_ids:
            raise SystemExit("TOP completion claim omits a requirement")
        for ident in implementation_ids:
            evidence = requirements.get(ident)
            references = evidence.get("evidence") if isinstance(evidence, dict) else None
            if (not isinstance(evidence, dict) or evidence.get("status") != "merged-current-evidence" or
                    not isinstance(references, list) or not references or
                    any(not isinstance(reference, str) or not reference.strip() for reference in references)):
                raise SystemExit(f"TOP implementation requirement is not evidenced: {ident}")
        for ident in owner_ids:
            action = requirements.get(ident)
            if not isinstance(action, dict) or action.get("status") != "owner-operating-action" or not isinstance(action.get("action"), str) or not action["action"]:
                raise SystemExit(f"TOP owner requirement is misclassified: {ident}")
        for ident in decision_ids:
            decision = requirements.get(ident)
            if not isinstance(decision, dict) or decision.get("status") != "separate-owner-product-decision" or not isinstance(decision.get("decision"), str) or not decision["decision"]:
                raise SystemExit(f"TOP product decision is not recorded: {ident}")
        candidate = claim.get("deployment_candidate")
        if not isinstance(candidate, dict) or not isinstance(candidate.get("commit"), str) or not re.fullmatch(r"[0-9a-f]{40}", candidate["commit"]):
            raise SystemExit("TOP completion claim lacks an immutable deployment candidate")
        checks = candidate.get("required_ci")
        if (not isinstance(checks, list) or not checks or
                any(not isinstance(check, dict) or not isinstance(check.get("name"), str) or not check["name"].strip() or
                    check.get("conclusion") != "success" or check.get("commit") != candidate["commit"] for check in checks) or
                claim.get("unresolved_review_findings") != []):
            raise SystemExit("TOP completion claim lacks current verification evidence")


def verify_document_references(documents=DOCS, references=TRANSLATION_REFERENCES):
    for korean, english in references:
        ko_path, en_path = documents / korean, documents / english
        if not en_path.is_file():
            raise SystemExit(f"missing English canonical document: {english}")
        if not ko_path.is_file():
            raise SystemExit(f"missing historical Korean reference: {korean}")
        ko = ko_path.read_text(encoding="utf-8")
        en = en_path.read_text(encoding="utf-8")
        if f"]({english})" not in ko:
            raise SystemExit(f"historical Korean reference lacks English canonical link: {korean}")
        for text, source in ((en, english), (ko, korean)):
            for link in links(text):
                if not (documents / link).is_file():
                    raise SystemExit(f"missing local link in {source}: {link}")


def verify_reference_registry(documents=DOCS, references=TRANSLATION_REFERENCES,
                              exclusions=KOREAN_REFERENCE_EXCLUSIONS):
    paired = {
        korean.name for korean in documents.glob("*.ko.md")
        if korean.with_name(korean.name.replace(".ko.md", ".en.md")).is_file()
    }
    registered = {korean for korean, _ in references}
    expected = paired - set(exclusions)
    if registered != expected:
        raise SystemExit("Korean reference registry does not cover every eligible internal pair")


def main():
    verify_reference_registry()
    verify_document_references()
    mp1_en = (DOCS / TRANSLATION_REFERENCES[1][1]).read_text(encoding="utf-8")
    if phase_table_ids(mp1_en) != PHASE_IDS:
        raise SystemExit(f"MP1 phase table sequence failure: {TRANSLATION_REFERENCES[1][1]}")
    plan=json.loads((ROOT / "delivery-plan.yaml").read_text(encoding="utf-8"))
    verify_traceability(plan)
    workspace_contract = (DOCS / "file-workspace-first-experience-contract.en.md").read_text(encoding="utf-8")
    if ("FILE-WS-A-01" not in workspace_contract or "FILE-WS-B-01" not in workspace_contract or
            "FILE-WS-C-01" not in workspace_contract or "FILE-UX-" in workspace_contract):
        raise SystemExit("file-workspace contract substep identifiers do not match the delivery plan")
    workspace_program = plan.get("programs", {}).get("FILE-WORKSPACE-01", {})
    workspace_design = plan["iterations"][next(index for index, item in enumerate(plan["iterations"])
                                                if item["id"] == "FILE-WS-A-01")]
    if (not isinstance(workspace_program.get("issue"), int) or
            workspace_program["issue"] == workspace_design.get("issue")):
        raise SystemExit("file-workspace program and active substep require distinct issue records")
    print("Canonical internal documents and historical Korean references verified")


if __name__ == "__main__":
    main()
