"""Shared top-level-goal invariants for delivery-governance regressions.

The delivery plan has exactly two legitimate top-level shapes:

``goal-ready``
    Exactly one top-level program is declared and armed. Goal-readiness on
    its own still selects nothing and still starts no heartbeat.

``terminal``
    The declared program closed out and no successor was selected. No
    program is declared, armed, or holding execution authority.

`AGENTS.md` contemplates both -- the delivery heartbeat "stays paused when no
top-level goal is active or after top-level closeout" -- but until
EPIC-REUSE-01 / #418 closed out there had always been exactly one active
program, so every governance test pinned the first shape only.

Relaxing those tests to ``assertIn(status, {...})`` and stopping there would
be a weakening: it would tolerate the terminal shape without checking
anything about it. So each branch below carries its own positive invariants,
and both branches share the non-execution invariants that were the point of
the original assertions.

This module is deliberately not named ``test_*``: neither ``pytest tests``
nor ``unittest discover -s tests`` collects it, so it adds no test cases.
"""
import json
import re
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "delivery-plan.yaml"

#: Iteration activation states from which `DeliveryPlan.select` can proceed
#: once `next_goal.status` becomes ``active``.
ARMED = {"owner-activated-goal-ready", "active"}
#: Program states that hold no execution authority.
TERMINAL_PROGRAM_STATUS = {"complete", "owner-paused"}
GOAL_READY = "owner-activated-goal-ready"
CLOSED_OUT = "complete"


def load_plan(path=PLAN_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def program_iterations(plan):
    """Iteration records that are themselves top-level programs.

    Only these matter for top-level quiescence. Many historical iterations
    (GOV-01, TOP-00, FILE-WS-A-01, USE-01 ...) still carry an
    ``owner-activated-goal-ready`` activation_status as a record of how they
    were once activated, so "no iteration anywhere is armed" is not, and has
    never been, true of this plan.
    """
    programs = plan.get("programs", {})
    return {item["id"]: item for item in plan["iterations"] if item.get("id") in programs}


def armed_programs(plan):
    """Top-level programs whose iteration record is ready to be selected."""
    return sorted(
        identifier
        for identifier, item in program_iterations(plan).items()
        if item.get("activation_status") in ARMED
    )


def executing_programs(plan):
    """Top-level programs that still hold execution authority."""
    return sorted(
        name
        for name, program in plan.get("programs", {}).items()
        if program.get("status") not in TERMINAL_PROGRAM_STATUS
    )


#: Programs that predate the closeout-record contract. They are recorded
#: complete without an iteration record, a `closeout` string or per-substep
#: evidence. The list is closed: a new program may not join it, so a future
#: program cannot escape the closeout requirements by omitting its iteration.
LEGACY_CLOSED_PROGRAMS = frozenset({"FILE-WORKSPACE-01"})


def closed_out_programs(plan):
    """Programs recorded complete that must carry a full closeout record."""
    programs = plan.get("programs", {})
    iterations = program_iterations(plan)
    complete = {name for name, program in programs.items() if program.get("status") == CLOSED_OUT}
    # Anything complete without an iteration record must be a named legacy
    # exemption; otherwise it is a program dodging the closeout contract.
    undocumented = sorted(complete - set(iterations) - LEGACY_CLOSED_PROGRAMS)
    if undocumented:
        raise AssertionError(
            f"programs recorded complete with no iteration record and no legacy exemption: {undocumented}"
        )
    return sorted(complete & set(iterations))


class RecordingRunner:
    """Records any external command the heartbeat attempts to run."""

    def __init__(self):
        self.calls = []

    def run(self, args, cwd=None, timeout=900):
        self.calls.append(list(args))
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def assert_heartbeat_is_paused(case, plan=None, path=PLAN_PATH):
    """Nothing is selectable and the heartbeat issues no external command.

    Runs the real `DeliveryController` against a throwaway copy of the plan,
    so this asserts the selection code's behaviour rather than restating the
    plan's own fields back at it.
    """
    from personal_agent.delivery import DeliveryController

    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder) / "repo"
        root.mkdir()
        text = json.dumps(plan) if plan is not None else Path(path).read_text(encoding="utf-8")
        (root / "delivery-plan.yaml").write_text(text, encoding="utf-8")
        runner = RecordingRunner()
        controller = DeliveryController(
            root, root / "state.json", runner, now=lambda: 1_700_000_000
        )
        case.assertIsNone(controller.plan.select({}))
        case.assertEqual(
            controller.run_once(dry_run=False)["status"], "awaiting-owner-activated-goal"
        )
        case.assertEqual(runner.calls, [])


SHA = re.compile(r"\A[0-9a-f]{7,40}\Z")


