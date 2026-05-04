package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/textinput"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

type workflowStatus struct {
	Workspace               string `json:"workspace"`
	RuntimeEntryMode        string `json:"runtime_entry_mode"`
	OperatorVisibleState    string `json:"operator_visible_state"`
	GuidedOperatorReachable bool   `json:"guided_operator_surface_reachable"`
	RuntimeSecretReadiness  struct {
		TelegramTokenConfigured       bool   `json:"telegram_token_configured"`
		TelegramAllowedChatConfigured bool   `json:"telegram_allowed_chat_configured"`
		TelegramLiveSendReady         bool   `json:"telegram_live_send_ready"`
		TelegramSecretSource          string `json:"telegram_secret_source"`
	} `json:"runtime_secret_readiness"`
	Summary struct {
		WorkflowStatusReady       bool `json:"workflow_status_ready"`
		TelegramLiveSearchSuccess bool `json:"telegram_live_search_success"`
		TelegramReplySent         bool `json:"telegram_reply_sent"`
		ExternalSecretBlocked     bool `json:"external_secret_blocked"`
	} `json:"summary"`
	TopTasks []struct {
		ID      string `json:"id"`
		Label   string `json:"label"`
		Ready   bool   `json:"ready"`
		Surface string `json:"surface"`
	} `json:"top_tasks"`
	Workflows []struct {
		WorkflowID    string `json:"workflow_id"`
		Label         string `json:"label"`
		WorkflowReady bool   `json:"workflow_ready"`
	} `json:"workflows"`
}

type llmSetupStatus struct {
	Provider            string `json:"provider"`
	SelectedModel       string `json:"selected_model"`
	OpenAIKeyConfigured bool   `json:"openai_key_configured"`
	ProviderReady       bool   `json:"provider_ready"`
	FailureClass        string `json:"failure_class"`
	Summary             struct {
		Provider      string `json:"provider"`
		SelectedModel string `json:"selected_model"`
	} `json:"summary"`
}

type askResponse struct {
	OK           bool   `json:"ok"`
	Message      string `json:"message"`
	Response     string `json:"response"`
	Provider     string `json:"provider"`
	Model        string `json:"model"`
	Workspace    string `json:"workspace"`
	FailureClass string `json:"failure_class"`
}

type activityFeed struct {
	Events []struct {
		Time         string `json:"time"`
		Kind         string `json:"kind"`
		Label        string `json:"label"`
		HumanMessage string `json:"human_message"`
		Intent       string `json:"intent"`
		Capability   string `json:"capability"`
		RequestID    string `json:"request_id"`
	} `json:"events"`
}

type commandResult struct {
	label string
	text  string
	err   error
}

type statusBundle struct {
	workflow workflowStatus
	llm      llmSetupStatus
	activity activityFeed
	err      error
}

type tickMsg time.Time

type model struct {
	kernelctl string
	workspace string
	input     textinput.Model
	viewport  viewport.Model
	width     int
	height    int
	mode      string
	status    workflowStatus
	llm       llmSetupStatus
	statusErr string
	working   bool
	logs      []string
	logPath   string
	seenActivity map[string]bool
}

var (
	headerStyle = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("120")).Background(lipgloss.Color("22")).Padding(0, 1)
	subtleStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("245"))
	okStyle     = lipgloss.NewStyle().Foreground(lipgloss.Color("120")).Bold(true)
	warnStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color("214")).Bold(true)
	errStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("203")).Bold(true)
	boxStyle    = lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("238")).Padding(0, 1)
)

func main() {
	workspace := flag.String("workspace", defaultWorkspace(), "AgentOS workspace")
	kernelctl := flag.String("kernelctl", defaultKernelctl(), "agentos-kernelctl path")
	selfTest := flag.Bool("self-test", false, "run a non-interactive startup/render test")
	noAlt := flag.Bool("no-alt-screen", false, "disable alternate screen")
	flag.Parse()

	m := newModel(*workspace, *kernelctl)
	if *selfTest {
		status, err := readWorkflowStatus(*kernelctl, *workspace)
		if err != nil {
			fmt.Fprintf(os.Stderr, "self-test workflow-status failed: %v\n", err)
			os.Exit(1)
		}
		m.status = status
		m.width = 96
		m.height = 28
		m.appendLog("AgentOS", "self-test render")
		fmt.Print(m.View())
		return
	}

	opts := []tea.ProgramOption{tea.WithMouseCellMotion()}
	if !*noAlt {
		opts = append(opts, tea.WithAltScreen())
	}
	if _, err := tea.NewProgram(m, opts...).Run(); err != nil {
		fmt.Fprintf(os.Stderr, "agentos-operator-tui failed: %v\n", err)
		os.Exit(1)
	}
}

