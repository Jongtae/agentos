# Early-access owner smoke test

This is a hands-on test of the merged experimental checkpoint PR #362, not a new
architecture program or a claim that all USE-01 criteria passed. #358 remains open;
#363 tracks outcome evaluation/live-runner work and #364 tracks known private-data
and first-use defects. Original 72/72 and 3/3 claims are not accepted product-quality evidence.

## Isolation and installation

Use a fresh state and synthetic documents only. Do not import prior AgentOS data, personal
Memory, email, real private folders or credentials from another installation. Do not ask
this checkpoint to save canonical memories. These restrictions do not fix the deferred
code defects; they limit the test. Private-data use is not approved.

Use Python 3.12+ and source containing PR #362. Do not reset or clean an existing Codex
working tree. Use a separate checkout when there are unrelated modifications. Inspect
`git status --short` and record `git rev-parse HEAD`; install from that checkout:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Use the setup helper to create a new root and print the exact start/restart commands:

```sh
python3 scripts/prepare_owner_smoke.py --root "$HOME/agentos-smoke-test" --port 8788
```

Existing roots and inherited AgentOS integration/state settings are refused; choose a
new directory on another run. The helper creates one synthetic Launch review document,
empty state and workspace, and no provider connection. Run its printed start command
only on the owner's machine after inspecting it. Do not copy personal state into it.

Alternatively, the following explicit setup creates a unique root. Keep its path for restarts:

```sh
umask 077
SMOKE_ROOT="$(mktemp -d "$HOME/agentos-smoke.XXXXXX")"
mkdir "$SMOKE_ROOT/reference" "$SMOKE_ROOT/workspace"
printf '%s\n' "$SMOKE_ROOT"
cat > "$SMOKE_ROOT/reference/launch.md" <<'NOTE'
# Launch review
This is synthetic test data, not a real project.
Decision: publish the local preview after the owner smoke test.
Owner: Demo User. Deadline: 2030-01-15.
Open question: does the saved result remain available after restart?
NOTE
agentos start --host 127.0.0.1 --port 8788 --data "$SMOKE_ROOT/state"
```

`--data`, `--host`, `--port` and `--no-browser` are existing quickstart options.
A fresh store prevents automatic reuse of old chats/settings, but this native process is
not an OS sandbox. Ensure no external integration is opted in through inherited
`AGENTOS_DRIVE_*` or `AGENTOS_ISOLATED_ENGINE_URL` settings; do not inspect their secret values.
Do not expose the server through a public tunnel. If the port is in use, choose another
free loopback port; do not kill unrelated processes.

## One existing provider, only by explicit owner selection

Open the local browser page, finish owner setup and choose one already-supported direct
provider for the file-workspace path. A Codex development login is not that connection.
An existing key does not authorize a paid request. Let the owner enter credentials only
in the local settings UI; never request them in chat or copy them into logs/repo.

For a real call the owner chooses provider/model, approved destination, synthetic-only
inputs and a small cost/request ceiling before execution. This runbook does not enforce
a spending ceiling in the unfinished live evaluator; use the provider's limit or manual
approval per call. Without this permission, finish credential-free setup checks and
report `owner_validation_pending`. A mock response is not a live model result.

## Three useful outcomes

1. **Public reading:** after explicit destination approval, read two owner-selected public
   pages and produce a short comparison with source links. Separate fetched facts from
   unknown/dynamic content. Do not visit checkout, hold tickets, log in or book anything.
2. **File to real result:** register exactly the synthetic reference and workspace folders
   above. Approve sharing to the selected external provider only if intended. Ask:
   `Summarize "Launch review" into "Launch notes": decision, owner, deadline and open question.`
   Verify the actual Markdown result contains the right facts and that launch.md is unchanged.
   No generic 'pass' based on a nonempty answer or file existence.
3. **Restart and reuse:** Ctrl-C, then restart with the SAME `--data` path. Ask to find
   `Launch notes` and change only the deadline to 2030-01-22 in a NEW result. Inspect that
   the date changed, other facts stayed correct and the original result was preserved.

Record each outcome as observed, failed, partial or not_run, with actual revision/model,
a redacted result path and the one next fix. State HTTP-only versus actual browser evidence.
Do not turn this smoke into the full #363 benchmark. If an optional path is unfinished,
leave it disabled; fix only a reproduced blocker to these three tasks in a small PR.

## Development handoff

Continue under the owner-selected #358 smoke substep; no second preparation cycle or
heartbeat is needed. Keep #358 open until its remaining scope is explicitly accounted for.
Do not activate #363/#364 or other roadmap items wholesale. Scope each real first-use fix
and follow [incremental delivery](incremental-delivery.en.md) for any merge wait.
A working browser URL and runnable commands are more useful than another design document.