def assert_substep_evidence_is_complete(case, name, program, done, detail):
    """Every activated substep must be evidenced, by itself or by its children.

    An earlier form matched by prefix, so ``R1a`` alone satisfied ``R1``. That
    is exactly how R1c went unnoticed: R1 was split into R1a, R1b and R1c, only
    the first two ran, and the prefix test could not tell. A split must now be
    declared in ``substep_children`` and *every* declared child must carry
    evidence.
    """
    children = program.get("substep_children", {})
    unexecuted = program.get("unexecuted_substeps", {})
    for substep in program.get("ordered_substeps", []):
        if substep in done:
            continue
        declared = children.get(substep)
        case.assertTrue(
            declared,
            f"{name} closed out without evidence for {substep} and without declaring how it was split",
        )
        missing = [child for child in declared if child not in done]
        case.assertEqual(
            missing, [],
            f"{name} closed out {substep} without evidence for {missing}",
        )
        # A split that silently loses a child is the R1c failure. The full
        # child set is declared separately, and every declared child must be
        # accounted for as either evidenced or explicitly unexecuted -- so a
        # dropped child cannot be made to disappear by omitting it.
        for child in declared:
            case.assertNotIn(child, unexecuted, f"{name}: {child} is both evidenced and unexecuted")
        every_child = program.get("declared_substep_children", {}).get(substep)
        case.assertTrue(
            every_child,
            f"{name}: {substep} was split but the full child set is not declared",
        )
        unaccounted = [c for c in every_child if c not in done and c not in unexecuted]
        case.assertEqual(
            unaccounted, [],
            f"{name}: {substep} children neither evidenced nor recorded unexecuted: {unaccounted}",
        )

    # The evidence itself must be substantive, not a placeholder. The program
    # lists substep names; the iteration record carries the evidence block.
    records = detail if isinstance(detail, dict) else {}
    case.assertTrue(records, f"{name} records no per-substep evidence")
    case.assertEqual(sorted(records), sorted(done), f"{name}: evidence and completed_substeps disagree")
    seen_commits, seen_prs = set(), set()
    for substep, record in records.items():
        if not isinstance(record, dict):
            continue
        case.assertIsInstance(record.get("issue"), int, f"{name}: {substep} has no issue")
        case.assertIsInstance(record.get("pull_request"), int, f"{name}: {substep} has no pull request")
        case.assertTrue(record["issue"] > 0 and record["pull_request"] > 0, f"{name}: {substep}")
        commit = record.get("merge_commit", "")
        case.assertTrue(SHA.match(str(commit)), f"{name}: {substep} merge_commit is not a sha: {commit!r}")
        case.assertTrue(record.get("decision"), f"{name}: {substep} records no decision")
        # Distinct per substep: a block filled with one repeated value is a
        # placeholder, not evidence.
        case.assertNotIn(commit, seen_commits, f"{name}: {substep} repeats merge_commit {commit}")
        case.assertNotIn(record["pull_request"], seen_prs, f"{name}: {substep} repeats a pull request")
        seen_commits.add(commit)
        seen_prs.add(record["pull_request"])


def assert_declared_goal_shape(case, plan=None, path=PLAN_PATH):
    """Assert the plan is in exactly one legitimate shape; return its name.

    Returns ``"goal-ready"`` or ``"terminal"`` so a caller can add the
    shape-specific pins it owns. Callers must branch on the result rather
    than treating either shape as an excuse to assert nothing.
    """
    plan = load_plan(path) if plan is None else plan
    goal = plan["next_goal"]
    programs = plan["programs"]
    completed = plan["history"]["documented_completed_iterations"]
    armed = armed_programs(plan)
    executing = executing_programs(plan)

    # Only an explicit owner `active` transition authorises execution, and
    # neither legitimate resting shape is that transition.
    case.assertNotEqual(goal["status"], "active")
    case.assertIn(goal["status"], {GOAL_READY, CLOSED_OUT})

    if goal["status"] == GOAL_READY:
        shape = "goal-ready"
        # Exactly one program is declared, armed and still holding authority,
        # and it is the same program in all three views.
        case.assertIsNotNone(goal["id"])
        case.assertIn(goal["id"], programs)
        case.assertEqual(armed, [goal["id"]])
        case.assertEqual(executing, [goal["id"]])
        case.assertEqual(programs[goal["id"]]["status"], GOAL_READY)
        case.assertNotIn(goal["id"], completed)
    else:
        shape = "terminal"
        # Closed out: nothing is declared, nothing is armed, nothing holds
        # authority, and the closeout is recorded rather than merely implied.
        case.assertIsNone(goal["id"])
        case.assertEqual(armed, [])
        case.assertEqual(executing, [])
        closed = closed_out_programs(plan)
        case.assertTrue(closed, "a terminal plan must record which program closed out")
        for name in closed:
            program = programs[name]
            case.assertIn(name, completed)
            case.assertEqual(program.get("active_substeps", []), [])
            case.assertTrue(program.get("closeout"), name)
            done = program.get("completed_substeps", [])
            case.assertTrue(done, name)
            assert_substep_evidence_is_complete(
                case, name, program, done, program_iterations(plan)[name].get("completed_substeps")
            )
            # A deferred substep may never be claimed as completed.
            deferred = program.get("deferred_substeps", {}).get("substeps", [])
            case.assertFalse(set(deferred) & set(done), name)
            # Nor may an unexecuted one. Each must name a successor issue, so
            # an unfinished substep cannot be dropped silently.
            unexecuted = program.get("unexecuted_substeps", {})
            case.assertFalse(set(unexecuted) & set(done), name)
            for substep, record in unexecuted.items():
                case.assertIsInstance(record.get("successor_issue"), int,
                                      f"{name}: {substep} is unexecuted with no successor issue")
                case.assertTrue(record.get("reason"), f"{name}: {substep} is unexecuted with no reason")

    # Shared: whichever shape, the heartbeat must refuse to run.
    assert_heartbeat_is_paused(case, plan=plan)
    return shape