func newModel(workspace, kernelctl string) model {
	input := textinput.New()
	input.Placeholder = "Ask AgentOS, /mode shell, /setup llm, /setup telegram, /status, or /help"
	input.Prompt = "Agent > "
	input.Focus()
	input.CharLimit = 2048
	input.Width = 80
	vp := viewport.New(80, 20)
	return model{
		kernelctl: kernelctl,
		workspace: workspace,
		input:     input,
		viewport:  vp,
		mode:      "agent",
		logPath:   filepath.Join(workspace, "artifacts", "operator", "agentos-operator-session.log"),
		logs: []string{
			"Welcome to AgentOS. You are in Agent mode.",
			"Talk normally here. Switch to Linux with /mode shell, or run one command with % <command>.",
			"First setup shortcuts: /setup llm, /setup telegram, /status",
		},
		seenActivity: map[string]bool{},
	}
}

func (m model) Init() tea.Cmd {
	return tea.Batch(refreshCmd(m.kernelctl, m.workspace), tickCmd())
}

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmds []tea.Cmd
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		m.resize()
	case tickMsg:
		cmds = append(cmds, refreshCmd(m.kernelctl, m.workspace), tickCmd())
	case statusBundle:
		telegramWasReady := m.telegramReady()
		if msg.err != nil {
			m.statusErr = msg.err.Error()
		} else {
			m.status = msg.workflow
			m.llm = msg.llm
			m.statusErr = ""
			if !telegramWasReady && m.telegramReady() {
				m.appendLog("Telegram", "Connected. The background Telegram receiver will pick up new bot messages automatically. Use /telegram status for the latest proof.")
			}
			m.appendActivity(msg.activity)
		}
	case commandResult:
		m.working = false
		if msg.err != nil {
			m.appendLog(msg.label, errStyle.Render(msg.err.Error()))
		} else {
			m.appendLog(msg.label, msg.text)
		}
	case error:
		m.statusErr = msg.Error()
	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c":
			return m, tea.Quit
		case "pgup":
			m.viewport.LineUp(max(1, m.viewport.Height-2))
			return m, nil
		case "pgdown":
			m.viewport.LineDown(max(1, m.viewport.Height-2))
			return m, nil
		case "ctrl+u":
			m.viewport.LineUp(8)
			return m, nil
		case "ctrl+d":
			m.viewport.LineDown(8)
			return m, nil
		case "home":
			m.viewport.GotoTop()
			return m, nil
		case "end":
			m.viewport.GotoBottom()
			return m, nil
		case "tab":
			m.toggleMode()
		case "enter":
			line := strings.TrimSpace(m.input.Value())
			m.input.Reset()
			cmd := m.dispatch(line)
			if cmd != nil {
				cmds = append(cmds, cmd)
			}
		}
	}
	var cmd tea.Cmd
	m.input, cmd = m.input.Update(msg)
	cmds = append(cmds, cmd)
	m.viewport.SetContent(strings.Join(m.logs, "\n\n"))
	return m, tea.Batch(cmds...)
}

func (m model) View() string {
	if m.width == 0 {
		m.width = 100
	}
	if m.height == 0 {
		m.height = 30
	}
	header := headerStyle.Width(m.width - 2).Render("AgentOS — AI-Native OS")
	status := m.statusLine()
	actions := boxStyle.Width(m.width - 4).Render(m.actionLine())
	bodyHeight := m.height - lipgloss.Height(header) - lipgloss.Height(status) - lipgloss.Height(actions) - 4
	if bodyHeight < 5 {
		bodyHeight = 5
	}
	vp := m.viewport
	vp.Width = m.width - 2
	vp.Height = bodyHeight
	vp.SetContent(strings.Join(m.logs, "\n\n"))
	inputModel := m.input
	inputModel.Prompt = m.prompt()
	input := boxStyle.Width(m.width - 4).Render(m.input.View())
	input = boxStyle.Width(m.width - 4).Render(inputModel.View())
	return lipgloss.JoinVertical(lipgloss.Left, header, status, actions, vp.View(), input)
}

func (m *model) resize() {
	m.input.Width = max(20, m.width-20)
	m.viewport.Width = max(20, m.width-2)
	m.viewport.Height = max(5, m.height-8)
}

