# AgentOS Tasks

Status: Current
Owner: Autonomous Codex implementation loop

## Active Execution State

Current parent branch:

- `main`

Current public milestone:

- **Docker session report closeout** — completed Docker-safe runtime report with explicit stronger-proof blockers

Current task:

- `[P2-126] Close Docker session report epic`

Runtime impact statement:

- This task records Docker-safe session reporting as completed Product Layer work while preserving runtime-first truthfulness and leaving Docker daemon, VM/ISO, live OAuth, browser, release, mutation, and attestation proof blockers explicit until observed evidence exists.

Current autonomous completion loop:

- A Codex heartbeat automation runs every 15 minutes against this thread.
- Each pass starts from the repo startup order, compares README, PRD, TASKS, roadmap, and GitHub milestone/issue state, runs the roadmap direction judge, and decides whether to continue an epic, create a missing milestone-backed epic, or defer because a blocker requires user/external input.
- Every epic must declare a completion goal, roadmap milestone alignment, validation plan, and exit condition before implementation work proceeds.
- When the direction judge finds no safe task candidate, it should inspect uncovered completion tracks and propose the next missing epic candidate before falling back to lightweight status checks.
- Created epic candidates must be registered in the roadmap state before the loop chooses the next task, so repeated passes do not create duplicate epics.
- Roadmap changes that require product or architecture judgment should be backed by primary or credible external research before they become milestone, epic, or exit-condition updates.
- A direction verdict of `accept_with_risk` means the loop may finish lightweight validation, but should not repeat heavy smoke-only passes when no safe forward-progress candidate exists.
- A direction verdict of `reject` means autonomous apply work should stop and hand off or open a repair issue before continuing.
- ISO smoke is limited to at most once per calendar day unless ISO/build code changed or the user explicitly requests it.
- Live Gmail OAuth and observed VM/ISO proof remain explicit blockers until a tester provides credentials or a VM run can be observed and recorded.

## Phase 1 Closeout Truth

Phase 1 proves:

- AgentOS can boot into a terminal-first operator surface.
- A bundled local Ollama path can provide a baseline local LLM.
- AgentOS exposes runtime/capability surfaces through `agentos-kernelctl`.
- Telegram setup/reply experiments exist and are integrated with the OS-native workflow substrate.
- Intent dispatch and activity events establish the direction for “AgentOS narrates its work.”
- ISO build/remaster scripts exist for local ARM64 VM experimentation.

Phase 1 does not claim:

- production-ready Telegram automation
- polished first-run setup
- always-on receiver reliability
- user-friendly lifecycle/recovery flows
- verified boot or attestation
- public installer distribution
- broad app ecosystem support

## Current Public Artifacts

Keep in Git:

- source code
- scripts
- docs
- reference contracts
- runbooks
- lifecycle ledger
- `.env.example`
- `LICENSE`

Do not commit:

- `build-output/`
- generated ISOs
- remaster workdirs
- runtime `workspaces/*/artifacts/`
- `.env`
- personal tokens or API keys
- `.DS_Store`

## Phase 2 Recommended Work

Phase 2 should productize the local-first runtime loop that Phase 1 exposed:

```text
local or booted AgentOS runtime
-> configure local-first runtime adapters
-> receive a user prompt
-> classify intent
-> run a bounded capability
-> narrate progress
-> store user-visible records
-> reply or fail with clear recovery guidance
```

Recommended Phase 2 tasks:

