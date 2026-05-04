#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from stage_bundled_ollama import DEFAULT_MODEL, _model_store_paths


SCHEMA_VERSION = "agentos-bundled-ollama-verify.v1"


def build_report(*, live_root: Path, runtime_root: Path, model: str) -> dict:
    live_manifest, live_blobs = _model_store_paths(live_root / "var/lib/agentos/models", model)
    runtime_manifest, runtime_blobs = _model_store_paths(runtime_root / "assets/ollama/models", model)
    live_binary = live_root / "usr/local/bin/ollama"
    if not live_binary.exists():
        live_binary = live_root / "usr/local/ollama"
    runtime_binary = runtime_root / "assets/ollama/usr-local-root/bin/ollama"
    if not runtime_binary.exists():
        runtime_binary = runtime_root / "assets/ollama/usr-local-root/ollama"
    live_link = live_root / "usr/local/bin/ollama"
    live_service = live_root / "etc/systemd/system/agentos-ollama.service"
    live_service_enabled = live_root / "etc/systemd/system/multi-user.target.wants/agentos-ollama.service"
    live_firstrun_enabled = live_root / "etc/systemd/system/multi-user.target.wants/agentos-firstrun.service"
    live_firstrun_override = live_root / "etc/systemd/system/agentos-firstrun.service.d/10-live-window10.conf"
    live_firstrun_wrapper = live_root / "usr/local/bin/agentos-live-firstrun-service"
    bundled_provider_staged = live_binary.is_file() and runtime_binary.is_file() and live_link.exists()
    bundled_model_staged = live_manifest.is_file() and runtime_manifest.is_file() and live_blobs.is_dir() and runtime_blobs.is_dir()
    bundled_service_staged = live_service.is_file() and live_service_enabled.is_symlink()
    override_text = live_firstrun_override.read_text(encoding="utf-8") if live_firstrun_override.is_file() else ""
    bundled_firstrun_service_staged = (
        live_firstrun_enabled.is_symlink()
        and live_firstrun_override.is_file()
        and live_firstrun_wrapper.is_file()
        and "User=root" in override_text
        and "ExecStart=/usr/local/bin/agentos-live-firstrun-service" in override_text
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "provider": "ollama",
        "model": model,
        "bundled_local_provider_staged": bundled_provider_staged,
        "bundled_local_model_staged": bundled_model_staged,
        "bundled_local_service_staged": bundled_service_staged,
        "bundled_local_firstrun_service_staged": bundled_firstrun_service_staged,
        "bundled_local_provider_name": "ollama",
        "bundled_local_model_name": model,
        "live_binary_path": str(live_binary),
        "runtime_binary_path": str(runtime_binary),
        "live_manifest_path": str(live_manifest),
        "runtime_manifest_path": str(runtime_manifest),
        "live_service_path": str(live_service),
        "live_service_enable_path": str(live_service_enabled),
        "live_firstrun_enable_path": str(live_firstrun_enabled),
        "live_firstrun_override_path": str(live_firstrun_override),
        "live_firstrun_wrapper_path": str(live_firstrun_wrapper),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify bundled Ollama assets are staged into live and runtime roots")
    parser.add_argument("--live-root", required=True)
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = build_report(live_root=Path(args.live_root), runtime_root=Path(args.runtime_root), model=args.model)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=True) + "\n", encoding="utf-8")
    return 0 if report["bundled_local_provider_staged"] and report["bundled_local_model_staged"] and report["bundled_local_service_staged"] and report["bundled_local_firstrun_service_staged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
