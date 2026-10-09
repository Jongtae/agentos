# Security policy

## Reporting a vulnerability

Please report vulnerabilities **privately** through GitHub: open the repository's **Security** tab and choose **Report a vulnerability** ([direct link](https://github.com/Jongtae/agentos/security/advisories/new)). Do not open a public issue, pull request or discussion for a suspected vulnerability.

A useful report includes the affected version or commit, what an attacker can do, and the steps to reproduce it. Personal AgentOS is maintained by one person, so there is no guaranteed response time. Reports are acknowledged and handled as quickly as that allows, and fixes are credited in the advisory unless you ask otherwise.

## Supported versions

| Version | Supported |
|---|---|
| `main` | Yes |
| Latest Homebrew release (currently 1.1.x) | Yes |
| Older releases | No. Please upgrade |

## What is in scope

Personal AgentOS runs on the owner's own machine and keeps their state there. These are security bugs:

- a secret (model key, OAuth token, Telegram bot token, saved login) reaching a model prompt, a log, Evidence or an export;
- a payment or other consequential action happening without the owner's per-action approval;
- a read outside the folders the owner granted, or a write outside the owner's workspace;
- someone other than the paired owner controlling the assistant through Telegram or the local web app;
- installing, updating or enabling a package or connector granting authority the owner did not give;
- memory the owner deleted still being returned or exported.

## Current posture (pilot)

The project is in a single-owner pilot: one owner, on their own machine, with their own accounts. By the owner's decision, some protections are deliberately deferred to a later hardening program rather than missing by accident. [`AGENTS.md`](../AGENTS.md) (*Secretary agency re-plan*) records these decisions. In particular:

- the assistant may use the owner's private material and web search in the same task. Each task instead records which owner information it used and where that information went;
- a check on private values leaving to new destinations, and further isolation, are deferred ([#828](https://github.com/Jongtae/agentos/issues/828)).

Reports about these deferred areas are still welcome, and they inform the hardening program. They are not treated as regressions of an enforced guarantee.

The canonical boundaries are in the [Owner Control Contract](../docs/owner-control-contract.en.md), the [Secretary Agency Contract](../docs/secretary-agency-contract.en.md) and [Personal AgentOS Architecture](../docs/personal-agentos-architecture.en.md).
