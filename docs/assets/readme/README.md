# Public README visuals

The public READMEs introduce the desired personal-assistant relationship, owner control, the structure that makes continuity possible, a short representative conversation, and a first trial. [The documentation map](../../README.md) remains the documentation authority map.

## Current introduction

`presence-overview.{en,ko,ja,zh-CN}.svg` is the illustrated overview used by the four READMEs. Three example cards show answering a question, carrying out an explicit command and continuing a personal conversation. An Owner/PA/AgentOS architecture and a short coffee conversation over time connect that experience to owner-held context, work, authority and evidence above replaceable AI/tools. Original vector icons and dialogue cards carry the explanation; detailed ontology definitions remain in the linked documents.

The visual follows the composition of the owner-provided NVIDIA/Amazon/continuing-conversation reference. It does not reproduce a messaging application, market price or completed purchase. All depicted interactions are illustrative product direction, not observed runs or shipped-integration claims.

Each locale has a `.narrow.svg` composition selected by the README's `<picture>` at viewport widths of 600 pixels or less. Desktop and narrow versions carry the same meanings. Desktop canvases are 1120 pixels wide and narrow canvases are 420 pixels wide; their heights follow the localized content instead of squeezing text into a fixed panel. These are architecture illustrations, not operating evidence. There are no external fonts, images or scripts.

## Supporting and historical figures

- `interaction-model.*.svg`, `presence.*.svg` and `continuing-conversation.*.svg` preserve the earlier, more detailed concept figures. Their NASDAQ/Amazon examples and reconstructed conversations remain illustrative product direction, not shipped integrations or observed runs. They are no longer the public README's required layout.
- `hero.*.html` / `hero.*.png` and `scenes.*.html` / `scenes.*.png` reconstruct condensed v1 synthetic journeys. [English product status](../../product-status.en.md#published-release-journey-illustrations) and [Korean product status](../../product-status.ko.md#공개-배포본의-여정-설명) retain those examples with their evidence boundaries and release limits. These are not live-account screenshots. Their source is [build_readme_visuals.py](../../../scripts/build_readme_visuals.py).

## Editing and visual verification

[build_concept_visuals.py](build_concept_visuals.py) is the standard-library source for the eight current overview SVGs and 24 preserved concept SVGs. Run `python3 docs/assets/readme/build_concept_visuals.py` after editing content or layout. Keep the same relationships and evidence boundaries across locales and screen sizes. Do not squeeze glyphs with `textLength` or `spacingAndGlyphs`.

1. Read the whole README as a newcomer: desired relationship → why owner control matters → how continuity works → first trial → references/licence. Diagrams should shorten the explanation.
2. Run `python3 scripts/verify_readme_localization.py` and check local links. This protects semantic parity, localized assets and factual boundaries without requiring the old screenshot sections.
3. Inspect text against the viewport, cards and other text under sans-serif and serif fallback. Check native GitHub desktop width, 375px and 320px in all four locales. Verify image decoding, selected `currentSrc`, alt text and legibility, then read the entire page in order.
4. Keep representative interaction explicitly illustrative. Published-release evidence, current-main fixture checks, owner-pilot observations and product direction remain distinct in the linked status documentation.

Browser captures and layout measurements establish documentation rendering only. They do not establish live AgentOS behavior.
