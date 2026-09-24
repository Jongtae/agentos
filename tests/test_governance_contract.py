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


def test_github_is_authoritative_for_execution_status_and_plans_are_not_status_mirrors() -> None:
    agents = _read("AGENTS.md")
    goal = _read("docs/goal-execution-contract.en.md")
    governance = _read("docs/development-governance.en.md")
    incremental = _read("docs/incremental-delivery.en.md")

    for text in (agents, governance, incremental):
        _assert_all(
            text,
            "GitHub Issues, Pull Requests",
            "authoritative for execution status",
        )

    _assert_all(
        agents,
        "`delivery-plan.yaml` is authoritative for active goal selection",
        "duplicate database",
        "Do not create a follow-up commit or pull request solely",
        "scope, sequencing, dependency, authority, acceptance criteria, milestone, activation, re-scope, blocker/disposition, next-goal selection",
    )
    _assert_all(
        goal,
        "does not mirror GitHub PR/Issue status",
        "Never create a follow-up commit or PR whose sole purpose is to mirror",
        "GitHub-native merge/Issue/Check status does not require tracker/roadmap/ledger mirroring",
        "Do not require or create a tracker/roadmap/ledger update solely to mirror GitHub execution status",
    )
    _assert_all(
        governance,
        "they are not a second database of GitHub status",
        "Do not create a follow-up commit or pull request solely",
    )
    _assert_all(
        incremental,
        "do not create a follow-up commit or PR solely",
        "`delivery-plan.yaml`",
        "`TASKS.md`",
        "`docs/roadmap.md`",
        "a ledger",
    )

    stale_goal_rules = (
        "tracker/roadmap/ledger closeout",
        "update `TASKS.md`, `docs/roadmap.md`, and the ledger together",
    )
    normalized_goal = _normalize(goal)
    for stale in stale_goal_rules:
        assert _normalize(stale) not in normalized_goal, (
            f"goal execution contract still requires redundant status mirroring: {stale}"
        )


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
        "re-review only when the remediation changes the boundary that triggered review",
        "mechanical or non-boundary remediation does not automatically reopen independent review",
        "consolidated final remediation head",
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
        "any post-review pa1 commit",
        "consolidated final head",
    )



def test_independent_review_is_risk_based_not_default_completion_gate() -> None:
    agents = _read("AGENTS.md")
    constitution = _read("docs/development-constitution.en.md")
    goal = _read("docs/goal-execution-contract.en.md")
    incremental = _read("docs/incremental-delivery.en.md")
    usefulness = _read("docs/default-agent-usefulness.en.md")
    handoff = _read("docs/agent-handoff-loop.en.md")

    _assert_all(
        agents,
        "Independent review is required only for a material security/authority boundary change",
        "OAuth",
        "sandbox/isolation/privilege",
        "private-data egress",
        "supply-chain",
        "safety invariant",
        "Recovery work requires independent review only when it changes one of those semantics",
        "Final completion",
        "do not trigger review by themselves",
    )
    _assert_all(
        constitution,
        "Independent review is a risk-based escalation control",
        "OAuth scopes or credential boundaries",
        "sandbox, isolation or privilege boundaries",
        "private-data egress or external-recipient boundaries",
        "package/dependency supply-chain trust or install/update authority",
        "safety invariant",
        "does not require independent review merely because it is final closeout, recovery work",
        "requires re-review only if that remediation changes the boundary that triggered the review",
    )
    _assert_all(
        goal,
        "Ordinary recovery, final completion",
        "do not trigger review by themselves",
        "Re-review only when the remediation changes the boundary that triggered review",
        "mechanical or non-boundary remediation does not automatically reopen independent review",
    )
    _assert_all(
        incremental,
        "only when the Development Constitution's material security/authority escalation criteria apply",
        "otherwise proceed with required CI and evidence without a review gate",
        "risk-triggered review",
        "validated full head SHA",
    )
    _assert_all(
        usefulness,
        "required CI and any independent review triggered by the Development Constitution's material security/authority escalation criteria",
    )
    _assert_all(
        handoff,
        "independent_review_required",
        "Omission fails closed to `true`",
        "routine, non-boundary candidate directly",
        "`agent:review`",
        "Issue text cannot grant itself a review bypass",
    )


def test_claude_bootstrap_points_at_no_completed_program() -> None:
    """The first file a Claude session reads must not name finished work.

    It used to. `CLAUDE.md` told every session to read the EPIC-PA1 / #386
    execution cursor first and to update that cursor after any state
    transition -- long after #386 closed, its execution authority was retired
    (GOV-PA1-07 / #467) and `next_goal.id` became `null`. No runtime effect,
    because `DeliveryPlan.select` refuses completed work outright, but it
    pointed a fresh session at a completed program as the place to look for
    the next action. That is the re-selection risk arriving through
    documentation instead of through the controller.
    """
    claude = _read("CLAUDE.md")

    # No program identity is hardcoded here. A program that wants a resume
    # source defines its own; this file must not name one, and must not
    # outlive the program it named.
    for stale in ("#386", "EPIC-PA1", "agentos-execution-cursor"):
        assert _normalize(stale) not in _normalize(claude), (
            f"CLAUDE.md still names {stale}; a bootstrap must not point at a "
            "specific program, least of all a closed one"
        )

    # Fail closed, stated rather than implied.
    _assert_all(
        claude,
        "next_goal",
        "no work is selected",
        "do not infer one from open issues",
    )
    _assert_any(
        claude,
        "only an explicit owner `active` transition authorises execution",
        "only an explicit owner `active` transition authorizes execution",
    )


def test_following_the_bootstrap_selects_nothing_while_no_goal_is_active() -> None:
    """The behavioural half: do what CLAUDE.md says and get nothing.

    The document assertions above would pass against a file that said the
    right words over a plan that still handed out work. This walks the
    bootstrap's own stated route -- read `next_goal`, and select only on an
    explicit `active` transition -- against the real plan and the real
    controller.
    """
    import json

    from scripts.dev.delivery import DeliveryPlan

    plan_path = ROOT / "delivery-plan.yaml"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))

    # Step 3 of the bootstrap. Step 4 covers both "no top-level goal is
    # active" forms: `next_goal.id` is null, OR its status is not `active`.
    # An earlier form pinned `id is None`, i.e. the first form only, and so
    # broke as soon as the owner declared a goal-ready program (GOV-FU1-01 /
    # #502). Each form is now asserted in full for whichever one holds.
    declared = plan["next_goal"]["id"]
    assert plan["next_goal"]["status"] != "active"
    if declared is None:
        assert plan["next_goal"]["status"] == "complete"
    else:
        # A declared goal is goal-ready only: a real program, not recorded
        # complete, awaiting the explicit owner `active` transition.
        assert plan["next_goal"]["status"] == "owner-activated-goal-ready"
        assert declared in plan["programs"]
        assert declared not in plan["history"]["documented_completed_iterations"]

    # Step 4: nothing is selected, and nothing in the backlog substitutes.
    assert DeliveryPlan(plan_path).select({}) is None

    # And not merely because the runtime state happens to be empty: a
    # populated or corrupt state must not change the answer either --
    # including a runtime state that claims the declared goal is running.
    states = [{}, {"completed": []}, {"active": "EPIC-PA1", "status": "running"}]
    if declared is not None:
        states.append({"active": declared, "status": "running"})
    for state in states:
        assert DeliveryPlan(plan_path).select(state) is None, state
