# Retired Kubernetes owner-runtime cluster

Relocated here by REUSE-R8 / #435 under #418's "relocate, do not delete" rule.
Nothing is deleted: the historical implementation and its acceptance behaviour
are preserved, and the test still runs in the declared suites.

## Contents

| File | Former location |
| --- | --- |
| `runtime.py` | `src/personal_agent/runtime.py` |
| `cli.py` | `src/personal_agent/cli.py` |
| `e2e.py` | `scripts/e2e.py` |

`tests/test_runtime.py` stays under `tests/` so `pytest -q tests` and
`unittest discover -s tests` still discover it; it loads these modules by path,
the same way the repository already tests other `scripts/` modules
(`test_agentos_doctor.py`, `test_pr_preflight.py`, `test_operating_preflight.py`).

## Why these were retired from the product package

The three relocated modules are a self-consistent legacy cluster on a container
contract that nothing in the repository builds:

- **No product code imports them.** No module under `src/personal_agent/`
  imports `runtime` or `cli`; the package `__init__.py` is empty, so nothing is
  re-exported. The sole non-test reference was the string-based subprocess call
  `scripts/e2e.py:24` (`python -m personal_agent.cli`), and `e2e.py` is itself
  invoked by nothing — no workflow, script, doc or test runs it. It also needs a
  live `kind` cluster and `kubectl`, so it cannot run in CI.
- **Their container contract is not the shipped one.** `cli.py` generates
  manifests for image `personal-agent:dev` on port **8080**. The live
  `deploy/kubernetes/owner-runtime.yaml` uses `personal-agentos:managed` on port
  **8787**, matching the root `Dockerfile`. `personal-agent:dev` appears exactly
  once in the repository — as `cli.py`'s own default argument. No Dockerfile
  builds it.
- **Kubernetes is documented as out of scope.** `QUICKSTART.md:3` states "Docker
  and Kubernetes are not required"; `QUICKSTART.md:83` lists Kubernetes
  packaging as "future deployment work".

Relocating them removes an unreachable HTTP server, a `kubectl`-shelling
provisioning CLI and a stale container contract from the installed product
package, while keeping the record and the tests intact.

## What this is not

This is not a decision about whether Kubernetes will be supported later, and not
an expansion of the Python-generated manifest path. #418 directs that if
Kubernetes is revived, Helm or Kustomize should be evaluated rather than these
generators extended.
