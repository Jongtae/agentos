from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import json
import os
from urllib import error as urllib_error
from urllib import request as urllib_request

from io_utils import scrub_sensitive_text
from kernel.engine.base import EngineRunResult, HealthCheckResult


class OllamaEngine:
    """KernelEngine implementation backed by `ollama run`."""

    def __init__(
        self,
        workspace_dir: Path,
        command: str = "ollama",
        model: str = "llama3.1:8b",
        timeout_sec: int = 90,
    ):
        self._workspace_dir = Path(workspace_dir).resolve()
        self._command = command
        self._model = model.strip() or "llama3.1:8b"
        self._timeout_sec = max(1, int(timeout_sec))

    @property
    def name(self) -> str:
        return "ollama"

    def _binary_path(self) -> str:
        return shutil.which(self._command) or ""

    def models_dir(self) -> Path:
        configured = (
            os.environ.get("OLLAMA_MODELS", "").strip()
            or os.environ.get("AGENTOS_OLLAMA_MODELS", "").strip()
            or "/var/lib/agentos/models"
        )
        return Path(configured).expanduser()

    def _model_manifest_path(self) -> Path:
        registry = "registry.ollama.ai"
        name = self._model
        namespace = "library"
        tag = "latest"
        model_name = name
        if ":" in name:
            model_name, tag = name.rsplit(":", 1)
        if "/" in model_name:
            namespace, model_name = model_name.split("/", 1)
        return self.models_dir() / "manifests" / registry / namespace / model_name / tag

    def _local_model_store_ready(self) -> bool:
        manifest_path = self._model_manifest_path()
        if not manifest_path.is_file():
            return False
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return False

        digests = []
        config = payload.get("config") or {}
        if config.get("digest"):
            digests.append(str(config["digest"]))
        for layer in payload.get("layers") or []:
            digest = (layer or {}).get("digest")
            if digest:
                digests.append(str(digest))
        if not digests:
            return False

        blobs_dir = self.models_dir() / "blobs"
        for digest in digests:
            if not blobs_dir.joinpath(digest.replace(":", "-")).is_file():
                return False
        return True

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("OLLAMA_MODELS", str(self.models_dir()))
        return env

    def _api_base_url(self) -> str:
        raw = os.environ.get("OLLAMA_HOST", "").strip() or "127.0.0.1:11434"
        if "://" not in raw:
            raw = f"http://{raw}"
        return raw.rstrip("/")

    def _api_json(
        self,
        *,
        path: str,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        timeout_sec: int | None = None,
    ) -> dict[str, Any]:
        request = urllib_request.Request(
            f"{self._api_base_url()}{path}",
            data=json.dumps(payload, ensure_ascii=True).encode("utf-8") if payload is not None else None,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method=method,
        )
        try:
            with urllib_request.urlopen(request, timeout=timeout_sec or self._timeout_sec) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib_error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(scrub_sensitive_text(detail or str(e))) from e
        except TimeoutError as e:
            raise TimeoutError(f"Ollama execution timed out after {timeout_sec or self._timeout_sec}s.") from e
        except urllib_error.URLError as e:
            raise ConnectionError(scrub_sensitive_text(str(e.reason or e))) from e
        except Exception as e:
            raise RuntimeError(f"Ollama execution failed: {e}") from e

        return json.loads(body)

    def _server_ready(self) -> HealthCheckResult:
        try:
            self._api_json(path="/api/tags", timeout_sec=min(self._timeout_sec, 15))
        except TimeoutError as exc:
            return HealthCheckResult(ok=False, reason="timeout", detail=str(exc))
        except ConnectionError as exc:
            return HealthCheckResult(ok=False, reason="service_unreachable", detail=str(exc))
        except Exception as exc:
            return HealthCheckResult(ok=False, reason="api_error", detail=str(exc))
        return HealthCheckResult(ok=True, reason="ok", detail="Ollama server is reachable.")

    def _generate_via_http(self, prompt: str) -> EngineRunResult:
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
        }
        try:
            parsed = self._api_json(path="/api/generate", method="POST", payload=payload)
        except TimeoutError as exc:
            return EngineRunResult(ok=False, error_type="timeout", error_message=str(exc))
        except ConnectionError as exc:
            return EngineRunResult(ok=False, error_type="service_unreachable", error_message=str(exc))
        except json.JSONDecodeError:
            return EngineRunResult(
                ok=False,
                error_type="invalid_response",
                error_message="Ollama returned invalid JSON.",
            )
        except Exception as exc:
            return EngineRunResult(ok=False, error_type="execution_error", error_message=str(exc))

        if parsed.get("error"):
            return EngineRunResult(
                ok=False,
                error_type="api_error",
                error_message=scrub_sensitive_text(str(parsed.get("error"))),
                metadata={"response": scrub_sensitive_text(json.dumps(parsed, ensure_ascii=True)[:2000])},
            )

        content = str(parsed.get("response", "")).strip()
        return EngineRunResult(
            ok=True,
            content=content,
            exit_code=0,
            metadata={"done": bool(parsed.get("done", False))},
        )

    def _model_exists(self) -> bool:
        if self._local_model_store_ready():
            return True
        binary = self._binary_path()
        if not binary:
            return False

        try:
            proc = subprocess.run(
                [binary, "list"],
                cwd=str(self._workspace_dir),
                capture_output=True,
                text=True,
                timeout=min(self._timeout_sec, 15),
                env=self._env(),
            )
        except Exception:
            return False

        if proc.returncode != 0:
            return False

        for line in (proc.stdout or "").splitlines():
            item = line.strip()
            if not item or item.lower().startswith("name "):
                continue
            if item.split()[0] == self._model:
                return True
        return False

    def health_check(self) -> HealthCheckResult:
        if not self._binary_path():
            return HealthCheckResult(
                ok=False,
                reason="binary_not_found",
                detail=f"`{self._command}` is not installed or not in PATH.",
            )

        if not self._model_exists():
            return HealthCheckResult(
                ok=False,
                reason="model_not_found",
                detail=f"Model '{self._model}' is not available. Run: {self._command} pull {self._model}",
            )
        return self._server_ready()

    def run_intent(self, intent: str, context: str = "") -> EngineRunResult:
        binary = self._binary_path()
        if not binary:
            return EngineRunResult(
                ok=False,
                error_type="binary_not_found",
                error_message=f"`{self._command}` is not installed or not in PATH.",
            )
        if not self._model_exists():
            return EngineRunResult(
                ok=False,
                error_type="model_not_found",
                error_message=f"Model '{self._model}' is not available. Run: {self._command} pull {self._model}",
            )

        full_prompt = intent.strip()
        if context.strip():
            full_prompt = f"Context:\n{context.strip()}\n\nTask:\n{intent.strip()}"

        return self._generate_via_http(full_prompt)

    def invoke(self, messages: list[Any]) -> Any:
        parts: list[str] = []
        for msg in messages:
            role = getattr(msg, "type", msg.__class__.__name__).upper()
            content = getattr(msg, "content", "")
            if isinstance(content, list):
                text_chunks = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_chunks.append(item.get("text", ""))
                    else:
                        text_chunks.append(str(item))
                content = "\n".join(text_chunks)
            parts.append(f"[{role}]\n{content}")

        run = self.run_intent(
            intent=(
                "You are the planning engine for AgentOS. "
                "Respond exactly according to the provided system/user messages.\n\n"
                + "\n\n".join(parts)
            )
        )
        if not run.ok:
            raise RuntimeError(f"ollama planner invoke failed: {run.error_type}: {run.error_message}")
        return SimpleNamespace(content=run.content)
