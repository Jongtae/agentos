#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


BOOT_CONFIG_CANDIDATES = (
    "boot/grub/grub.cfg",
    "boot/grub/loopback.cfg",
    "grub/grub.cfg",
    "grub/loopback.cfg",
    "isolinux/txt.cfg",
)

REPLACEMENTS = (
    ("Try or Install Ubuntu Server", "Continue to AgentOS"),
    ("Ubuntu Server with the HWE kernel", "AgentOS Recovery"),
    ("Ubuntu Server", "Continue to AgentOS"),
    ("Try or Install Ubuntu", "Continue to AgentOS"),
    ("Try Ubuntu without installing", "Continue to AgentOS"),
    ("Try Ubuntu", "Continue to AgentOS"),
    ("Ubuntu (safe graphics)", "AgentOS Recovery"),
    ("Ubuntu (recovery mode)", "AgentOS Recovery"),
)

FORBIDDEN_LABELS = tuple(old for old, _ in REPLACEMENTS)
DEFAULT_BOOT_TARGET_LABEL = "Continue to AgentOS"
SERIAL_CONSOLE_ARGS = (
    "console=tty0",
    "console=ttyAMA0,115200n8",
)
HEADLESS_BOOT_ARGS = (
    # Apple Silicon UTM arm64 live-server boots reliably with a single guest CPU.
    # Without this, the same ISO can stall in casper/live-user setup on 4 vCPU VMs
    # before the AgentOS TTY operator handoff is reached.
    "maxcpus=1",
    "systemd.unit=multi-user.target",
    "plymouth.enable=0",
    "systemd.mask=snapd.service",
    "systemd.mask=snapd.socket",
    "systemd.mask=snapd.seeded.service",
    "systemd.mask=snapd.apparmor.service",
    "systemd.mask=casper-md5check.service",
    "systemd.mask=serial-getty@ttyS0.service",
)
REMOVED_DESKTOP_BOOT_ARGS = {"quiet", "splash"}
GRUB_TERMINAL_PREAMBLE = (
    "terminal_input console",
    "terminal_output console",
)


def _ensure_grub_default_target(text: str) -> tuple[str, bool]:
    lines = text.splitlines()
    default_line = 'set default="0"'
    timeout_style_line = "set timeout_style=hidden"
    timeout_line = "set timeout=1"
    changed = False
    found_default = False
    found_timeout_style = False
    found_timeout = False

    for index, line in enumerate(lines):
        if re.match(r"^\s*set\s+default\s*=", line):
            found_default = True
            if line != default_line:
                lines[index] = default_line
                changed = True
        elif re.match(r"^\s*set\s+timeout_style\s*=", line):
            found_timeout_style = True
            if line != timeout_style_line:
                lines[index] = timeout_style_line
                changed = True
        elif re.match(r"^\s*set\s+timeout\s*=", line):
            found_timeout = True
            if line != timeout_line:
                lines[index] = timeout_line
                changed = True

    if not found_default:
        lines.insert(0, default_line)
        changed = True
    if not found_timeout_style:
        insert_at = 1 if lines and lines[0] == default_line else 0
        lines.insert(insert_at, timeout_style_line)
        changed = True
    if not found_timeout:
        insert_at = 2 if timeout_style_line in lines[:2] else 1
        lines.insert(insert_at, timeout_line)
        changed = True

    updated = "\n".join(lines)
    if text.endswith("\n") or updated:
        updated += "\n"
    return updated, changed


def _ensure_grub_serial_terminal(text: str) -> tuple[str, bool]:
    lines = text.splitlines()
    filtered_lines = []
    changed = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("serial --unit=") or stripped in {
            "terminal_input console serial",
            "terminal_output console serial",
            "terminal_input serial console",
            "terminal_output serial console",
        }:
            changed = True
            continue
        filtered_lines.append(line)
    if all(line in filtered_lines for line in GRUB_TERMINAL_PREAMBLE):
        updated = "\n".join(filtered_lines)
        if text.endswith("\n") or updated:
            updated += "\n"
        return updated, changed
    lines = filtered_lines
    insert_at = 0
    while insert_at < len(lines) and (
        lines[insert_at].startswith("#") or not lines[insert_at].strip()
    ):
        insert_at += 1
    lines[insert_at:insert_at] = list(GRUB_TERMINAL_PREAMBLE)
    updated = "\n".join(lines)
    if text.endswith("\n") or updated:
        updated += "\n"
    return updated, True


def _remove_invalid_grub_platform_command(text: str) -> tuple[str, bool]:
    lines = text.splitlines()
    updated_lines = [line for line in lines if line.strip() != "grub_platform"]
    if len(updated_lines) == len(lines):
        return text, False
    updated = "\n".join(updated_lines)
    if text.endswith("\n") or updated:
        updated += "\n"
    return updated, True


_MENUENTRY_OPEN_RE = re.compile(
    r'^(?P<indent>[ \t]*)menuentry\s+(?P<quote>["\'])(?P<title>[^"\']*)(?P=quote)[^{]*\{\s*$'
)


def _extract_menuentry_block(text: str, title: str) -> tuple[int, int, str] | None:
    """Return (start_line_index, end_line_index_exclusive, block_text) for a menuentry.

    Tracks brace depth starting at the opening ``menuentry ... {`` line so nested
    blocks (e.g. grub ``if/else``) inside a menuentry are handled correctly.
    """
    lines = text.splitlines()
    for start, line in enumerate(lines):
        match = _MENUENTRY_OPEN_RE.match(line)
        if not match or match.group("title") != title:
            continue
        depth = 1
        for end in range(start + 1, len(lines)):
            depth += lines[end].count("{")
            depth -= lines[end].count("}")
            if depth <= 0:
                block = "\n".join(lines[start : end + 1])
                return start, end + 1, block
        return None
    return None


