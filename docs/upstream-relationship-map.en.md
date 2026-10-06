# Upstream relationship map and pilot selection

## Status and evidence boundary

This is the enduring relationship register for UPSTREAM-MAP-01
[#1023](https://github.com/Jongtae/agentos/issues/1023), under UPSTREAM-01
[#1022](https://github.com/Jongtae/agentos/issues/1022). The inspected AgentOS
baseline is merge commit `a3c6a8d4899be919978d8d4b18ddc1f78ec2fba7` on
2026-10-06. The external maintenance snapshot was also checked on 2026-10-06.

This is a selected-source map, not a claim that every repository file,
transitive dependency, vulnerability database or live service was audited. It
records the material boundaries named by #1023, the current delta from the
reuse program, and explicit gaps. Package ranges in
[`pyproject.toml`](../pyproject.toml), immutable content pins in their
provenance records, and GitHub issues, pull requests and checks remain the
authoritative facts. Versions observed here are review evidence rather than a
second package manifest.

No dependency, account, external service, bot, runtime route or deployment was
changed while producing this map. External project submissions remain subject
to separate owner approval.

## Relationship vocabulary

| Relation | Meaning in this register |
| --- | --- |
| `reference-only` | A definition, design or comparison source. No executable or validation claim. |
| `vendored/patched` | Reviewed source bytes are stored in the repository, with the upstream revision and local delta identified. |
| `runtime-package` | An installed package is imported by a production path. A declaration with no consumer does not qualify. |
| `protocol/schema-conformance` | AgentOS implements or validates a published contract. This does not imply use of the publisher's runtime. |
| `versioned-content` | Instruction or resource content is pinned and consumed as content. It grants no authority. |
| `external-service` | A process or network API outside AgentOS is actually invoked. The service remains outside local control. |

Several rows have more than one relation because installed mechanics, protocol
meaning and a remote destination are different facts. Attack surface means
code installed into the environment. Effective authority means the
filesystem, network, account, secret or action access that AgentOS actually
projects at execution time. Neither implies the other.

## Decision continuity

| Prior decision | Preserved result | Current delta or owner |
| --- | --- | --- |
| Reuse audit [#413](https://github.com/Jongtae/agentos/issues/413) and completed tranche [#418](https://github.com/Jongtae/agentos/issues/418) | Reuse commodity mechanics below AgentOS-owned state, Grant, approval, effect, Evidence and recovery boundaries. The tranche adopted `oauthlib`, adopted the `mcp-types` version registry, adapted stdlib email parsing and retained measured custom boundaries. | The product gained browser, skill supply, current-context, recovery, search and steering paths after the audit. This register maps those deltas; it does not reopen every rejected migration. |
| MCP decision [#426](https://github.com/Jongtae/agentos/issues/426) | Keep strict local envelope validation; use `mcp-types` for supported handshake versions and tested result shapes. The full SDK was rejected for that bounded 2026-09 path because its closure exceeded the stdio need. | The official SDK is now 2.3.0 and the bridge has grown substantially. #1025 may re-test one exact stdio seam, while the old decision remains correct evidence for its original scope. |
| Skill preparation and supply [#960](https://github.com/Jongtae/agentos/issues/960), [#961](https://github.com/Jongtae/agentos/issues/961) | Adopt Agent Skills representation and PyYAML `SafeLoader`; keep immutable content, Work-pinned bindings, revocation and authority in AgentOS. | The first external fixture and development skills now provide actual content relationships. Reuse `SkillLibrary` and `SkillBinding`; do not create another loader or registry. |
| Memory interoperability [#875](https://github.com/Jongtae/agentos/issues/875), spike [#894](https://github.com/Jongtae/agentos/issues/894) | Adapt Portable Memory vocabulary and a future optional import/export adapter; do not replace canonical Memory or its approval state. | No runtime package or consumer was added. #875 Track A remains the owner after SECRETARY-01 resumes; UPSTREAM-01 must not create a competing memory project. |
| Role/reuse publication [#1019](https://github.com/Jongtae/agentos/issues/1019), PR [#1020](https://github.com/Jongtae/agentos/pull/1020) | OWL 2, SKOS, SHACL and PROV-O are explicit conceptual references with evidence limits. | There is still no RDF, OWL reasoner, SHACL validator or PROV runtime. The register below keeps these relations `reference-only`. |

## Current relationship map

### Protocols, model workers and external services

| ID | Area and relation | Upstream source and version policy | Actual consumer and retained AgentOS responsibility | Current delta, gap and revisit trigger |
| --- | --- | --- | --- | --- |
| U01 | MCP stdio: `runtime-package`, `protocol/schema-conformance` | [`mcp-types`](https://pypi.org/project/mcp-types/) range is authoritative in [`pyproject.toml`](../pyproject.toml). PyPI reported 2.3.0, MIT, Python ≥3.10, released 2026-10-02; the matching official SDK [v2.3.0](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.3.0) was active on inspection. | [`mcp_bridge.py`](../src/personal_agent/mcp_bridge.py) and [`isolated_engine_mcp_bridge.py`](../src/personal_agent/isolated_engine_mcp_bridge.py) import handshake constants. Protocol result shapes are exercised against `mcp_types` in [`test_mcp_bridge_protocol.py`](../tests/test_mcp_bridge_protocol.py). AgentOS retains exact envelope/method/id checks, tool subsets, Work budgets, callback mediation, errors, secret redaction, effects, Event and Evidence. | Since #418, the host bridge added route profiles, recovery, native search, service/browser relays, information-use audit, skills and steering. There is no lock or exact resolved closure. Revisit through the U01 pilot below; HTTP/SSE support alone is not a reason to widen the product. |
| U02 | Agent Skills shape: `protocol/schema-conformance`; YAML parser: `runtime-package` | Agent Skills is pinned for comparison at [`agentskills/agentskills@69ef37e`](https://github.com/agentskills/agentskills/commit/69ef37e9424c0a7ea9dd2293b559e43ec8176379): repository/spec code is [Apache-2.0](https://github.com/agentskills/agentskills/blob/69ef37e9424c0a7ea9dd2293b559e43ec8176379/LICENSE), its `docs/` content is [CC-BY-4.0](https://github.com/agentskills/agentskills/blob/69ef37e9424c0a7ea9dd2293b559e43ec8176379/docs/LICENSE), and `skills-ref` has its own Apache-2.0 notice. [`PyYAML`](https://pypi.org/project/PyYAML/)'s manifest range is authoritative; PyPI reported 6.0.3, MIT, released 2025-09-25. | [`skills.py`](../src/personal_agent/skills.py) parses `SKILL.md` frontmatter with a no-alias, no-duplicate-key `SafeLoader` subclass and enforces local file, licence, digest, lifecycle and Work-binding rules. [`test_skill_supply.py`](../tests/test_skill_supply.py) exercises the real parser/library/bridge path. | Actual content support was added after #418. AgentOS intentionally does not adopt another agent loop or tool authority from the spec. Revisit when the spec changes a field AgentOS consumes or PyYAML changes supported Python/security behavior. |
| U03 | Model providers: `external-service` | OpenAI-compatible, OpenAI, Anthropic and Ollama wire contracts are implemented without their SDK packages. Endpoints/models are owner configuration, not pinned dependencies. | [`providers.py`](../src/personal_agent/providers.py) uses an injected or stdlib HTTP transport; [`agent_runtime.py`](../src/personal_agent/agent_runtime.py) owns the AgentOS tool/effect loop. Provider serialization is local while Grants, redaction, tools, Work state and Evidence remain AgentOS-owned. | The #413 SDK/framework recommendation has not been executed. Current official SDK compatibility, streaming/tool-call conformance and transitive footprint are an explicit uninspected gap. Revisit only for an observed provider defect or a separately selected adapter migration. |
| U04 | Subscription AI workers: `external-service` | Codex and Claude Code are discovered local executables. The isolated image pins `@openai/codex@0.153.4` in [`Dockerfile.engine`](../Dockerfile.engine); host binaries are observed at runtime and are not dependency declarations. | [`subscription_engines.py`](../src/personal_agent/subscription_engines.py), [`bounded_execution.py`](../src/personal_agent/bounded_execution.py) and [`isolated_engine_sidecar.py`](../src/personal_agent/isolated_engine_sidecar.py) launch and parse bounded processes. AgentOS retains route choice, environment, process-group stop, MCP tools, time/output budgets, failure classification and Evidence. | The CLI path gained native search, browser/service relay, skills, steering and usage-limit handling after #418. Official SDK replacement remains untested; exact host binary resolution is operating evidence, not a repository pin. Revisit on a stable official structured API or a parsing regression. |
| U05 | Google OAuth and Workspace: `runtime-package`, `external-service` | [`oauthlib`](https://pypi.org/project/oauthlib/) is constrained to `>=3.3.1,<4`; PyPI reported 4.0.0, BSD-3-Clause, released 2026-09-28. Google OAuth, Drive, Calendar and Gmail endpoints are remote service contracts. | [`drive_web_oauth.py`](../src/personal_agent/drive_web_oauth.py), [`calendar_oauth.py`](../src/personal_agent/calendar_oauth.py) and [`gmail.py`](../src/personal_agent/gmail.py) use `WebApplicationClient`; Workspace REST remains local HTTP in those connectors and [`google_calendar.py`](../src/personal_agent/google_calendar.py). AgentOS retains exact scopes, owner binding, encrypted secret references, lifecycle, approvals, effects and redacted Evidence. | #418 adopted OAuth mechanics but deferred Workspace SDK migration. The new oauthlib major is excluded and therefore a concrete #1024 review trigger. Direct REST and Gmail message-body behavior still need a separately bounded compatibility decision; no live account test is implied. |
| U06 | Browser and public destinations: `runtime-package`, `external-service` | Manifest ranges cover [`pyobjc-framework-WebKit`](https://pypi.org/project/pyobjc-framework-WebKit/), [`publicsuffixlist`](https://pypi.org/project/publicsuffixlist/1.0.2.20261003/) and [`cryptography`](https://pypi.org/project/cryptography/). PyPI JSON reported WebKit 12.2.2 (MIT), latest-observed publicsuffixlist 1.0.2.20261003 (MPL-2.0, uploaded 2026-10-03) and cryptography 50.0.2 (Apache-2.0 OR BSD-3-Clause). The first observed updater candidate selected for #1024 is publicsuffixlist 1.0.2.20261002; its exact release and recovery evidence is recorded in the dependency update contract. WebKit itself is the macOS platform framework. | [`browser_worker.py`](../src/personal_agent/browser_worker.py), [`browser_session.py`](../src/personal_agent/browser_session.py) and [`browser_jar.py`](../src/personal_agent/browser_jar.py) use the platform browser, public-suffix data and Fernet/Keychain-backed session storage. AgentOS retains destination checks, mediated output, login handoff, payment guard, owner/site binding, effect uncertainty and recovery. | This is a large post-#418 subsystem. Installed browser bindings do not grant arbitrary browsing; effective destinations and actions remain gated per Work. Wheel/platform compatibility, transitive closure and package advisories are explicit #1024 inventory gaps. Revisit on macOS/Python support change or an observed session/security defect. |
| U07 | Search, public-page HTTP and Telegram: `external-service`; public-suffix support shares U06 | Bing RSS, Brave, model-native search and Telegram Bot API are called through local stdlib/injected transports; there is no adopted search or Telegram SDK package. | [`search_providers.py`](../src/personal_agent/search_providers.py) and [`local_tools.py`](../src/personal_agent/local_tools.py) consume search/page APIs. [`conversation_handoff.py`](../src/personal_agent/conversation_handoff.py) owns `telegram_request_json` and `TelegramChannel`, wired by [`quickstart_service.py`](../src/personal_agent/quickstart_service.py); `telegram_presence.py` is presentation logic, not the transport. AgentOS retains SSRF/DNS/redirect bounds, configured destinations, owner pairing, callback replay protection, Work state and effects. | #418 retained the HTTP/extraction boundary after measured candidate mismatch and recommended a Telegram library. The later `TelegramChannel` transport seam and native-search routes make the old “no seam” premise stale. Current SDK/provider conformance is an explicit uninspected gap; revisit on API drift or a selected transport issue, not for dependency-count targets. |
| U08 | A2A: `reference-only` at current head | The historical custom `a2a.py` reviewed by #413 is absent from the current package. A2A remains an architectural comparison and a separately ordered future program, not a package dependency. | Current runtime has no A2A module to claim as an adopted consumer. AgentOS's parent-Work authority-subset rule remains in canonical contracts. | No migration is selected here. Reinspect the then-current official SDK, protocol revision and actual owner journey only when SEC-A2A-01 is separately made ready. |

### Owner state, schemas, documents and knowledge

| ID | Area and relation | Upstream source and version policy | Actual consumer and retained AgentOS responsibility | Current delta, gap and revisit trigger |
| --- | --- | --- | --- | --- |
| U09 | Documents: `runtime-package` | Manifest ranges cover [`pypdf`](https://pypi.org/project/pypdf/), [`python-docx`](https://pypi.org/project/python-docx/) and [`openpyxl`](https://pypi.org/project/openpyxl/). PyPI reported pypdf 6.19.0 (BSD-3-Clause, 2026-09-16), python-docx 1.2.0 (MIT, 2025-06-16) and openpyxl 3.1.5 (MIT, 2024-06-28). | [`document_reader.py`](../src/personal_agent/document_reader.py) calls `PdfReader`, `docx.Document` and `load_workbook`; stdlib `zipfile` enforces pre-read bounds. [`test_documents.py`](../tests/test_documents.py) exercises real installed packages. AgentOS retains folder Grant, path/symlink checks, size/decompression limits, original preservation and source labels. | This remains the positive reuse example from #413. Exact resolution, transitive XML libraries and current security posture are not locked or fully inventoried. #1024 should resolve and test the existing boundary before any upgrade; add XML hardening only from a reproduced gap. |
| U10 | AgentPackage schemas: `protocol/schema-conformance`; optional development validator package | Repository schemas declare JSON Schema 2020-12. [`jsonschema[format]>=4.23`](https://pypi.org/project/jsonschema/) is optional development/schema-validation tooling, not a production `runtime-package`; PyPI reported 4.26.0, MIT, released 2026-01-07. | [`verify_agentpackage_v01.py`](../scripts/verify_agentpackage_v01.py) uses `Draft202012Validator` and a referencing registry. Product [`manifests.py`](../src/personal_agent/manifests.py) retains AgentOS semantic and authority validation; it is not silently certified by the optional package. | No supported lock exists for the optional validator or its format extras. Revisit if runtime validation is selected, the schema draft changes, or a semantic rule duplicates a supported standard facility. |
| U11 | Persistence, recovery and service lifecycle: standard-library/platform adoption | Python 3.12 stdlib `sqlite3`, `json`, `hashlib`, `tarfile`, `zipfile`, `fcntl` and macOS `launchd` mechanics are the public facilities. There is no ORM, migration framework or scheduler dependency. | [`quickstart_store.py`](../src/personal_agent/quickstart_store.py), [`portable_state.py`](../src/personal_agent/portable_state.py), recovery modules and [`service_control.py`](../src/personal_agent/service_control.py) consume them. AgentOS necessarily owns canonical state, migrations, atomicity, redaction, backup/restore, Work recovery and health meaning. | #418 kept SQLite but identified ad hoc migration and service-manager growth as revisit points. This map does not propose a framework. Revisit when a concrete migration/recovery defect or cross-platform service requirement exceeds the supported facilities. |
| U12 | Memory interchange: `reference-only` | Portable Memory was inspected at [`MacPaw/portable-memory@f341f07`](https://github.com/MacPaw/portable-memory/commit/f341f0703d739edfdf94eba58e66a4cc7c925df7), SDK 0.3.0 / format 1.1, MIT, in [#894](https://github.com/Jongtae/agentos/issues/894). | There is no imported package or production consumer. [`memory_service.py`](../src/personal_agent/memory_service.py), [`quickstart_store.py`](../src/personal_agent/quickstart_store.py) and current-context stores remain canonical. | The spike proved a model-free round trip with documented lossy/passthrough fields and selected **Adapt** for future import/export. #875 Track A owns any implementation after its own activation; revisit Portable Memory's exact current release and provenance RFC then. |
| U13 | Ontology and provenance terms: `reference-only` | W3C Recommendations: [OWL 2 Primer](https://www.w3.org/TR/2012/REC-owl2-primer-20121211/), [SKOS Reference](https://www.w3.org/TR/2009/REC-skos-reference-20090818/), [SHACL](https://www.w3.org/TR/2017/REC-shacl-20170720/) and [PROV-O](https://www.w3.org/TR/2013/REC-prov-o-20130430/). | The terms support distinctions in the [role/reuse register](research/role-ontology-reuse-2026-10-05.ko.md) and owner-model research. Runtime fields use AgentOS contracts; no schema, axioms or reasoning engine consumes those standards. | A citation or conceptual correspondence is not an exact mapping, validation or authority decision. Revisit only for a separately selected export/schema consumer; do not introduce graph infrastructure to relabel existing state. |
| U14 | External skill content: `versioned-content`, with development copies also `vendored/patched` | Product test fixture: `anthropics/skills@8a1541c4` `internal-comms`, Apache-2.0, recorded in [`PROVENANCE.md`](../tests/fixtures/skills/PROVENANCE.md). Development aids: `frontend-design@34040c9` (Apache-2.0) and `web-interface-guidelines@e3d624b` (MIT), recorded in [`.claude/skills/README.md`](../.claude/skills/README.md). | `internal-comms` is consumed through the real `SkillLibrary`/`SkillBinding` and MCP bridge tests. Development assistants consume the pinned `.claude/skills` files under repository instructions; these are outside the product runtime and grant no authority. | `internal-comms` has no content change after its current pin on inspected upstream main. `frontend-design` has a genuine historical semantic revision and is selected for the U14 pilot below. Future source discovery must preserve immutable review targets and local wrappers. |

### Build, test and distribution

| ID | Area and relation | Upstream source and version policy | Actual consumer and retained AgentOS responsibility | Current delta, gap and revisit trigger |
| --- | --- | --- | --- | --- |
| U15 | Python build and tests: build/runtime packages plus external CI service | [`pyproject.toml`](../pyproject.toml) uses [`setuptools>=68`](https://pypi.org/project/setuptools/); CI installs an unpinned [`pytest`](https://pypi.org/project/pytest/). PyPI reported setuptools 84.0.0 (2026-08-08) and pytest 9.1.1 (2026-06-19), both MIT. GitHub Actions uses major tags for checkout/setup-python. | The PEP 517 backend builds AgentOS; [validate](../.github/workflows/validate.yml) runs required gates and the test suite. AgentOS owns which checks are required and what evidence they support. | There is no project lock/constraints file and CI resolves floating transitive versions. The manifest still uses the legacy `license = {text = ...}` form; [setuptools' PEP 639 migration guide](https://github.com/pypa/setuptools/blob/main/docs/userguide/license_migration.rst) documents SPDX string support from 77.0.0, while the current lower bound admits older backends. SBOM/CVE state and hashes are not recorded. #1024 owns an established updater plus reproducible resolution; do not build a scheduler or dependency database. |
| U16 | Containers and distribution: platform images/packages | Dockerfiles use mutable `python:3.12-slim` and apt indexes; the engine image pins Codex but not the base digest or OS packages. Homebrew/Compose/release artifacts are project distribution surfaces, not runtime authority. | [`Dockerfile`](../Dockerfile), [`Dockerfile.engine`](../Dockerfile.engine), [`Dockerfile.egress`](../Dockerfile.egress), Compose and release checks consume them. AgentOS retains process users, mounts, egress topology, health, secrets and release evidence. | Immutable resolution and automated update coverage are explicit gaps for #1024. A base-image or tool update that changes isolation, network, credentials or supply-chain trust requires the corresponding review; discovery never means automatic deployment. |

## Update and rejoin ownership

1. **Manifest and resolution owner:** #1024 owns updater configuration,
   reproducible resolution, one attributable upgrade, rollback evidence and the
   shared `pyproject.toml`/CI files. It must compare established Dependabot and
   Renovate managers against the files actually present. Renovate's
   [PEP 621 manager](https://docs.renovatebot.com/modules/manager/pep621/)
   directly describes `[project.dependencies]`, optional/build dependencies
   and supported lock files, making it the straightforward current-manifest
   candidate; its [custom manager](https://docs.renovatebot.com/modules/manager/regex/)
   may discover immutable content revisions. Dependabot documents its
   [supported ecosystems and manifests](https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-manifests-for-dependency-scope),
   so #1024 must test whether a supported resolution artifact such as `uv`
   provides the required fit rather than assuming generic PEP 621 coverage.
   Availability is not repository compatibility, and neither bot alone creates
   a lock. No bot is installed by this map.
2. **Runtime adapter owner:** #1025 owns U01 implementation files and focused
   protocol tests. It coordinates dependency resolution with #1024, but it
   does not own updater policy or unrelated packages.
3. **Content owner:** #1026 owns the selected U14 source comparison and
   change-impact evidence. It uses #1024's discovery mechanism only if that
   mechanism supports immutable Git source revisions safely; the existing
   manual revision-review path remains valid.
4. **Patch/rejoin owner:** #1027 owns a publishable reproducer and records each
   necessary local delta with upstream base, reason, test and release rejoin
   trigger. GitHub links remain execution status; this document must not copy
   submitted/accepted/released state.

For every update, the affected maintainer records the candidate version,
source and licence; resolved direct and transitive artifacts; changed
behavior/authority; focused real-boundary tests; rollback or forward-fix; and
the next trigger. A failed candidate leaves the known-good revision and its
evidence inspectable. A local patch is removed only after a released artifact
passes the same boundary. Mutable `latest` content never replaces an approved
historical target.

## Verification, update and ownership matrix

The paths below are the focused starting set, not permission to skip a test
revealed by the actual diff. “Revert” means return to the last reviewed
manifest/content and code commit without replaying owner effects or deleting
durable evidence.

| ID | Focused conformance/regression evidence | Update, rollback or forward-fix constraint | Responsible role and revisit trigger |
| --- | --- | --- | --- |
| U01 | `test_mcp_bridge_protocol`, `test_isolated_engine_mcp_bridge`, `test_isolated_mcp_proxy`, affected bounded-execution/skill tests | #1024 resolves artifacts; #1025 changes one adapter. Revert code/package together because there is no state migration; never keep a hidden second dispatcher. | Runtime adapter maintainer; new MCP release/spec, protocol defect or the selected #1025 experiment. |
| U02 | `test_skill_supply`, `test_skill_manage`, `test_no_scenario_code` | Review the spec/parser diff and pin before merge. Reject content/parse widening that bypasses resource or authority rules; restore the prior parser/package on failure. | Skill supply maintainer; consumed spec field or PyYAML compatibility/security change. |
| U03 | `test_agent_runtime`, `test_agency_loop`, `test_ai_route_selection` and affected provider route tests with injected transport | Provider changes stay behind `ModelAdapter`; revert adapter and package together. A wire incompatibility gets a bounded forward-fix or separate SDK migration issue. | Model-route maintainer; reproduced provider defect or separately selected SDK/API migration. |
| U04 | `test_subscription_engines`, `test_bounded_execution`, `test_strict_isolation`, `test_engine_auth` | Keep executable/version observation truthful. Roll back the CLI image pin or adapter as one reviewed unit; never downgrade sandbox, stop or output bounds to fit an SDK. | Subscription runtime maintainer; CLI structured-output change, supported SDK stabilization or observed parse/recovery defect. |
| U05 | `test_drive_web_oauth`, `test_calendar_oauth`, `test_gmail`, `test_gmail_http_transport`, Google service tests | Review oauthlib 4 as a major update with exact scope/redirect/token regressions. Preserve encrypted credentials and connector state on rollback; forward-fix provider API drift without widening scopes. | Connector maintainer; excluded oauthlib major, Google contract change or reproduced connector defect. |
| U06 | `test_browser_webkit`, `test_browser_session`, `test_browser_limits`, `test_session_keepalive`, `test_engine_auth` | Resolve macOS wheels and transitive packages; revert package and worker change without erasing jars or asking for a new login solely because of migration. Never relax payment/destination/session guards. | Browser boundary maintainer; macOS/Python/package support or observed navigation/session/security defect. |
| U07 | `test_search_providers`, `test_private_provenance_egress`, `test_telegram_conversation_channel`, `test_telegram_native_presence` | Keep transports injected in tests. A provider/SDK change must preserve destination, pairing, replay and effect rules; revert without replaying sends or searches. | Search or Telegram maintainer for the affected seam; API drift, observed defect or separately selected transport migration. |
| U08 | Current absence/static source inspection plus future A2A contract tests | No package or compatibility code until the separate program selects a real journey and exact protocol. Remove an unsuccessful experiment cleanly; do not leave dormant authority. | Future A2A iteration owner; separately made-ready SEC-A2A-01 only. |
| U09 | `test_documents` through real pypdf/python-docx/openpyxl packages and file-workspace denial tests | #1024 resolves the candidate set. Reject an upgrade that breaks bounded extraction; revert packages together with no original-file mutation. Forward-fix only a reproduced parser/security gap. | File workspace maintainer; package/security/Python change or observed format regression. |
| U10 | `verify_agentpackage_v01.py`, `test_agentpackage_v01_schemas`, `test_manifests` | Keep JSON Schema validation and AgentOS semantic/authority checks distinct. Revert validator/schema together; never accept a package solely because generic schema validation passes. | AgentPackage contract maintainer; schema-draft, validator or package-format change. |
| U11 | Store, backup/restore, operating recovery and service-control tests relevant to the changed file | Versioned migrations and recovery evidence precede a storage/framework change. Roll back without discarding owner state; a non-reversible migration needs its own contract. | Owner-state/recovery maintainer; concrete migration/recovery defect or selected platform expansion. |
| U12 | Reuse #894's model-free round-trip design on synthetic fixtures if Track A activates | No dependency/update under this program. Future import routes third-party writes through existing Memory policy; the last export format and owner state remain readable on rollback. | #875 Track A owner; its separately made-ready implementation and then-current SDK/RFC. |
| U13 | Citation/source checks and any future schema/export conformance test | A changed Recommendation or mapping is reviewed as semantics, not silently installed. Remove an invalid mapping without rewriting historical evidence. | Owning research/contract issue; an actual runtime schema/export consumer or corrected standard interpretation. |
| U14 | `test_skill_supply` real loader/bridge fixture plus exact content hashes; development instructions also need repository-contract review | Pin immutable source and retain prior bytes/history. Reject an incompatible candidate without overwriting the usable version; withdrawal never revives stopped Work. | #1026 content maintainer; a detected upstream revision or licence/source change. |
| U15 | Required `validate`, reuse-review gate and the affected package's real-boundary tests | #1024 introduces reproducible resolution and updater config. Roll back config/resolution together; do not auto-merge majors or turn discovery into product deployment. | Dependency-maintenance owner; updater PR, manifest/build backend or CI action change. |
| U16 | Compose/isolation/operating-preflight/release traceability tests for the changed artifact | Pin and verify candidate images/packages before merge. Roll back to the prior known-good image/build; do not deploy as part of an update PR. | Distribution maintainer; base image, OS package, Codex image pin or isolation topology change. |

## Selected runtime pilot for #1025: official MCP SDK on one host stdio path

**Selection:** compatibility-first **Adapt** candidate, not a pre-approved
dependency addition. Probe `mcp==2.3.0` from the official v2.3.0 release on the
production host bridge seam in `mcp_bridge.serve`. Use its documented low-level
server/stdio APIs for session framing, initialization and method dispatch only
if a public extension point preserves the current checks.

- **Supported scope:** the existing host CLI stdio bridge; `initialize`,
  `notifications/initialized`, `tools/list` and `tools/call`; current request
  ids, error mapping and shutdown. Exercise the real installed SDK with a
  synthetic peer and the existing AgentOS tool facade.
- **Retained local work:** pre-dispatch exact top-level shape and method
  allowlist if the SDK would normalize unknown fields; Work-state and budget
  checks; tool subsets; Skills and service/browser relays; secrets, effects,
  information-use records, Event/Evidence and cancellation/recovery.
- **Unsupported scope:** the isolated callback bridge, HTTP/SSE/stateless
  transports, resources, prompts, sampling, roots, new tools, model/provider
  calls, live CLI/account tests and private SDK APIs. Those cannot enter as a
  side effect of installing the SDK.
- **Compatibility experiment:** characterize the current bridge first, then
  run valid discovery/calls plus unknown keys/methods, malformed params,
  duplicate/mismatched ids, cancellation, EOF and shutdown against the real
  SDK. Record normalization differences. Mock the effect target, not the SDK.
- **Dependency and authority review:** resolve the exact wheel/source and full
  closure. PyPI 2.3.0 currently lists HTTP/server, JSON Schema, telemetry, JWT,
  validation and ASGI dependencies in addition to `mcp-types`. Installed
  attack surface therefore increases even if the configured stdio process
  receives no new network listener, destination, secret or filesystem scope.
- **Packaging constraint:** [`Dockerfile.engine`](../Dockerfile.engine) installs
  the same base `pyproject.toml`, so a mandatory `mcp` dependency would also
  place the full closure in the isolated image even though its bridge is
  outside this implementation scope. Before Phase B, prove a supported
  host-only extra/install path or explicitly review and test the shared-image
  closure. If neither preserves the selected profiles, stop and reselect; a
  host-only code edit is not evidence of an unchanged isolated package surface.
- **Shared files:** #1025 owns the bridge and bridge tests; #1024 owns updater,
  lock/constraints and CI integration. Coordinate any `pyproject.toml` edit on
  one stable head.
- **Preservation evidence:** reuse
  [`test_mcp_bridge_protocol.py`](../tests/test_mcp_bridge_protocol.py) and
  relevant bounded-execution/skill/recovery tests. Add a model-free integration
  through the real SDK and a denial control proving the underlying tool/effect
  is not reached.
- **Rollback and stop rule:** no state migration is allowed. A failed candidate
  leaves the current bridge and manifest unchanged. After successful adoption,
  remove superseded framing/dispatch rather than maintaining two paths; revert
  to the prior reviewed commit/package set on regression. If public APIs cannot
  preserve strict input handling, cancellation or process behavior, record the
  exact mismatch and reselect through #1022 instead of copying SDK internals.
- **Concrete benefit baseline:** AgentOS currently owns handshake negotiation,
  JSON-RPC framing and method dispatch in addition to policy. The pilot succeeds
  only if the maintained SDK owns a meaningful part of those mechanics on the
  actual call path while current behavior remains covered. Package or line
  counts are supporting observations, not the outcome.

Because a full SDK addition changes supply-chain and protocol/isolation
boundaries, #1025 requires risk-triggered independent review on its stable
head. This mapping PR does not.

## Selected non-code pilot for #1026: `frontend-design` revision impact

**Selection:** development-only `versioned-content`, expressly outside the
product runtime. The actual consumer is the repository's coding assistant
workflow through [`.claude/skills/frontend-design`](../.claude/skills/frontend-design/SKILL.md)
and the constraints in [`.claude/skills/README.md`](../.claude/skills/README.md).
The current pin `34040c9c568585f6929bedeaad110ad08f079624` is byte-identical
for `SKILL.md` to inspected upstream main
`683bc88e56f3e09ba94f7055977f3d3aa499f202`; there is no forward content update
to invent.

The genuine comparison is upstream
[`2235be7`](https://github.com/anthropics/skills/commit/2235be7c60b551f5de82ade908fd3816455afcda)
to [`41bbe19`](https://github.com/anthropics/skills/commit/41bbe19d1a1a7eaab5e7bb9050a417e5c6cffc8f),
which the current pin already contains. The newer text changes behavior-relevant
guidance: it asks the worker to confirm an underspecified subject with the
client, allows one or two type families instead of requiring a pair, adds
line-length and generic-style checks, narrows unsolicited motion, and expands
copy and self-critique guidance. #1026 must decide each change against the
existing AgentOS web/Presence constraints rather than treating a clean parse as
semantic compatibility.

- **Compatibility experiment:** install immutable old and current bytes in a
  temporary `SkillLibrary` with an injected source transport, bind them through
  `SkillBinding`, then exercise `Capabilities.execute('skill_load')` and
  `skill_resource` through the real `AgentOSMcpTools` boundary with an injected
  scripted worker transport. Record the exact instructions and preserved
  `LICENSE.txt` resource bytes, hashes, licence and semantic diff. Passing the
  development skill through this disposable product seam is compatibility
  evidence; its actual operational consumer remains the repository
  contribution workflow. It is model-free evidence, not proof of design quality.
- **Negative and recovery cases:** source outage after install, mismatched
  digest, unsupported script/hook content, withdrawal during a binding,
  restart, and rollback to the older immutable revision. Reuse existing skill
  supply tests rather than another loader.
- **Update path:** preserve the current manual exact-revision review. #1024 may
  add discovery only if it can identify the copied source and immutable commit;
  it must still open a normal review PR with the upstream diff and licence
  check. A moving fetch in the coding workflow remains prohibited.
- **Shared files:** #1026 owns `.claude/skills/README.md`, the selected
  `.claude/skills/frontend-design/*` copy, and any dedicated fixture,
  provenance and focused test it adds. Preserve the `internal-comms` fixture
  and tests. Change `skills.py` only for a reproduced missing seam and then
  coordinate that shared runtime file separately; coordinate any active UI
  work before changing development guidance used by that work.
- **Preserved boundaries:** no product installation, runtime package, tool
  grant, external account, model call, Memory write or automatic instruction
  promotion. The repository's AGENTS, web and Presence contracts continue to
  win over upstream content.
- **Benefit baseline:** the historical revision contains concrete instruction
  changes that could alter UI and copy decisions. A repeatable impact review
  prevents an apparently harmless content refresh from silently changing those
  decisions. The outcome is attributable review and preserved history, not a
  claim that the newer prose is universally better.

`internal-comms@8a1541c4` remains the stronger product-loader fixture and must
continue to protect the real supply boundary. It was not selected as the
revision-impact case because its inspected upstream content did not change
after the pin; unchanged evidence is preserved rather than converted into a
fictional update.

## Verification plan for this map

- Check every local Markdown target and every named repository path.
- Check that every material area in #1023 is represented by an attributable
  decision/current delta or an explicit gap.
- Check the U01 and U14 briefs for scope, unsupported profiles, shared-file
  ownership, preservation tests, rollback and stop conditions.
- Run canonical document verification and required exact-head CI. No model,
  account, paid API, dependency installation, bot configuration, external
  submission or deployment is required.
