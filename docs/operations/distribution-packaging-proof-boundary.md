# Distribution Packaging Proof Boundary

Status: Phase 2 operational contract

## Purpose

This boundary defines what AgentOS distribution packaging work can prove with
safe local checks, what requires release artifacts, and what remains blocked
until observed in a VM or release environment.

The goal is to let packaging work advance without claiming ISO freshness,
installer readiness, signing, or public distribution proof that was not actually
observed.

## Local Packaging Checks

Safe local checks may validate:

- repository files required by ISO layout and remaster scripts exist
- `scripts/smoke_agentos_iso_layout.sh` passes without requiring a generated ISO
- Docker/local preview proof remains separate from boot or installer proof
- cleanup policy reports no stale temp or build artifacts
- generated release artifacts are not committed
- release notes or PR text identify proof that is automated, blocked, or not claimed

These checks are useful preflight evidence. They do not prove a bootable release.

## Release Artifact Requirements

A release packaging claim requires observed evidence for:

- generated ISO path and filename contract
- release manifest with version, architecture, build timestamp, and source commit
- checksum publication for each release artifact
- signing or an explicit unsigned-preview statement
- secret-free artifact review
- build-output cleanup or a documented closeout exception

If any of these are missing, the release state is `blocked`, not `passed`.

## VM And Installer Blockers

The following proof requires an observed VM or release run:

- ISO boot reaches the AgentOS runtime surface
- reboot, recovery, and managed runtime rejoin converge back to AgentOS
- installer behavior works on the supported target
- VM networking and setup surfaces are usable
- generated ISO freshness matches the intended commit

Docker evidence must not be reused as VM/ISO proof.

## Non-Claims

Distribution packaging work must not claim:

- production OS distribution readiness
- installer readiness
- verified boot or hardware attestation
- release signing, notarization, or checksum publication without observed evidence
- ISO freshness without a generated artifact and matching manifest
- boot, reboot, recovery, or runtime rejoin proof without an observed VM run

## Promotion Gate

A packaging task can be promoted when:

- local packaging checks pass
- cleanup policy passes
- release artifact requirements are either satisfied or explicitly blocked
- VM/installer blockers are named with recovery actions
- README, TASKS, and roadmap do not overstate the proof

## Exit Condition

The distribution packaging proof boundary epic is complete when this document is
linked from the docs index, smoke-tested, and used by roadmap-governed automation
to distinguish local packaging preflight, release artifact proof, VM/ISO
blockers, and packaging non-claims.
