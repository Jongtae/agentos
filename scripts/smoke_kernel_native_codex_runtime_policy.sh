#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

rg -q "kernel-native Codex CLI runtime" AGENTS.md
rg -q "primary managed runtime of AgentOS" PRD.md
rg -q "no new phase should be opened for shell resemblance only" TASKS.md
rg -q "anti-drift rule" .codex/context.md
rg -q 'primary_goal = "kernel_native_codex_cli_runtime"' .codex/config.toml
rg -q "codex-runtime-agent" .agents/registry.md
rg -q "Codex CLI must become the primary managed runtime" .agents/codex-runtime-agent.md
rg -q "# Kernel-Native Codex Runtime MVP Policy v1" docs/reference/kernel-native-codex-runtime-mvp-policy-v1.md
