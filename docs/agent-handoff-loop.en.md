# State-driven GitHub handoff loop

`python3 -m scripts.dev.delivery handoff --role implementer` and the
reviewer equivalent are one-shot, dispatch-only checks for the existing
delivery heartbeat. They never create a schedule, model session, branch, PR,
merge, or issue. A configured role worker uses `StateHandoffLoop` with its
bounded executor or independent reviewer; without one it returns a compact
`dispatch-required` receipt without changing an eligible issue's label.

The queue is exactly one of `agent:ready`, `agent:working`, `agent:review`,
`agent:rework`, `agent:approved`, or `agent:blocked`. Admission requires an
open, goal-ready issue with `## Executable goal`, `## Allowed authority`, and
the owner-maintained `<!-- agentos:owner-authorized -->` plus
`<!-- agentos:dependencies-satisfied -->` markers; the label alone is not
authority. Implementers prefer rework over ready and
do not start while another writer has a live claim. Review accepts only the
candidate PR explicitly named in the implementation receipt, with a current
head, non-draft status, known required checks, and success evidence.

Receipts are owner-authored GitHub comments marked `agentos-handoff:*`:
one implementation receipt records PR/head/CI, and one review receipt records
either bounded findings or `agent:approved`. The local state file holds only
lease, candidate identity, finding digest/text, and receipt markers. A comment
timeout is read back before retry; the next tick completes a pending label
transition instead of duplicating a comment.

Schedule state is separate from this code. No schedule is created or changed
by a handoff tick. An operator must inspect the actual account/host state,
explicitly choose one identified existing heartbeat or registration, configure
its permitted GitHub actions and role worker, then observe a one-shot smoke
before enabling recurrence.
