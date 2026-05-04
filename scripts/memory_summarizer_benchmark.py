#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from kernel.memory.summarizer import ScaffoldMemoryWindowSummarizer


def _fixture_context() -> str:
    return (
        "Recent relevant context:\n"
        "- [bash] IMPORTANT security warning on risky command\n"
        "- [file_write] updated kernel runtime loop and selector integration\n"
        "- [file_read] reviewed roadmap and runbook documentation\n"
        "- [web_fetch] read external article about indexing\n"
        "- [bash] ran full acceptance checks with diagnostics\n"
        "- [bash] [error] timeout occurred during external fetch\n"
        "- [file_write] drafted migration notes for phase4\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Memory summarizer quality benchmark")
    parser.add_argument("--output", default="artifacts/benchmarks/memory_summarizer_benchmark.json")
    parser.add_argument("--max-chars", type=int, default=180)
    parser.add_argument("--max-lines", type=int, default=4)
    args = parser.parse_args()

    summarizer = ScaffoldMemoryWindowSummarizer(max_chars=args.max_chars, max_lines=args.max_lines)
    original = _fixture_context()
    compacted = summarizer.compact_message_window("what did I work on yesterday?", original, memory=object())
    metrics = summarizer.metrics(original, compacted)
    payload = {
        "max_chars": args.max_chars,
        "max_lines": args.max_lines,
        "metrics": metrics,
        "compacted_preview": compacted,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n")

    print(f"memory summarizer benchmark: wrote {output}")
    print(json.dumps(payload, ensure_ascii=True))


if __name__ == "__main__":
    main()
