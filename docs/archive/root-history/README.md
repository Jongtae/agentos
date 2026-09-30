# Historical root artifacts

These files used to sit at the repository root. They record early prototypes and acceptance runs, and they do not describe the current product. They were moved here by OSS-READY-01 [#878](https://github.com/Jongtae/agentos/issues/878) so the root shows what is current. Their content is unchanged except for relative links.

| File | What it records |
|---|---|
| [PLAN.md](PLAN.md) | Execution plan of the early Kubernetes-based prototype |
| [KUBERNETES_ARCHITECTURE.ko.md](KUBERNETES_ARCHITECTURE.ko.md) | Draft Kubernetes architecture for that prototype (2026-09-05) |
| [E2E_RESULT.json](E2E_RESULT.json) | Acceptance result of that prototype, written by `scripts/legacy/kubernetes/e2e.py` |
| [QUICKSTART_PLAN.md](QUICKSTART_PLAN.md) | The first self-hosted quickstart slice |
| [TOOL_ACCEPTANCE.md](TOOL_ACCEPTANCE.md) | Native tool-calling acceptance for the weather tool |
| [WEATHER_ACCEPTANCE_RESULT.json](WEATHER_ACCEPTANCE_RESULT.json) | Live weather acceptance result, written by `scripts/verify_weather_acceptance.py` |
| [GENERAL_AGENT_PLAN.md](GENERAL_AGENT_PLAN.md), [GENERAL_AGENT_VERIFICATION.md](GENERAL_AGENT_VERIFICATION.md) | AgentOS 0.2 general personal-agent runtime plan and verification |
| [GENERAL_AGENT_ACCEPTANCE.json](GENERAL_AGENT_ACCEPTANCE.json), [GENERAL_AGENT_ROUTER_ACCEPTANCE.json](GENERAL_AGENT_ROUTER_ACCEPTANCE.json) | Acceptance results of that runtime |

For the current product, start at the [README](../../../README.md). For the current plan, see [`delivery-plan.yaml`](../../../delivery-plan.yaml) and the [roadmap](../../roadmap.md).