func (m model) statusLine() string {
	llmLabel := "LLM loading"
	if m.llm.Provider != "" {
		model := m.llm.SelectedModel
		if model == "" {
			model = m.llm.Summary.SelectedModel
		}
		llmLabel = fmt.Sprintf("LLM: %s/%s", m.llm.Provider, model)
	}
	llm := okStyle.Render(llmLabel)
	if m.llm.ProviderReady == false && m.llm.Provider != "" {
		llm = warnStyle.Render(llmLabel)
	}
	if !m.status.GuidedOperatorReachable && m.status.Workspace == "" && m.llm.Provider == "" {
		llm = warnStyle.Render("status loading")
	}
	telegram := warnStyle.Render("Telegram setup needed")
	if m.status.RuntimeSecretReadiness.TelegramLiveSendReady {
		telegram = okStyle.Render("Telegram ready")
	} else if m.status.RuntimeSecretReadiness.TelegramTokenConfigured {
		telegram = warnStyle.Render("Telegram token set")
	}
	web := okStyle.Render("Web ready")
	workspace := m.workspace
	if m.status.Workspace != "" {
		workspace = m.status.Workspace
	}
	ip := localIP()
	state := m.status.OperatorVisibleState
	if state == "" {
		state = "operator"
	}
	if m.statusErr != "" {
		state = errStyle.Render("status error")
	}
	mode := "Mode: " + strings.ToUpper(m.mode)
	parts := []string{mode, llm, telegram, web, "Workspace: " + shortPath(workspace), "IP: " + ip, "State: " + state}
	if m.working {
		parts = append(parts, warnStyle.Render("working"))
	}
	return subtleStyle.Width(m.width - 2).Render(strings.Join(parts, "  |  "))
}

func (m model) telegramReady() bool {
	return m.status.RuntimeSecretReadiness.TelegramTokenConfigured &&
		m.status.RuntimeSecretReadiness.TelegramAllowedChatConfigured
}

func (m *model) dispatch(line string) tea.Cmd {
	if line == "" {
		return nil
	}
	line = normalizeCommand(line)
	switch {
	case line == "/help" || line == "help":
		m.appendLog("Help", "Modes:\n/mode agent  - talk to AgentOS normally\n/mode shell  - type Linux commands directly\n/mode setup  - focused setup shortcuts\n\nCore setup:\n/setup llm       open the LLM setup page and QR\n/engine ollama   force bundled local Ollama\n/engine codex    force OpenAI/Codex with gpt-4o-mini\n/engine guide    degraded guide mode only\n/setup telegram  open QR setup page\n/test telegram   manual drain/fallback receive-send check\n/status          human-readable runtime status\n/logs            show operator log path\n\nScrollback:\nPageUp/PageDown, Ctrl+U/Ctrl+D, Home/End\n\nLinux:\n% <command> runs one Linux command from any mode.\nIn Shell mode, plain input is a Linux command.\n\nLifecycle:\n/power shows reboot/shutdown/restart options.")
		return nil
	case line == "/mode agent" || line == "/agent":
		m.setMode("agent")
		return nil
	case line == "/mode shell" || line == "/shell":
		m.setMode("shell")
		return nil
	case line == "/mode setup" || line == "/setup":
		m.setMode("setup")
		return nil
	case line == "/power":
		m.appendLog("Power", "Lifecycle commands are explicit for safety:\n/restart agentos  - restart AgentOS user-facing services\n/reboot           - reboot the VM\n/shutdown         - power off the VM\n\nLinux equivalents:\n% sudo systemctl reboot\n% sudo systemctl poweroff\n\nAgentOS should return to this operator shell after reboot.")
		return nil
	case line == "/restart agentos":
		m.working = true
		m.appendLog("Power", "Restarting AgentOS services...")
		return runShellCmd("sudo systemctl restart agentos-telegram-webhookd.service agentos-ollama.service || true", m.workspace)
	case line == "/reboot":
		m.appendLog("Power", "Reboot is available as a Linux command for now: % sudo systemctl reboot")
		return nil
	case line == "/shutdown":
		m.appendLog("Power", "Shutdown is available as a Linux command for now: % sudo systemctl poweroff")
		return nil
	case line == "/clear":
		m.logs = nil
		m.viewport.SetContent("")
		return nil
	case line == "/quit" || line == "quit" || line == "exit":
		return tea.Quit
	case line == "/status":
		m.appendLog("Operator", "Refreshing status...")
		m.working = true
		return statusSummaryCmd(m.kernelctl, m.workspace)
	case line == "/logs":
		m.appendLog("Logs", "Operator session log:\n"+m.logPath+"\nActivity event log:\n"+filepath.Join(m.workspace, "artifacts", "os_events.jsonl"))
		return nil
	case line == "/setup llm" || line == "/llm":
		m.working = true
		m.appendLog("LLM setup", "Starting LLM setup page. Scan the QR or open the URL to choose bundled Ollama or OpenAI/Codex gpt-4o-mini.")
		return runKernelctlCmd("LLM setup", m.kernelctl, "llm-setup", "--workspace", m.workspace, "--serve-http", "--background", "--host", "0.0.0.0", "--display-host", localIP(), "--json")
	case line == "/engine ollama":
		m.working = true
		m.appendLog("LLM setup", "Selecting bundled local Ollama engine...")
		return runKernelctlCmd("LLM setup", m.kernelctl, "llm-setup", "--workspace", m.workspace, "--set-provider", "ollama", "--json")
	case line == "/engine codex":
		m.working = true
		m.appendLog("LLM setup", "Selecting Codex/OpenAI engine with gpt-4o-mini. Add the API key through /setup llm if needed.")
		return runKernelctlCmd("LLM setup", m.kernelctl, "llm-setup", "--workspace", m.workspace, "--set-provider", "codex", "--json")
	case line == "/engine guide" || line == "/engine none":
		m.working = true
		m.appendLog("LLM setup", "Switching to degraded guide mode. This is a fallback, not the normal runtime path.")
		return runKernelctlCmd("LLM setup", m.kernelctl, "llm-setup", "--workspace", m.workspace, "--set-provider", "none", "--json")
	case line == "/setup telegram":
		m.working = true
		m.appendLog("Operator", "Starting Telegram setup page. Open the QR/URL, paste your bot token once, then send /start to your bot. AgentOS will update this screen when setup is ready.")
		return runKernelctlCmd("Telegram setup", m.kernelctl, "telegram-setup", "--workspace", m.workspace, "--serve-http", "--background", "--host", "0.0.0.0", "--display-host", localIP(), "--json")
	case line == "/test telegram":
		m.working = true
		m.appendLog("Operator", "Running one manual Telegram receive/send check. Webhook is the product path; this is only a polling fallback/manual drain.")
		return runKernelctlCmd("Telegram live loop", m.kernelctl, "telegram-live-loop", "--workspace", m.workspace, "--once", "--send", "--json")
	case line == "/telegram status":
		m.working = true
		m.appendLog("Telegram", "Checking Telegram webhook/status surfaces...")
		return runKernelctlCmd("Telegram status", m.kernelctl, "telegram-status", "--workspace", m.workspace, "--json")
	case strings.HasPrefix(line, "%"):
		m.working = true
		m.appendLog("Linux", "$ "+strings.TrimSpace(line[1:]))
		return runShellCmd(strings.TrimSpace(line[1:]), m.workspace)
	case m.mode == "shell":
		m.working = true
		m.appendLog("Linux", "$ "+line)
		return runShellCmd(line, m.workspace)
	case m.mode == "setup":
		m.appendLog("Setup", "Use /setup llm, /engine ollama, /setup telegram, /status, or /mode agent. Plain conversation is available in Agent mode.")
		return nil
	case isGreeting(line):
		m.appendLog("You", line)
		m.appendLog("AgentOS", "Hi. AgentOS is online. Try: search AgentOS roadmap and summarize it, or run /status.")
		return nil
	default:
		m.working = true
		m.appendLog("You", line)
		return intentDispatchCmd(m.kernelctl, m.workspace, line)
	}
}

