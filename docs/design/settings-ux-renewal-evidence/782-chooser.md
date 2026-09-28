# UX-PREF-02 — AI chooser evidence

Issue #782; parent #780. Implements specification A03–A07 and chooser portion of A10.

## Observed UI

The checked-out production assets were served by the existing local browser fixture on port 18789. `/app.js` and `/style.css` matched checkout bytes. Synthetic route responses and intercepted mutations were used; no actual account, secret, login, model, provider or external effect was exercised.

- Five providers remain in fixed order; current configuration is selected.
- Radio selection changes the draft; one account editor and one model editor are independent.
- Unsaved secret input survives route selection; dirty account switching and Escape offer keep/discard.
- Discard/reopen resets model drafts to observed configuration.
- One pending activation stays guarded after close/reopen; a late response leaves the new dialog open.
- Synthetic activation refusal retains route/model and reports an error. A key save sends only its key endpoint and reports success after refresh consumes the overview notice.
- Request spy observed exactly two intended activation calls (success and refusal) and one key save, with no duplicate activation.
- Desktop 1280×800: collapsed list and footer fit. At 320×740: document width 320 and footer bottom 740; body scrolls independently. This is browser viewport evidence, not an on-device virtual-keyboard claim.

![Chooser](782-chooser.png)
![Account panel](782-account.png)
![320 px account panel](782-mobile.png)

## Capture asset hashes

- `index.html`: `c3c62b50cd4c7335afbf6a991f80ffa3f860a8cd5f2d539ae7cc99b74f62bceb`
- `app.js`: `a66790a651021a9c5985c21bd63140b8b4cea4844fe68d9b8bc35bde99bcc68c`
- `style.css`: `ed82b72d36981ca321e7d5cc5c6d02989a1decce6d35c82210d22952b5439aae`

Unit tests preserve credential transport shapes, async session isolation, missing-key eligibility, cached model suggestions, sidecar model clearing and API failure retention. Required CI applies to the PR head. Final integrated evidence is delivered in #784.
