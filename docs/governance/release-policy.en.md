# Release governance and version policy

## Purpose
Separate code integration from public installation. **Merge != release**. This policy defines release decisions; [the existing release procedure](../release.en.md) remains authoritative for tag, checksum, tap, installer and manifest mechanics. No release script or disabled guard is enabled by this document.

## Versioning
Use SemVer for the public interface and compatibility commitments: **patch** for compatible fixes, **minor** for compatible features, **major** for incompatible supported interfaces, configuration or durable-data behavior. Internal refactors do not automatically require major. Pre-releases such as `v1.4.0-rc.1` are opt-in validation candidates, never silently presented as stable. Public contract/compatibility boundaries must be specified before selecting a bump; do not imply unverified support for older versions.

## Release cadence and authority
Review readiness approximately monthly, **not** an automatic monthly publish. Security/critical regressions may justify an out-of-band patch. The authorized human release maintainer approves the exact tag and public distribution; an AI may prepare notes, compare risks and recommend a version, but may not independently tag, publish, update Homebrew, deploy or access release credentials. Release roles do not imply repository permissions.

## Gates for stable promotion
1. Identify exact merged revision, included issues/PRs, user-visible changes, supported platforms and proposed SemVer bump.
2. Check required CI plus risk-triggered full validation and security/authority negative tests. Cancelled, missing or stale checks are not passing.
3. Verify schema/config/memory compatibility, migration and recovery where changed; document rollback limitations.
4. Execute release procedure's installed-smoke/upgrade checks on the actual published artifact, including Homebrew tap and install script consistency; distinguish CI/mock, installed-smoke and owner-live evidence.
5. Reconcile `docs/release-manifest.json`, release notes, known limitations, product-status and security supported-version statements with actual published state.
6. Prepare a Release Decision Brief: version/tag/head, scope, evidence, failures/unknowns, compatibility, known risks, blockers, publish recommendation and human authorization.
7. Explicit authorized approval precedes stable publication. Follow the [release procedure](../release.en.md) ordering; the tag archive checksum exists only after the tag is published, so record post-publication verification and rollback response honestly.

If a blocker remains, postpone stable, issue a bounded RC for further validation where appropriate, or defer the change to a later release. Never label a failed/partial/unknown external check as verified. A release does not require a human to repeat all development tests, but release-specific install/upgrade evidence cannot be replaced by PR CI.

## Contribution and review boundary
All contributors may suggest release notes and identify blockers. The maintainer may delegate preparation but not implicit publish authority. Merge approval and release approval are separate records. Protect release tags and credentials with GitHub rules and least privilege; this policy does not itself enforce repository settings.

## Rollout
First adopt this as a documentation contract and validate with one dry-run Release Decision Brief; later add automation only where it removes manual bookkeeping without bypassing approvals. Existing `delivery-plan.yaml` selection and paused programs are unchanged.