func (m *model) setMode(mode string) {
	if mode != "agent" && mode != "shell" && mode != "setup" {
		return
	}
	m.mode = mode
	m.input.Prompt = m.prompt()
	switch mode {
	case "agent":
		m.input.Placeholder = "Ask AgentOS, or switch with /mode shell"
		m.appendLog("Operator", "Agent mode: plain input talks to AgentOS. Use % <command> for one Linux command.")
	case "shell":
		m.input.Placeholder = "Type Linux commands directly, or /mode agent"
		m.appendLog("Operator", "Shell mode: plain input runs Linux commands. Use /mode agent to return to AgentOS.")
	case "setup":
		m.input.Placeholder = "/setup llm, /engine ollama, /setup telegram, /status"
		m.appendLog("Operator", "Setup mode: use /setup llm, /engine ollama, /setup telegram, or /mode agent.")
	}
}

func (m *model) toggleMode() {
	if m.mode == "agent" {
		m.setMode("shell")
		return
	}
	m.setMode("agent")
}

func (m model) prompt() string {
	switch m.mode {
	case "shell":
		return "Linux % "
	case "setup":
		return "Setup > "
	default:
		return "Agent > "
	}
}

func (m model) actionLine() string {
	return "Actions: /mode agent  /mode shell  /setup llm  /engine ollama  /setup telegram  /test telegram  /power  /clear"
}

