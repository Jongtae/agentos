# Browser Fallback Capability Boundary

Status: Phase 2 active contract

Browser automation is a fallback path for AgentOS, not the default product identity. The runtime should prefer internal capabilities first, allow browser fallback only when the request shape requires it, block external state that lacks explicit permission or credentials, and identify repeated fallback patterns that should graduate into OS-native capabilities.

## Routing Decisions

`scripts/kernel_phase2_browser_fallback_contract.py` exports `agentos-phase2-browser-fallback-contract.v1`.

The contract classifies a request into one of four decisions:

- `internal_capability` - AgentOS can handle the request through an internal capability such as native web access.
- `allowed_browser_fallback` - browser automation is allowed as a fallback for interactive, JavaScript-heavy, or compatibility-bound pages.
- `blocked_external_state` - the request requires blocked external state, a missing allow-domain, credentials, or unsupported proof.
- `graduate_to_capability` - repeated browser fallback should become a first-class internal capability candidate.

## Proof Boundary

This contract does not launch a browser, use third-party credentials, or claim live website proof. It records the routing decision and keeps `live_browser_executed=false`.

The contract exists so future runtime work can decide when browser fallback is allowed without accidentally making browser automation the default path.

## Acceptance

The focused smoke is:

```bash
scripts/smoke_phase2_browser_fallback_contract.sh
```

The smoke validates internal capability, allowed fallback, blocked external state, and capability graduation paths without live credentials or external browser state.

## Exit Condition

This slice is complete when the contract, documentation, and smoke make the browser fallback decision explicit and keep internal capability ownership preferred.
