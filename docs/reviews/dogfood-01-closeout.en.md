# DOGFOOD-01 requirement-to-evidence audit

This audit records the evidence for the owner-selected local vertical slice. It
does not claim that a live provider or browser session was operated in this
repository run.

| Requirement | Current evidence | Evidence class |
| --- | --- | --- |
| Start locally and open the owner flow | `agentos start`, loopback URL, setup-link recovery, and restart guidance in `QUICKSTART.md`; existing CLI/server tests | deterministic + local operating instructions |
| Connect a supported provider and chat | `test_owner_dogfood_vertical_slice_runs_over_http_and_restarts` configures and probes the existing OpenAI-compatible adapter, then completes a queued chat | deterministic fixture |
| Explicit reference-folder authority | The acceptance test configures one temporary reference folder and uses the existing file-workspace grant; existing escape/symlink/broad-scope negatives remain green | temporary-local-file integration + negative tests |
| Useful file-backed task and managed result | The test approves external document sharing, summarizes `launch.md`, verifies one Markdown result in the managed workspace, and verifies the original bytes are unchanged | temporary-local-file integration |
| Stop/restart and find/reuse | The test stops worker/server, constructs a new service/server over the same store, logs in, and successfully searches the saved result | temporary-local-file integration |
| Provenance and authority boundaries | Existing file-workspace evidence, approval, stale-source, save-failure, and redaction tests remain green; no new authority is introduced | deterministic + negative tests |
| Credential-free automation and recovery | Full pytest/unittest suites, document/source/parity verifiers, and package fixture verifier pass; no secret is placed in the test or evidence | repository CI + deterministic |
| Real-provider evidence separation | `QUICKSTART.md` states that repository tests use a simulated provider; live credentials and owner observation remain manual and unclaimed | evidence policy |
| Planned successor boundaries | Delivery-plan governance tests keep DOGFOOD-01 goal-ready/non-active until explicit activation and keep #335–#346 inactive | governance tests |

## Manual owner acceptance remaining

On a Mac with a supported provider credential (or an already-running Ollama
model), the owner must follow the **Recommended owner dogfood task** in
`QUICKSTART.md`. Record live-provider/browser observations separately from this
audit; do not put credentials or private document contents in repository
evidence.
