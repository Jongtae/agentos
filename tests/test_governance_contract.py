import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold())


def _assert_all(text: str, *markers: str) -> None:
    normalized = _normalize(text)
    missing = [marker for marker in markers if _normalize(marker) not in normalized]
    assert not missing, f"missing governance contract markers: {missing}"


def _assert_any(text: str, *alternatives: str) -> None:
    normalized = _normalize(text)
    assert any(_normalize(marker) in normalized for marker in alternatives), (
        f"missing every governance contract alternative: {alternatives}"
    )


def test_agents_declares_permanent_autonomous_delivery_guards() -> None:
    agents = _read("AGENTS.md")

    _assert_all(
        agents,
        "## Autonomous goal execution",
        "requested model",
        "observed execution result",
        "requirement-to-evidence audit",
        "enumerated, dependency-satisfied substep",
        "top-level goal",
        "declared authority",
        "non-goals",
    )
    _assert_any(agents, "must not select an unlisted", "may advance only")
    _assert_any(agents, "accepted setting", "tool-accepted setting")


def test_english_goal_contract_is_canonical_and_korean_reference_links_to_it() -> None:
    english = _read("docs/goal-execution-contract.en.md")
    korean = _read("docs/goal-execution-contract.ko.md")

    _assert_all(
        english,
        "## Delegation and independent review",
        "requested, accepted, and observed",
        "already enumerated, dependency-satisfied substep",
        "top-level goal",
        "requirement-to-evidence audit",
    )
    _assert_all(
        english,
        "goal-ready",
        "allowed authority",
        "non-goals",
        "evidence",
        "completion",
        "blocked",
        "automation",
    )
    _assert_all(korean, "과거 참고용 한국어 번역본", "](" + "goal-execution-contract.en.md" + ")")


def test_iteration_issue_template_collects_the_execution_contract() -> None:
    template = _read(".github/ISSUE_TEMPLATE/iteration.md")

    _assert_all(
        template,
        "## Goal-ready activation",
        "## Allowed authority",
        "## Evidence and completion audit",
        "## Delegation and independent review",
        "## Blocked / restart rule",
        "## Top-level goal / substep",
        "## Non-goals",
        "codex/",
    )


def test_ci_runs_the_governance_contract_test_as_part_of_full_pytest() -> None:
    workflow = _read(".github/workflows/validate.yml")

    # Running the whole tests directory keeps this guard in the required CI job
    # without maintaining a second, drift-prone governance-only command.
    _assert_all(workflow, "python3 -m pytest -q tests")


def test_verification_budget_requires_stable_heads_and_batched_remediation() -> None:
    agents = _read("AGENTS.md")
    goal = _read("docs/goal-execution-contract.en.md")
    pa1 = _read("docs/pa1-parallel-delivery.en.md")

    for text in (agents, goal):
        _assert_all(
            text,
            "verification budget",
            "stable",
            "focused tests",
            "coherent checkpoint",
            "batch",
            "unchanged head",
            "duplicate review",
            "poll",
            "exact-head",
            "independent review",
        )

    _assert_all(
        goal,
        "cycle 1",
        "cycle 2",
        "third or later",
        "newly discovered security",
        "unknown root cause",
        "do not run the full suite after every narrow mechanical edit",
        "never skip, weaken, relabel, or bypass",
    )
    _assert_all(
        pa1,
        "## Verification budget",
        "soft budget",
        "one review-ready broad cycle",
        "one consolidated remediation broad cycle",
        "third or later broad cycle",
        "critical",
        "auth/oauth",
        "batch findings",
    )
