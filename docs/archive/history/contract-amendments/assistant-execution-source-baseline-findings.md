# Assistant Execution — source-baseline findings history

Extracted under DOCS-FINAL-03 (#1063) from the canonical [Assistant Execution Contract](../../../assistant-execution-contract.en.md). This is dated source/test evidence from baseline `4a0d3e6fba987121298addb7349778a0a1b349bc`, not current normative execution policy and not a reproduction on the owner's Mac.

## Audited findings versus inference

Source baseline: `4a0d3e6fba987121298addb7349778a0a1b349bc`. These are source/test observations, not a reproduction on the owner's Mac.

| Finding | Baseline evidence | Owner |
| --- | --- | --- |
| Agent loop exists | `agent_runtime.run_agent` feeds tool results back to bounded model turns | #606 adapts it |
| Route tool exposure differs | `Capabilities.definitions`, `bounded_execution.MCP_TOOLS`, `mcp_bridge.serve`, isolated facade | #604 |
| CLI public preflight is lexical | `subscription_public_lookup_query` admits commands or selected city/weather wording | #606, after #605 |
| Prior assistant messages can close public egress | `quickstart_service.run_one` history provenance and `Capabilities.execute` | #605 |
| Bridge errors lose recovery distinctions | `mcp_bridge.serve` collapses different failures | #607 |
| Attempt failure and goal success are entangled | `run_agent` accumulates failure; CLI exit has different treatment | #607 integrating #598 |
| Fixtures do not establish model/deployed quality | [#512 record](presence-eval-01.en.md) and reported live mismatch | #603/#608 |

Their combination is a plausible cause of the reported weather/search behavior, not a proven account of that private incident. Installed revision, effective profile and exact events remain to be verified. #597 already owns semantic capability/remember fixes, #598 owns result truth, and #581 owns Telegram client behavior. Do not duplicate them.

