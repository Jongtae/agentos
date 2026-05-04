#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import urllib.request
from pathlib import Path


DEFAULT_MODEL = "smollm2:135m-instruct-q5_K_M"
DEFAULT_ARCH = "amd64"
DEFAULT_BINARY_URLS = {
    "amd64": "https://ollama.com/download/ollama-linux-amd64.tar.zst",
    "arm64": "https://ollama.com/download/ollama-linux-arm64.tar.zst",
}
DEFAULT_BINARY_URL = DEFAULT_BINARY_URLS[DEFAULT_ARCH]
DEFAULT_REGISTRY_BASE = "https://registry.ollama.ai"
SCHEMA_VERSION = "agentos-bundled-ollama-stage.v1"
PRUNED_ACCELERATOR_PREFIXES = ("cuda", "rocm", "jetpack", "oneapi", "mlx", "vulkan")


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return
    with urllib.request.urlopen(url, timeout=120) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def _parse_model_ref(model: str) -> tuple[str, str, str]:
    name = model.strip()
    namespace = "library"
    tag = "latest"
    model_name = name
    if ":" in name:
        model_name, tag = name.rsplit(":", 1)
    if "/" in model_name:
        namespace, model_name = model_name.split("/", 1)
    return namespace, model_name, tag


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _binary_url_for_arch(arch: str, binary_url: str = "") -> str:
    if binary_url:
        return binary_url
    if arch not in DEFAULT_BINARY_URLS:
        raise ValueError(f"unsupported Ollama arch: {arch}")
    return DEFAULT_BINARY_URLS[arch]


def _extract_ollama_root(cache_dir: Path, binary_url: str, arch: str) -> tuple[Path, Path]:
    archive_path = cache_dir / f"ollama-linux-{arch}.tar.zst"
    extract_root = cache_dir / f"ollama-linux-{arch}"
    _download(binary_url, archive_path)
    if extract_root.exists():
        binary = extract_root / "ollama"
        if binary.is_file():
            return extract_root, archive_path
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "/bin/bash",
            "-lc",
            f"zstd -d -c {shlex.quote(str(archive_path))} | tar -xf - -C {shlex.quote(str(extract_root))}",
        ],
        check=True,
    )
    binary = extract_root / "bin/ollama"
    if not binary.is_file():
        binary = extract_root / "ollama"
    if not binary.is_file():
        raise RuntimeError(f"extracted Ollama archive missing binary: {binary}")
    return extract_root, archive_path


def _model_manifest_url(model: str, registry_base: str) -> str:
    namespace, model_name, tag = _parse_model_ref(model)
    return f"{registry_base.rstrip('/')}/v2/{namespace}/{model_name}/manifests/{tag}"


def _model_blob_url(model: str, digest: str, registry_base: str) -> str:
    namespace, model_name, _ = _parse_model_ref(model)
    return f"{registry_base.rstrip('/')}/v2/{namespace}/{model_name}/blobs/{digest}"


def _model_store_paths(base: Path, model: str) -> tuple[Path, Path]:
    namespace, model_name, tag = _parse_model_ref(model)
    manifest_path = base / "manifests" / "registry.ollama.ai" / namespace / model_name / tag
    blobs_dir = base / "blobs"
    return manifest_path, blobs_dir


def _download_model_store(cache_dir: Path, model: str, registry_base: str) -> tuple[Path, Path, list[str]]:
    store_root = cache_dir / "models"
    manifest_path, blobs_dir = _model_store_paths(store_root, model)
    if manifest_path.is_file():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest_url = _model_manifest_url(model, registry_base)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(manifest_url, timeout=120) as response:
            payload = json.load(response)
        manifest_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    digests: list[str] = []
    config = payload.get("config") or {}
    if config.get("digest"):
        digests.append(str(config["digest"]))
    for layer in payload.get("layers") or []:
        digest = (layer or {}).get("digest")
        if digest:
            digests.append(str(digest))

    blobs_dir.mkdir(parents=True, exist_ok=True)
    for digest in digests:
        blob_path = blobs_dir / digest.replace(":", "-")
        if blob_path.is_file():
            continue
        with urllib.request.urlopen(_model_blob_url(model, digest, registry_base), timeout=300) as response, blob_path.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    return store_root, manifest_path, digests


def _copy_tree(src: Path, dest: Path, *, prune_ollama_accelerators: bool = False) -> None:
    if dest.exists():
        shutil.rmtree(dest)

    ignore = None
    if prune_ollama_accelerators:
        def ignore(directory: str, names: list[str]) -> list[str]:
            current = Path(directory)
            if current.name == "ollama" and current.parent.name == "lib":
                skipped: list[str] = []
                for name in names:
                    lowered = name.lower()
                    if lowered.startswith(PRUNED_ACCELERATOR_PREFIXES):
                        skipped.append(name)
                return skipped
            return []

    shutil.copytree(src, dest, symlinks=True, ignore=ignore)


