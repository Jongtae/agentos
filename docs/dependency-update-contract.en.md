# Reproducible dependency updates

## Scope and evidence boundary

This contract implements the first, bounded update path selected by
UPSTREAM-UPDATE-01 [#1024](https://github.com/Jongtae/agentos/issues/1024),
extended by the host-only stdio adoption in UPSTREAM-RUNTIME-01
[#1025](https://github.com/Jongtae/agentos/issues/1025).
It covers the root Python project and GitHub Actions. It does not enable
production upgrades, deployment, auto-merge, repository write tokens in CI,
owner data access, private indexes, or a second scheduler.

The checked-in `uv.lock` is the authoritative Python resolution for the
selected development and CI profiles. `pyproject.toml` remains the published
compatibility contract. A lock records selected artifacts and hashes; it is
not evidence that every supported machine, architecture, future Python
version, package behavior, or advisory source was tested.

Observed installation evidence must name its platform, Python version,
profile, lock Git blob, and command. The initial claimed profiles are:

| Profile | Resolution represented | Operating evidence required |
| --- | --- | --- |
| Linux CI host | Python 3.12, base project, `mcp-host`, `schema-validation`, and `dev` | Required `validate` on the exact PR head runs `uv sync --locked` and the full suite, including the real SDK consumer. |
| macOS source development host | Python 3.12, the same extras/groups, plus the `pyobjc-framework-WebKit` marker closure | A fresh disposable environment runs locked sync and the focused real dependency boundary. |
| Base / isolated dependency profile | Base project with `--no-dev`, without `mcp-host` | Fresh locked sync excludes `mcp` and its SDK-only closure; this is packaging evidence, not an engine-container execution claim. |

The universal lock also contains Linux and macOS markers and hashes for other
compatible Python versions, but no installed behavior is claimed for an
unobserved version or architecture. The current Homebrew formula installs
with Python 3.13 in the separate tap, and the Dockerfiles still install the
published ranges with pip. Those paths remain explicit resolution gaps; this
change does not modify a published formula, running container, or owner
installation. A later issue must test and migrate them before claiming that
they consume this lock.

## Existing solutions review — Adopt

### Problem and boundary

The root PEP 621 manifest previously declared ranges while CI installed a
fresh, unattributed resolution on every run. The repository also had no
updater configuration. The required boundary is reproducible developer/CI
resolution and bounded update discovery while setuptools packaging, AgentOS
runtime authority, product state, and operating installations remain intact.

### Internal repository candidates

The implementation reuses `pyproject.toml`, the existing `validate` and
`full-validate` workflows, the required structured reuse-review gate, focused
boundary tests, branch protection, and the relationship/ownership map from
#1023. No internal resolver, dependency database, scheduler, update worker, or
parallel status record exists or is added.

Repository search covered the root manifest, optional dependencies, all
workflows, three Dockerfiles, Compose, Homebrew template and release guidance,
`evals/requirements.txt`, copied skill provenance, and the real
`publicsuffixlist` consumer and tests. The evaluation environment, container
base images, npm command pin, and versioned skill content remain outside this
first updater scope.

### Platform and official candidates

- `pip lock` is an official pip facility, but its current command is
  experimental and produces a lock only for the current Python/platform.
- `pip-tools` is maintained and suitable for requirements files, but its own
  guidance requires separate compilation for each environment. That would
  introduce several profile artifacts for the macOS marker and optional/dev
  sets.
- Poetry supports markers and locking but would add a second project model
  without satisfying a boundary that `uv` cannot meet.
- `uv` 0.11.33 is the final 0.11 patch maintained by Astral, licensed MIT OR
  Apache-2.0, and
  provides one universal project lock, PEP 621 extras, dependency groups,
  platform markers, artifact hashes, locked sync, and exact build constraints.
  The repository therefore **Adopts** `uv` while retaining setuptools and PEP
  621. `setuptools==84.0.0` is an exact build constraint because project locks
  do not otherwise constrain isolated PEP 517 build dependencies. GitHub's
  current Dependabot support table names `uv` v0.11, while the current public
  `dependabot-core` updater image uses 0.12.19. The accepted `<0.13` writer
  range covers both current published boundaries; local and CI commands stay
  pinned to 0.11.33. The 0.11 lock records exact runtime, optional,
  development, and platform artifacts with hashes; the separately resolved
  build constraint is exact and attributable but is not artifact-hash locked
  by 0.11, which remains an explicit integrity limitation.

The CI bootstrap uses `astral-sh/setup-uv` v10.2.0 at exact commit
`c18668ad3cf93ea998bef934396af7bb5c839dc7` and requests `uv==0.11.33`.
`setup-uv` is MIT licensed. `[tool.uv]` rejects writers outside the reviewed
0.11.33 through 0.12.x compatibility window; contributor and CI commands pin
0.11.33 exactly. A Dependabot update records the hosted writer observed in
the job rather than pretending the repository controls it.

### Updater candidates

Dependabot and Renovate are both maintained, licence-compatible hosted
updaters. Dependabot documents native `uv` and GitHub Actions support.
Renovate additionally supports custom regex/Git-ref discovery, but changing a
skill commit or content reference cannot safely refresh copied bytes,
licences, digests, local wrappers, and semantic impact evidence. That work
already has an explicit manual provenance path. The repository therefore
**Adopts one updater: native Dependabot** for the root `uv` ecosystem and
GitHub Actions. It does not install another App or add an AgentOS scheduler.

Read-only inspection before activation found no checked-in Dependabot or
Renovate configuration and no historical PR authored by either bot. Current
credentials could not enumerate installed GitHub Apps, so this record does
not claim that account-level App inventory was observed. A later conflicting
updater/configuration is a stop condition, not permission to run both.

## Locked resolution contract

- Maintainer-authored `uv.lock` changes use `uv==0.11.33`. A native Dependabot
  job may use the hosted writer inside the reviewed `>=0.11.33,<0.13` range;
  its exact observed version is update evidence. CI uses `uv==0.11.33` and
  `uv sync --locked`; a stale manifest or lock fails.
- The lock represents `sys_platform == 'linux'` and `sys_platform ==
  'darwin'`. It includes the optional `schema-validation` and `mcp-host`
  closures and the `dev` group. Production-like checks use `--no-dev` when
  they do not need the test group. An optional package's presence in the lock
  does not select it for a base install.
- Resolver downloads use the default first PyPI index. No extra index,
  dependency-confusion fallback, credential, or owner package source is
  configured.
- Hashes establish the selected artifact bytes. They do not establish package
  safety, semantic compatibility, provenance beyond the named source, or
  freedom from vulnerabilities.
- The MCP SDK is selected only by the `mcp-host` extra. It does not enter the
  base dependency set shared with `Dockerfile.engine`. `mcp-types==2.3.0`
  remains a shared base dependency for the protocol-version registry.

Contributor commands:

```sh
uv lock --check
uv sync --locked --extra mcp-host --extra schema-validation --group dev --no-python-downloads
PYTHONPATH=src .venv/bin/python -m pytest -q tests
```

Use `uv lock --upgrade-package NAME==VERSION` for one reviewed candidate.
Inspect the whole lock diff. Do not use an unconstrained `uv lock --upgrade`
to turn a bounded update into an unrelated refresh.

## Host MCP package and recovery contract — #1025

The Phase A decision [recorded in #1025](https://github.com/Jongtae/agentos/issues/1025#issuecomment-6004656860)
**Adapts** the official public `mcp.server.stdio.stdio_server` and
`mcp.shared.jsonrpc_dispatcher.JSONRPCDispatcher` APIs behind the existing
host `mcp_bridge.serve` boundary. The exact release is
[`mcp==2.3.0`](https://pypi.org/project/mcp/2.3.0/), published 2026-10-02 from
source commit `2118f14f8a19bc158d8a1cf90af58d85d187f849`, MIT, Python >=3.10.
PyPI reports Trusted Publishing and attestations tied to that source commit;
these establish publishing identity, not behavioral safety. Its wheel SHA-256
is `dd0c44c089d16453e8ae31a3877a0054d7a2314caaa81f5e0541b9b1734b2377`
and sdist SHA-256 is
`8b147a50441cf059dc88c684e0aeed3687f0aa0f39c6cde7b90330effd2b34d8`.
The shared [`mcp-types==2.3.0`](https://pypi.org/project/mcp-types/2.3.0/)
is also MIT, Python >=3.10, with wheel SHA-256
`968efdbdaedfab06adae40d378a34395f1090c5921d4be3c9cde283aaf76d91d`
and sdist SHA-256
`d1e46549edb35ee19a94940fcee6d1addd7e589ab7ea92dda83f5d84781fc362`.
Its resolved version is unchanged from the #1024 lock; the published manifest
now pins it exactly to attribute the shared candidate closure.

Internal reuse keeps the current bridge entry point, profile/tool/Work checks,
broker callbacks and redaction. Python's standard library cannot supply an
upstream-maintained MCP stdio dispatcher. The official SDK fits this narrow
seam; its documented low-level `Server.run` was rejected by the Phase A probe
for the existing initialize shape and additional registered methods. The
existing `mcp-types` package supplies models/version constants, not transport
or dispatch. Another framework or copied dispatcher would duplicate the
selected supported SDK seam without satisfying a missing requirement.
The dispatcher is provisional upstream, so an exact pin and real-consumer
upgrade checks are required. The SDK's maintenance/release activity and
security review apply to this exact release and closure, not future releases.

Adding `mcp-host` with `uv==0.11.33` preserves every existing resolved version
and adds the following SDK-only packages to the lock. Release dates and licence
expressions were checked against each exact PyPI release on 2026-10-06:

| Package | Exact version | Licence | Upload date |
| --- | --- | --- | --- |
| mcp | 2.3.0 | MIT | 2026-10-02 |
| anyio | 4.15.1 | MIT | 2026-09-05 |
| click | 8.5.0 | BSD-3-Clause | 2026-08-26 |
| h11 | 0.16.0 | MIT | 2025-04-24 |
| httpcore2 | 2.13.1 | BSD-3-Clause | 2026-09-23 |
| httpx2 | 2.13.1 | BSD-3-Clause | 2026-09-23 |
| opentelemetry-api | 1.45.0 | Apache-2.0 | 2026-09-25 |
| pyjwt | 2.15.1 | MIT | 2026-09-28 |
| python-multipart | 0.0.32 | Apache-2.0 | 2026-06-04 |
| sse-starlette | 3.5.0 | BSD-3-Clause | 2026-09-28 |
| starlette | 1.7.0 | BSD-3-Clause | 2026-09-23 |
| truststore | 0.10.4 | MIT | 2025-08-12 |
| uvicorn | 0.54.0 | BSD-3-Clause | 2026-09-25 |

These licences are compatible with AGPL-3.0-only; distributions retain upstream
notices and licence terms. Existing locked `jsonschema`, `pydantic`,
`typing-extensions`, `typing-inspection` and their required dependencies are
also selected by the host closure. Hashes for all artifacts live in `uv.lock`.
HTTP, ASGI, JWT, telemetry API and multipart packages increase installed attack
surface even though the selected stdio imports do not configure a listener,
remote destination, credential, exporter, additional method or tool. AgentOS
Work/Grant/secret/effect/Evidence mediation remains authoritative. Neither
installation nor upstream code grants runtime network or owner-state authority.
No SDK CLI/rich extras or new private indexes are selected.

Install the source host profile with the locked contributor command above. A
published PEP 621 install uses `pip install '.[mcp-host]'`, which retains the
exact direct SDK/types pins but is not a lock-backed transitive installation.
The base command is `uv sync --locked --no-dev --no-python-downloads`;
`Dockerfile.engine` continues to use `pip install --no-cache-dir .` and does
not select the host extra. Container and Homebrew transitive lock consumption
remain the resolution gaps stated above; a base sync on macOS is not proof of
an observed Linux container run.

For a future SDK update, save the known-good commit and lock Git blob, link one
bounded issue, update the exact manifest pins, and use the pinned resolver to
update only the selected SDK/types candidate. Record source revision, artifact
hashes, writer, full transitive diff, platform/Python/profile and observed
commands. Exercise actual host caller -> SDK -> broker -> synthetic target
tests, including denial, stale/revoked Work, malformed input, redaction,
timeout/cancellation, typed and unknown-effect failures, EOF/Stop/shutdown.
Repeat the base exclusion check and the unchanged isolated bridge's protocol
regressions; a passing import is insufficient. Require exact-head CI and
independent review for the changed supply-chain/protocol/authority boundary.

Recovery restores the saved manifest, lock **and matching adapter code** to a
fresh disposable environment, syncs the same profile, verifies exact installed
versions, and reruns the affected boundary. Downgrading only the SDK under new
adapter code is not a demonstrated recovery path. The pre-adoption baseline
is commit `7965ddd0c4f1d544233764b26215ad0481dc7701` (the #1025 worktree start);
the base `mcp-types` version is
already 2.3.0 there and no `mcp` dependency is selected. Baseline restoration
and host-extra deselection are separate checks: removing the extra from the
new adapter does not claim to restore the prior host call path. Rollback does
not undo external effects, owner state changes, package Grants or deployment.

Observed disposable packaging evidence on 2026-10-06 uses macOS 26.3.1 arm64,
CPython 3.12.12 and `uv==0.11.33`:

| Check | Attributable result |
| --- | --- |
| Candidate resolution | Lock Git blob `96922ee3034f110ffe0f1d9a8302e330dbb81bf6`; 56 packages represented, 13 new SDK-only packages, no existing version changed. |
| Fresh host sync | Locked `mcp-host` / `schema-validation` / `dev` command above succeeds; exact SDK/types 2.3.0 and both public APIs import from installed packages. |
| Fresh base sync | Locked `--no-dev` command succeeds; installed types 2.3.0, no `mcp` module. All 13 SDK-only distributions are absent. |
| Known-good recovery | Saved source/manifest/lock at the baseline commit restored to a fresh environment; lock blob `551f8aeb0ce4d12ae13f1567b9f8f0f4058c9a77`; locked `schema-validation` / `dev` sync excludes SDK; baseline protocol and dependency-contract tests pass (29 tests, 71 subtests). |

These observations establish local package selection and restoration. Current
host adapter semantic tests and Linux exact-head CI are separate evidence;
this table does not claim live owner operation, Linux container execution or
production rollback.

## Dependabot discovery and promotion

`.github/dependabot.yml` checks the root `uv` resolution weekly at 09:00 Asia
/Seoul and GitHub Actions at 09:30. It permits at most two routine Python PRs
and one Actions PR. Routine Python discovery is limited to direct minor/patch
updates and explicitly excludes `evals/**`; evaluation requirements remain on
their separately authorized manual path. There is no auto-merge configuration.

A bot PR is a discovery candidate, not implementation authority and not an
exception to issue-first delivery:

1. Link the exact candidate to an existing bounded issue or create one before
   promotion. Use one matching issue branch/worktree for any maintainer edits.
2. Complete the PR's structured Existing solutions review with the actual
   source/release, licence, maintenance, security, compatibility, transitive
   diff and retained AgentOS boundary. Bot authorship is never an `N/A` reason.
3. Run the affected real boundary and the required exact-head CI. A green
   install alone does not prove semantic compatibility.
4. Keep major updates separate. Never enable auto-merge or production package
   application from discovery.

Repository observation found Dependabot alerts and automatic security updates
disabled. `uv` version-update support also does not prove dependency-graph or
transitive advisory coverage. Until a separately authorized settings change
is observed, an urgent advisory follows the normal security issue → matching
branch → exact lock update → affected boundary/security review path. The
routine PR limits above are not claimed to cap future security PRs.

## First update and recovery evidence

The selected first candidate is the bundled Public Suffix List data package:

- known baseline: `publicsuffixlist==1.0.2.20260925`, uploaded 2026-09-25;
- actual updater candidate: `publicsuffixlist==1.0.2.20261002`, uploaded
  2026-10-02;
- package licence: MPL-2.0; pure Python; no mandatory dependency; no runtime
  list fetch;
- real consumer: `browser_session._public_suffix_list()` and
  `registrable_domain()`;
- focused boundary: the login tests for lookalike, country-code, private,
  bare-suffix, IP and IDN hosts;
- candidate artifacts: wheel SHA-256
  `b8e159190c24b16420f58d7c2c21c02cfb24ab05b501331260485b8b32a57c1f`
  and sdist SHA-256
  `3d814ff5eb0ca4bb8a2c9d7e9fd029485a9cd76110a7f37dad39b5936e8764cc`;
- source: unsigned wrapper release commit
  `71d2fffa6b4bef58d83fbb25064cfc1de87ec1bf`, containing only the package
  version and bundled-list update, with the list itself sourced from
  publicsuffix/list commit `714ac1bf5f2d038161c7419478cc3207431d706d`
  whose GitHub signature is verified.

Pre-activation research prepared the then-newest `1.0.2.20261003` as a
possible disposable candidate. The first successful native Dependabot job on
the merged configuration instead proposed `1.0.2.20261002`. That actual bot
candidate is explicitly reselected here so the source review, lock bytes,
real-consumer tests, negative check, rollback, exact-head CI and independent
review all describe the same release. A later `20261003` proposal remains a
separate future update and is not silently folded into this evidence.

The initial lock intentionally records the known baseline. After this updater
configuration reaches the default branch, a successful Dependabot job/PR must
be observed before #1024 closes. Promotion of the candidate must record its
PyPI source/release hashes and the exact lock diff.

Verification uses three fresh, disposable environments and no owner state:

1. sync the saved baseline lock and run the focused real boundary;
2. sync the candidate lock and run the same boundary plus required CI;
3. restore the saved baseline lock into a new environment and rerun the
   focused boundary.

For the negative check, temporarily replace the disposable environment's PSL
behavior with an incompatible result for a private suffix such as
`owner.github.io`; the focused boundary must fail. This mutation is failure
evidence only. Positive compatibility always executes the actual installed
package. Rollback restores Python resolution and test behavior; it does not
claim to undo external effects, data migrations, permissions, or a deployed
installation.
