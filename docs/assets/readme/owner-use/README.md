# Recorded owner use

These GIFs are edited from the owner-supplied `PA Use Case Video.mp4`, selected for the public README by the owner on 2026-10-08 in issue #1131. The accompanying [shared ChatGPT conversation](https://chatgpt.com/share/6ac6c134-163c-83ee-99b8-170bf9d539cb) guided the four-scene order and the matching translated dialogue excerpts. These are owner-pilot screen recordings, separate from the reconstructed conversation images and concept figures in the parent directory.

| Edition | File | Presentation |
| --- | --- | --- |
| Korean | [owner-use.ko.gif](owner-use.ko.gif) | Korean dialogue excerpts |
| English | [owner-use.en.gif](owner-use.en.gif) | Korean screen with matching English translations |
| Japanese | [owner-use.ja.gif](owner-use.ja.gif) | Korean screen with matching Japanese translations |
| Simplified Chinese | [owner-use.zh-CN.gif](owner-use.zh-CN.gif) | Korean screen with matching Chinese translations |

All editions are 960 × 810, 1,140 frames and 57 seconds, with a 50 ms frame delay (20fps) and continuous looping. The retained motion plays at its original speed, including the emoji-selection and reaction sequence. The completed Spam-result screen has a 3.15-second stable hold so its reply can be read. Scene cards and cuts shorten waiting periods; this is an edited reel, not an uncut transaction or a word-for-word transcript. Caption panels summarize or translate the matching excerpts. The phone screen remains the recording.

The public READMEs place each GIF in a closed-by-default native HTML disclosure. Opening it is the reader’s explicit choice to view motion; closing it hides the animation while leaving the four-scene text available. This uses the existing Markdown/HTML renderer and adds no player script or dependency. The GIF files themselves remain continuously looping assets.

## What the recording supports

1. **Dongtan conversation:** a friend meeting, departure point, a corrected GTX route suggestion and dinner preferences appear in the conversation.
2. **E-Mart / SSG inquiry:** the PA replies that the cart contains 22 items and no Spam. This reel shows that reply, not independent backend verification of those counts.
3. **One small can:** the owner asks for one small can because his wife would dislike buying too much; the PA reports one 200g can and a count change of 22 → 23. No payment is shown.
4. **Separate Kyobo session:** the book cart is visible and the PA lists four books, then discusses points/discounts and an unverified step. This is a separate account/session, not a continuation of the E-Mart cart.

The recording does not identify the application commit, release or model. It does not demonstrate an AI switch or release-specific repeatability. This documentation work performed no live account, cart, payment or model-provider operation. Historical fixture evidence keeps its original scope; see [product status](../../../product-status.en.md).

## Source and editing record

The original MP4 was inspected during the earlier conversion. At README preparation time it was no longer present at the supplied workspace path, and no original-source digest had been captured. The README reel therefore uses the preserved lossless continuous 20fps exports made during that conversion. This provenance limitation is recorded explicitly rather than assigning an unobserved source hash.

[manifest.json](manifest.json) records the continuous-export SHA-256 digests, selected cut intervals and final GIF SHA-256 digests, dimensions/timing and file sizes. Cut times refer to the continuous export, including its scene cards. All 1,140 frames of each final GIF were decoded to verify dimensions, looping and uniform frame delay. Representative frames were inspected for caption layout and the sign-in-link omission.

The phone message panel is covered during the E-Mart inquiry and Kyobo book-list excerpts because short-lived sign-in URL/code text scrolls through that area; the matching excerpt captions remain visible. The temporary browser address is covered during the visible Kyobo cart excerpt, while the cart contents remain visible. No wider privacy audit is claimed. The full earlier exports remain local and are not the public README assets.

## File layout

- `docs/assets/readme/owner-use/`: these four curated public GIFs and their provenance.
- `output/readme-media/2026-10-08/gif-exports/`: local full-length, scene-specific and earlier GIF versions, moved from the former root `PA GIF Animations/` directory. `output/` is already excluded from Git.
- `output/readme-media/2026-10-08/editing/`: preserved continuous MP4 masters and editing scripts for local reuse. Paths in those historical scripts reflect the original conversion locations; adjust them before rerunning.

The local archive is not a portable README dependency. Public README links point only to the tracked assets in this directory. No runtime package, provider integration or AgentOS capability was added by this content update.
