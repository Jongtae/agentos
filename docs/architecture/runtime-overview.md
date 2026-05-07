# Runtime Overview

AgentOS is an OS-native agent runtime experiment. The intended demo is the
bootable image; repo-local commands are developer shortcuts.

```text
Bootable OS image
  |
  v
AgentOS runtime
  |
  v
TTY / Telegram / setup page input
  |
  v
Command router / intent dispatcher
  |
  v
Tools and surfaces
  - LLM provider status
  - workspace/files
  - web access
  - Telegram setup/reply
  - proof/activity log
  |
  v
Reply + proof log
```

## Important Entrypoints

- `cmd/agentos-operator-tui/` - full-screen terminal operator frontend
- `scripts/agentos-kernelctl` - main runtime command surface
- `scripts/kernel_intent_dispatch.py` - intent dispatch surface
- `scripts/kernel_activity_feed.py` - activity feed surface
- `scripts/kernel_llm_setup.py` - LLM setup surface
- `scripts/kernel_telegram_setup.py` - Telegram setup surface
- `src/kernel/event_fabric/` - event/proof substrate

## Proof-First Runtime

The prototype is intentionally proof-first. The interesting loop is not only
that a request gets a reply, but that the runtime can explain what happened:

```text
receive request
-> understand intent
-> choose capability
-> run capability
-> reply or surface failure
-> write proof/activity event
```

The proof surfaces are prototype-grade. Phase 2 work focuses on making the
activity feed more reliable, readable, and central to the operator UI.
