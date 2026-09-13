# D-MP2-02 — Reviewed Capability Discovery and Recommendation Contract

> **Historical contract.** This document remains authoritative for its original owner-local, read-only recommendation scope. It did **not** authorize marketplace discovery, download, installation, activation, credential setup, permission grants, or execution. The planned [Agent Distribution Platform / #333](https://github.com/Jongtae/personal-agentos/issues/333), including [D-REG-01 / #339](https://github.com/Jongtae/personal-agentos/issues/339), is a successor program and must not be used to retroactively widen what D-MP2-02 implemented or proved.

## Objective and scope

When an owner asks for an outcome that the enabled AgentOS capability set cannot safely handle, AgentOS may recommend a reviewed MCP, independent A2A Agent, or isolated runtime from an owner-local reviewed catalogue. It explains the recommendation and its boundaries without downloading, installing, activating, connecting, or executing it.

This is a contract-only design. It implements no marketplace, network discovery, plugin download, capability installation, activation, permission or scope grant, credential/OAuth flow, endpoint, external action, or operating deployment.

## Owner outcome and recommendation boundary

The owner asks for an outcome, not a connector. AgentOS first checks enabled reviewed capabilities. If none can meet the outcome, it returns zero or more recommendations with a plain-language reason and a safe next step. “Recommend” is R0 information: it never changes capability state. A model suggestion, a catalogue entry, or a bare “yes” is never an install or approval.

The catalogue is owner-local and curated into the shipped/reviewed set. It is not a public marketplace or a live web search result. Unknown URLs, unpinned versions, unsigned manifests, arbitrary code, and runtime-defined tools are rejected.

## Catalogue record and ranking

Each reviewed record has: opaque capability ID; kind (`mcp`, `a2a`, or `runtime`); human name and declared outcome tags; provenance publisher/source; fixed version and immutable artifact digest; license; declared tools; required permissions, OAuth scopes, data categories, outbound hosts, isolation profile, cost class, health-check contract, removal/recovery procedure, and compatibility constraints.

Ranking is deterministic and explainable: exact declared outcome tag match, owner-enabled compatibility, least requested data/permission surface, local-first/isolation preference, lower declared cost class, then stable capability ID. It never uses private message bodies as catalogue search terms or ranking inputs. A recommendation read model exposes only name, kind, outcome reason, declared boundary summary, cost class, health/recovery label, and a future approval handoff ID; it excludes secrets, raw paths, tokens, package URLs, arbitrary manifest payloads, and internal scores.

## Policy and data flow

`CapabilityRecommendationOrchestrator` is the future sole policy owner. It receives an owner ID, bounded outcome class, and current reviewed capability state; it emits a redacted recommendation model and audit evidence. HTTP, Telegram, and the local companion call that same read-only operation. No channel reaches a package manager, MCP transport, A2A peer, runtime launcher, or `CapabilityRegistry.transition` directly.

Only minimal classified outcome tags may be retained in recommendation audit records. Full prompt text, Personal Space content, selected documents, approval material, identifiers from external systems, secrets, and raw recommendation requests are excluded from portable evidence and export. Restore keeps only safe terminal recommendation history and never creates an install queue.

## Threat model and recovery

Implementation must resist prompt-injected catalogue entries, confused deputy installation, poisoned metadata, version substitution, dependency/license drift, misleading cost claims, recommendation replay, channel/owner confusion, and secret exfiltration. Stale, unavailable, or incompatible entries are omitted with a named recovery explanation; they are never silently replaced with an arbitrary alternative.

## Explicit future install handoff

A later design iteration may define an owner-visible approval/install handoff only after a selected recommendation is shown with its exact fixed record, requested permission/data boundary, isolation, cost, health check, and removal/recovery plan. That later contract must require explicit owner confirmation and separately cover download integrity, activation, credential/OAuth configuration, rollback, and live acceptance. D-MP2-02 grants none of those authorities.

## I-MP2-02 entry contract

I-MP2-02 may activate only after this design PR merges, its issue is closed, canonical-document/plan/ledger checks pass, and a new goal-ready implementation issue exists. Its minimum scope is a fixture-backed owner-local reviewed catalogue and read-only recommendation model with deterministic ranking, redaction, audit/export/restore safety, and HTTP/Telegram/local-companion parity. It excludes every installation, activation, connection, permission, scope, credential, OAuth, external action, and operating-mode behavior.