func (m *model) appendLog(label, text string) {
	if strings.TrimSpace(text) == "" {
		text = "(no output)"
	}
	m.logs = append(m.logs, okStyle.Render(label)+":\n"+strings.TrimSpace(text))
	if len(m.logs) > 80 {
		m.logs = m.logs[len(m.logs)-80:]
	}
	m.viewport.SetContent(strings.Join(m.logs, "\n\n"))
	m.viewport.GotoBottom()
	if m.logPath != "" {
		_ = os.MkdirAll(filepath.Dir(m.logPath), 0o755)
		handle, err := os.OpenFile(m.logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
		if err == nil {
			defer handle.Close()
			_, _ = fmt.Fprintf(handle, "[%s] %s:\n%s\n\n", time.Now().Format(time.RFC3339), label, strings.TrimSpace(text))
		}
	}
}

func (m *model) appendActivity(feed activityFeed) {
	for _, event := range feed.Events {
		key := event.Time + "|" + event.Kind + "|" + event.RequestID + "|" + event.HumanMessage
		if key == "|||" || m.seenActivity[key] {
			continue
		}
		m.seenActivity[key] = true
		label := event.Label
		if label == "" {
			label = "Activity"
		}
		prefix := ""
		if event.Time != "" {
			prefix = event.Time + " "
		}
		m.appendLog(label, prefix+event.HumanMessage)
	}
}

func refreshCmd(kernelctl, workspace string) tea.Cmd {
	return func() tea.Msg {
		status, err := readWorkflowStatus(kernelctl, workspace)
		llm, llmErr := readLLMStatus(kernelctl, workspace)
		activity, activityErr := readActivityFeed(kernelctl, workspace)
		if err != nil {
			return statusBundle{workflow: status, llm: llm, activity: activity, err: err}
		}
		if llmErr != nil {
			return statusBundle{workflow: status, llm: llm, activity: activity, err: llmErr}
		}
		if activityErr != nil {
			return statusBundle{workflow: status, llm: llm, activity: activity, err: activityErr}
		}
		return statusBundle{workflow: status, llm: llm, activity: activity}
	}
}

func statusSummaryCmd(kernelctl, workspace string) tea.Cmd {
	return func() tea.Msg {
		workflow, workflowErr := readWorkflowStatus(kernelctl, workspace)
		llm, llmErr := readLLMStatus(kernelctl, workspace)
		activity, activityErr := readActivityFeed(kernelctl, workspace)
		lines := []string{}
		if llmErr == nil {
			model := llm.SelectedModel
			if model == "" {
				model = llm.Summary.SelectedModel
			}
			lines = append(lines, fmt.Sprintf("LLM: %s / %s", llm.Provider, model))
			lines = append(lines, fmt.Sprintf("LLM ready: %v", llm.ProviderReady))
			lines = append(lines, fmt.Sprintf("OpenAI key configured: %v", llm.OpenAIKeyConfigured))
		} else {
			lines = append(lines, "LLM: status unavailable")
		}
		if workflowErr == nil {
			telegram := "setup needed"
			if workflow.RuntimeSecretReadiness.TelegramLiveSendReady {
				telegram = "webhook/live ready"
			} else if workflow.RuntimeSecretReadiness.TelegramTokenConfigured {
				telegram = "token configured; chat/setup may be pending"
			}
			lines = append(lines, "Telegram: "+telegram)
			lines = append(lines, "Runtime: "+workflow.OperatorVisibleState)
			if workflow.Workspace != "" {
				lines = append(lines, "Workspace: "+workflow.Workspace)
			}
			lines = append(lines, "Manual Telegram drain: /test telegram (fallback only)")
		} else {
			lines = append(lines, "Workflow: status unavailable")
		}
		if workflowErr != nil && llmErr != nil {
			return commandResult{label: "Status", text: strings.Join(lines, "\n"), err: fmt.Errorf("status refresh failed. Run /logs for details.")}
		}
		if activityErr == nil && len(activity.Events) > 0 {
			lines = append(lines, "")
			lines = append(lines, "Recent activity:")
			start := len(activity.Events) - 5
			if start < 0 {
				start = 0
			}
			for _, event := range activity.Events[start:] {
				prefix := event.Time
				if prefix != "" {
					prefix += " "
				}
				lines = append(lines, prefix+event.Label+": "+event.HumanMessage)
			}
		}
		return commandResult{label: "Status", text: strings.Join(lines, "\n")}
	}
}

func tickCmd() tea.Cmd {
	return tea.Tick(5*time.Second, func(t time.Time) tea.Msg { return tickMsg(t) })
}

func readWorkflowStatus(kernelctl, workspace string) (workflowStatus, error) {
	var status workflowStatus
	out, err := runJSON(kernelctl, "workflow-status", "--workspace", workspace, "--json")
	if err != nil {
		return status, err
	}
	if err := json.Unmarshal(out, &status); err != nil {
		return status, fmt.Errorf("workflow-status JSON parse failed: %w", err)
	}
	return status, nil
}

func readLLMStatus(kernelctl, workspace string) (llmSetupStatus, error) {
	var status llmSetupStatus
	out, err := runJSON(kernelctl, "llm-setup", "--workspace", workspace, "--json")
	if err != nil {
		return status, err
	}
	if err := json.Unmarshal(out, &status); err != nil {
		return status, fmt.Errorf("llm setup status JSON parse failed")
	}
	return status, nil
}

func readActivityFeed(kernelctl, workspace string) (activityFeed, error) {
	var feed activityFeed
	out, err := runJSON(kernelctl, "activity-feed", "--workspace", workspace, "--limit", "12", "--json")
	if err != nil {
		return feed, err
	}
	if err := json.Unmarshal(out, &feed); err != nil {
		return feed, fmt.Errorf("activity feed JSON parse failed")
	}
	return feed, nil
}

func intentDispatchCmd(kernelctl, workspace, message string) tea.Cmd {
	return func() tea.Msg {
		out, err := runJSON(kernelctl, "intent-dispatch", "--workspace", workspace, "--source", "operator", "--message", message, "--json")
		if err != nil {
			return commandResult{label: "AgentOS", err: err}
		}
		var data map[string]any
		if err := json.Unmarshal(out, &data); err != nil {
			return commandResult{label: "AgentOS", err: fmt.Errorf("AgentOS command failed. Run /logs for raw output details.")}
		}
		proof, _ := data["proof"].(map[string]any)
		if ok, _ := proof["ok"].(bool); !ok {
			detail, _ := proof["reason"].(string)
			if detail == "" {
				detail = "intent_dispatch_failed"
			}
			return commandResult{label: "AgentOS", err: fmt.Errorf("AgentOS request failed: %s", detail)}
		}
		return commandResult{label: "AgentOS", text: summarizeJSON(out)}
	}
}

func runKernelctlCmd(label, kernelctl string, args ...string) tea.Cmd {
	return func() tea.Msg {
		out, err := runJSON(kernelctl, args...)
		if err != nil {
			return commandResult{label: label, err: err}
		}
		return commandResult{label: label, text: summarizeJSON(out)}
	}
}

func runShellCmd(command, workspace string) tea.Cmd {
	return func() tea.Msg {
		if command == "" {
			return commandResult{label: "Linux", err: fmt.Errorf("empty shell command")}
		}
		ctx, cancel := context.WithTimeout(context.Background(), 120*time.Second)
		defer cancel()
		cmd := exec.CommandContext(ctx, "/bin/sh", "-lc", command)
		cmd.Dir = workspace
		out, err := cmd.CombinedOutput()
		if err != nil {
			return commandResult{label: "Linux", text: string(out), err: fmt.Errorf("%v\n%s", err, strings.TrimSpace(string(out)))}
		}
		return commandResult{label: "Linux", text: string(out)}
	}
}

func runMainCmd(label, workspace string, args ...string) tea.Cmd {
	return func() tea.Msg {
		mainPath := findMainPy()
		if mainPath == "" {
			return commandResult{label: label, err: fmt.Errorf("AgentOS main.py not found")}
		}
		cmdArgs := append([]string{mainPath, "--workspace", workspace}, args...)
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
		defer cancel()
		cmd := exec.CommandContext(ctx, "python3", cmdArgs...)
		out, err := cmd.CombinedOutput()
		text := strings.TrimSpace(string(out))
		if err != nil {
			return commandResult{label: label, text: text, err: fmt.Errorf("%v\n%s", err, text)}
		}
		if text == "" {
			text = "Engine command completed."
		}
		return commandResult{label: label, text: text}
	}
}

func findMainPy() string {
	candidates := []string{
		"/usr/lib/agentos/src/main.py",
		"src/main.py",
		"main.py",
	}
	for _, candidate := range candidates {
		if _, err := os.Stat(candidate); err == nil {
			return candidate
		}
	}
	return ""
}

func runJSON(kernelctl string, args ...string) ([]byte, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Minute)
	defer cancel()
	cmd := exec.CommandContext(ctx, kernelctl, args...)
	out, err := cmd.CombinedOutput()
	if jsonOut, ok := extractJSON(out); ok {
		return jsonOut, nil
	}
	if err != nil {
		return out, fmt.Errorf("%s failed. Run /logs for details.", strings.Join(args, " "))
	}
	return out, fmt.Errorf("%s returned non-JSON output. Run /logs for details.", strings.Join(args, " "))
}

