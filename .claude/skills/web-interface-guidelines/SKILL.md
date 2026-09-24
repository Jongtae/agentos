---
name: web-interface-guidelines
description: Review AgentOS local web UI code (src/personal_agent/web/) against the pinned Vercel Web Interface Guidelines — forms, focus, accessibility, empty states, destructive actions, locale-aware dates, copy. Use when asked to review, audit or improve UI/UX, components, forms or Settings/작업 현황/내 기록 screens.
---

# Web Interface Guidelines (pinned)

The rules are in [upstream-command.md](upstream-command.md), a verbatim copy of
`vercel-labs/web-interface-guidelines` at commit
`e3d624baaf29dc1fc645aff3e38f03e564d2d6b1` (MIT, see [LICENSE](LICENSE)).
Use that local copy. Do not fetch the upstream `main` branch; updates arrive only
through a reviewed repository PR. Provenance: [../README.md](../README.md).

## How to review

1. Read `AGENTS.md`, `src/personal_agent/web/AGENTS.md` and the Settings section of
   `docs/presence-experience-contract.en.md` first. They win over any rule here.
2. Read the files the user named (default: `src/personal_agent/web/index.html`,
   `app.js`, `style.css`).
3. Apply every rule in `upstream-command.md` except the ones listed below.
4. Report findings in its `file:line` format. Because `app.js` and `style.css` are
   single long lines, also name the element id, class or function.

## Rules that do not apply here

This UI is vanilla HTML/CSS/JS with Korean owner-facing copy.

- React/Next/Tailwind syntax (`htmlFor`, `spellCheck={false}`, `focus-visible:ring-*`,
  `min-w-0`, `nuqs`, `priority`): apply the underlying intent with plain HTML/CSS.
- **Hydration Safety**: not applicable (no server rendering of the UI).
- **Content & Copy — Title Case, curly quotes, `&` over "and"**: English-only; keep
  Korean sentence style. Active voice, specific button labels and actionable errors
  still apply.
- **Navigation & State — URL reflects state**: only where it does not expose private
  owner content in the URL.
