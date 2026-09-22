# Release procedure

Canonical English source. This writes down a procedure that previously existed
only as unreachable code in `src/personal_agent/delivery.py`, where
`_run_release` returns unconditionally at its first statement, so the body
below it never executes. That guard stays; this document is not a request to
re-enable it, and `tests/test_delivery.py` continues to assert the helper fails
closed with `blocked-manual-governance-execution-required`.

## What the published artifact actually is

`brew install jongtae/agentos/agentos` resolves the tap repository
**`Jongtae/homebrew-agentos`**, which holds `Formula/agentos.rb` and nothing
else. The formula has never lived in this repository — the first record in
`docs/issue-branch-ledger.jsonl` documents the migration that made the tap
Formula-only.

This matters because `git ls-files` in this repository finds no `.rb`, no tap
and no checksum, and that absence has been misread as "no release artifact
exists". It does exist. What the formula points at is a **GitHub tag source
archive**, not a wheel:

```ruby
url "https://github.com/Jongtae/personal-agentos/archive/refs/tags/vX.Y.Z.tar.gz"
sha256 "<64 hex>"
```

`deploy/homebrew/agentos.rb.template` is the in-repo template for that file, so
the relationship is traceable from here.

## Ordering, and why the checksum cannot be precomputed

The archive the `sha256` describes **does not exist until the tag is pushed**.
GitHub generates it on demand, and its gzip output is not guaranteed to be
byte-identical to a local `git archive`. So the checksum is irreducibly
post-publication. Any formula committed before that point must carry the
`__SHA256__` placeholder; a fabricated hex string would produce a formula that
looks reviewable and installs nothing.

## Steps

Steps 1–4 are local and reversible. Steps 5 onward publish, and none of them is
authorized by EPIC-PA1 / #386, which explicitly excludes public deployment.

1. **Decide the version.** Bump `version` in `pyproject.toml`. It must differ
   from the newest tag; `tests/test_release_traceability.py` fails if they
   converge, because an in-tree version equal to the last release makes source
   indistinguishable from the shipped build.
2. **Record what the release carries.** Add the journey/issue coverage to
   `docs/release-manifest.json` so a reader can map a version to the work in it.
3. **Run the full suite and the verifier gates** on the exact commit:
   `pytest tests`, `python3 -m unittest discover -s tests -t tests`,
   `scripts/verify_master_plan_docs.py`, `scripts/verify_src_layout.py`, and
   `cmp -s delivery-plan.yaml src/personal_agent/delivery-plan.yaml`.
4. **Merge to `main`** through the normal issue/branch/PR/CI/review path.

--- everything below publishes ---

5. **Tag and push** `vX.Y.Z` at the merge commit, and create the GitHub release.
6. **Compute the archive checksum** of
   `https://github.com/Jongtae/personal-agentos/archive/refs/tags/vX.Y.Z.tar.gz`.
   `delivery.py` `_archive_sha256` is the reference implementation.
7. **Render the formula** from `deploy/homebrew/agentos.rb.template`, replacing
   `__VERSION__` and `__SHA256__`, and open a PR against
   `Jongtae/homebrew-agentos` `Formula/agentos.rb`.
8. **Verify the install**: `brew update`, `brew upgrade jongtae/agentos/agentos`,
   `brew test jongtae/agentos/agentos`, then
   `python3 scripts/quickstart_install_check.py`.

## Evidence classes

Steps 1–4 produce **contract/static** evidence. Step 8 is the only step that
produces **installed-smoke** evidence, and a real login service surviving a
machine restart plus a Telegram result with no terminal open remain
**owner live** — `scripts/quickstart_install_check.py` returns
`"background_service": "owner_validation_pending"` by construction and does not
install or mutate a launchd service.

Do not describe a release as verified on the strength of steps 1–4.
