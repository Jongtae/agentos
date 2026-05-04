#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from kernel.context.selector import ContextSelector
from kernel.memory.store import MemoryItem


QUERY = "what did I work on yesterday?"
EXPECTED_MARKERS = ["mem:yday_a", "mem:yday_b"]


@dataclass
class BenchmarkResult:
    run_at_utc: str
    query: str
    selected_count: int
    relevant_returned: int
    expected_relevant: int
    precision_at_k: float
    recall_at_k: float
    latency_ms: float
    threshold_status: str
    selected_lines: list[str]
    expected_markers: list[str]


class _FixtureStore:
    def __init__(self, items: list[MemoryItem]):
        self._items = items

    def recent(self, limit: int = 100) -> list[MemoryItem]:
        return self._items[:limit]


def _build_fixture() -> _FixtureStore:
    ts = datetime(2026, 4, 1, 9, 0, 0)
    items = [
        MemoryItem(
            id=1,
            summary="mem:yday_a worked on kernel onboarding wizard",
            detail="",
            tool_name="file_write",
            importance=0.95,
            created_at=ts,
        ),
        MemoryItem(
            id=2,
            summary="mem:yday_b worked on codex cli runtime wiring",
            detail="",
            tool_name="bash",
            importance=0.90,
            created_at=ts,
        ),
        MemoryItem(
            id=3,
            summary="mem:other checked weather forecast",
            detail="",
            tool_name="web_fetch",
            importance=0.20,
            created_at=ts,
        ),
        MemoryItem(
            id=4,
            summary="mem:other listed directory files",
            detail="",
            tool_name="bash",
            importance=0.20,
            created_at=ts,
        ),
    ]
    return _FixtureStore(items)


def run_benchmark(top_k: int, min_precision: float, min_recall: float, max_latency_ms: float) -> BenchmarkResult:
    started = time.perf_counter()
    selector = ContextSelector(top_k=top_k)
    context = selector.select(QUERY, _build_fixture())

    selected_lines = []
    if context:
        selected_lines = [line[2:].strip() for line in context.splitlines() if line.startswith("- ")]

    relevant_returned = 0
    for marker in EXPECTED_MARKERS:
        if any(marker in line for line in selected_lines):
            relevant_returned += 1

    selected_count = len(selected_lines)
    precision = relevant_returned / selected_count if selected_count else 0.0
    recall = relevant_returned / len(EXPECTED_MARKERS) if EXPECTED_MARKERS else 0.0
    latency_ms = (time.perf_counter() - started) * 1000.0
    threshold_status = (
        "pass"
        if precision >= min_precision and recall >= min_recall and latency_ms <= max_latency_ms
        else "fail"
    )

    return BenchmarkResult(
        run_at_utc=datetime.now(timezone.utc).isoformat(),
        query=QUERY,
        selected_count=selected_count,
        relevant_returned=relevant_returned,
        expected_relevant=len(EXPECTED_MARKERS),
        precision_at_k=round(precision, 4),
        recall_at_k=round(recall, 4),
        latency_ms=round(latency_ms, 4),
        threshold_status=threshold_status,
        selected_lines=selected_lines,
        expected_markers=list(EXPECTED_MARKERS),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Memory recall benchmark harness")
    parser.add_argument("--top-k", type=int, default=2)
    parser.add_argument(
        "--output",
        default="artifacts/benchmarks/memory_recall_benchmark.json",
        help="Output JSON path",
    )
    parser.add_argument(
        "--trend-output",
        default="artifacts/benchmarks/memory_recall_trend.jsonl",
        help="Append-only trend artifact path",
    )
    parser.add_argument("--min-precision", type=float, default=1.0)
    parser.add_argument("--min-recall", type=float, default=1.0)
    parser.add_argument("--max-latency-ms", type=float, default=50.0)
    args = parser.parse_args()

    result = run_benchmark(
        top_k=args.top_k,
        min_precision=args.min_precision,
        min_recall=args.min_recall,
        max_latency_ms=args.max_latency_ms,
    )
    payload = asdict(result)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n")

    trend_path = Path(args.trend_output)
    trend_path.parent.mkdir(parents=True, exist_ok=True)
    with trend_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")

    print(f"memory recall benchmark: wrote {output_path}")
    print(f"memory recall benchmark: appended {trend_path}")
    print(json.dumps(payload, ensure_ascii=True))

    if result.threshold_status != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