def _merge_tree(src: Path, dest: Path, *, prune_ollama_accelerators: bool = False) -> None:
    ignore = None
    if prune_ollama_accelerators:
        def ignore(directory: str, names: list[str]) -> list[str]:
            current = Path(directory)
            if current.name == "ollama" and current.parent.name == "lib":
                skipped: list[str] = []
                for name in names:
                    lowered = name.lower()
                    if lowered.startswith(PRUNED_ACCELERATOR_PREFIXES):
                        skipped.append(name)
                return skipped
            return []

    shutil.copytree(src, dest, symlinks=True, ignore=ignore, dirs_exist_ok=True)


def _stage_live_root(live_root: Path, extracted_root: Path, model_store_root: Path) -> dict:
    target_prefix = live_root / "usr/local"
    target_prefix.mkdir(parents=True, exist_ok=True)
    for child in extracted_root.iterdir():
        target = target_prefix / child.name
        if child.is_dir():
            _merge_tree(child, target, prune_ollama_accelerators=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, target)
    bin_link = target_prefix / "bin" / "ollama"
    if not bin_link.exists():
        bin_link.parent.mkdir(parents=True, exist_ok=True)
        root_binary = target_prefix / "ollama"
        if root_binary.is_file():
            if bin_link.exists() or bin_link.is_symlink():
                bin_link.unlink()
            bin_link.symlink_to(Path("..") / "ollama")

    live_models = live_root / "var/lib/agentos/models"
    _copy_tree(model_store_root, live_models)
    return {
        "binary_path": str(bin_link if bin_link.exists() else (target_prefix / "ollama")),
        "binary_link_path": str(bin_link),
        "models_root": str(live_models),
    }


def _stage_runtime_assets(runtime_root: Path, extracted_root: Path, model_store_root: Path) -> dict:
    asset_root = runtime_root / "assets" / "ollama"
    binary_root = asset_root / "usr-local-root"
    model_root = asset_root / "models"
    asset_root.mkdir(parents=True, exist_ok=True)
    _copy_tree(extracted_root, binary_root, prune_ollama_accelerators=True)
    _copy_tree(model_store_root, model_root)
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "provider": "ollama",
        "model": DEFAULT_MODEL,
        "install_strategy": "bundled_local",
        "usr_local_root": str(binary_root),
        "models_root": str(model_root),
    }
    (asset_root / "bundled-ollama.json").write_text(json.dumps(metadata, ensure_ascii=True), encoding="utf-8")
    return {
        "asset_root": str(asset_root),
        "binary_root": str(binary_root),
        "models_root": str(model_root),
    }


def build_report(
    *,
    live_root: Path,
    runtime_root: Path,
    cache_dir: Path,
    model: str,
    binary_url: str,
    registry_base: str,
    arch: str = DEFAULT_ARCH,
) -> dict:
    resolved_binary_url = _binary_url_for_arch(arch, binary_url)
    extracted_root, archive_path = _extract_ollama_root(cache_dir, resolved_binary_url, arch)
    model_store_root, manifest_path, digests = _download_model_store(cache_dir, model, registry_base)
    live_stage = _stage_live_root(live_root, extracted_root, model_store_root)
    runtime_stage = _stage_runtime_assets(runtime_root, extracted_root, model_store_root)
    return {
        "schema_version": SCHEMA_VERSION,
        "provider": "ollama",
        "model": model,
        "arch": arch,
        "bundled_local_provider_staged": True,
        "bundled_local_model_staged": True,
        "binary_url": resolved_binary_url,
        "binary_archive": str(archive_path),
        "binary_archive_sha256": _sha256(archive_path),
        "model_manifest_path": str(manifest_path),
        "blob_count": len(digests),
        "install_strategy": "bundled_local",
        "live_stage": live_stage,
        "runtime_stage": runtime_stage,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage a bundled local Ollama runtime and model into the AgentOS image roots")
    parser.add_argument("--live-root", required=True)
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--arch", choices=sorted(DEFAULT_BINARY_URLS), default=DEFAULT_ARCH)
    parser.add_argument("--binary-url", default="")
    parser.add_argument("--registry-base", default=DEFAULT_REGISTRY_BASE)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    report = build_report(
        live_root=Path(args.live_root),
        runtime_root=Path(args.runtime_root),
        cache_dir=Path(args.cache_dir),
        model=args.model,
        binary_url=args.binary_url,
        registry_base=args.registry_base,
        arch=args.arch,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
