# Updater Hardening State Contract

Status: Phase 2 active contract

This contract defines how AgentOS reports updater, rollback, recovery, and managed runtime rejoin state during the updater hardening epic. It is a local and smoke-verifiable contract. It does not claim that a live updater, reboot, rollback, VM, or ISO proof run happened unless that run is separately observed and recorded.

## Runtime Goal

Updater hardening exists to protect the primary AgentOS product goal: after update, restart, rollback, or recovery, the system should converge back to a managed AgentOS runtime session instead of leaving the user in an unmanaged appliance or generic Linux shell.

The state contract must therefore report:

- current update/stage/health state
- whether rollback or recovery is suggested
- whether return to the managed runtime is required
- what proof has actually been observed
- which external proof remains blocked

## State Values

`scripts/kernel_phase2_updater_state.py` exports `agentos-phase2-updater-state.v1`.

The command accepts four safe state values:

- `ready` - no recovery is requested by this contract run
- `blocked` - live updater, VM, reboot, rollback, or ISO proof is required before signoff can be claimed
- `rollback-needed` - recovery is suggested and rollback intent is explicit
- `recovery-suggested` - recovery guidance should be shown without running a destructive action

Every state keeps `managed_runtime_return_required=true`.

## Proof Boundary

This command is deliberately non-destructive:

- it does not run the updater
- it does not reboot
- it does not roll back slots
- it does not claim VM/ISO proof
- it does not claim live updater proof

The JSON `proof` object must keep `destructive_action_executed`, `live_updater_executed`, and `vm_iso_proof_completed` false until a separate observed acceptance run records otherwise.

## Acceptance

The focused smoke is:

```bash
scripts/smoke_phase2_updater_state.sh
```

The smoke validates the ready, rollback-needed, and blocked paths and asserts that live updater and VM/ISO proof are not claimed.

## Exit Condition

This contract slice is complete when:

- the state contract is documented
- the CLI emits and validates `agentos-phase2-updater-state.v1`
- the smoke proves blocked and rollback states are represented truthfully
- the roadmap and task state point from the updater epic to this first implementation slice
