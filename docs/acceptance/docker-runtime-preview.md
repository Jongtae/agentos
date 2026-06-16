# Docker Runtime Preview Acceptance

Status: Active Preview

Docker is the easiest public way to try the AgentOS runtime today. It does not
claim to prove boot ownership, installer behavior, reboot/rejoin, recovery
partition behavior, kernel-level supervision, or ISO freshness.

## Required User Flow

```bash
git clone git@github.com:Jongtae/agentos.git
cd agentos
cp .env.example .env
docker compose up
```

Then open:

```text
http://localhost:8787
```

## Acceptance Criteria

- `docker compose up` starts a local AgentOS preview.
- `http://localhost:8787` opens.
- Runtime status is visible.
- Docker Onboarding Status is visible.
- `/api/onboarding` exposes quickstart steps, a readiness checklist, preview entrypoints, validation smokes, and proof non-claims without requiring an API key.
- Guided Demo Journey is visible.
- `/api/demo-journey` exposes the customer path across Runtime Home, Work Inbox, prompt execution, Activity Timeline, Evidence Dashboard, and Recovery Center with expected success outcomes, blocked-until-observed outcomes, and a completion summary, without claiming VM/ISO, live OAuth, browser, release, external mutation, or hardware attestation proof.
- A customer-facing Runtime Home is visible.
- Work Inbox, Activity Timeline, Recovery Center, and Evidence Dashboard states are summarized.
- `/api/work-inbox` exposes read-first inbox sources, workflows, live blockers, and mutation non-claims.
- `/api/timeline` exposes customer-readable runtime events, user-visible record paths, and external-app/live-provider non-claims.
- `/api/capabilities` exposes safe local capabilities, confirmation-needed capabilities, and blocked destructive capabilities from the permission registry.
- `/api/approvals` exposes setup-needed, confirmation-needed, observed-proof-needed, and blocked approval requirements without executing them.
- `/api/proofs` exposes future observed-proof evidence requirements and mock submission fields without accepting secrets or auto-promoting claims.
- `/api/release-trust` exposes release artifact, manifest, checksum, signing, publication, customer readiness decisions, and VM/ISO proof requirements without claiming release readiness.
- `/api/attestation` exposes Secure Boot, TPM/PCR, event-log, IMA, and hardware attestation requirements without claiming Docker proves device trust.
- `/api/recovery` exposes customer-facing recovery actions for VM/ISO, live OAuth, browser, release, attestation, and setup blockers without claiming observed proof.
- `/api/evidence` exposes observed Docker/local proof and explicit non-claims for VM/ISO, live OAuth, browser, release trust, and hardware attestation.
- `/api/proof-packet` exposes completed Docker-local claims, validation commands, proof sources, readiness checks, next blockers, and explicit non-claims without claiming automatic proof promotion.
- `/api/customer-handoff` exposes the Docker try path, handoff checklist, share-safe handoff report, inspectable Product Layer surfaces, validation commands, proof sources, next observed-proof blockers, and explicit non-claims without claiming stronger observed proof.
- `/api/proof-promotion` exposes Docker-local claim promotion decisions, a proof sharing checklist, source surfaces, required observed evidence, and explicit non-claims without automatic claim promotion.
- `/api/product-map` exposes start, safe-work, proof/handoff, and blocked-until-observed surface groups with a recommended customer path, reviewer routes, and explicit non-claims.
- LLM setup/readiness state is visible.
- Telegram setup/readiness state is visible.
- Activity feed is visible.
- At least one prompt can be routed through intent dispatch.
- Proof/log output is written under `./agentos-data` or mounted workspace paths.
- Missing credentials appear as degraded/setup-needed states, not raw tracebacks.
- No raw Telegram token, OpenAI key, or OAuth token is written to committed files or proof/activity output.

## Suggested Manual Checks

Run these from the web preview:

```text
hi
status
workspace 파일 목록 보여줘
search AgentOS roadmap and summarize it
```

Expected behavior:

