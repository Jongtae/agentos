# README demo

Each public README shows the demo GIF for its language: `demo.en.gif`, `demo.ko.gif`, `demo.ja.gif` and `demo.zh-CN.gif`. All four use the same phone recording (the Korean Telegram interface); a strip under the phone gives the scene title, the speaker and the key line in the README's language, and the opening title card is localized.

| | |
| --- | --- |
| Size | 480 × 876 (a 480 × 720 window of the phone screen + 156 px subtitle strip), 491 frames at 10 fps (49.1 s), looping; about 3.5 MB each |
| Scenes | 1. dinner meeting route and restaurant · 2. adding one small item to a grocery cart, stopping before payment · 3. book-cart discount question, with the unchecked step stated |
| Sources | four iPhone screen recordings of Telegram sessions made on 2026-10-07 (digests in [manifest.json](manifest.json)) |
| Selected for public use | by the owner on 2026-10-08 (#1133, #1137, #1139) |

## Editing

Waiting time is cut and typing is sped up (2–4×); still frames hold replies long enough to read. Each segment shows a 720-pixel window of the screen that holds the conversation, which drops the on-screen keyboard and empty space; the window positions are in the manifest. A 1.5-second title card opens the loop and doubles as the still preview; a numbered badge (1–3) over the status bar marks each scene. Subtitles summarise or translate the matching on-screen message; they are not a word-for-word transcript. [manifest.json](manifest.json) lists every segment with its source time, speed and the subtitle text in each language.

Personal details are blurred frame by frame. Apple Vision OCR located the text boxes of sign-in links (tunnel host and one-time code), the home neighbourhood and an apartment-complex link, and each box was blurred, including in the neighbouring frames. Afterwards every distinct phone frame was OCR-checked again for those patterns; there were zero matches.

## Evidence class

The demo is edited from real sessions. The screens show what the PA replied; they are not an independent trace of the account or tool calls, and the recording names no application revision or model. It is not a repeatability check of a published release. See [product status](../../../product-status.en.md) for the evidence behind each area.
