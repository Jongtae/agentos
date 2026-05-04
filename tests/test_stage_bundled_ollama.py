from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from stage_bundled_ollama import build_report
from verify_bundled_ollama_staging import build_report as verify_report


class StageBundledOllamaTests(unittest.TestCase):
    def test_stage_and_verify_bundled_ollama(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            source.mkdir()
            (source / "ollama").write_text("binary", encoding="utf-8")
            lib_dir = source / "lib/ollama"
            lib_dir.mkdir(parents=True)
            (lib_dir / "README").write_text("lib", encoding="utf-8")
            cuda_dir = lib_dir / "cuda_v12"
            cuda_dir.mkdir(parents=True)
            (cuda_dir / "libggml-cuda.so").write_text("gpu", encoding="utf-8")
            mlx_dir = lib_dir / "mlx_cuda_v13"
            mlx_dir.mkdir(parents=True)
            (mlx_dir / "libcudnn.so").write_text("mlx", encoding="utf-8")
            vulkan_dir = lib_dir / "vulkan"
            vulkan_dir.mkdir(parents=True)
            (vulkan_dir / "libvulkan.so").write_text("vk", encoding="utf-8")

            archive = root / "ollama-linux-amd64.tar.zst"
            subprocess.run(
                [
                    "/bin/bash",
                    "-lc",
                    f"tar -C {source} -cf - . | zstd -q -o {archive}",
                ],
                check=True,
            )

            registry_root = root / "registry/v2/library/smollm2"
            (registry_root / "manifests").mkdir(parents=True, exist_ok=True)
            (registry_root / "blobs").mkdir(parents=True, exist_ok=True)
            (registry_root / "manifests/135m-instruct-q5_K_M").write_text(
                '{"schemaVersion":2,"config":{"digest":"sha256:abc"},"layers":[{"digest":"sha256:def"}]}',
                encoding="utf-8",
            )
            (registry_root / "blobs/sha256:abc").write_text("config", encoding="utf-8")
            (registry_root / "blobs/sha256:def").write_text("model", encoding="utf-8")

            live_root = root / "live-root"
            runtime_root = root / "runtime-root"
            existing_bin = live_root / "usr/local/bin"
            existing_bin.mkdir(parents=True, exist_ok=True)
            (existing_bin / "agentos-ollama-serve").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            report = build_report(
                live_root=live_root,
                runtime_root=runtime_root,
                cache_dir=root / "cache",
                model="smollm2:135m-instruct-q5_K_M",
                binary_url=archive.as_uri(),
                registry_base=(root / "registry").as_uri(),
                arch="arm64",
            )

            self.assertTrue(report["bundled_local_provider_staged"])
            self.assertTrue(report["bundled_local_model_staged"])
            self.assertEqual(report["arch"], "arm64")
            self.assertTrue(report["binary_archive"].endswith("ollama-linux-arm64.tar.zst"))
            service_dir = live_root / "etc/systemd/system/multi-user.target.wants"
            service_dir.mkdir(parents=True, exist_ok=True)
            service_file = live_root / "etc/systemd/system/agentos-ollama.service"
            service_file.write_text("[Service]\nExecStart=/usr/local/bin/agentos-ollama-serve\n", encoding="utf-8")
            (service_dir / "agentos-ollama.service").symlink_to("../agentos-ollama.service")
            firstrun_dropin = live_root / "etc/systemd/system/agentos-firstrun.service.d"
            firstrun_dropin.mkdir(parents=True, exist_ok=True)
            (live_root / "usr/local/bin/agentos-live-firstrun-service").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            (firstrun_dropin / "10-live-window10.conf").write_text(
                "[Service]\n"
                "User=root\n"
                "Environment=AGENTOS_FIRSTRUN_CHOICE=local\n"
                "ExecStart=\n"
                "ExecStart=/usr/local/bin/agentos-live-firstrun-service\n",
                encoding="utf-8",
            )
            (service_dir / "agentos-firstrun.service").symlink_to("../agentos-firstrun.service")
            verify = verify_report(live_root=live_root, runtime_root=runtime_root, model="smollm2:135m-instruct-q5_K_M")
            self.assertTrue(verify["bundled_local_provider_staged"])
            self.assertTrue(verify["bundled_local_model_staged"])
            self.assertTrue(verify["bundled_local_service_staged"])
            self.assertTrue(verify["bundled_local_firstrun_service_staged"])
            self.assertTrue((live_root / "usr/local/bin/ollama").exists())
            self.assertTrue((live_root / "usr/local/bin/agentos-ollama-serve").exists())
            self.assertTrue((runtime_root / "assets/ollama/usr-local-root/ollama").is_file())
            self.assertFalse((live_root / "usr/local/lib/ollama/cuda_v12").exists())
            self.assertFalse((runtime_root / "assets/ollama/usr-local-root/lib/ollama/cuda_v12").exists())
            self.assertFalse((live_root / "usr/local/lib/ollama/mlx_cuda_v13").exists())
            self.assertFalse((runtime_root / "assets/ollama/usr-local-root/lib/ollama/mlx_cuda_v13").exists())
            self.assertFalse((live_root / "usr/local/lib/ollama/vulkan").exists())
            self.assertFalse((runtime_root / "assets/ollama/usr-local-root/lib/ollama/vulkan").exists())


if __name__ == "__main__":
    unittest.main()