func summarizeJSON(raw []byte) string {
	var data map[string]any
	if err := json.Unmarshal(raw, &data); err != nil {
		return strings.TrimSpace(string(raw))
	}
	if capability, _ := data["capability"].(string); capability == "telegram_live_loop" {
		return summarizeTelegramLiveLoop(data)
	}
	if capability, _ := data["capability"].(string); capability == "intent_dispatch" {
		return summarizeIntentDispatch(data)
	}
	if schema, _ := data["schema_version"].(string); schema == "agentos-telegram-setup-page.v1" {
		return summarizeTelegramSetupPage(data)
	}
	if summary, ok := data["summary"].(map[string]any); ok {
		pairs := make([]string, 0, len(summary))
		for key, value := range summary {
			pairs = append(pairs, fmt.Sprintf("%s=%v", key, value))
			if len(pairs) >= 8 {
				break
			}
		}
		return strings.Join(pairs, "\n")
	}
	if ok, exists := data["ok"]; exists {
		return fmt.Sprintf("ok=%v", ok)
	}
	if provider, exists := data["provider"].(string); exists {
		lines := []string{"Provider: " + provider}
		if model, _ := data["selected_model"].(string); model != "" {
			lines = append(lines, "Model: "+model)
		}
		if ready, exists := data["provider_ready"]; exists {
			lines = append(lines, fmt.Sprintf("Ready: %v", ready))
		}
		if key, exists := data["openai_key_configured"]; exists {
			lines = append(lines, fmt.Sprintf("OpenAI key configured: %v", key))
		}
		if url, _ := data["setup_page_url"].(string); url != "" {
			lines = append(lines, "Setup page: "+url)
			if qr := terminalQR(url); qr != "" {
				lines = append(lines, "Scan this QR from your phone or host:", qr)
			}
		}
		return strings.Join(lines, "\n")
	}
	if url, exists := data["setup_page_url"].(string); exists && url != "" {
		lines := []string{"Setup page: " + url}
		if qr := terminalQR(url); qr != "" {
			lines = append(lines, "Scan this QR from your phone or host:", qr)
		}
		if already, _ := data["setup_page_already_running"].(bool); already {
			lines = append(lines, "Already running: yes, reused existing setup page")
		}
		if action, _ := data["operator_action_required"].(string); action != "" {
			lines = append(lines, "Next: open_setup_page")
		}
		if logPath, _ := data["log_path"].(string); logPath != "" {
			lines = append(lines, "Log: "+logPath)
		}
		return strings.Join(lines, "\n")
	}
	return strings.TrimSpace(string(raw))
}

