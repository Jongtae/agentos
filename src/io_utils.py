from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path


def write_json_file(output_path: str, payload: dict) -> None:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        delete=False,
        dir=str(target.parent),
    ) as tf:
        tf.write(json.dumps(scrub_payload(payload), ensure_ascii=True))
        tf.write("\n")
        temp_name = tf.name

    Path(temp_name).replace(target)


def scrub_sensitive_text(value: str) -> str:
    text = str(value)

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if api_key:
        text = text.replace(api_key, "***REDACTED_OPENAI_API_KEY***")

    # Generic provider key pattern fallback.
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "sk-***REDACTED***", text)

    # Assignment-style key exposure.
    text = re.sub(
        r"(OPENAI_API_KEY\s*=\s*)([^\s\"']+)",
        r"\1***REDACTED***",
        text,
    )
    return text


def scrub_payload(payload):
    if isinstance(payload, dict):
        return {k: scrub_payload(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [scrub_payload(v) for v in payload]
    if isinstance(payload, str):
        return scrub_sensitive_text(payload)
    return payload
