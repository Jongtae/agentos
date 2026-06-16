# VM/ISO Proof Preflight

Status: preflight only

VM/ISO proof is a completion track for AgentOS, but it must not be claimed from
local smoke checks alone. The preflight exists to make the required proof path
machine-checkable while keeping the actual observed VM run explicit.

The preflight verifies that the local repository has the scripts needed to:

- build or select an AgentOS ISO
- boot or observe a VM through the UTM observation path
- refresh VM E2E scenario artifacts
- validate the VM E2E proof payload
- assemble the remastered VM boot checklist

It deliberately reports:

- `proof.vm_iso_proof_completed: false`
- `proof.observed_vm_boot: false`
- `proof.observed_reboot_recovery: false`
- `proof.observed_managed_runtime_rejoin: false`

Those fields may become true only after a real VM run is observed and evidence is
attached to the lifecycle issue or release signoff.

## Commands

```bash
python3 scripts/kernel_vm_iso_proof_preflight.py --json
scripts/smoke_vm_iso_proof_preflight.sh
```

The output includes planned commands and a blocker that tells the operator which
evidence is still required.

## Runtime Status Surface

`phase2-run --message "status"` attaches the same
`agentos-vm-iso-proof-preflight.v1` payload under
`capability_result.vm_iso_preflight_status` and writes the latest payload under
the workspace artifacts directory. This makes the proof path and blocker state
visible from the normal runtime status command without running a VM, building an
ISO, or claiming observed proof.