func summarizeIntentDispatch(data map[string]any) string {
	intentName, _ := data["intent"].(string)
	capabilityName, _ := data["capability_executed"].(string)
	response, _ := data["response"].(string)
	lines := []string{}
	if intentName != "" {
		lines = append(lines, "Understood as: "+intentName)
	}
	if capabilityName != "" {
		lines = append(lines, "Capability: "+capabilityName)
	}
	if web, _ := data["web_search_used"].(bool); web {
		lines = append(lines, "Internal web/search was used.")
	} else {
		lines = append(lines, "No web search needed.")
	}
	if sent, _ := data["telegram_reply_sent"].(bool); sent {
		lines = append(lines, "Telegram reply sent.")
	}
	if strings.TrimSpace(response) != "" {
		lines = append(lines, "", strings.TrimSpace(response))
	}
	return strings.Join(lines, "\n")
}

func summarizeTelegramSetupPage(data map[string]any) string {
	lines := []string{}
	if url, _ := data["setup_page_url"].(string); url != "" {
		lines = append(lines, "Setup page: "+url)
		if qr := terminalQR(url); qr != "" {
			lines = append(lines, "Scan this QR from your phone or host:", qr)
		}
	}
	if completed, _ := data["completed"].(bool); completed {
		lines = append(lines, "Status: Telegram connected")
		lines = append(lines, "Next: send a new message to your bot. AgentOS should answer automatically.")
	} else {
		lines = append(lines, "Status: waiting for token/chat confirmation")
		lines = append(lines, "Next: paste token in the setup page, send /start to the bot, then click Connect Telegram.")
	}
	if already, _ := data["setup_page_already_running"].(bool); already {
		lines = append(lines, "Already running: yes, reused existing setup page")
	}
	if setup, ok := data["telegram_setup"].(map[string]any); ok {
		if summary, ok := setup["summary"].(map[string]any); ok {
			if transport, _ := summary["target_transport"].(string); transport != "" {
				lines = append(lines, "Transport after setup: "+transport)
			}
			if clear, ok := summary["webhook_clear_ok"]; ok {
				lines = append(lines, fmt.Sprintf("Stale webhook cleared: %v", clear))
			}
			if failure, _ := summary["failure_class"].(string); failure != "" {
				lines = append(lines, "Issue: "+friendlyFailure(failure))
			}
		}
	}
	if logPath, _ := data["log_path"].(string); logPath != "" {
		lines = append(lines, "Log: "+logPath)
	}
	return strings.Join(lines, "\n")
}

func summarizeTelegramLiveLoop(data map[string]any) string {
	summary, _ := data["summary"].(map[string]any)
	if summary == nil {
		summary = data
	}
	failure, _ := summary["failure_class"].(string)
	if failure == "telegram_webhook_active" || failure == "telegram_webhook_transport_active" {
		return strings.Join([]string{
			"Manual polling check was blocked because Telegram has an active webhook.",
			"Run /setup telegram again to refresh setup and clear stale webhooks when no public webhook URL is configured.",
			"If you intentionally use a public webhook, check /telegram status instead of /test telegram.",
		}, "\n")
	}
	lines := []string{
		fmt.Sprintf("Update received: %v", summary["telegram_live_update_received"]),
		fmt.Sprintf("Message routed: %v", summary["telegram_live_message_routed"]),
		fmt.Sprintf("Search success: %v", summary["telegram_live_search_success"]),
		fmt.Sprintf("Reply sent: %v", summary["telegram_reply_sent"]),
		fmt.Sprintf("Offset saved: %v", summary["telegram_update_offset_persisted"]),
	}
	if failure != "" {
		lines = append(lines, "Issue: "+friendlyFailure(failure))
	}
	if failure == "" && truthy(summary["telegram_reply_sent"]) {
		lines = append(lines, "Telegram check passed.")
	}
	return strings.Join(lines, "\n")
}

