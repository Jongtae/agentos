# UPSTREAM-CONTRIB-01 — prepared contribution and release rejoin record

Issue: [#1027](https://github.com/Jongtae/agentos/issues/1027), under
UPSTREAM-01 #1022. Review and reproduction date: 2026-10-06. This record is
**prepared** inside AgentOS. It does not report an external issue, comment,
discussion or pull request as submitted. External posting, an agreement and any
licence grant still require separate owner approval.

## Decision, consumer and reuse

The primary contribution candidate is a packaging mismatch in
[`publicsuffixlist==1.0.2.20261003`](https://pypi.org/project/publicsuffixlist/1.0.2.20261003/):
the published universal wheel and source distribution contain different Public
Suffix List snapshots. The real AgentOS consumer is
[`browser_session.registrable_domain`](../src/personal_agent/browser_session.py),
which uses the package's bundled data for login-site and destination boundaries.
AgentOS currently locks the known-good `1.0.2.20261002`; rejected update
[PR #1077](https://github.com/Jongtae/agentos/pull/1077) preserved that lock.

The official MCP Python SDK response-drain finding is retained as a secondary
rejoin record. It is genuine, but upstream
[#2678](https://github.com/modelcontextprotocol/python-sdk/issues/2678) and
[#2680](https://github.com/modelcontextprotocol/python-sdk/pull/2680) already
cover the EOF response-loss subject. A new issue or unsolicited replacement PR
would duplicate existing work. No MCP submission is selected here.

**Adopt** each upstream's own issue and release mechanisms and the repository's
existing dependency, test and provenance records. **Adapt** the existing #1024
rejection evidence into one privacy-reviewed public reproduction and an explicit
release rejoin condition. Internal search covered `pyproject.toml`, `uv.lock`,
the dependency-update contract, upstream relationship map,
`browser_session.registrable_domain`, its real login-flow tests, the MCP bridge
and SDK tests, and PRs #1077/#1080. Python 3.12 standard-library `urllib`,
`hashlib`, `zipfile` and `tarfile` are enough to reproduce the packaging result;
no package installation, new dependency, contribution platform, tracker, runtime
authority or owner-state store is needed. A factual upstream issue is preferable
to a speculative local patch because there is no AgentOS code defect to mask.

## Primary candidate: exact artifacts and reproduction

PyPI's per-release JSON and both artifacts were fetched on 2026-10-06. Each
downloaded artifact matched the SHA-256 published by PyPI before its embedded
`public_suffix_list.dat` was inspected.

| Distribution | Published artifact SHA-256 | Embedded PSL identity | Embedded data SHA-256 | Normalized rules |
| --- | --- | --- | --- | --- |
| `publicsuffixlist-1.0.2.20261003-py2.py3-none-any.whl` | `836bcbfb66f44eea6ee7917864635a0d5f49ef5220e3074bc8611f683a34c11c` | `2026-09-30_20-56-07_UTC`, commit `714ac1bf5f2d038161c7419478cc3207431d706d` | `73c95828f5f62a3fce06d3fa9b2efd3f0a45a8c8dc2a65411545fab898a576f7` | 10,334; `juniper` present |
| `publicsuffixlist-1.0.2.20261003.tar.gz` | `d88339d4752d866a5be66ca4234257ca1e8277541c8518f6e6615d581a8d8b03` | `2026-10-01_23-02-52_UTC`, commit `6cd82aff889e3d64e5e03bc5c1f43da1934a960a` | `e0fe072d26b0536525badea237953ff451c9f8e64c9d02c6daa81a4491d2fc66` | 10,333; `juniper` absent |

The rule-set difference is exactly one line: the wheel alone contains
`juniper`. As a control, both published `1.0.2.20261002` artifacts contain the
10,334-rule snapshot with `juniper`, and the `20261003` wheel matches that older
snapshot. Comment-only differences are excluded by normalization.

### Executed public reproduction

This standalone script uses only public PyPI data and Python's standard library.
It contains no AgentOS import, owner material, account, credential, path or
runtime log. It was executed with Python 3.12.12 on Darwin arm64; the table above
is its observed result.

```python
from __future__ import annotations

import hashlib
import io
import json
import tarfile
import urllib.request
import zipfile

VERSION = "1.0.2.20261003"
EXPECTED = {
    "bdist_wheel": "836bcbfb66f44eea6ee7917864635a0d5f49ef5220e3074bc8611f683a34c11c",
    "sdist": "d88339d4752d866a5be66ca4234257ca1e8277541c8518f6e6615d581a8d8b03",
}


def get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read()


def embedded_psl(kind: str, artifact: bytes) -> bytes:
    if kind == "bdist_wheel":
        with zipfile.ZipFile(io.BytesIO(artifact)) as archive:
            names = [name for name in archive.namelist()
                     if name.endswith("/public_suffix_list.dat")]
            assert len(names) == 1
            return archive.read(names[0])
    with tarfile.open(fileobj=io.BytesIO(artifact), mode="r:gz") as archive:
        members = [member for member in archive.getmembers()
                   if member.name.endswith("/public_suffix_list.dat")]
        assert len(members) == 1
        stream = archive.extractfile(members[0])
        assert stream is not None
        return stream.read()


metadata = json.loads(get(
    f"https://pypi.org/pypi/publicsuffixlist/{VERSION}/json"
))
observed = {}
for item in metadata["urls"]:
    kind = item["packagetype"]
    if kind not in EXPECTED:
        continue
    artifact = get(item["url"])
    artifact_hash = hashlib.sha256(artifact).hexdigest()
    assert artifact_hash == item["digests"]["sha256"] == EXPECTED[kind]
    data = embedded_psl(kind, artifact)
    lines = data.decode("utf-8").splitlines()
    rules = {line.strip() for line in lines
             if line.strip() and not line.lstrip().startswith("//")}
    observed[kind] = {
        "artifact_sha256": artifact_hash,
        "data_sha256": hashlib.sha256(data).hexdigest(),
        "headers": [line for line in lines
                    if line.startswith("// VERSION:")
                    or line.startswith("// COMMIT:")],
        "rules": rules,
    }

wheel = observed["bdist_wheel"]["rules"]
sdist = observed["sdist"]["rules"]
print("wheel only:", sorted(wheel - sdist))
print("sdist only:", sorted(sdist - wheel))
assert wheel - sdist == {"juniper"}
assert not sdist - wheel
```

Observed terminal lines:

```text
wheel only: ['juniper']
sdist only: []
```

### Expectation, observation and interpretation

- **Expectation:** one immutable Python release version selects one bundled PSL
  data revision, regardless of whether an installer selects its wheel or sdist.
- **Observation:** the registry-verified `20261003` wheel and sdist carry
  different source timestamps, commits, hashes and normalized rule sets.
- **Interpretation:** this is a reproducible packaging/release consistency defect
  useful to report to the package maintainer. It does not establish a malicious
  publication, a root cause, an exploitable vulnerability or an error in the
  authoritative Mozilla PSL. Consumer behavior can differ by selected artifact
  and API usage; AgentOS observed no security incident.

## Duplicate search, channel, policy and licence

The package repository's default `master` was inspected at immutable commit
[`4e975f1cb3ea8aff9bdbd6b460b7fbb1f7e8c8f4`](https://github.com/ko-zu/psl/commit/4e975f1cb3ea8aff9bdbd6b460b7fbb1f7e8c8f4).
Its [`DEVELOPMENT.md`](https://github.com/ko-zu/psl/blob/4e975f1cb3ea8aff9bdbd6b460b7fbb1f7e8c8f4/DEVELOPMENT.md)
blob is `84fa0e997955bddf329f1df16b1a783d3181a876`; it describes development,
release and PSL-update branches. GitHub reported Discussions disabled.

The complete visible inventory on 2026-10-06 contained 23 issues and 16 pull
requests. All-state searches for `wheel sdist`, `20261003`, `juniper` and
`artifact mismatch` returned no match. Historical issue
[#1](https://github.com/ko-zu/psl/issues/1) concerns the existence of an sdist,
[#7](https://github.com/ko-zu/psl/issues/7) missing old source, and
[#24](https://github.com/ko-zu/psl/issues/24) source tagging; none reports two
different PSL snapshots under one current release version. Open issues #35 and
#42 concern typing and supported Python versions. The selected destination is a
normal packaging bug in [`ko-zu/psl` Issues](https://github.com/ko-zu/psl/issues),
not the Mozilla PSL rule tracker, a security advisory or a new pull request.

The inspected tree has no `CONTRIBUTING`, `CODE_OF_CONDUCT`, `SECURITY`, CLA,
DCO, issue template or pull-request template. This records an absence in the
current tree, not permission for a later patch or legal assurance. The repository
and PyPI identify the package as MPL-2.0; the upstream README also attributes
the vendored PSL and test data. This factual report copies no package or AgentOS
code and grants no licence. A later patch must recheck then-current policy and
preserve applicable MPL/CC0 attribution. No upstream AI-disclosure rule was
found, so the prepared report discloses AI assistance voluntarily.

## Privacy-reviewed publication draft

**Destination:** a new normal issue in `ko-zu/psl`.

**Title:** `PyPI 1.0.2.20261003 wheel and sdist bundle different Public Suffix Lists`

**Prepared body:**

> AI assistance disclosure: Codex assisted with comparing the public artifacts,
> checking the tracker and drafting this report. I reviewed the reproduction and
> the statements below.
>
> The two files published for `publicsuffixlist==1.0.2.20261003` contain
> different `public_suffix_list.dat` snapshots. I downloaded the artifact URLs
> from the release JSON, verified each SHA-256 against that JSON, then extracted
> and compared the non-comment rules without installing the package.
>
> - wheel SHA-256 `836bcb...4c11c`: PSL timestamp
>   `2026-09-30_20-56-07_UTC`, commit `714ac1b...d706d`, 10,334 rules;
> - sdist SHA-256 `d88339...d8b03`: PSL timestamp
>   `2026-10-01_23-02-52_UTC`, commit `6cd82af...960a`, 10,333 rules;
> - the only normalized rule-set difference is `juniper`, present in the wheel
>   and absent from the sdist.
>
> Expected: both distributions for one release version bundle the same PSL
> revision. Observed: installers can receive different PSL data according to
> artifact selection. I have not inferred a security impact or root cause.
>
> Minimal reproduction: [paste the standard-library script from this record].
> Could you confirm which snapshot was intended and publish a subsequent release
> whose wheel and sdist contain the same PSL revision?

Before posting, expand abbreviated hashes in the draft from the identity table
and include the complete executed script. The report contains only public
artifact metadata and synthetic comparison output. It excludes owner data,
accounts, secrets, sessions, internal paths, private transcripts and production
logs. It makes no acceptance, release or downstream-adoption claim. Posting it
remains blocked only by the explicit separate-owner-approval boundary.

## AgentOS disposition and release rejoin condition

AgentOS has no local source patch for this package. The local difference is the
deliberate `uv.lock` pin at `publicsuffixlist==1.0.2.20261002` after #1077 was
closed unmerged. The rejected wrapper tag `v1.0.2.20261003-gha` resolved to
unsigned commit `d08104aa385a809f379f32dff91d0cc820ae8808`; tag or workflow
identity did not make the mismatched artifacts acceptable. The candidate wheel
passed focused AgentOS behavior tests, which proves only that the older snapshot
remained compatible with current consumers. It cannot establish sdist/wheel
equivalence.

The dependency maintainer may reopen normal #1024-style update work only after a
released package artifact set meets all of these conditions:

1. wheel and sdist registry hashes are recorded and each matches its downloaded
   file;
2. both distributions contain the same PSL timestamp, commit, bytes and
   normalized rule set;
3. source/tag/workflow provenance and licence remain reviewable;
4. `PYTHONPATH=src python -m pytest -q
   tests/test_flow_login.py::LoginPromptAndThreads::test_the_registrable_domain_is_the_site_a_lookalike_host_really_is`
   passes against the candidate;
5. the normal candidate update, known-good restore, required exact-head CI and
   relevant review complete before the lock changes.

An upstream issue close, favourable comment, accepted patch or unreleased commit
does not satisfy this trigger. If the report is declined or no consistent release
appears, retain the bounded known-good pin or choose another maintained package
in a separately scoped dependency issue. Do not add a local data rewrite merely
to hide publisher divergence.

## MCP duplicate and rejoin disposition

AgentOS adopted `mcp==2.3.0`, tag commit
[`2118f14f8a19bc158d8a1cf90af58d85d187f849`](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.3.0),
through [PR #1080](https://github.com/Jongtae/agentos/pull/1080). Its host bridge
uses the public `JSONRPCDispatcher` with an all-inline membership adapter to
preserve serialized Work, budget and Evidence ordering and to flush accepted or
rejected requests before EOF. Notifications are intercepted inline. This is a
local compatibility adaptation, not an SDK fork.

Duplicate review found open upstream issue #2678, its existing 2.2.0 synthetic
confirmation, open fix PR #2680, closed duplicate drain PR #3026 and broader
shutdown issue #1739. Upstream intentionally cancels in-flight handlers when the
transport closes; therefore the desired bounded drain/serial mode is an extension
question, not a violated documented promise. The current contribution policy
requires an issue first, AI disclosure and accountable human review; an external
PR must be assigned or labelled `help wanted`. The existing issue is neither
assigned to AgentOS nor labelled `help wanted`.

No new MCP report or patch is prepared. A short current-version comment on #2678
would be useful only if a separately executed raw-dispatcher reproduction adds
new `inline_methods` evidence rather than repeating the general EOF claim. The
local adapter remains owned by the AgentOS runtime maintainer and is covered by
`test_batched_same_tool_calls_stay_serialized_and_eof_flushes_all_responses`,
`test_unsupported_method_as_only_request_before_eof_is_answered`,
`test_call_notifications_execute_without_response_and_late_cancel_does_not_replay`
and `test_empty_input_eof_closes_cleanly_without_effects` in
[`test_mcp_sdk_bridge.py`](../tests/test_mcp_sdk_bridge.py).

Remove only the wildcard/EOF compatibility adaptation after a released SDK
offers a supported replacement that passes those response-completeness,
arbitrary-method rejection, notification-order, shutdown, redaction and truthful
cancellation-evidence regressions. Retain AgentOS serialization and policy glue.
Resolve the released artifact through normal dependency review; merged upstream
code alone is not a rejoin event.

## Model and delegation record

The primary task selected current Codex with high reasoning because a public
package report requires exact provenance, duplicate, privacy and licence review.
The host exposed no exact applied-model or reasoning receipt, so this record does
not claim an applied setting.

Three read-only delegates were requested as `gpt-6.1-sol` with high reasoning:
one for MCP, one for the PSL artifact candidate and one for independent
cross-candidate review. The follow-up interface did not expose a selectable or
accepted applied setting, and every delegate reported that no applied receipt
was observable. Their observed results were the public-source findings reconciled
above. Repository edits, validation, GitHub changes and final convergence remain
exclusive to the primary issue worktree.

## Requirement-to-evidence audit

| #1027 acceptance | Current evidence and boundary |
| --- | --- |
| Genuine exact-version candidate and duplicate search | Registry-verified `20261003` artifact reproduction, one-rule difference, complete visible issue/PR inventory and targeted all-state queries |
| Current channel, scope, disclosure and licence | Immutable PSL repository/policy identities, Issues destination, no current templates/CLA/DCO/AI rule observed, voluntary disclosure, MPL-2.0 boundary |
| Privacy-ready selected submission scope | Prepared title/body and standard-library public reproduction; no owner/private material; external state remains prepared, not submitted |
| Tested local rejoin/removal condition | Known-good `20261002` pin, #1077 recovery evidence, exact future artifact-equivalence gate and focused real-consumer test; MCP tests and released-SDK gate |
| Truthful external state | No submission, acceptance, release or adoption inferred; separate approval remains explicit |
| Repository validation and review | Document link/source checks, `git diff --check`, canonical document verification and required exact-head CI on the eventual PR; no runtime, dependency, authority or safety-boundary change |

This preparation changes no runtime, dependency, package data, Grant, owner state,
network destination, secret handling, deployment or external project. Normal
focused review is sufficient; an independent security/authority review is not
triggered by this evidence-only document.