def _ensure_serial_console_args(text: str) -> tuple[str, bool]:
    lines = text.splitlines()
    changed = False
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if not re.match(r"^linux\s+", stripped):
            continue
        prefix = line[: len(line) - len(stripped)]
        parts = stripped.split()
        separator_index = parts.index("---") if "---" in parts else len(parts)
        pre_separator = parts[:separator_index]
        post_args = []
        if separator_index < len(parts):
            post_args = [part for part in parts[separator_index + 1 :] if part != "console=tty0"]
        post_separator = ["---", *post_args] if post_args else []
        for arg in SERIAL_CONSOLE_ARGS + HEADLESS_BOOT_ARGS:
            if arg not in pre_separator:
                pre_separator.append(arg)
        updated = prefix + " ".join(pre_separator + post_separator)
        if updated != line:
            lines[index] = updated
            changed = True
    result = "\n".join(lines)
    if text.endswith("\n") or result:
        result += "\n"
    return result, changed


def _remove_desktop_boot_args(text: str) -> tuple[str, bool]:
    lines = text.splitlines()
    changed = False
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if not re.match(r"^linux\s+", stripped):
            continue
        prefix = line[: len(line) - len(stripped)]
        parts = stripped.split()
        updated_parts = [part for part in parts if part not in REMOVED_DESKTOP_BOOT_ARGS]
        if updated_parts != parts:
            lines[index] = prefix + " ".join(updated_parts)
            changed = True
    result = "\n".join(lines)
    if text.endswith("\n") or result:
        result += "\n"
    return result, changed


def patch_boot_entries(iso_root: Path) -> dict:
    patched_files: list[str] = []
    changed_files: list[str] = []
    file_summaries: list[dict] = []
    aggregate_text_parts: list[str] = []
    grub_default_target_configured = False

    for candidate in BOOT_CONFIG_CANDIDATES:
        path = iso_root / candidate
        if not path.exists() or not path.is_file():
            continue

        original = path.read_text(encoding="utf-8", errors="replace")
        updated = original
        replacements_applied: list[dict] = []
        for old, new in REPLACEMENTS:
            count = updated.count(old)
            if count:
                updated = updated.replace(old, new)
                replacements_applied.append({"from": old, "to": new, "count": count})

        if path.name in {"grub.cfg", "loopback.cfg"}:
            updated, grub_platform_removed = _remove_invalid_grub_platform_command(updated)
            if grub_platform_removed:
                replacements_applied.append({"from": "standalone grub_platform command", "to": "removed", "count": 1})
            updated, default_changed = _ensure_grub_default_target(updated)
            if 'set default="0"' in updated or "set default=0" in updated:
                grub_default_target_configured = True
            if default_changed:
                replacements_applied.append({"from": "grub default target", "to": DEFAULT_BOOT_TARGET_LABEL, "count": 1})
            updated, serial_terminal_changed = _ensure_grub_serial_terminal(updated)
            if serial_terminal_changed:
                replacements_applied.append({"from": "grub terminal", "to": "serial input/output", "count": 1})

        updated, desktop_args_removed = _remove_desktop_boot_args(updated)
        if desktop_args_removed:
            replacements_applied.append({"from": "desktop live boot args", "to": "headless tty boot", "count": 1})

        updated, serial_changed = _ensure_serial_console_args(updated)
        if serial_changed:
            replacements_applied.append({"from": "linux boot args", "to": "headless serial console diagnostics", "count": 1})

        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed_files.append(str(path))

        patched_files.append(str(path))
        aggregate_text_parts.append(updated)
        file_summaries.append(
            {
                "path": str(path),
                "changed": updated != original,
                "replacements": replacements_applied,
            }
        )

    aggregate_text = "\n".join(aggregate_text_parts)
    continue_present = "Continue to AgentOS" in aggregate_text
    recovery_present = "AgentOS Recovery" in aggregate_text
    install_present = "Install AgentOS" in aggregate_text
    forbidden_remaining = [label for label in FORBIDDEN_LABELS if label in aggregate_text]
    install_path_available = bool(continue_present)
    default_boot_target_configured = bool(
        patched_files
        and continue_present
        and grub_default_target_configured
        and not forbidden_remaining
    )
    installer_hidden_default_path = bool(default_boot_target_configured)

    return {
        "ok": True,
        "iso_root": str(iso_root),
        "patched_files": patched_files,
        "changed_files": changed_files,
        "files": file_summaries,
        "continue_present": continue_present,
        "install_present": install_present,
        "install_path_available": install_path_available,
        "recovery_present": recovery_present,
        "default_boot_target_label": DEFAULT_BOOT_TARGET_LABEL if continue_present else "",
        "default_boot_target_entry_index": 0 if continue_present else None,
        "grub_default_target_configured": grub_default_target_configured,
        "default_boot_target_configured": default_boot_target_configured,
        "forbidden_labels_remaining": forbidden_remaining,
        "installer_hidden_default_path": installer_hidden_default_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch remastered ISO boot entries to AgentOS-owned labels")
    parser.add_argument("--iso-root", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = patch_boot_entries(Path(args.iso_root).resolve())
    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(json.dumps(report, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
