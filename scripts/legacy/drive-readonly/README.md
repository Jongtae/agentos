# Retired `drive.readonly` Drive design

Relocated here by REUSE-R1c / #440. #418 permits deleting historical runtime
code "only after proving it is not a current supported path"; the proof is
below, and relocation rather than deletion preserves the record anyway.
Nothing is deleted: the historical implementation and its acceptance behaviour
are preserved, and `tests/test_google_drive.py` still runs all of it in both
declared suites.

| File | Former location |
| --- | --- |
| `google_drive.py` | `src/personal_agent/google_drive.py` |

## Why it was retired

**Nothing reached it.** Established by execution, not by reading — this
repository has produced several rounds of wrong reachability claims from
greps. Running the real console entry point (`agentos`) under `-X importtime`
shows the serving process imports 20 `personal_agent` modules; this is not one
of them. Rebuilding the production object graph with `AGENTOS_DRIVE_LOCAL_ONLY=1`
and every Drive secret supplied — the most-wired Drive configuration the
product supports — still leaves `orchestrator.drive` as `None` and still never
imports this module. An AST sweep over every `.py`, walking imports at any
nesting depth, found its only importer was its own test.

**Its replacement ships, with strictly narrower authority.** `drive_web_oauth.py`
does the same job — get the owner's Drive files into the assistant as reading
material — under a different authority design:

| | this module | `drive_web_oauth.py` |
| --- | --- | --- |
| scope | `drive.readonly` | `drive.file` |
| owner picks | *after* the grant exists | *before* any access exists |
| shipped | no | yes (`quickstart.py:185`) |

The decisive evidence is `drive_web_oauth.py:349`:

```python
def search(self, *_args, **_kwargs):
    raise DriveScopeError("drive.file does not allow arbitrary or full-Drive search; choose a file first.")
```

That method has no purpose except to be interface-compatible with
`GoogleDrive.search()` and refuse it. The Picker handoff was deliberately
shaped as a drop-in for this adapter, turning the one capability the broader
scope enabled — server-side full-Drive search — into an explicit refusal.

The capability catalogue had already moved: `google-drive-read`
(`capabilities.py:10`) declares tools `["search", "read_selected"]`, and
`read_selected` is `drive_web_oauth`'s method name, not this module's.

**No owner-reachable capability is lost**, because nothing populates
`orchestrator.drive` in production — `quickstart_service.py:134` constructs
`PersonalAssistantOrchestrator(store)` with no `drive=`, and no other caller
injects one.

An earlier version of this file claimed instead that "both classes are accepted
at the same seam, so retiring this one does not remove the seam's usability".
That was false and is withdrawn. The constructor type-checks nothing, so
"accepted" is trivially true, but the seam has two call sites and they are not
equally served: `personal_assistant.py:88` calls `.search()`, which
`DriveWebOAuthHandoff` provides as a graceful refusal, while
`personal_assistant.py:131` calls `.read(file_id)`, which it does not have at
all — it has `read_selected(owner, file_id, transport)`. Retiring this module
removes the only in-package class that satisfies the `.read()` call site. That
costs nothing today because the seam is never populated, but it is a real gap
for whoever wires Drive into the orchestrator later.

## What this is not

This is not a decision that Drive support is going away — the shipped Picker
path is unaffected. It is not a judgement that `drive.readonly` is wrong in
principle; it is a record that this repository chose the narrower grant and
only one of the two designs is wired.

`SEC-DRIVE-SCOPE-01 / #441` hardened this module's scope check shortly before
this retirement. That was correct at the time: the module shipped in the wheel,
#432 required the fix, and deletion was outside that issue's scope. The
security value of that work lives in `drive_web_oauth.py`, which stays.

## Provenance

Added by `48964a5` (2026-09-08, "feat: add read-only Google Drive connector",
#191); later touched by MP1 R-04 #223, the `src/` package move `1699bbc`, and
SEC-DRIVE-SCOPE-01 #441.