- Docker preview is promoted as the primary public try path at `http://localhost:8787`.
- Docker preview now exposes `agentos-product-layer-runtime-home.v1` through `/api/product` and the browser Runtime Home without claiming VM/ISO boot proof.
- Docker preview now exposes `agentos-product-layer-work-inbox.v1` through `/api/work-inbox` and the browser Work Inbox without claiming live OAuth, browser-default behavior, or external mutations.
- Docker preview now exposes `agentos-product-layer-activity-timeline.v1` through `/api/timeline` and the browser Activity Timeline without claiming external app execution or live-provider proof.
- Docker preview now exposes `agentos-product-layer-capability-store.v1` through `/api/capabilities` and the browser Capability Store without claiming destructive, external-write, or live-provider proof.
- Docker preview now exposes `agentos-product-layer-approval-center.v1` through `/api/approvals` and the browser Approval Center without claiming approval execution, external writes, or destructive actions.
- Docker preview now exposes `agentos-product-layer-observed-proof-uploader.v1` through `/api/proofs` and the browser Observed Proof Uploader without claiming file upload execution, secret-material acceptance, or automatic claim promotion.
- Docker preview now exposes `agentos-product-layer-release-trust-panel.v1` through `/api/release-trust` and the browser Release Trust Panel with a customer readiness checklist and decision guidance without claiming release upload, signing, checksum publication, or VM/ISO release proof.
- Docker preview now exposes `agentos-product-layer-attestation-status.v1` through `/api/attestation` and the browser Attestation Status panel without claiming Secure Boot, TPM/PCR, event-log, IMA, or hardware attestation proof.
- Docker preview now exposes `agentos-product-layer-recovery-center.v1` through `/api/recovery` and the browser Recovery Center without claiming VM/ISO, live OAuth, browser, release-trust, or hardware-attestation proof.
- Docker preview now exposes `agentos-product-layer-evidence-dashboard.v1` through `/api/evidence` and the browser Evidence Dashboard so customers can distinguish observed Docker/local proof from explicit non-claims.
- Docker preview now exposes `agentos-product-layer-customer-proof-packet.v1` through `/api/proof-packet` and the browser Customer Proof Packet panel so customers can inspect completed Docker-local claims, validation commands, proof sources, readiness checks, next blockers, and non-claims in one place.
- Docker preview now exposes `agentos-product-layer-customer-handoff-bundle.v1` through `/api/customer-handoff` and the browser Customer Handoff Bundle panel so customers can run, inspect, validate, follow the handoff checklist, generate a share-safe handoff report, and explain the Docker-safe Product Layer path from one bundle.
- Docker preview now exposes `agentos-product-layer-proof-promotion-center.v1` through `/api/proof-promotion` and the browser Proof Promotion Center panel so customers can decide which Docker-local claims are ready and which stronger claims require observed evidence.
- Docker preview now exposes a Proof Sharing Checklist inside `/api/proof-promotion` and the browser Proof Promotion Center panel so customers can distinguish share-ready Docker-local language from blocked stronger claims before handing evidence to reviewers.
- Docker preview now exposes `agentos-product-layer-observed-proof-request-board.v1` through `/api/proof-requests` and the browser Observed Proof Request Board panel so customers can see evidence requests, redaction rules, validation commands, and promotion boundaries for each blocked proof category without accepting secrets or auto-promoting claims.
- Docker preview now exposes `agentos-product-layer-recovery-drill-board.v1` through `/api/recovery-drills` and the browser Recovery Drill Board panel so customers can run Docker-safe health, runtime preview, Product Layer, cleanup, VM/ISO blocker, and live adapter recovery drills without promoting stronger proof claims.
- Docker preview now exposes `agentos-product-layer-session-report.v1` through `/api/session-report` and the browser Session Report panel so customers can review runtime state, recent activity, proof sources, recovery drills, and stronger-proof blockers in one Docker-safe report.
- Docker preview now exposes `agentos-product-layer-map.v1` through `/api/product-map` and the browser Product Layer Map panel so customers can follow the recommended path and reviewer-specific routes across Product Layer surfaces and proof blockers.
- Docker preview now exposes `agentos-product-layer-next-work-board.v1` through `/api/next-work` and the browser Next Work Board panel so customers can see completed Docker-local proof, safe next implementation candidates, blocked observed-proof tracks, and validation commands without automatic claim promotion.
- Docker Product Layer completion is guarded by `scripts/smoke_docker_product_layer_completion.sh`, which verifies Runtime Home, Work Inbox, Activity Timeline, Capability Store, Approval Center, Observed Proof Uploader, Release Trust Panel, Attestation Status, Recovery Center, Evidence Dashboard, Customer Proof Packet, Customer Handoff Bundle, Proof Promotion Center, Observed Proof Request Board, Product Layer Map, and Next Work Board together.
- Docker customer onboarding is guarded by `scripts/smoke_docker_customer_onboarding_quickstart.sh`, which keeps README quickstart, Docker acceptance, public preview operations, roadmap, and task state aligned around the Docker-first public try path.
- Docker preview now exposes `agentos-product-layer-onboarding-status.v1` through `/api/onboarding` and the browser Docker Onboarding Status panel without claiming VM/ISO, live OAuth, browser, release, external mutation, or hardware attestation proof.
- Docker onboarding readiness is guarded by `scripts/smoke_docker_onboarding_status_contract.sh`, which verifies the running preview exposes customer-facing quickstart readiness, entrypoints, Docker-safe validation, and explicit observed-proof blockers.
- Docker preview now exposes `agentos-product-layer-guided-demo-journey.v1` through `/api/demo-journey` and the browser Guided Demo Journey panel without claiming VM/ISO, live OAuth, browser, release, external mutation, or hardware attestation proof.
- Gmail setup is exposed through `agentos-kernelctl gmail-setup --serve-http`; live Gmail remains read-only and requires explicit user OAuth credentials.
- Phase 2 closeout is recorded in `docs/reference/phase2-local-first-runtime-loop-closeout-v1.md`.
- Practical local/Docker-safe proof is aggregated by `scripts/smoke_phase2_golden_demo.sh`.
- A 15-minute roadmap-governed completion loop is active as an operational loop that compares source-of-truth docs, GitHub work state, and roadmap milestones before deciding whether to create or continue an epic.
- Roadmap direction judging is part of that loop so stable Phase 2 validation can promote the next safe completion task instead of becoming the whole product motion.
- Calendar read-only now has a fixture-backed contract and smoke path; live Calendar OAuth remains future work until explicit credentials and adapter design exist.
- VM/ISO proof now has a preflight smoke and blocker contract; observed boot, reboot/recovery, and managed runtime rejoin still require a real VM run before signoff.
- Gmail live read-only proof now has a manual acceptance pack and blocker capture; automated smokes still avoid real user credentials.
- VM/ISO proof remains an explicit blocker until a VM run is observed and recorded.
- Capability result smokes now enforce permission levels and blocked outcomes for safe local reads, missing external setup, and destructive unsupported requests.
- `phase2-run` should expose permission level, outcome, recovery, and secret-redaction proof in JSON output and user-owned records.
- Capability permission declarations should be backed by `docs/architecture/capability-permission-registry.json`.
- The capability permission boundary epic is closed for this Phase 2 slice; future loops should return to the roadmap before selecting the next epic.
- The updater hardening epic is closed for this Phase 2 slice; future updater work should require an observed VM/live-updater proof issue before claiming reboot, rollback, or ISO behavior.
- The first updater hardening slice is `agentos-phase2-updater-state.v1`, which records ready, blocked, rollback-needed, and recovery-suggested states without running destructive updater actions.
- `phase2-run` lifecycle recovery should surface updater state artifacts for update, rollback, restart, and recovery prompts while keeping live updater and VM/ISO proof blocked until observed.
- The browser fallback capability boundary epic is closed for this Phase 2 slice; future browser fallback work should return to the roadmap and open a new task only when it adds observed fallback proof or graduates a repeated pattern into an internal AgentOS capability.
- The first browser fallback slice is `agentos-phase2-browser-fallback-contract.v1`, which classifies internal capability, allowed fallback, blocked external state, and capability graduation paths without launching a browser.
- `phase2-run` web/search requests should attach the browser fallback contract artifact and keep live browser proof unclaimed unless a separate observed browser acceptance run exists.
- The browser fallback observed proof acceptance epic is closed for this Phase 2 slice; future live browser work should require an explicit user-approved run and sanitized observed proof before claiming live browser fallback proof.
- The first browser fallback observed proof slice is `agentos-browser-fallback-observed-acceptance.v1`, which accepts a sanitized observed proof record only after the fallback contract allows browser fallback and keeps `browser_is_default=false`.
- The public preview operations epic is closed for this Phase 2 slice; future preview work should return to the roadmap and open a new task only when it adds observed proof, release packaging, or a new promotion decision surface.
- The first public preview operations slice is `docs/operations/public-preview-operations.md`, smoke-tested by `scripts/smoke_public_preview_operations.sh`.
- The public preview operations smoke is included in the Phase 2 golden demo runner so preview promotion gates remain part of practical local/Docker-safe proof.
- The distribution packaging proof boundary epic is closed for this Phase 2 slice; future distribution work should require real release artifacts, signing/checksum publication, or observed VM/ISO proof before claiming release readiness.
- The first distribution packaging slice is `docs/operations/distribution-packaging-proof-boundary.md`, smoke-tested by `scripts/smoke_distribution_packaging_boundary.sh`.
- Release manifest/checksum preflight is covered by `scripts/release_manifest_checksum_preflight.py` and `scripts/smoke_release_manifest_checksum_preflight.sh` without publishing or signing artifacts.
- The release manifest/checksum preflight smoke is included in the Phase 2 golden demo runner so packaging non-claims remain part of practical local/Docker-safe proof.
- The Docker release trust customer checklist epic is closed for this Phase 2 slice; future release-trust work should require real release artifacts, checksum publication, signing or unsigned-preview evidence, observed VM/ISO release proof, live browser evidence, or a new customer-facing release promotion need before reopening.
- P2-115 adds a Release Trust readiness checklist, customer decisions, a browser panel section, and `scripts/smoke_docker_release_trust_panel.sh` so customers can see which release trust language is share-ready and which claims remain blocked.
- P2-116 closes the Docker release trust customer checklist epic after README, TASKS, roadmap, Docker acceptance, release trust gate, Product Layer completion gate, runtime preview Python smoke, compose config, cleanup policy, and CI checks preserve the Docker-safe release trust decision path.
- The Docker public preview readiness board epic is closed for this Phase 2 slice; future preview readiness work should require observed Docker daemon proof, live browser evidence, release proof, VM/ISO proof, or a new customer-facing public preview promotion need before reopening.
- P2-117 adds `/api/preview-readiness`, a browser Preview Readiness Board panel, and `scripts/smoke_docker_preview_readiness_board.sh` so customers can see share-ready Docker-local preview claims, recommended local gates, and blocked stronger claims from the Product Layer.
- P2-118 closes the Docker public preview readiness board epic after README, TASKS, roadmap, Docker acceptance, preview readiness gate, Product Layer completion gate, runtime preview Python smoke, compose config, cleanup policy, and CI checks preserve the Docker-safe public preview go/no-go path.
- The Docker next work board epic is closed for this Phase 2 slice; future next-work-board changes should require observed Docker daemon proof, live proof evidence, VM/ISO proof, release proof, hardware attestation evidence, or a new customer-facing next-work promotion need before reopening.
- P2-119 adds `/api/next-work`, a browser Next Work Board panel, and `scripts/smoke_docker_next_work_board.sh` so customers can see completed Docker-local Product Layer proof, safe next implementation candidates, and blocked stronger proof tracks from the Product Layer.
- P2-120 closes the Docker next work board epic after README, TASKS, roadmap, Docker acceptance, next-work gate, Product Layer completion gate, runtime preview Python smoke, compose config, cleanup policy, and CI checks preserve the Docker-safe completed-proof and next-work path.
- The Docker observed proof request board epic is closed for this Phase 2 slice; future proof-request-board changes should require observed Docker daemon proof, live proof evidence, VM/ISO proof, release proof, hardware attestation evidence, or a new customer-facing evidence-request promotion need before reopening.
- P2-121 adds `/api/proof-requests`, a browser Observed Proof Request Board panel, and `scripts/smoke_docker_observed_proof_request_board.sh` so customers can see the exact evidence, redaction, validation, and promotion boundaries required before stronger proof claims can be promoted.
- P2-122 closes the Docker observed proof request board epic after README, TASKS, roadmap, Docker acceptance, proof-request gate, Product Layer completion gate, runtime preview Python smoke, compose config, cleanup policy, and CI checks preserve evidence-request truthfulness without stronger proof claims.
- The Docker recovery drill board epic is closed for this Phase 2 slice; future recovery-drill changes should require observed Docker daemon proof, VM/ISO recovery evidence, live adapter proof, release proof, or a new customer-facing recovery promotion need before reopening.
- P2-123 adds `/api/recovery-drills`, a browser Recovery Drill Board panel, and `scripts/smoke_docker_recovery_drill_board.sh` so customers can run or review concrete recovery drills while VM/ISO, live OAuth, browser, release, mutation, and attestation proof remain unclaimed.
- P2-124 closes the Docker recovery drill board epic after README, TASKS, roadmap, Docker acceptance, recovery-drill gate, Product Layer completion gate, runtime preview Python smoke, compose config, cleanup policy, and CI checks preserve Docker-safe recovery truthfulness without stronger proof claims.
- The Docker session report epic is closed for this Phase 2 slice; future session-report changes should require observed Docker daemon proof, VM/ISO proof, live adapter proof, release proof, or a new customer-facing reporting promotion need before reopening.
- P2-125 adds `/api/session-report`, a browser Session Report panel, and `scripts/smoke_docker_session_report.sh` so customers can inspect one report covering runtime state, recent activity, proof sources, recovery drills, validation commands, and stronger-proof non-claims.
- P2-126 closes the Docker session report epic after README, TASKS, roadmap, Docker acceptance, session-report gate, Product Layer completion gate, runtime preview Python smoke, compose config, cleanup policy, and CI checks preserve Docker-safe reporting truthfulness without stronger proof claims.
- The inbox capability ownership boundary epic is closed for this Phase 2 slice; future inbox work should require live read-only OAuth proof, observed Maildir/user data proof, or a later confirmed external mutation model before claiming broader inbox ecosystem support.
- The first inbox ownership slice is `docs/architecture/inbox-capability-ownership-boundary.md`, smoke-tested by `scripts/smoke_inbox_capability_ownership_boundary.sh`.
- The inbox ownership boundary smoke is included in the Phase 2 golden demo runner so inbox capability ownership remains part of practical local/Docker-safe proof.
- `phase2-run --message "status"` attaches the inbox routing/ownership contract artifact so inbox capability ownership is visible in the user-testable runtime status proof.
- The broader app/inbox workflow promotion epic is closed for this Phase 2 slice; future broader app/inbox work should require a new milestone-backed epic when it adds a real workflow candidate, observed proof, or live adapter promotion beyond the completed Docker Product Layer completion gate.
- The first broader app/inbox promotion slice is `docs/architecture/inbox-workflow-promotion-boundary.md`, smoke-tested by `scripts/smoke_inbox_workflow_promotion_boundary.sh`.
- The Docker-first customer onboarding proof epic is closed for this Phase 2 slice; future Docker onboarding work should require a new milestone-backed epic when it adds observed Docker daemon proof, release packaging, live browser evidence, or a new customer-facing public try-path surface.
- The first Docker-first customer onboarding slice is `scripts/smoke_docker_customer_onboarding_quickstart.sh`, included in the Phase 2 golden demo runner so onboarding drift is caught with the practical Docker/local proof set.
- P2-95 promotes Docker Onboarding Status into the running preview through `/api/onboarding`, so customers can inspect quickstart steps, entrypoints, validation smokes, and non-claims from the product surface itself.
- P2-96 adds a Docker onboarding readiness checklist and focused contract smoke so customers can distinguish ready local-preview steps from observed-proof blockers before trying AgentOS.
- P2-97 closes the Docker-first customer onboarding proof epic after README, Docker acceptance, TASKS, roadmap, product surfaces, quickstart gate, onboarding contract gate, Product Layer completion gate, and golden runner all point to the same Docker-first public try path.
- The Docker guided Product Layer demo journey epic is closed for this Phase 2 slice; future guided demo work should require a new milestone-backed epic when it adds observed Docker daemon proof, live browser evidence, release proof, VM/ISO proof, or a new customer-facing journey surface.
- P2-98 adds `/api/demo-journey`, a browser Guided Demo Journey panel, and `scripts/smoke_docker_guided_demo_journey.sh` so customers can follow a Docker-safe path through runtime readiness, read-first work, prompt execution, activity narration, evidence, and recovery.
- P2-99 adds customer-facing expected outcomes to `/api/demo-journey`, the browser Guided Demo Journey panel, and Docker-safe smokes so successful local proof and blocked-until-observed proof claims are visible before customers try the path.
- P2-100 adds a Docker guided demo completion summary with completed local claims and next observed-proof blockers so customers know what the demo proves and what still requires external evidence.
- P2-101 closes the Docker guided demo journey epic after README, Docker acceptance, TASKS, roadmap, guided demo gate, Product Layer completion gate, runtime preview Python smoke, compose config, cleanup policy, and the golden runner all preserve the same proof-safe customer path.
- The Docker customer proof packet epic is closed for this Phase 2 slice; future proof packet work should require observed Docker daemon proof, live browser evidence, release proof, VM/ISO proof, or a new customer-facing proof promotion surface before reopening.
- P2-102 adds `/api/proof-packet`, a browser Customer Proof Packet panel, and `scripts/smoke_docker_customer_proof_packet.sh` so customers can see completed Docker-local claims, validation commands, proof sources, next blockers, and explicit non-claims together.
- P2-103 adds a Customer Proof Packet readiness checklist so completed claims, validation commands, proof-source links, explicit non-claims, and disabled automatic claim promotion are visible before customers rely on the packet.
- P2-104 closes the Docker customer proof packet epic after README, TASKS, roadmap, Docker acceptance, proof packet gate, Product Layer completion gate, runtime preview Python smoke, compose config, cleanup policy, and the golden runner all preserve the same proof-safe customer packet.
- The Docker customer handoff bundle epic is closed for this Phase 2 slice; future handoff work should require observed Docker daemon proof, live browser evidence, release proof, VM/ISO proof, or a new customer-facing proof promotion surface before reopening.
- P2-105 adds `/api/customer-handoff`, a browser Customer Handoff Bundle panel, and `scripts/smoke_docker_customer_handoff_bundle.sh` so customers can find the run command, first prompt, inspectable surfaces, validation commands, proof sources, and next observed-proof blockers in one place.
- P2-106 adds a handoff checklist to `/api/customer-handoff`, the browser Customer Handoff Bundle panel, and Docker-safe smokes so customers can follow run, inspect, validate, and blocker-recording steps in proof-safe order.
- P2-107 adds a share-safe handoff report to `/api/customer-handoff`, the browser Customer Handoff Bundle panel, and Docker-safe smokes so customers can summarize reproduced local proof and remaining observed-proof blockers without including secrets or auto-promoting claims.
- P2-108 closes the Docker customer handoff bundle epic after README, TASKS, roadmap, Docker acceptance, handoff bundle gate, Product Layer completion gate, runtime preview Python smoke, compose config, cleanup policy, and CI checks all preserve the Docker-safe customer handoff path.
- The Docker proof promotion center epic is closed for this Phase 2 slice; future proof promotion work should require observed Docker daemon proof, VM/ISO evidence, live OAuth evidence, release proof, browser evidence, external mutation proof, hardware attestation evidence, or a new customer-facing promotion surface before reopening.
- P2-109 adds `/api/proof-promotion`, a browser Proof Promotion Center panel, and `scripts/smoke_docker_proof_promotion_center.sh` so customers can see which claims are ready to describe and which require sanitized observed evidence.
- P2-110 adds a Proof Sharing Checklist to `/api/proof-promotion`, the browser Proof Promotion Center panel, and Docker-safe smokes so customers know which Docker-local Product Layer statements are share-ready and which stronger claims remain blocked.
- P2-111 closes the Docker proof promotion center epic after README, TASKS, roadmap, Docker acceptance, proof promotion gate, Product Layer completion gate, runtime preview Python smoke, compose config, cleanup policy, and CI checks all preserve the Docker-safe proof promotion path.
- The Docker Product Layer map epic is closed for this Phase 2 slice; future Product Layer map work should require observed Docker daemon proof, live browser evidence, release proof, VM/ISO proof, or a new customer-facing navigation need before reopening.
- P2-112 adds `/api/product-map`, a browser Product Layer Map panel, and `scripts/smoke_docker_product_layer_map.sh` so customers can see what to inspect first, where safe work appears, where proof is collected, and which blockers remain external.
- P2-113 adds reviewer routes to `/api/product-map`, the browser Product Layer Map panel, and Docker-safe smokes so runtime evaluators, proof reviewers, capability reviewers, and trust reviewers can inspect the same Product Layer surface in proof-safe order.
- P2-114 closes the Docker Product Layer map epic after README, TASKS, roadmap, Docker acceptance, Product Layer map gate, Product Layer completion gate, runtime preview Python smoke, compose config, cleanup policy, and CI checks preserve the Docker-safe customer navigation path.
- The verified boot and attestation proof boundary epic is closed for this Phase 2 slice; future verified boot work should require observed VM or hardware evidence before claiming Secure Boot, TPM measured boot, PCR/event-log, IMA, or hardware attestation proof.
- The first verified boot slice is `docs/architecture/verified-boot-attestation-proof-boundary.md`, smoke-tested by `scripts/smoke_verified_boot_attestation_boundary.sh`.
- `phase2-run --message "status"` attaches the verified boot/attestation non-claim artifact so boot-chain trust proof remains visibly separate from local runtime proof.
- The observed proof intake and blocker handoff epic is closed for this Phase 2 slice; future observed-proof work should require actual sanitized observed records or a new proof promotion task before claiming live credential, VM/ISO, release, browser, or boot-chain proof.
- The first observed proof intake slice is `docs/architecture/observed-proof-intake-boundary.md`, smoke-tested by `scripts/smoke_observed_proof_intake_boundary.sh`.
- Observed proof intake must keep secrets out of repo/workspace records, require sanitized evidence before proof promotion, and preserve explicit blockers for live credentials, VM/ISO, release, browser, and boot-chain proof.
- Observed proof records now use `docs/architecture/observed-proof-intake-schema.json` and can be checked with `scripts/observed_proof_intake_validate.py`; `scripts/smoke_observed_proof_intake_validator.sh` covers valid, blocked, and secret-term rejection behavior.
- `phase2-run --message "status"` attaches `agentos-observed-proof-intake-status.v1` so observed proof intake readiness and missing observed-record blockers are visible in the user-testable runtime status output.
- The capability graduation registry epic is closed for this Phase 2 slice; future broader app/inbox work should choose a candidate from `docs/architecture/capability-graduation-registry.json` before expanding browser or external app mediation.
- Capability graduation must prefer internal AgentOS capabilities, keep browser/external app mediation non-default, preserve permission/data boundaries, and require observed proof before live claims.
- The Calendar read-only live adapter readiness epic is closed for this Phase 2 slice; future Calendar work should require explicit live OAuth adapter design, tester credentials, or a confirmed mutation model before claiming more than fixture-backed readiness.
- The Gmail read-only live readiness epic is closed for this Phase 2 slice; future Gmail work should require explicit tester OAuth credentials, observed read-only proof, or a later confirmed mutation model before claiming more than setup readiness.
- The VM/ISO observed proof status epic is closed for this Phase 2 slice; future VM/ISO work should require a real observed VM run, sanitized evidence, or a new release/boot proof promotion task before claiming boot, reboot/recovery, managed runtime rejoin, ISO freshness, or VM signoff.
- The Calendar live read-only acceptance epic is closed for this Phase 2 slice; future Calendar live work should require real tester OAuth evidence, a live read-only adapter run, or a new proof promotion task before claiming live account proof or Calendar mutations.
- The Calendar live adapter candidate epic is closed for this Phase 2 slice; future Calendar live adapter work should require real tester OAuth evidence, an implementation task with credential storage and redaction behavior, or a new observed-proof promotion task before claiming live account proof.
- The Maildir inbox intake proof epic is closed for this Phase 2 slice; future broader app/inbox work should require real user Maildir evidence, a broader inbox workflow promotion task, or a new observed-proof promotion task before claiming production sync, external mutation, retention/compliance behavior, or full app ecosystem replacement.

