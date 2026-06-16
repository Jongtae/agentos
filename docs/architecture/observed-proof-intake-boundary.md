# Observed Proof Intake Boundary

Status: Phase 2 completion epic active

## Purpose

AgentOS has many proof surfaces that cannot be completed by an automated local
smoke alone. Live Gmail OAuth, Calendar OAuth, VM/ISO boot, release signing,
browser acceptance, verified boot, TPM measured boot, IMA, and hardware
attestation all require a human-observed run, explicit credentials, real
artifacts, or hardware/VM state.

This boundary defines how AgentOS should accept that evidence later without
turning unobserved blockers into claimed proof.

## Intake Scope

Observed proof intake may record:

- the proof surface being tested
- the exact claim being evaluated
- who observed the run
- when and where it was observed
- sanitized evidence paths or URLs
- command lines or UI flows used for the run
- blocker status and recovery action
- explicit non-claims that still remain after the run

Observed proof intake must not record:

- OAuth refresh tokens, access tokens, bot tokens, API keys, or passwords
- raw mailbox contents beyond a tester-approved excerpt or summary
- private VM screenshots or logs that contain secrets
- hardware identifiers unless a maintainer intentionally publishes them
- claims that were not directly observed

## Proof Classes

| Proof class | Examples | Automated status | Promotion gate |
| --- | --- | --- | --- |
| Live credential proof | Gmail read-only, Calendar read-only | fixture and missing-credential paths only | tester provides credentials and records a successful non-mutating run |
| VM/ISO proof | boot, reboot, recovery, runtime rejoin | preflight and blocker checks only | observed VM run attaches sanitized logs or screenshots |
| Release proof | ISO artifact, checksum, signing, publication | manifest/checksum preflight only | real artifacts and signatures are published and verified |
| Browser proof | user-approved browser fallback run | fallback contract only | observed browser acceptance run records target, permission, and result |
| Boot-chain proof | Secure Boot, TPM event log, PCR replay, IMA | explicit non-claim only | VM or hardware evidence is captured and reviewed |

## Required Record Shape

An observed proof record should be representable as
`agentos-observed-proof-intake.v1`. The seed schema is tracked in
`docs/architecture/observed-proof-intake-schema.json`, and local records can be
checked with `scripts/observed_proof_intake_validate.py`.

```json
{
  "schema_version": "agentos-observed-proof-intake.v1",
  "proof_surface": "gmail_readonly_live",
  "claim": "AgentOS can read and summarize a tester-approved Gmail query without mutation.",
  "status": "observed|blocked|rejected",
  "observed_by": "maintainer or tester identity",
  "observed_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
  "evidence": [
    {
      "kind": "sanitized_log|screenshot|record_path|pr|issue_comment",
      "path_or_url": "redacted or reviewed evidence location",
      "redaction": "tokens and private content removed"
    }
  ],
  "remaining_non_claims": [
    "send/delete/archive are not proven"
  ],
  "blockers": [
    {
      "id": "gmail-oauth-live",
      "reason": "Tester credentials were not provided.",
      "recovery_action": "Run the Gmail read-only acceptance pack with explicit OAuth credentials."
    }
  ]
}
```

## Storage Boundary

Observed proof records belong in reviewed repo docs, issue comments, PR
summaries, or user-owned runtime records only after redaction. Secrets remain in
the tester secret store and must not be copied into workspace records,
`build-output/`, Docker bind records, or git-tracked files.

## Runtime Impact

The runtime may surface observed proof status, blockers, and recovery actions.
It must not flip a proof flag from `false` to `true` unless the corresponding
observed proof record exists and names the exact claim that was observed.

This keeps the Phase 2 local-first runtime loop honest:

```text
automated smoke proof
-> explicit blocker
-> observed run with sanitized evidence
-> claim-specific promotion
-> remaining non-claims stay visible
```

## Epic Exit Condition

The observed proof intake and blocker handoff epic is complete when:

- this boundary is documented and linked from the public docs map
- a smoke check verifies the boundary, roadmap, README, and TASKS state
- observed proof records have a machine-checkable schema and validator smoke
- the Phase 2 golden demo runner includes the intake boundary smoke
- README and roadmap identify the active epic and its exit condition
- future live credential, VM/ISO, release, browser, and boot-chain proof work
  can attach evidence without claiming unobserved proof
