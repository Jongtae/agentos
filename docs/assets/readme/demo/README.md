# README demo

`demo.gif` is the demo at the top of all four public READMEs. It is one language-neutral file: the phone screen is the Korean Telegram interface, and each README describes the scenes in its own language.

| | |
| --- | --- |
| Size | 480 × 1044, 472 frames at 10 fps (47.2 s), looping |
| Scenes | 1. dinner meeting route and restaurant · 2. adding one small item to a grocery cart, stopping before payment · 3. book-cart discount question, with the unchecked step stated |
| Sources | four iPhone screen recordings of Telegram sessions made on 2026-10-07 (digests in [manifest.json](manifest.json)) |
| Selected for public use | by the owner on 2026-10-08 (#1133) |

## Editing

Waiting time is cut and typing is sped up (2–4×); still frames hold replies long enough to read. A 1.5-second title card opens the loop and doubles as the still preview; a numbered badge (1–3) over the status bar marks each scene. [manifest.json](manifest.json) lists every segment with its source time and speed.

Personal details are blurred frame by frame. Apple Vision OCR located the text boxes of sign-in links (tunnel host and one-time code), the home neighbourhood and an apartment-complex link, and each box was blurred, including in the neighbouring frames. Afterwards every distinct output frame was OCR-checked again for those patterns; there were zero matches.

## Evidence class

The demo is edited from real sessions. The screens show what the PA replied; they are not an independent trace of the account or tool calls, and the recording names no application revision or model. It is not a repeatability check of a published release. See [product status](../../../product-status.en.md) for the evidence behind each area.