func friendlyFailure(failure string) string {
	switch failure {
	case "":
		return ""
	case "telegram_token_missing":
		return "Telegram token was not received. Paste the bot token once in the setup page."
	case "telegram_chat_id_missing":
		return "Chat ID is missing. Send /start to your bot, then click Connect Telegram again."
	case "telegram_webhook_active_chat_id_lookup_blocked":
		return "Telegram has an active webhook, so auto chat lookup is blocked. Enter the chat ID manually or rerun setup."
	case "telegram_live_update_timeout":
		return "No new Telegram message was waiting. Send a fresh message to the bot and retry."
	case "telegram_webhook_active":
		return "A Telegram webhook is active, so polling is blocked. Rerun setup to clear stale webhooks when using local VM mode."
	default:
		return failure
	}
}

func truthy(value any) bool {
	switch v := value.(type) {
	case bool:
		return v
	case string:
		return v == "true" || v == "1" || v == "yes"
	default:
		return false
	}
}

func extractJSON(raw []byte) ([]byte, bool) {
	text := strings.TrimSpace(string(raw))
	if text == "" {
		return nil, false
	}
	if json.Valid([]byte(text)) {
		return []byte(text), true
	}
	start := strings.LastIndex(text, "{")
	for start >= 0 {
		candidate := strings.TrimSpace(text[start:])
		if json.Valid([]byte(candidate)) {
			return []byte(candidate), true
		}
		next := strings.LastIndex(text[:start], "{")
		start = next
	}
	return nil, false
}

func normalizeCommand(line string) string {
	trimmed := strings.TrimSpace(line)
	lower := strings.ToLower(trimmed)
	aliases := map[string]string{
		"setup llm":       "/setup llm",
		"llm":             "/llm",
		"setup telegram":  "/setup telegram",
		"telegram status": "/telegram status",
		"test telegram":   "/test telegram",
		"status":          "/status",
		"help":            "/help",
		"power":           "/power",
		"clear":           "/clear",
		"logs":            "/logs",
		"mode shell":      "/mode shell",
		"mode agent":      "/mode agent",
		"mode setup":      "/mode setup",
	}
	if alias, ok := aliases[lower]; ok {
		return alias
	}
	return trimmed
}

func isGreeting(line string) bool {
	normalized := strings.ToLower(strings.TrimSpace(line))
	switch normalized {
	case "hi", "hello", "hey", "안녕", "안녕하세요":
		return true
	default:
		return false
	}
}

func terminalQR(url string) string {
	candidates := []string{"/usr/local/bin/agentos-terminal-qr", "scripts/agentos-terminal-qr", "agentos-terminal-qr"}
	for _, candidate := range candidates {
		cmd := exec.Command(candidate, "--compact", url)
		out, err := cmd.CombinedOutput()
		if err == nil && strings.TrimSpace(string(out)) != "" {
			return strings.TrimRight(string(out), "\n")
		}
	}
	return ""
}

func defaultWorkspace() string {
	if value := os.Getenv("AGENTOS_DEFAULT_WORKSPACE"); value != "" {
		return value
	}
	if value := os.Getenv("DEFAULT_WORKSPACE"); value != "" {
		return value
	}
	home := os.Getenv("HOME")
	if home == "" {
		home = "/home/ubuntu"
	}
	return filepath.Join(home, "agentos-ws")
}

func defaultKernelctl() string {
	if value := os.Getenv("AGENTOS_KERNELCTL_BIN"); value != "" {
		return value
	}
	if _, err := os.Stat("/usr/local/bin/agentos-kernelctl"); err == nil {
		return "/usr/local/bin/agentos-kernelctl"
	}
	return "agentos-kernelctl"
}

func localIP() string {
	ifaces, err := net.Interfaces()
	if err != nil {
		return "127.0.0.1"
	}
	for _, iface := range ifaces {
		if iface.Flags&net.FlagUp == 0 || iface.Flags&net.FlagLoopback != 0 {
			continue
		}
		addrs, err := iface.Addrs()
		if err != nil {
			continue
		}
		for _, addr := range addrs {
			var ip net.IP
			switch v := addr.(type) {
			case *net.IPNet:
				ip = v.IP
			case *net.IPAddr:
				ip = v.IP
			}
			if ip == nil || ip.To4() == nil {
				continue
			}
			return ip.String()
		}
	}
	return "127.0.0.1"
}

func shortPath(path string) string {
	if len(path) <= 36 {
		return path
	}
	return "..." + path[len(path)-33:]
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
