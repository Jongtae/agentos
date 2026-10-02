# SKILL-PREP-01 — Skill-supply interface decision and pinned compatibility

**Issue:** [#960](https://github.com/Jongtae/agentos/issues/960) (child of [SKILL-SUPPLY-01 #959](https://github.com/Jongtae/agentos/issues/959))
**Date:** 2026-10-02
**Status:** decision record. It sets the contracts and gates for [#961](https://github.com/Jongtae/agentos/issues/961). It changes no runtime behavior, dependency, constitution text or active goal.
**Inspected repository baseline:** `bd7fec18` (`main` after #965)
**Governing specification:** [Supplied Skills and Reusable Execution — Implementation Preparation](skill-supply-execution-preparation.en.md), section 18

The owner directed this preparation on 2026-10-02 ("960 이슈 구현 진행하고 … 머지까지"). The work stayed inside #960's own authority: public source inspection, a disposable model-free spike, and this record. No paid model call, owner file, live session, package import into the product, dependency installation into AgentOS, or `delivery-plan.yaml` change was made.

Evidence classes used here: **static review** (repository and upstream source read at pinned revisions), **disposable fixture execution** (the model-free spike in section 7, run outside the repository), and **published documentation**. No evidence comes from **real runtime operation**.

## 1. ADR — optional skill knowledge behind the existing package seam

**Context.** AgentOS already has one package lifecycle (`PluginRegistry`), one resolution step (`manifests.runtime_packages`), one action source (`agent_runtime.action_definitions` over `DEFINITIONS`) and one execution object (`Capabilities`). Every route projects those: the direct API tool list, the trusted-local Codex/Claude Code MCP bridge (`mcp_bridge.serve`) and the strict-isolated bridge. Browser, settings, family and Work recovery behavior already works and must not be re-implemented.

**Decision.**

1. A skill is **optional, versioned knowledge carried by an existing AgentPackage**, not a new executor or permission. The package keeps declaring existing host actions only.
2. The **skill-supply port** is a read-only boundary next to the existing action ports. It lists bounded descriptors and loads pinned content. It never launches a browser, changes settings, installs anything or mutates an account.
3. The worker reaches skill content through **two new effect-free host actions** defined once in `DEFINITIONS`. Every route then gets them through `action_definitions`. They are not a second tool registry. The names are decided in #961; the conceptual pair is *load a skill body* and *read a skill resource*, matching the de facto names `load_skill` / `read_skill_resource` used by Microsoft Agent Framework.
4. **Foreign formats are normalized once, at acquisition**, by a source adapter (Anti-Corruption Layer). No per-call translation model is used.
5. **Rollout is Branch by Abstraction.** With skills off, the request/tool path is the pre-skill path, byte for byte in tool surface. The original executor stays the only executor.

**Pattern mapping.** These are mappings onto existing symbols; no pattern implies a new class.

| Pattern / principle | Where it applies | Existing symbol reused | Rejected alternative |
| --- | --- | --- | --- |
| Ports & Adapters | Skill-supply port beside the action ports | `PluginRegistry`, `runtime_packages`, `DEFINITIONS`/`action_definitions`, `Capabilities.offered_tools` | A skill service with its own runtime; agent-framework `SkillsProvider` as the runtime (section 4) |
| Adapter / Anti-Corruption Layer | Upstream `SKILL.md` + resources → pinned AgentOS package record; `allowed-tools` → metadata only | Manifest validation style in `manifests.validate`; host-action vocabulary `HOST_ACTIONS` | Guessing that a foreign `Read`/`Bash`/browser tool equals an AgentOS action; per-call LLM translation |
| Design by Contract | Pre/postconditions per boundary (section 2) | Existing typed refusals (`ExecutionError` failure classes), `finish`/`check_claim`/goal judgment | Treating a matching JSON shape or a model's success flag as compatibility |
| Branch by Abstraction | Skills switch off → pre-skill path; on with zero skills → same surface plus an empty catalogue | `Capabilities.offered_tools` hiding pattern (#656/#659/#774/#814/#826) | Two runtimes; shadow-running old and new cart mutations |

**Not adopted as patterns:** a Strategy per site, site inheritance trees, a mandatory specialist chain, a translator agent, a skill-specific verifier.

**Untouched by this decision:** `BrowserSession`/`browser_worker`, `SettingsOrchestrator` setters, `family_setup`/`family_share`, login and payment checks, `WorkBudget`, `WorkLedger`, the outcome contract (`finish`, `check_claim`, goal judgment), Memory/MemoryCandidate policy, folder grants, the CLI argument builders except the native-discovery risk in section 6, and `delivery-plan.yaml`.

## 2. Behavioral interface and change-surface table

| Boundary | Existing owner / symbol | Input meaning | Output meaning | Permitted side effects | Errors | Retry / continuation | Version compatibility | Allowed change surface in #961 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **Source adapter** (acquisition) | New thin adapter module; storage under the existing `PluginRegistry` root | Pinned source spec: URI, immutable revision, path | Staged package record (section 5 identity) plus compatibility status set | Network read of the pinned source; writes only into a staging directory, then an atomic rename | `invalid_package`, `licence_unknown`, source unreachable (a supply failure, never an authority denial) | Re-fetch the same revision only; a different revision is a new candidate | Upstream revision is pinned; a new revision is a separate staged candidate | New adapter module and its tests. Adding a supplier changes only its adapter. |
| **Supply / resource loading** | `PluginRegistry` (lifecycle), `runtime_packages` (resolution) | Package id + skill name; resource path relative to the pinned root | Bounded descriptors (name, description, package, revision); body or resource text | None. Never browser, settings, account, install or hook execution. | `skill_unavailable` (missing, disabled, removed, source failure); `invalid_package` (path escape, symlink, oversize) | A content miss leaves the general path usable; the next Work re-resolves | Skill revision is captured per Work; no mid-Work silent swap | `runtime_packages` gains optional skill descriptors; v1 manifests without them stay valid (section 7 shows that `validate` ignores unknown top-level keys) |
| **Knowledge → worker** | Instruction construction for each route; `Capabilities.offered_tools` | Owner request verbatim, current constraints, catalogue | Same request and constraints plus the catalogue and selected loaded content, attributed to package and revision | Context tokens only | None new. An empty catalogue is not an error. | Unchanged | Catalogue text is generated from records, not by a model | Catalogue injection and the two read tools; `offered_tools` hides them when skills are off |
| **Worker → host action** | `DEFINITIONS`, `action_definitions`, `Capabilities.execute`, `mcp_bridge.serve` | Unchanged argument meanings for every existing action | Unchanged results, observations and refusals | Unchanged | Unchanged; skill provenance never reclassifies an old call | Unchanged; stop/deadline from `WorkBudget` | Optional provenance argument only. Old callers never need a skill id. | Two new effect-free definitions; nothing else in existing definitions |
| **Observation → outcome → resume** | `finish`, `check_claim`, goal judgment, `WorkLedger`, effect history | Unchanged | Partial/unknown/failed classifications unchanged; loaded skill revisions recorded as Work provenance | Evidence record of which skill revision was loaded | A revoked skill blocks further package-scoped use (reusing the #604 `current_packages` stale check already applied to `delegate_agent`) | Changing method does not reset effect history or authorize replay; reconcile before any retry | Recorded revision travels with the Work | Provenance field on existing Evidence; no new outcome type |

**Preserved contracts (explicit).**

- **Off:** no loader, catalogue, extra model call or new tool in any route. `offered_tools` equals today's set.
- **On, zero/missing/broken skills:** existing browser, settings, calendar, file, search and Memory tools stay offered exactly as today. A knowledge miss is reported as `skill_unavailable`, never as a denied account permission.
- **No forced migration:** no reinstall, re-login, family re-creation, model reset or settings migration on upgrade.
- **Revocation:** disable or remove blocks further package-scoped use through the existing `current_packages` resolver. Loaded text already sent to a model cannot be recalled. The Work stops or rebuilds its context through existing recovery, preserving the original goal and effect ledger. A different permitted method is a new selection, not a fallback that launders a revoked skill.
- **Unknown effects:** after a possible mutation, current state is read before any retry or method change. Disabling skills cannot undo a cart change.

## 3. Profile mapping

| Route / profile | #961 support | How content arrives | Native CLI skill discovery |
| --- | --- | --- | --- |
| Direct API (owner-configured model) | **Supported** | The two host actions in the native tool list | Not applicable |
| Trusted-local Codex (`trusted-local`) | **Supported via the bridge** | Same two actions through `mcp_bridge` `tools/list` | **Risk to close in #961.** Codex 0.153.4 reports feature `skill_search` stable/on and `skip_host_skill_discovery` "under development"/off. The worker keeps the owner's `CODEX_HOME` for login, and `--ignore-user-config` only skips `config.toml`. Unreviewed host skills under `$CODEX_HOME/skills` may therefore reach the worker today. This matches the already documented `AGENTS.md` caveat in `bounded_execution.py`. #961 must establish the actual behavior model-free and disable host discovery with a documented flag, or record the limitation. |
| Trusted-local Claude Code (`trusted-local`) | **Supported via the bridge** | Same two actions; `--allowedTools` gains their exact bridge names | HOME and cwd are the turn's own directory, so no owner or project skills are present. Claude Code 2.1.280 documents `--disable-slash-commands` ("Disable all skills"); #961 adds it to make that explicit. |
| Strict-isolated (`strict-isolated`) | **Unsupported in #961** (`unsupported_environment`) | None. The isolated bridge has no owner store, and serving package content into the sandbox is a separate isolation change. | Built-ins already removed (`--tools ''`). |
| Delegated specialist (`delegate_agent`) | **Not offered in #961** | The child keeps its role tools only | Not applicable |

Nothing is added to any profile silently. An unsupported profile tells the worker that skills are unavailable there instead of offering a tool that fails.

## 4. Existing Solutions Review — Adopt / Adapt / Build

Upstream revisions inspected on 2026-10-02 (shallow clones; release data from PyPI JSON).

| Need | Candidate (exact revision) | Licence / maintenance | Fit | Decision |
| --- | --- | --- | --- | --- |
| Skill representation | Agent Skills specification, `agentskills/agentskills@69ef37e9424c0a7ea9dd2293b559e43ec8176379` `docs/specification.mdx` | Apache-2.0; active spec | Required `name` (1–64, lowercase/digits/hyphen, equals the directory) and `description` (1–1024). Optional `license`, `compatibility` (≤500), `metadata` (string map), `allowed-tools` (experimental). Layout: `SKILL.md` plus optional `scripts/`, `references/`, `assets/`. | **Adopt** the format and its progressive-disclosure model. AgentOS execution metadata stays outside the standard frontmatter. |
| Reference parser/validator | `skills-ref` 0.1.1 (PyPI, 2026-01-10) | Apache-2.0; "Development Status :: 3 - Alpha". README: *"This library is intended for demonstration purposes only. It is not meant to be used in production."* Depends on `strictyaml` 1.7.3 (last release 2023-03-10), `click`, `python-dateutil`, `six`. | API: `validate(skill_dir) -> list[str]`, `read_properties(skill_dir) -> SkillProperties`, `to_prompt(skill_dirs)`. It validated the pinned upstream skill with no errors. | **Reject as runtime dependency** (self-declared non-production, stale YAML dependency, rejects every non-standard key). Its rules are the conformance reference for #961 tests. |
| Loader / resource provider | Microsoft Agent Framework `SkillsProvider` / `FileSkillsSource`, `agent-framework-core` 1.19.0 (2026-09-18), `python/packages/core/agent_framework/_skills.py` @ `6d8e16ea364100497723b99e3251f8c158047bf5` | MIT; "5 - Production/Stable"; active | Model tools `load_skill`, `read_skill_resource`, `run_skill_script`, with framework approvals on by default. SafeLoader with duplicate-key detection; `Path.is_relative_to` containment; rejects symlinks and junctions below the root; re-validates each file just before reading. No script runner in core. | **Adapt the semantics, not the dependency.** It subclasses the framework's `ContextProvider` and emits `FunctionTool`s for its own agent loop. AgentOS tools must come from `DEFINITIONS` through `action_definitions` on every route, including the MCP bridge. Its approval layer would duplicate AgentOS authority, and it adds about 10 packages (pydantic, opentelemetry-api, msgspec, python-dotenv, PyYAML). Unmet contract: one action source across API and CLI bridge routes. |
| YAML parsing | PyYAML 6.0.3 (2025-09-25) | MIT; maintained | `SafeLoader` builds no Python objects from tags (the spike's `!!python/object/apply` case is refused). Duplicate keys need a small loader hook, as agent-framework does. | **Adopt** PyYAML as #961's one new runtime dependency, used only through `SafeLoader` with duplicate-key rejection. AgentOS has no YAML dependency in `pyproject.toml` today; this needs the normal dependency review in #961. |
| Frontmatter split | `python-frontmatter` 1.3.0 (2026-05-20) | MIT; maintained; requires PyYAML | Uses a SafeLoader-equivalent `yaml.load`; silently keeps the last duplicate key. | **Reject.** It does not add a needed contract over the ten-line split. AgentOS must reject duplicate keys rather than accept them silently. |
| Multi-source supply and locks | `vercel-labs/skills` (skills.sh CLI, npm 1.7.0) @ `3694740352eeef5cdd689af694c485f1ff62eec3` | MIT; active | Sources: GitHub/GitLab/any git/local/archive (10 MiB download, 25 MiB extracted, 1000-file caps). Lock records source, optional branch/tag `ref` and a tree hash, not a commit. Installs into each agent's own skill directory. Never runs skill scripts. Telemetry on by default. | **Adapt conventions** (source spec shape, archive caps, never execute scripts). **Reject the CLI** as the acquisition path: it writes into CLI-native skill directories that AgentOS must not depend on (R5), pins no commit and sends telemetry by default. |
| Hub, trust and quarantine | `NousResearch/hermes-agent` Skills Hub @ `e05b16348b1d06a3311237423b0a4fc30d9c5aa1` (`tools/skills_hub.py`, `skills_hub_install.py`, `skills_guard.py`) | MIT; active | Lock with source, trust level, scan verdict and a sha256 truncated to 16 hex. Quarantine copy before install. Trust tiers builtin/trusted/community. No user commit pinning. | **Adapt conventions** (quarantine/staging before enable; trust tier as a recorded attribute, not authority). Reject its truncated hash and regex scan as identity or safety proof. |
| External catalogue metadata | skills.sh index, Hermes taps, MCP Registry | Various | Discovery metadata only | **Deferred.** Not in the #961 MVP. A documented metadata path may be compared later. No scraping of closed stores. |

**Build (thin glue only), with the unmet contract stated:** a source adapter for a pinned Git revision, a compatibility classifier producing the section 5 vocabulary, and the two host actions. The unmet contract is that skill content must be served through AgentOS's single action source on every route, under its Work budget, stale-package revocation and Evidence. No inspected candidate exposes that without bringing its own agent loop or approval layer. Containment rules follow `SkillsProvider` exactly rather than being invented.

## 5. Compatibility mapping, identity and failure vocabulary

**Field mapping (standard frontmatter stays standard).**

| Upstream field | AgentOS record | Note |
| --- | --- | --- |
| `name` | skill name, unique within the package | Must equal the directory name. Skills are addressed as package id plus name, so equal names in two packages do not collide. A duplicate within one package is `invalid_package`. |
| `description` | catalogue text | The only text offered before loading. Bounded (section 6). |
| `license` | licence expression plus the licence file's digest | "Complete terms in LICENSE.txt" resolves only when that file is pinned. Otherwise `licence_unknown`. |
| `compatibility` | shown with the catalogue entry | Informational; environment checks remain AgentOS's. |
| `metadata` | preserved verbatim | Never read as authority. |
| `allowed-tools` | preserved as metadata | **Never a grant.** Names matching `HOST_ACTIONS` are informational. Others (for example `Bash(git:*)`, `Read`) set `requires_connection` or `scripts_or_hooks_required` only when the skill depends on them. |
| Any other key | `adapted` with the key kept as metadata | AgentOS execution metadata lives in the AgentOS package record, not in upstream frontmatter. |

**Identity, attributed separately.** A digest alone is not a verified publisher.

| Attribute | Example (spike) |
| --- | --- |
| AgentOS package id and local adaptation revision | `internal-comms`, adaptation `1` |
| Claimed publisher / source identity | GitHub owner `anthropics` (claimed by the URL; not a signature) |
| Source URI and upstream path | `https://github.com/anthropics/skills`, `skills/internal-comms` |
| Immutable upstream revision | `8a1541c4a3ffa5a20a5a91de0dcf3f0bab1d1ef4` |
| Per-file sha256 and package content digest | `SKILL.md` `067b7587…6475`; content digest (sha256 of the sorted file map) `28876ab11f28ab257dd5c53398741dacf2f3781ea03e9e93a5eb4470d1a249a3` |
| Licence | Apache-2.0 by the pinned `LICENSE.txt` (`bc6b3af2…1362`) |

**Compatibility status set** (a package can carry several): `supported_as_is`, `adapted`, `requires_connection`, `unsupported_environment`, `scripts_or_hooks_required`, `licence_unknown`, `invalid_package`. Only `supported_as_is` and `adapted` can be enabled in #961. `scripts_or_hooks_required` is never downgraded by deleting the script.

**Runtime knowledge errors** (distinct from authority refusals): `skill_unavailable` (missing, disabled, removed, source failure) and `skill_revoked` (a loaded revision no longer current). Neither hides an existing tool.

## 6. Budgets, supplier and acquisition policy

**Budgets inside the existing `WorkBudget`.** No second budget service. Each load or resource read is one ordinary tool attempt (`WORK_TOOL_ATTEMPTS = 40`). #961 caps:

- catalogue: at most 32 descriptors and 8 KB of text per Work;
- loads: at most 3 skill bodies per Work, each at most 500 lines and 32 KB;
- resource reads: at most 8 per Work, each at most 64 KB; text resources only;
- package files: at most 256 KB each, at most 200 files, at most 4 MB per package at acquisition;
- discovery: none during a Work in the MVP. Acquisition is a separate owner-directed step.

The concrete numbers are #961 defaults that #961's tests pin. They are not quality claims.

**MVP supplier.** Bundled reviewed skills (AgentOS-authored, for #962/#963) plus **one pinned Git source**: `anthropics/skills` at an exact commit, restricted to skill directories whose own `LICENSE.txt` is Apache-2.0. The spike target is `skills/internal-comms`. That repository's `docx`, `pdf`, `pptx` and `xlsx` skills are source-available, not open source, and are excluded. `doc-coauthoring` has no licence file and stays `licence_unknown`. `internal-comms` was not authored for AgentOS, which satisfies the "not authored to pass the AgentOS fixture" requirement. It is not a shopping or management skill, so it proves import, not usefulness for those slices.

**Acquisition and enable policy.** Acquisition happens when the owner asks for it in conversation, with a notice and a disable undo. There is no settings page (Presence Pages rule) and no automatic marketplace install. Staging writes bytes to a temporary directory, verifies the pinned digests, classifies, then atomically installs under the `PluginRegistry` root. An enabled trusted instruction read needs no per-task prompt. Enabling is a lifecycle state, not account authority.

## 7. Disposable compatibility spike (model-free)

The spike ran on 2026-10-02 with Python 3.12.12 and PyYAML 6.0.3 from a temporary directory outside the repository. It imported this worktree's `personal_agent.manifests` read-only. No model, account, browser or owner file was used, and it is not committed as product code. It fetched the six pinned files of `anthropics/skills@8a1541c4…/skills/internal-comms` from `raw.githubusercontent.com`.

| Case | Result |
| --- | --- |
| Upstream digests against the pin | all six match |
| Upstream classification | `supported_as_is`; 27 body lines; licence resolved through the pinned `LICENSE.txt` |
| Resource `examples/faq-answers.md` | read, 2366 bytes, inside the pinned root |
| Resource `../../etc/passwd` | refused: outside pinned root |
| v1 manifest with no tools/roles, enabled | accepted by `validate_package`; the resolved host-action set is identical to built-in only |
| `scripts/run.py` present | `scripts_or_hooks_required` |
| Symlink to `/etc/hosts` under `references/` | refused: `invalid_package` |
| File over 256 KB | refused: `invalid_package` |
| Duplicate `name` key | refused at parse |
| `name` differs from directory | refused: `invalid_package` |
| No `license` | `licence_unknown` |
| `!!python/object/apply:os.system` tag | refused by `SafeLoader` (no constructor) |
| `allowed-tools: Bash(git:*) Read browser_read` | `requires_connection`; `Bash(git:*)` and `Read` noted as unmapped; nothing granted |
| Extra `agentos:` frontmatter key | `adapted`, kept as metadata |

The upstream skill's `examples/*.md` mention Slack, Google Drive and Calendar as places to gather information. That is prose for the model to judge, not a tool declaration. AgentOS offers what is connected (`calendar_query`) and reports nothing else as available.

**Not demonstrated** (stated, not hidden): loading through a real route, catalogue token cost, any model's use of the content, and the Codex host-discovery behavior in section 3. Those belong to #961.

## 8. C16 amendment — proposed here, applied by #974

**Status update:** [#974](https://github.com/Jongtae/agentos/issues/974) applies this amendment to the constitution and AGENTS.md. The replacement coverage in `tests/test_no_scenario_code.py` is:

- `CoreNamesNoSkill`: no core literal names a bundled skill, even inside a sentence.
- `CoreReadsNoSkillFiles`: only `skills.py` refers to skill files.
- The existing scan, which `skills.py` joined in #961.

`tests/test_skill_supply.py::test_skill_text_reaches_a_work_only_through_skill_load` checks the behavior. The proposal's wider check ("no core module reads a site or category token from skill content into a control-flow position") is narrowed to this structural and behavioral pair, because skill content is runtime data that a static scan cannot see. The rest of this section is the original proposal, kept as written.

C16 currently forbids "request-specific guidance text" and task-named branches. #963's site know-how would violate the first unless C16 distinguishes core code from declared package content. Proposed replacement for C16's third bullet, for a separately activated governance change with independent review (it changes a declared invariant):

> **Never implement a specific owner request in core code.** No per-task features and no site-, provider-, category- or task-named branches or guidance text in AgentOS runtime modules. Domain and site know-how may be distributed only as explicit, inspectable, versioned Skill content inside an AgentPackage, with pinned identity and licence. The owner's AI selects and uses it through the same host capabilities and Work, authority and evidence paths. Skill content cannot grant authority, change host behavior or certify an unobserved effect. Moving scripted behavior into another core module is not compliance.

**Replacement regression coverage, same change:** `tests/test_no_scenario_code.py` keeps scanning every core module and adds the #961 skill-supply modules to `SCANNED_MODULES`. A new static check asserts that no core module reads a site or category token from skill content into a control-flow position. Skill content directories are data, not scanned for tokens. The constitution, `AGENTS.md` and `CLAUDE.md` pointers change together. Until that change merges, #962/#963 may not ship site-named guidance.

## 9. #918 and #661 reconciliation

- **#918** (GOV-ASK-LESS-01) is **open**. On `main` at `bd7fec18`, `settings_change` still drafts and the owner confirms with a typed yes or a button (#814/#855, `SettingsOrchestrator.handle_text`, `NOT_OWNER_TYPED_MESSAGE`). #962 binds to whatever `settings_change` does when it starts and must not add its own confirmation or bypass one. Skill loading and resource reads are effect-free reads like `information_use`, so they require no confirmation under either the current or the #918 semantics.
- **#661** (SEC-A2A-01) is **open** and owns family delegation. This record imports no family execution and does not change cookie sharing. Sharing public skill knowledge with a family assistant is a later #661-scoped decision.
- **#343** remains closed/not planned; nothing here reopens it.

## 10. Minimal verification map

| Changed boundary (#961) | Reused tests / evidence | Concrete uncovered risk | Smallest added check |
| --- | --- | --- | --- |
| Manifest/package resolution | `tests/test_manifests.py`, `tests/test_plugins.py`, `tests/test_agentpackage_v01_schemas.py` | A skill field breaking v1 validation or install | Unit tests: v1 without skills unchanged; skills metadata round-trip; duplicate skill ids refused |
| Source adapter / parser | Section 7 spike cases (to become fixtures); `skills-ref` rules as reference | Path escape, symlink, oversize, duplicate keys, YAML tags, unknown licence | Model-free fixture tests with a fake transport; one pinned upstream fixture copied with its Apache-2.0 licence |
| Tool surface per route | `tests/test_capability_profiles.py`, `tests/test_mcp_bridge_protocol.py`, `tests/test_cli_route_agency.py`, `tests/test_bounded_execution.py`, `tests/test_strict_isolation.py` | Skills off changes any route's tool list; strict profile gains tools | Off: exact equality with today's `offered_tools` per route. On: exactly two added effect-free tools on supported routes, none on strict. |
| Revocation / stale skill | Existing #604 `current_packages` tests in `tests/test_plugins.py` / `tests/test_capability_profiles.py` | A disabled package's skill keeps loading mid-Work | Counterexample: disable after load, then the next load or read is `skill_revoked`, with existing tools still usable |
| Native CLI discovery | `bounded_execution.py` CODEX_HOME caveat; strict-isolation tests with a synthetic `CODEX_HOME` | Owner host skills reach the trusted-local Codex worker | Model-free argv/env assertion for the chosen flag, or an explicit recorded limitation |
| No scenario code | `tests/test_no_scenario_code.py` | Site logic moving into the loader | Add the new modules to `SCANNED_MODULES` |

No live model call, account mutation, evaluator or all-profile sweep is part of this map. Live budget is zero until separately authorized. Structural compatibility evidence will not be reported as model-quality evidence.

## 11. Gates before #961 starts

- [x] ADR and change-surface table (sections 1–2), with off/empty/missing preservation explicit.
- [x] Adopt/Adapt/Build with exact revisions, licences, dependencies and maintenance (section 4).
- [x] A third-party skill not authored for AgentOS is represented without scripts, hooks or a new browser (section 7).
- [x] Established YAML parsing selected (PyYAML `SafeLoader`); Build limited to glue with the unmet contract stated.
- [x] Profile mapping with nothing added silently (section 3).
- [x] Separate identity attributes (section 5).
- [x] Verification map (section 10); C16 amendment and replacement coverage stated (section 8).
- [x] **#961 activation by the owner** (2026-10-02), with: the PyYAML dependency review in its PR, the Codex host-discovery risk closed (section 12), and the preservation tests landing with the code. Skills stay off by default.

## 12. Implementation record (#961)

[#961](https://github.com/Jongtae/agentos/issues/961) implements sections 1–6 with these concrete choices.

| Decision here | As implemented | Where |
| --- | --- | --- |
| Two effect-free host actions | `skill_load` and `skill_resource` in `DEFINITIONS`. They are offered only when the Work has a `SkillBinding` (`Capabilities.offered_tools`). | `agent_runtime.py`, `skills.py` |
| Skills off, or on with nothing loadable, is the pre-skill path | `SkillLibrary.binding()` returns None in both cases: no catalogue section, no tool, no lookup. The switch is off by default, and PyYAML is imported only when a skill is parsed. | `skills.py`, `quickstart_service.skill_binding` |
| Work-scoped binding and revocation | The binding pins content digests once per Work. After a skill is loaded, every later tool call checks that it is still current: in `Capabilities.execute`, and in `AgentOSMcpTools.call` before a call is relayed to the service. Disable, remove, update, switch-off and on-disk tampering all refuse with `skill_revoked`. | `agent_runtime.check_skills`, `bounded_execution.py` |
| Same content on every supported route | The host passes `--skill=<package>/<name>@<digest>` to the trusted-local bridge, which rebuilds the binding from the store. Strict-isolated and isolated declare the actions unavailable. | `mcp_bridge.py`, `CLI_PROFILES` |
| Native CLI discovery (section 3 risk) | **Closed for Codex.** Trusted-local now passes `-c skills.include_instructions=false`, the same override the judgment route and the strict profile already use. An opt-in process test against the real `codex` 0.153.4 and a loopback fake model shows that a `CODEX_HOME` canary skill reaches the model without the flag and does not reach it with the flag. Claude Code gets `--disable-slash-commands`. | `bounded_execution.py`, `tests/test_strict_isolation.py` |
| Acquisition when the owner asks | It runs through `settings_change` category `skills` (`enabled`, `add`, `remove`). #918 is still open, so this uses today's confirm-before-apply drafts rather than apply-then-undo. A branch or tag is resolved to its commit while the draft is built, so the owner confirms an exact revision. | `settings_orchestrator.py` |
| Package identity | `PluginRegistry` declarations carry `skills` (name, description, digest, licence, status, file digests), `source` (repo, commit, path, claimed publisher) and `adaptation`. A skill package declares no tools or roles. `agentos` is reserved for the bundled skills. | `manifests.py` |
| Bundled reviewed skill | `agentos-skills`: how skills work and how the owner adds, switches or removes them. | `bundled_skills/` |

Evidence classes are named separately:
- `tests/test_skill_supply.py`: focused unit tests and a model-free run of the real MCP bridge process. A fake GitHub transport serves the byte-identical upstream fixture.
- The opt-in Codex process test listed in the table above.

No live model, live GitHub download during tests, or owner account was used. Model quality with skills is not claimed.

## 13. Management content (#962)

[#962](https://github.com/Jongtae/agentos/issues/962) adds the bundled skill `agentos/agentos-management`: a `SKILL.md` plus three references, one each for the Main AI, family assistants and site sharing.

- **Content only.** It directs the worker to the existing `settings_read` and `settings_change` tools and their owning services. It adds no tool, setter or confirmation of its own.
- **Not blocked by C16.** It names no owner task, site or provider. It describes AgentOS's own settings, so it does not need the section 8 amendment that site and task know-how waits for.
- **One bounded service change.** Repeating a request to create a family assistant (`family add`) is now refused when a paired assistant on this Mac already has that name, the owner's own assistant included. An unfinished setup can still be requested again; the existing setter reuses it. The change only narrows what a draft may do.
- **Existing semantics are kept and cited, not changed:**
  - Main AI continuity: a running Work keeps its route snapshot (`test_ai_route_selection`).
  - The #814 draft contract: a Work that drafted a change reports that change as waiting for the owner.
  - Family setup states and sharing receipts.

## 14. Shopping and site content (#963)

[#963](https://github.com/Jongtae/agentos/issues/963) adds content only.

**Packaging.** The skills are published in this repository's `skills/` folder and installed through the #961 pinned-GitHub path. They are not bundled. The amended C16 (#974) requires an AgentOS-authored site skill to get the same review as an external one and to be individually removable by the owner. Installed packages already meet both requirements, with no change to the common loader. The bundled `agentos-skills` guide lists their addresses, so the AI can offer to add one, and the owner confirms as for any skill.

Owners start with skills off, so the AI cannot see that guide on a fresh install. The reference list is therefore also kept as data (`skill_references.json`, read only by `skills.py`). `settings_read skills` lists it even while skills are off, and `skills add` accepts a reference skill's name. Adding a skill while skills are off switches them on in the same confirmed draft, and the draft says so. No code names a particular skill.

**Supply review first.** On 2026-10-02 a public code search found no Emart or SSG skill. Three generic shopping candidates were rejected:

| Candidate | Licence | Why rejected |
| --- | --- | --- |
| `MassLab-SII/open-agent-skills` `skills/shopping` | Apache-2.0 | Needs Python scripts and Playwright (`scripts_or_hooks_required`) |
| `martinwheeler/skills` `syncing-shopping-cart` | None | Woolworths only, Playwright MCP with injected JavaScript |
| `martparve/selver-mcp` `selver-cart` | None | Needs its own MCP servers |

The AgentOS references fill that gap. They are not evidence that a third-party skill was imported; #961's `internal-comms` remains that evidence.

**What each package holds.**

- `shopping-cart` is the site-independent method: quantity semantics (add, set, ensure), exact matching, a single change, cart read-back, reconcile-before-retry, and truthful reporting.
- `emart-ssg` holds only site facts, each with its provenance: home, search results, cart and category addresses, and page titles seen in redacted AgentOS browser records. It also states the account and cart scope and the delivery-type caution.
- The search query parameter was not recorded, and an anonymous request cannot confirm it because the page is rendered by JavaScript. The skill therefore names no query parameter.

**Evidence.** `tests/test_skill_shop.py` runs model-free scripted flows on the deterministic fixture shop:

- First use on a fresh store, with the method plus a second site package (`tests/fixtures/skills/fixture-mart`).
- Exactly one change, with the claim resting on the cart read afterwards.
- The published site package installed and loaded with no core edits.
- Each package removable on its own.
- Withdrawing the method mid-flow stops the next click before it reaches the shop.

No live site, account or model was used. Whether a model follows the method well on the real Emart site is a #964 question that needs a separately capped live run.

## 15. Evidence consolidation (#964)

[SKILL-EVAL-01 coverage](skill-eval-01-coverage.en.md) maps the #964 inventory to the evidence gathered in #961–#963 and #974. It adds three model-free gap checks: a repeat makes no supplier call, a rollback restores only content, and supplied knowledge adds no hidden model call. It also fixes the A / A-off / B protocol and adds one rubric-judged eval scenario. The live, model-dependent questions (method adherence on the real site, drift and concurrency handling, transcript quality) remain pending. Its section 4 holds a capped, cleanup-defined live sample that only the owner can approve.
