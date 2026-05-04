"""
FileTool — reads and writes files within the workspace root.
All paths are validated through sandbox.safe_path().
"""
from __future__ import annotations

import os
from pathlib import Path

from kernel.capability_substrate import build_document_access_report
from workspace.sandbox import safe_path

_MAX_READ = 100_000   # bytes (~100KB)
_MAX_OUTPUT = 4_000   # chars returned to LLM


class FileReadTool:
    name = "file_read"

    def __init__(self, workspace_dir: Path):
        self._root = workspace_dir

    def run(self, args: dict) -> str:
        """
        args:
            path (str): path relative to workspace root
        """
        user_path = args.get("path", "")
        if not user_path:
            return "[error] path is required"

        try:
            target = safe_path(self._root, user_path)
        except ValueError as e:
            return f"[error] {e}"

        if not target.exists():
            return f"[error] file not found: {user_path}"
        if not target.is_file():
            return f"[error] not a file: {user_path}"

        try:
            content = target.read_bytes()[:_MAX_READ].decode("utf-8", errors="replace")
            if len(content) > _MAX_OUTPUT:
                return content[:_MAX_OUTPUT] + f"\n... [truncated, {len(content)} chars total]"
            return content
        except Exception as e:
            return f"[error] could not read file: {e}"


class DocumentAccessTool:
    name = "document_access"

    def __init__(self, workspace_dir: Path):
        self._root = workspace_dir

    def run(self, args: dict) -> str:
        user_path = args.get("path", "")
        if not user_path:
            return "[error] path is required"
        report = build_document_access_report(self._root, user_path)
        if not report.get("native_handled", False):
            reason = str((report.get("proof") or {}).get("reason", "document access failed"))
            return f"[error] {reason}"
        return str((report.get("proof") or {}).get("text_preview", "")) or "(no text content found)"


class FileWriteTool:
    name = "file_write"

    def __init__(self, workspace_dir: Path):
        self._root = workspace_dir

    def run(self, args: dict) -> str:
        """
        args:
            path     (str):  path relative to workspace root
            content  (str):  text content to write
            overwrite (bool): if False and file exists, return error
        """
        user_path = args.get("path", "")
        content   = args.get("content", "")
        overwrite = args.get("overwrite", False)

        if not user_path:
            return "[error] path is required"

        try:
            target = safe_path(self._root, user_path)
        except ValueError as e:
            return f"[error] {e}"

        if target.exists() and not overwrite:
            return f"[error] file already exists: {user_path}. Set overwrite=true to replace."

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write: write to .tmp then rename
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_text(content, encoding="utf-8")
            tmp.rename(target)
            return f"Written {len(content)} chars to {user_path}"
        except Exception as e:
            return f"[error] could not write file: {e}"


class FileListTool:
    name = "file_list"

    def __init__(self, workspace_dir: Path):
        self._root = workspace_dir

    def run(self, args: dict) -> str:
        """
        args:
            path (str): directory path relative to workspace root (default: ".")
        """
        user_path = args.get("path", ".")

        try:
            target = safe_path(self._root, user_path)
        except ValueError as e:
            return f"[error] {e}"

        if not target.is_dir():
            return f"[error] not a directory: {user_path}"

        try:
            entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name))
            lines = []
            for entry in entries:
                prefix = "📁 " if entry.is_dir() else "📄 "
                size = f"  ({entry.stat().st_size:,} bytes)" if entry.is_file() else ""
                lines.append(f"{prefix}{entry.name}{size}")
            return "\n".join(lines) if lines else "(empty directory)"
        except Exception as e:
            return f"[error] could not list directory: {e}"
