# Retired MP1 assistant compatibility router

Relocated by PRESENCE-CONT-01 / #511 after owner-requested code cleanup.

This directory preserves the historical MP1 `PersonalAssistantOrchestrator` and
its focused test as evidence. It is intentionally outside the installed
`personal_agent` package and is not part of the supported runtime.

## Why it was retired

The current product has one conversation path owned by `AgentService`,
`IntentClassifier`, connector handoff, Calendar conversation, Work/Event/Evidence,
and the Presence projection layer. The older orchestrator was a second assistant
router reachable only through the explicit `/assistant ...` form.

Production constructed `PersonalAssistantOrchestrator(store)` without its Drive,
A2A, or Calendar adapters. Those adapters were supplied only by the historical
unit test, so the main Drive/A2A/Calendar branches were not owner-reachable through
the shipped object graph. Current Drive, Gmail, and Calendar paths use different,
owner-bound connector contracts.

Retirement removes the duplicate speaking/routing seam from the product package.
It does not remove the canonical Capability/Grant/Work/Evidence model, current
connector handoff, Calendar approval path, or isolated subscription-engine boundary.

The source and test are preserved here for history; they are not collected by the
normal product test suite.
