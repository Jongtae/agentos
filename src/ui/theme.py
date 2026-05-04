"""
AgentOS TUI theme — colors and CSS for textual.
"""

# Textual CSS (injected into AIKernelApp.CSS)
AGENTOS_CSS = """
Screen {
    background: $background;
}

#header-bar {
    height: 1;
    background: $primary-darken-3;
    color: $text;
    content-align: center middle;
    text-style: bold;
}

#main-container {
    height: 1fr;
}

#output-panel {
    width: 2fr;
    border-right: solid $primary-darken-2;
    padding: 0 1;
    scrollbar-gutter: stable;
}

#monitor-panel {
    width: 1fr;
    padding: 0 1;
    border-left: solid $primary-darken-2;
    overflow-y: auto;
}

#monitor-title {
    color: $accent;
    text-style: bold;
    padding-bottom: 1;
}

#prompt-container {
    height: 3;
    border-top: solid $primary-darken-2;
    padding: 0 1;
    align: left middle;
}

#prompt-input {
    border: none;
    background: transparent;
    color: $text;
    width: 1fr;
}

#prompt-prefix {
    color: $accent;
    text-style: bold;
    padding-right: 1;
    width: auto;
}

.approval-box {
    background: $warning-darken-2;
    color: $text;
    border: solid $warning;
    padding: 1;
    margin: 1 0;
}
"""
