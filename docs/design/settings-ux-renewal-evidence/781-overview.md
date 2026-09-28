# UX-PREF-01 evidence

Issue #781, owner program #780. This is the real checked-out web HTML/CSS/JS served by tests/web_management_browser_fixture.py on 127.0.0.1:18789, with synthetic /api/state responses injected through Playwright. No credentials, model requests or external provider operation.

- A01: [configured desktop](781-overview.png), [390px layout](781-mobile.png); unconfigured state and effective independent Judgment AI observed in the browser and covered by DOM checks.
- A02: table-driven DOM projections cover login unknown/unchecked/signed-in/signed-out/token-saved/sidecar, pending API key, failed check and unchecked API. No selected route is labelled currently executing.
- A08: short file-access implication stays visible; raw profile, limitations and CLI versions are disclosed. Changing a profile retains the existing verification endpoint. Disclosure state survives refresh.
- Shared shell: one sidebar, no logo, four-language selector and authenticated logout retained. Korean preference reload observed.
- Focused regressions: 65 passed (settings UI, AI connection UI, UI quality/locales, Main AI routes). Required CI is recorded on the PR. Existing chooser behavior is preserved here and redesigned in #782.

## Asset provenance

- `index.html` SHA-256 `7a7e284d2369ecd213df4f0dda5630ab643bf14ed20eaa622659ea71e75b3457`
- `app.js` SHA-256 `5736b946989f4c5d959782a8b35fe76c3b3aa35b894d69d81cbdda46136e109c`
- `style.css` SHA-256 `c2864ead27edb427552311770d8f3098097ffc842db271d9947e08616e56ca4a`

Rollback: revert the implementation PR through normal checked branch workflow; no data migration or configuration mutation.
