package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestWorkflowStatusParsing(t *testing.T) {
	raw := []byte(`{
		"workspace":"/tmp/ws",
		"runtime_entry_mode":"tty",
		"operator_visible_state":"ready",
		"guided_operator_surface_reachable":true,
		"runtime_secret_readiness":{
			"telegram_token_configured":true,
			"telegram_allowed_chat_configured":true,
			"telegram_live_send_ready":true,
			"telegram_secret_source":"runtime_env"
		},
		"summary":{"workflow_status_ready":true,"telegram_reply_sent":false}
	}`)
	var status workflowStatus
	if err := json.Unmarshal(raw, &status); err != nil {
		t.Fatal(err)
	}
	if !status.GuidedOperatorReachable {
		t.Fatal("expected guided operator reachable")
	}
	if !status.RuntimeSecretReadiness.TelegramLiveSendReady {
		t.Fatal("expected telegram live send readiness")
	}
}

func TestDispatchRoutesCommands(t *testing.T) {
	m := newModel("/tmp/ws", "agentos-kernelctl")
	if cmd := m.dispatch("/help"); cmd != nil {
		t.Fatal("help should be handled synchronously")
	}
	if !strings.Contains(strings.Join(m.logs, "\n"), "/setup telegram") {
		t.Fatal("expected help text in log")
	}
	if cmd := m.dispatch("/clear"); cmd != nil {
		t.Fatal("clear should be handled synchronously")
	}
	if len(m.logs) != 0 {
		t.Fatal("expected logs to be cleared")
	}
	if cmd := m.dispatch("/status"); cmd == nil {
		t.Fatal("status should return a command")
	}
	if cmd := m.dispatch("/power"); cmd != nil {
		t.Fatal("power should be handled synchronously")
	}
	if !strings.Contains(strings.Join(m.logs, "\n"), "systemctl reboot") {
		t.Fatal("expected lifecycle commands in log")
	}
	if cmd := m.dispatch("/setup llm"); cmd == nil {
		t.Fatal("llm setup should return a command")
	}
	if cmd := m.dispatch("setup llm"); cmd == nil {
		t.Fatal("slashless llm setup should return a command")
	}
	if cmd := m.dispatch("/engine ollama"); cmd == nil {
		t.Fatal("engine selection should return a command")
	}
	if cmd := m.dispatch("% echo ok"); cmd == nil {
		t.Fatal("shell escape should return a command")
	}
	if cmd := m.dispatch("hello agentos"); cmd == nil {
		t.Fatal("normal ask should return a command")
	}
	if cmd := m.dispatch("hi"); cmd != nil {
		t.Fatal("greeting should be handled locally")
	}
	if !strings.Contains(strings.Join(m.logs, "\n"), "AgentOS is online") {
		t.Fatal("expected local greeting response")
	}
}

func TestModeSwitchingChangesDefaultDispatch(t *testing.T) {
	m := newModel("/tmp/ws", "agentos-kernelctl")
	if m.mode != "agent" {
		t.Fatalf("expected agent mode, got %s", m.mode)
	}
	if cmd := m.dispatch("/mode shell"); cmd != nil {
		t.Fatal("mode switch should be synchronous")
	}
	if m.mode != "shell" {
		t.Fatalf("expected shell mode, got %s", m.mode)
	}
	if m.prompt() != "Linux % " {
		t.Fatalf("unexpected shell prompt: %q", m.prompt())
	}
	if cmd := m.dispatch("echo shell-ok"); cmd == nil {
		t.Fatal("plain input in shell mode should run a shell command")
	}
	if cmd := m.dispatch("/mode agent"); cmd != nil {
		t.Fatal("mode switch should be synchronous")
	}
	if m.mode != "agent" {
		t.Fatalf("expected agent mode, got %s", m.mode)
	}
	if m.prompt() != "Agent > " {
		t.Fatalf("unexpected agent prompt: %q", m.prompt())
	}
}

func TestRunJSONExtractsLastJSON(t *testing.T) {
	dir := t.TempDir()
	fake := filepath.Join(dir, "agentos-kernelctl")
	if err := os.WriteFile(fake, []byte(`#!/bin/sh
printf 'Policy warning before JSON\n'
printf '{"ok":true,"response":"hello"}\n'
`), 0o755); err != nil {
		t.Fatal(err)
	}
	out, err := runJSON(fake, "ask", "--json")
	if err != nil {
		t.Fatal(err)
	}
	var data map[string]any
	if err := json.Unmarshal(out, &data); err != nil {
		t.Fatal(err)
	}
	if data["ok"] != true {
		t.Fatalf("unexpected payload: %s", string(out))
	}
}

func TestNormalizeSlashlessCommands(t *testing.T) {
	cases := map[string]string{
		"setup llm":       "/setup llm",
		"setup telegram":  "/setup telegram",
		"telegram status": "/telegram status",
		"status":          "/status",
		"mode shell":      "/mode shell",
	}
	for input, want := range cases {
		if got := normalizeCommand(input); got != want {
			t.Fatalf("normalizeCommand(%q)=%q, want %q", input, got, want)
		}
	}
}

func TestSummarizeSetupPageIncludesURL(t *testing.T) {
	text := summarizeJSON([]byte(`{
		"setup_page_started":true,
		"setup_page_background":true,
		"setup_page_already_running":true,
		"setup_page_url":"http://127.0.0.1:8787/setup",
		"operator_action_required":"open_setup_page"
	}`))
	if !strings.Contains(text, "http://127.0.0.1:8787/setup") {
		t.Fatalf("expected setup URL in summary: %s", text)
	}
	if !strings.Contains(text, "Already running") {
		t.Fatalf("expected idempotent reuse note: %s", text)
	}
}

func TestSelfTestWithFakeKernelctl(t *testing.T) {
	dir := t.TempDir()
	fake := filepath.Join(dir, "agentos-kernelctl")
	if err := os.WriteFile(fake, []byte(`#!/bin/sh
set -eu
case "$1" in
  workflow-status)
    printf '{"workspace":"/tmp/ws","operator_visible_state":"ready","guided_operator_surface_reachable":true,"runtime_secret_readiness":{"telegram_live_send_ready":false},"summary":{"workflow_status_ready":true}}\n'
    ;;
  *)
    printf '{"ok":true}\n'
    ;;
esac
`), 0o755); err != nil {
		t.Fatal(err)
	}
	status, err := readWorkflowStatus(fake, "/tmp/ws")
	if err != nil {
		t.Fatal(err)
	}
	if status.Workspace != "/tmp/ws" {
		t.Fatalf("unexpected workspace: %s", status.Workspace)
	}
}
