# Verified Boot And Attestation Proof Boundary

Status: Phase 2 operational contract

## Purpose

This boundary defines what AgentOS may claim about verified boot, measured boot,
runtime integrity, and hardware-backed attestation.

AgentOS can safely prove local runtime behavior today. It must not claim Secure
Boot, TPM attestation, PCR integrity, IMA enforcement, or hardware trust unless
those facts are observed from a VM or physical machine and attached to the
proof record.

## Research Basis

This boundary follows the public proof shape implied by:

- UEFI Secure Boot and driver signing, which centers on firmware-managed
  authentication of boot components:
  `https://uefi.org/specs/UEFI/2.9_A/32_Secure_Boot_and_Driver_Signing.html`
- TCG TPM 2.0, which provides TPM commands and capabilities used by
  platform-specific attestation:
  `https://trustedcomputinggroup.org/resource/tpm-library-specification/`
- TCG EFI Platform Specification, which describes measuring boot events into
  TPM PCRs and recording boot event log entries:
  `https://trustedcomputinggroup.org/resource/tcg-efi-platform-specification/`
- Linux Integrity Measurement Architecture, which provides measurement,
  appraisal, and audit concepts for runtime file integrity:
  `https://sourceforge.net/p/linux-ima/wiki/Home/`

These sources do not make AgentOS verified by themselves. They define the proof
classes AgentOS must observe before making a trust claim.

## Local Runtime Proof

Safe local or Docker checks may prove:

- the AgentOS runtime starts
- intent dispatch and bounded capabilities work
- activity and record output are created
- Docker/local preview remains secret-free
- cleanup policy has no stale temp or build artifacts
- proof payloads keep VM, ISO, Secure Boot, TPM, and IMA claims explicit

These checks are useful runtime evidence. They do not prove boot-chain trust.

## Secure Boot Proof Requirements

A Secure Boot claim requires observed VM or hardware evidence for:

- firmware or VM Secure Boot state
- the bootloader or shim signature path used by the booted AgentOS image
- kernel and initramfs signature policy when applicable
- the source commit, ISO or disk image, and firmware configuration under test
- recovery behavior when Secure Boot is disabled, unavailable, or mismatched

If this evidence is missing, the Secure Boot state is `blocked` or
`not_observed`, not `passed`.

## TPM Measured Boot And Attestation Requirements

A measured boot or TPM attestation claim requires observed evidence for:

- TPM or vTPM availability
- boot event log capture
- PCR values bound to the observed boot
- a verifier or local validation step that checks event-log replay against PCRs
- a record of which image, kernel, initramfs, and runtime artifacts were
  measured

Docker evidence must not be reused as TPM measured boot proof.

## Linux IMA Requirements

An IMA runtime integrity claim requires observed evidence for:

- kernel support and boot parameters for IMA measurement, appraisal, or audit
- the active IMA policy
- measurement, appraisal, or audit logs from the tested system
- a rule that states whether AgentOS is only recording measurements or also
  enforcing access decisions
- a recovery path when IMA is unavailable or policy validation fails

IMA measurement is not the same as IMA appraisal. AgentOS must distinguish
read-only measurement evidence from enforcement claims.

## Non-Claims

AgentOS must not claim:

- production verified boot readiness
- hardware-backed attestation
- TPM PCR integrity
- Secure Boot enforcement
- IMA appraisal or audit enforcement
- firmware trust or supply-chain integrity
- Docker runtime proof as boot-chain proof

Any of those claims require observed VM or hardware evidence and a matching
proof artifact.

## Promotion Gate

A verified boot or attestation task can be promoted when:

- local runtime proof remains separate from boot-chain trust proof
- Secure Boot, TPM, PCR/event-log, and IMA states are either observed or
  explicitly blocked
- README, TASKS, roadmap, and PR text do not overstate the claim
- recovery actions are recorded for unavailable firmware, TPM, vTPM, or IMA
  surfaces
- cleanup policy passes after any build, remaster, or VM proof work

## Exit Condition

The verified boot and attestation proof boundary epic is complete when this
document is linked from the docs index, smoke-tested, included in the Phase 2
golden demo runner, and used by roadmap-governed automation to separate local
runtime proof from Secure Boot, TPM measured boot, PCR/event-log, IMA, and
observed VM/hardware proof requirements.