## Validation Standards

Before closing a task:

- run targeted tests or smokes relevant to the change
- commit meaningful slices
- close the issue only after the completion commit exists
- merge into the correct parent branch
- delete completed child branches when safe
- run cleanup:

```bash
python3 scripts/cleanup_temp_artifacts.py --delete --json
python3 scripts/cleanup_build_artifacts.py --delete --json
```

## Source Companions

- `README.md`
- `PRD.md`
- `AGENTS.md`
- repo-local private context when present
- `docs/index.md`
- `docs/next-roadmap.md`
- `docs/architecture/docker-runtime-preview-boundary.md`
- `docs/architecture/intent-classification-contract.md`
- `docs/architecture/capability-permission-boundary.md`
- `docs/architecture/capability-permission-registry.json`
- `docs/architecture/capability-graduation-registry.md`
- `docs/architecture/capability-graduation-registry.json`
- `docs/architecture/user-owned-runtime-data-boundary.md`
- `docs/architecture/verified-boot-attestation-proof-boundary.md`
- `docs/architecture/observed-proof-intake-boundary.md`
- `docs/architecture/observed-proof-intake-schema.json`
- `docs/acceptance/phase2-golden-runtime-loop.md`
- `docs/acceptance/docker-runtime-preview.md`
- `docs/acceptance/phase2-intent-eval.json`
- `docs/roadmap/phase2-local-first-runtime-loop.md`
- `docs/reference/phase2-local-first-runtime-loop-closeout-v1.md`
- `.agents/roadmap-direction-judge.md`
- `docs/architecture/calendar-readonly-capability-contract.md`
- `docs/architecture/calendar-live-adapter-candidate-boundary.md`
- `docs/architecture/inbox-capability-ownership-boundary.md`
- `docs/architecture/maildir-inbox-intake-proof-boundary.md`
- `docs/architecture/inbox-workflow-promotion-boundary.md`
- `docs/architecture/browser-fallback-capability-boundary.md`
- `docs/acceptance/browser-fallback-observed-acceptance.md`
- `docs/architecture/updater-hardening-state-contract.md`
- `docs/acceptance/vm-iso-proof-preflight.md`
- `docs/acceptance/gmail-live-readonly-acceptance.md`
- `docs/acceptance/calendar-live-readonly-acceptance.md`
