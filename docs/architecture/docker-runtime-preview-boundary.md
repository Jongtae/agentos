# Docker Runtime Preview Boundary

Status: Active Preview

Docker support is a developer and demo runtime preview for AgentOS. It exists
to lower the public contribution barrier and to make Phase 2 runtime smokes
repeatable without requiring an ISO or VM.

Docker is not the AgentOS product target.

Default entry:

```bash
docker compose up
```

Open:

```text
http://localhost:8787
```

## Docker May Prove

- the runtime can start in a local developer environment
- setup/status can report local runtime and adapter readiness
- the customer-facing Runtime Home can summarize product-layer readiness
- the Work Inbox product surface can summarize read-first inbox sources without live-provider claims
- the Activity Timeline product surface can summarize runtime events and user-visible records without claiming external app execution
- the Capability Store product surface can summarize permission-registry capabilities without executing destructive actions or claiming external writes
- the Approval Center product surface can summarize setup, confirmation, observed-proof, and blocked requirements without claiming approval execution
- the Recovery Center product surface can turn missing proof into customer-facing next actions without claiming observed VM/ISO, live OAuth, browser, release, or attestation evidence
- the Evidence Dashboard product surface can separate observed Docker/local proof from explicit external-proof non-claims
- prompt intake can reach the same intent classification path used by AgentOS
- bounded capabilities can emit activity events
- generated outputs can be written to user-owned mounted storage
- missing credentials or unavailable adapters produce friendly degraded states
- Phase 2 smoke checks can run in CI without a booted VM

## Docker Must Not Claim

- boot ownership
- installer readiness
- reboot or rejoin proof
- kernel-level service supervision
- recovery partition behavior
- VM-level recovery proof
- ISO freshness or release image truth

## Runtime Shape

The Docker preview should expose a narrow runtime harness:

```text
host checkout
-> docker compose up
-> localhost:8787
-> mounted user data path
-> setup/status
-> sample prompt
-> intent classification
-> bounded capability result
-> activity/records output
```

The same prompt/capability code should be used by local, Docker, and VM paths
when possible. Docker-only behavior should stay in wrapper scripts or compose
configuration, not in the core runtime contract.

## Data And Secret Boundaries

Docker bind mounts are part of the user-owned data boundary. They may contain
workspace files, generated outputs, exported activity logs, diagnostics, records,
and acceptance artifacts.

Bind mounts must not be the default plaintext location for:

- API keys
- Telegram bot tokens
- OAuth tokens
- provider credentials
- mailbox contents unless the user explicitly supplied them for a fixture or
  adapter smoke

## Acceptance

Docker preview work is acceptable when a contributor can run a documented
command that produces:

- a setup/status report
- a Runtime Home product-layer summary
- a Work Inbox read-first product-layer summary
- an Activity Timeline product-layer summary
- a Capability Store product-layer summary
- an Approval Center product-layer summary
- a Recovery Center product-layer summary
- an Evidence Dashboard product-layer summary
- at least one classified prompt
- at least one activity feed event
- a user-owned output path
- a friendly degraded response for missing external credentials
- a browser-visible preview page on `localhost:8787`

Any Stage E closeout must still distinguish Docker proof from VM/ISO proof.
