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

The same mistake then recurred one level down. The callers kept asserting
*which named program* held which role -- EPIC-PA1 is the paused one,
EPIC-REUSE-01 is the active one -- which was true when written and stopped
being true the moment the owner swapped the roles (#443). Most failed loudly.
One did not fail at all: it iterated the live plan's paused programs, and when
the only paused program resumed the loop emptied and it passed while asserting
nothing.

So roles are now derived from the plan ("the declared program", "the paused
programs", "the closed-out programs") and the *full* invariant is asserted
for whichever program currently holds each role. Two rules keep that from
becoming a relaxation:

* a role check may never be satisfiable by an empty subject set -- if no
  program currently holds a role that must remain tested, the scenario is
  constructed (see ``synthetic_paused_program``);
* "nothing terminal may execute" cannot be derived from the status field
  alone, because ``executing_programs`` is defined by that same field and
  the check would be a tautology. ``programs_barred_from_authority``
  therefore derives the bar from independent records -- completion history,
  ``complete-on-merge`` iterations, and unresumed ``paused_by`` records.

This module is deliberately not named ``test_*``: neither ``pytest tests``
nor ``unittest discover -s tests`` collects it, so it adds no test cases.
"""
import contextlib
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
PAUSED = "owner-paused"
CLOSED_ON_MERGE = "complete-on-merge"


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


def paused_programs(plan):
    """Programs currently recorded ``owner-paused``."""
    return sorted(
        name
        for name, program in plan.get("programs", {}).items()
        if program.get("status") == PAUSED
    )


def assert_activation_record(case, label, record):
    """A pause or resume record must be auditable, not a truthy placeholder.

    These records are the only thing that distinguishes an owner-directed
    role change from a program quietly regaining authority, so a bare
    ``True`` or empty dict must not satisfy one.
    """
    case.assertIsInstance(record, dict, label)
    case.assertIsInstance(record.get("issue"), int, f"{label} names no issue")
    case.assertTrue(record["issue"] > 0, label)
    reason = record.get("reason")
    case.assertIsInstance(reason, str, f"{label} records no reason")
    # No test can confirm an issue exists on GitHub, so the reason is the only
    # part a reader can audit. "x" is truthy and tells them nothing.
    case.assertGreaterEqual(len(reason.strip()), MIN_REASON_CHARS,
                            f"{label} reason is a placeholder, not a record: {reason!r}")


#: A reason shorter than this is a placeholder. The bar is deliberately low --
#: it excludes "x" and "ok", not terse honesty.
MIN_REASON_CHARS = 24


def is_resumed(program):
    """True when an owner explicitly reactivated a previously paused program.

    The resuming issue may not be the pausing issue: a program cannot lift its
    own pause, which is the most literal form of self-authorisation.
    """
    record = program.get("reactivated_by")
    paused_by = program.get("paused_by")
    if not (isinstance(record, dict)
            and isinstance(record.get("issue"), int)
            and record["issue"] > 0
            and isinstance(record.get("reason"), str)
            and len(record["reason"].strip()) >= MIN_REASON_CHARS):
        return False
    if isinstance(paused_by, dict) and record["issue"] == paused_by.get("issue"):
        return False
    return True


def programs_barred_from_authority(plan):
    """Programs that evidence *other than their own status* says must be quiet.

    Deriving this from ``programs[*]["status"]`` alone would be circular --
    ``executing_programs`` is defined by that same field, so "no paused
    program executes" would be a tautology. The name pins these tests used
    to carry (``assertNotIn("EPIC-PA1", executing)``) were not tautological
    precisely because they came from outside the status field.

    So each rule below is an independent record that contradicts execution:

    * the program is listed in the documented completion history;
    * its iteration is recorded ``complete-on-merge``;
    * it carries a ``paused_by`` record and no owner ``reactivated_by``.

    Returns ``{name: reason}``. A program escapes only by an explicit,
    auditable owner record -- which is the transition these tests exist to
    make visible rather than to forbid.
    """
    programs = plan.get("programs", {})
    iterations = program_iterations(plan)
    documented = set(plan.get("history", {}).get("documented_completed_iterations", []))
    barred = {}
    for name, program in programs.items():
        if name in documented:
            barred[name] = "is recorded in the documented completion history"
        elif iterations.get(name, {}).get("activation_status") == CLOSED_ON_MERGE:
            barred[name] = "has an iteration recorded complete-on-merge"
        elif program.get("paused_by") and not is_resumed(program):
            barred[name] = "carries a pause record and no owner reactivation record"
    return barred


def assert_no_unauthorised_execution_authority(case, plan):
    """No program may execute or be declared unless it currently may.

    Two independent halves:

    1. Nothing whose recorded status is terminal (paused or complete) may be
       the declared goal or appear in ``executing``.
    2. Nothing that outside evidence bars (see
       ``programs_barred_from_authority``) may hold a non-terminal status,
       execute, be declared, or keep substeps in flight.

    Half 2 is what replaced the ``EPIC-PA1`` name pins. It is strictly wider:
    the pins guarded one named program, this guards every program that has
    ever been closed out or paused, in whichever direction the cast moves.
    """
    programs = plan.get("programs", {})
    goal_id = plan.get("next_goal", {}).get("id")
    executing = executing_programs(plan)

    for name in sorted(programs):
        if programs[name].get("status") in TERMINAL_PROGRAM_STATUS:
            # Only the declared-goal half is assertable here. "a terminal
            # program is not in `executing`" cannot fail: executing_programs
            # is *defined* as "status not in TERMINAL_PROGRAM_STATUS", so it
            # would restate its own input. The status-independent bar below is
            # what actually catches a quiet program holding authority.
            case.assertNotEqual(goal_id, name, f"{name} is terminal but is the declared goal")

    for name, reason in sorted(programs_barred_from_authority(plan).items()):
        program = programs[name]
        case.assertIn(program.get("status"), TERMINAL_PROGRAM_STATUS,
                      f"{name} {reason} but its status is {program.get('status')!r}")
        case.assertNotIn(name, executing, f"{name} {reason} but holds execution authority")
        case.assertNotEqual(goal_id, name, f"{name} {reason} but is the declared goal")
        if "active_substeps" in program:
            case.assertEqual(program["active_substeps"], [],
                             f"{name} {reason} but keeps substeps in flight")
        iteration = program_iterations(plan).get(name)
        if iteration is not None:
            case.assertNotIn(iteration.get("activation_status"), ARMED,
                             f"{name} {reason} but its iteration is armed for selection")


@contextlib.contextmanager
def plan_file(plan):
    """Write a plan variant to a throwaway path for the real loader to read."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "delivery-plan.yaml"
        path.write_text(json.dumps(plan), encoding="utf-8")
        yield path


SYNTHETIC_PAUSED = "SYNTHETIC-PAUSED-01"


def synthetic_paused_program(plan, name=SYNTHETIC_PAUSED):
    """Build a paused top-level program so the pause rule is always testable.

    The pause regressions used to iterate the live plan's paused programs.
    ``test_a_paused_program_holds_no_running_work`` had no guard against an
    empty subject set, so when the owner resumed the only paused program it
    passed while asserting nothing. Its sibling
    ``test_a_paused_program_cannot_be_selected_even_if_redeclared_active`` did
    have a guard and failed loudly -- but a guard only converts an evaporated
    test into a broken one. The scenario is constructed here instead, so it
    survives a role swap in either direction, and the real paused programs are
    checked in addition to it rather than instead of it.

    The record is deliberately selectable-if-unpaused: its dependency is
    drawn from the documented completion history, so the only thing stopping
    selection is the pause itself. ``assert_pause_survives_redeclaration``
    proves that with a positive control.
    """
    altered = json.loads(json.dumps(plan))
    iteration_ids = {item["id"] for item in altered["iterations"]}
    assert name not in iteration_ids and name not in altered["programs"]
    documented = altered["history"]["documented_completed_iterations"]
    dependency = next(item for item in documented if item in iteration_ids)
    altered["programs"][name] = {
        "issue": 999_002,
        "status": PAUSED,
        "active_substeps": [],
        "ordered_substeps": [],
        "resume_condition": "Synthetic fixture: resume only on explicit owner direction.",
        "paused_by": {"issue": 999_003, "reason": "Synthetic pause fixture for the pause regression."},
    }
    altered["iterations"].append({
        "id": name,
        "issue": 999_002,
        "milestone": "Fixture milestone",
        "contract": "fixture-contract.en.md",
        "activation_status": PAUSED,
        "depends_on": [dependency],
    })
    return altered, name


def assert_pause_survives_redeclaration(case, plan, name):
    """Pausing must remove execution authority, not merely relabel it.

    An earlier form asserted ``select({}) is None`` against the real plan and
    claimed that proved pausing worked. It did not: selection reads the
    iterations layer and never ``programs[*]["status"]``, so the assertion
    passed for an unrelated reason. This forces the path instead --
    redeclaring the paused program as the *active* goal, the exact mistake a
    pause has to survive -- and then pays for the refusal with a positive
    control: arming the same record at the iterations layer, while leaving
    ``programs[*]["status"]`` paused, IS selectable. That is what makes the
    two-layer consistency assertion below load-bearing rather than decorative.
    """
    from personal_agent.delivery import DeliveryPlan

    program = plan["programs"][name]
    case.assertEqual(program.get("status"), PAUSED, name)
    case.assertEqual(program.get("active_substeps", []), [], f"{name} is paused with work in flight")
    case.assertTrue(program.get("resume_condition"), f"{name} is paused with no resume condition")
    assert_activation_record(case, f"{name} paused_by", program.get("paused_by"))
    iteration = program_iterations(plan)[name]
    # Two-layer consistency. Selection only reads this layer, so a pause
    # recorded only on the program record would be cosmetic.
    case.assertNotIn(
        iteration.get("activation_status"), ARMED,
        f"{name} is paused at the program layer but armed where selection reads",
    )

    altered = json.loads(json.dumps(plan))
    altered["next_goal"] = {"id": name, "status": "active"}
    with plan_file(altered) as path:
        case.assertIsNone(
            DeliveryPlan(path).select({}),
            f"{name} is paused but was selected after being redeclared active",
        )

    # Positive control: the identical record, armed at the layer selection
    # reads, IS selected. Without it the refusal above could come from a
    # malformed fixture instead of from the pause.
    armed = json.loads(json.dumps(altered))
    entry = next(item for item in armed["iterations"] if item["id"] == name)
    entry["activation_status"] = GOAL_READY
    with plan_file(armed) as path:
        selected = DeliveryPlan(path).select({})
    case.assertIsNotNone(
        selected,
        f"{name} did not select even when armed: the refusal above proves nothing",
    )
    case.assertEqual(selected["id"], name)


def assert_completion_survives_redeclaration(case, plan, name):
    """A completed iteration is not selectable even if redeclared active.

    ``DeliveryPlan.select`` has two gates: ``next_goal.status == "active"``,
    and the named iteration carrying ``activation_status`` ``GOAL_READY``. A
    completed program used to satisfy the *second* one -- EPIC-PA1 sat at
    ``owner-activated-goal-ready`` for a whole cycle after every substep had
    merged and its issues had closed. Nothing was selectable, but only
    because one field nobody had touched still read ``goal-ready``; a single
    flip would have handed authority back to a finished program and told a
    worker to advance two closed issues.

    Every existing selection test stops at the first gate, so none of them
    could see that. This forces the first gate open and asserts the second
    one holds on its own -- the same shape as
    ``assert_pause_survives_redeclaration``, including its positive control,
    because a refusal from a malformed fixture would prove nothing.
    """
    from personal_agent.delivery import DeliveryPlan

    altered = json.loads(json.dumps(plan))
    altered["next_goal"] = {"id": name, "status": "active"}
    with plan_file(altered) as path:
        case.assertIsNone(
            DeliveryPlan(path).select({}),
            f"{name} is complete but was selected after being redeclared active",
        )

    # Positive control: the same record, armed where selection reads, IS
    # selected. This is what makes the refusal above attributable.
    armed = json.loads(json.dumps(altered))
    entry = next(item for item in armed["iterations"] if item["id"] == name)
    entry["activation_status"] = GOAL_READY
    entry.setdefault("issue", 1)
    armed["history"]["documented_completed_iterations"] = [
        item for item in armed["history"]["documented_completed_iterations"] if item != name
    ]
    with plan_file(armed) as path:
        selected = DeliveryPlan(path).select({})
    case.assertIsNotNone(
        selected,
        f"{name} did not select even when armed and not recorded complete: "
        "the refusal above proves nothing",
    )
    case.assertEqual(selected["id"], name)


def assert_completed_work_is_unselectable(case, plan=None, path=PLAN_PATH):
    """No closed-out program and no completed substep can be selected.

    Covers both layers the plan records completion in, because they are
    written by different hands and drifted apart before: a program can be
    ``complete`` while the iteration selection actually reads is still armed.
    """
    plan = load_plan(path) if plan is None else plan
    items = {item["id"]: item for item in plan["iterations"]}
    completed = plan["history"]["documented_completed_iterations"]

    subjects = set(closed_out_programs(plan))
    for program in plan["programs"].values():
        subjects.update(program.get("completed_substeps") or [])
    subjects = sorted(name for name in subjects if name in items)
    case.assertTrue(subjects, "no completed work to check")

    for name in subjects:
        with case.subTest(completed=name):
            # Recorded complete in the layer selection reads, not only in the
            # program record.
            case.assertNotEqual(items[name].get("activation_status"), GOAL_READY,
                                f"{name} is complete but armed where selection reads")
            case.assertIn(name, completed, f"{name} is complete but not recorded so")
            case.assertNotEqual(plan["next_goal"].get("id"), name)
            assert_completion_survives_redeclaration(case, plan, name)


def assert_closed_out_record(case, plan, name):
    """Full closeout requirements for one program recorded complete.

    Extracted from the terminal branch of ``assert_declared_goal_shape`` so
    it runs in *both* plan shapes. A program that closed out while another
    program holds the declared goal used to escape every one of these checks
    purely because the plan was no longer terminal.
    """
    programs = plan["programs"]
    program = programs[name]
    iteration = program_iterations(plan)[name]
    completed = plan["history"]["documented_completed_iterations"]

    case.assertEqual(program.get("status"), CLOSED_OUT, name)
    case.assertEqual(iteration.get("activation_status"), CLOSED_ON_MERGE, name)
    case.assertIn(name, completed)
    # A closed-out program keeps no authority, whichever shape the plan is in.
    case.assertNotEqual(plan.get("next_goal", {}).get("id"), name,
                        f"{name} is complete but is the declared goal")
    case.assertNotIn(name, executing_programs(plan))
    case.assertEqual(program.get("active_substeps", []), [])
    case.assertTrue(program.get("closeout"), name)
    done = program.get("completed_substeps", [])
    case.assertTrue(done, name)
    assert_substep_evidence_is_complete(case, name, program, done,
                                        iteration.get("completed_substeps"))
    # A deferred substep may never be claimed as completed.
    deferred = program.get("deferred_substeps", {}).get("substeps", [])
    case.assertFalse(set(deferred) & set(done), name)
    # Nor may an unexecuted one. Each must name a successor issue, so an
    # unfinished substep cannot be dropped silently.
    unexecuted = program.get("unexecuted_substeps", {})
    case.assertFalse(set(unexecuted) & set(done), name)
    for substep, record in unexecuted.items():
        case.assertIsInstance(record.get("successor_issue"), int,
                              f"{name}: {substep} is unexecuted with no successor issue")
        case.assertTrue(record.get("reason"), f"{name}: {substep} is unexecuted with no reason")


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


def assert_active_substeps_are_legitimate(case, plan, name):
    """At most one substep in flight, and it must be one the program may run.

    Several tests asserted ``active_substeps == []`` for EPIC-PA1. That was a
    fact about the cast -- no substep happened to be running -- not an
    invariant, and it broke the moment the owner activated PA1-INT-01. The
    property actually worth holding is that the program cannot have work in
    flight it was never allowed to start: at most one substep, declared in
    ``ordered_substeps``, not already recorded complete, and whose iteration
    is still ``parent-controlled`` so a child cannot self-activate.
    """
    program = plan["programs"][name]
    active = program.get("active_substeps", [])
    case.assertIsInstance(active, list, name)
    case.assertLessEqual(len(active), 1, f"{name} has more than one substep in flight: {active}")
    if not active:
        return None
    substep = active[0]
    case.assertIn(substep, program.get("ordered_substeps", []),
                  f"{name} is running {substep}, which it never enumerated")
    case.assertNotIn(substep, program.get("completed_substeps", {}),
                     f"{name} is running {substep} after recording it complete")
    case.assertNotIn(substep, plan.get("history", {}).get("documented_completed_iterations", []),
                     f"{name} is running {substep} after documenting it complete")
    iteration = {item["id"]: item for item in plan["iterations"]}.get(substep)
    case.assertIsNotNone(iteration, f"{substep} is active with no iteration record")
    case.assertEqual(iteration.get("activation_status"), "parent-controlled",
                     f"{substep} is active but not parent-controlled, so it could self-activate")
    return substep


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
        case.assertTrue(closed_out_programs(plan),
                        "a terminal plan must record which program closed out")

    # Shared: every closed-out program carries its full closeout record, in
    # either shape. This used to sit inside the terminal branch, so a program
    # that closed out while a *different* program held the declared goal was
    # checked by nothing at all.
    for name in closed_out_programs(plan):
        assert_closed_out_record(case, plan, name)

    # Shared: nothing paused, complete or otherwise barred holds authority.
    assert_no_unauthorised_execution_authority(case, plan)

    # Shared: whichever shape, the heartbeat must refuse to run.
    assert_heartbeat_is_paused(case, plan=plan)
    return shape