- greeting does not trigger web search
- status returns runtime state
- Runtime Home explains product-layer readiness and proof blockers
- Work Inbox shows fixture, Maildir, Gmail, and Calendar sources without claiming live OAuth or mutations
- Activity Timeline shows recent runtime events and record paths without claiming external app execution
- Capability Store shows safe local actions, external-read setup needs, lifecycle confirmation, and destructive blocked actions
- Approval Center shows approval-gated actions without claiming approval execution, external writes, or destructive actions
- Observed Proof Uploader shows evidence requirements without claiming file upload execution or claim promotion
- Release Trust Panel shows release evidence requirements, readiness checklist items, and customer decisions without claiming upload, signing, checksum publication, or VM/ISO release proof
- Attestation Status shows boot-chain and hardware trust evidence requirements without claiming Secure Boot, TPM/PCR, event-log, IMA, or hardware attestation proof
- Recovery Center shows proof blockers as next recovery actions without claiming Docker is boot, release, browser, or hardware proof
- Evidence Dashboard separates what Docker/local smokes have observed from what still requires external evidence
- workspace request uses bounded local workspace behavior
- search-style request routes through search-like intent
- activity feed narrates request, intent, capability, and result

## Automated Smoke

```bash
scripts/smoke_docker_runtime_preview.sh
```

The smoke should validate compose config, build the image, start the preview,
check `localhost:8787`, verify `/api/product`, `/api/work-inbox`,
`/api/onboarding`, `/api/demo-journey`, `/api/timeline`, `/api/capabilities`, `/api/approvals`, `/api/proofs`, `/api/release-trust`, `/api/attestation`, `/api/recovery`, `/api/evidence`, `/api/proof-packet`, `/api/customer-handoff`, `/api/proof-promotion`, and `/api/product-map`, run a prompt through `/api/prompt`,
verify activity, and check that common secret patterns are not present in the
response.

## Product Layer Completion Gate

```bash
scripts/smoke_docker_product_layer_completion.sh
```

This gate starts the Python Docker runtime preview, verifies every customer-facing
Product Layer surface together, and asserts that Docker still does not claim
live OAuth, VM/ISO boot, browser, release, external mutation, Secure Boot,
TPM/PCR, IMA, or hardware attestation proof.

## Customer Onboarding Quickstart Gate

```bash
scripts/smoke_docker_customer_onboarding_quickstart.sh
```

This gate verifies that README quickstart, Docker acceptance, public preview
operations, roadmap, and task state all point to the same Docker-first public
try path and keep Docker proof separate from VM/ISO, live OAuth, browser,
release, external mutation, and attestation proof.

## Onboarding Status Contract Gate

```bash
scripts/smoke_docker_onboarding_status_contract.sh
```

This gate starts the Python Docker runtime preview and verifies that
`/api/onboarding` exposes customer-facing quickstart readiness, preview
entrypoints, no-key local preview status, Docker-safe validation, and explicit
observed-proof blockers.

## Guided Demo Journey Gate

```bash
scripts/smoke_docker_guided_demo_journey.sh
```

This gate starts the Python Docker runtime preview and verifies that
`/api/demo-journey` exposes the customer path, expected outcomes, and completion
summary through runtime readiness, read-first work, prompt execution, activity
narration, evidence, and recovery while preserving VM/ISO, live OAuth, browser,
release, mutation, and attestation non-claims.

## Customer Proof Packet Gate

```bash
scripts/smoke_docker_customer_proof_packet.sh
```

This gate starts the Python Docker runtime preview and verifies that
`/api/proof-packet` exposes customer-readable completed Docker-local claims,
validation commands, proof sources, readiness checks, next blockers, and
explicit non-claims without automatic claim promotion.

## Customer Handoff Bundle Gate

```bash
scripts/smoke_docker_customer_handoff_bundle.sh
```

This gate starts the Python Docker runtime preview and verifies that
`/api/customer-handoff` exposes the Docker try path, handoff checklist,
share-safe handoff report, inspectable Product Layer surfaces, validation
commands, proof sources, next observed-proof blockers, and explicit non-claims
without promoting Docker proof into VM/ISO, live OAuth, browser, release,
mutation, or attestation proof.

## Proof Promotion Center Gate

```bash
scripts/smoke_docker_proof_promotion_center.sh
```

This gate starts the Python Docker runtime preview and verifies that
`/api/proof-promotion` exposes customer-facing claim promotion decisions,
proof sharing checklist items, required evidence, source surfaces, share policy,
and explicit non-claims without automatically promoting Docker-local proof into
Docker daemon observed, VM/ISO, live OAuth, browser, release, mutation, or
attestation proof.

## Product Layer Map Gate

```bash
scripts/smoke_docker_product_layer_map.sh
```

This gate starts the Python Docker runtime preview and verifies that
`/api/product-map` exposes a customer-facing path across start-here,
safe-work, proof/handoff, and blocked-until-observed groups, plus reviewer
routes for runtime evaluators, proof reviewers, capability reviewers, and trust
reviewers, while preserving VM/ISO, live OAuth, browser, release, mutation, and
attestation non-claims.
