# Reproducible dependency updates

## Scope and evidence boundary

This contract implements the first, bounded update path selected by
UPSTREAM-UPDATE-01 [#1024](https://github.com/Jongtae/agentos/issues/1024).
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
| Linux CI | Python 3.12, base project, `schema-validation`, and `dev` | Required `validate` on the exact PR head runs `uv sync --locked` and the full suite. |
| macOS source development | Python 3.12, the same extras/groups, plus the `pyobjc-framework-WebKit` marker closure | A fresh disposable environment runs locked sync and the focused real dependency boundary. |

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
  'darwin'`. It includes the optional `schema-validation` closure and the
  `dev` group. Production-like checks use `--no-dev` when they do not need the
  test group.
- Resolver downloads use the default first PyPI index. No extra index,
  dependency-confusion fallback, credential, or owner package source is
  configured.
- Hashes establish the selected artifact bytes. They do not establish package
  safety, semantic compatibility, provenance beyond the named source, or
  freedom from vulnerabilities.
- A future host-only MCP SDK extra belongs to #1025. It must not enter the base
  dependency set shared with `Dockerfile.engine` without reviewing that
  isolated image's closure.

Contributor commands:

```sh
uv lock --check
uv sync --locked --extra schema-validation --group dev --no-python-downloads
.venv/bin/python -m pytest -q tests
```

Use `uv lock --upgrade-package NAME==VERSION` for one reviewed candidate.
Inspect the whole lock diff. Do not use an unconstrained `uv lock --upgrade`
to turn a bounded update into an unrelated refresh.

## Dependabot discovery and promotion

`.github/dependabot.yml` checks the root `uv` resolution weekly at 09:00 Asia
/Seoul and GitHub Actions at 09:30. It permits at most two routine Python PRs
and one Actions PR. Routine Python discovery is limited to direct minor/patch
updates. There is no auto-merge configuration.

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
