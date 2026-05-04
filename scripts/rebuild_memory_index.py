#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from kernel.memory.index import TokenEmbeddingMemoryIndex, try_load_token_index
from kernel.memory.store import MemoryStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild token memory index and verify reload parity")
    parser.add_argument("--memory-db", required=True, help="Path to memory sqlite db")
    parser.add_argument("--output", required=True, help="Path to index json output")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--query", action="append", default=[], help="Query string for parity checks")
    args = parser.parse_args()

    memory = MemoryStore(args.memory_db)
    items = memory.recent(limit=args.limit)

    output = Path(args.output)
    recovered_from_corrupt_index = False
    if output.exists():
        old = try_load_token_index(output)
        if old is None:
            recovered_from_corrupt_index = True

    index = TokenEmbeddingMemoryIndex()
    index.rebuild(items)
    index.save_to_file(output)

    reloaded = TokenEmbeddingMemoryIndex.load_from_file(output)

    queries = list(args.query)
    if not queries:
        queries = ["kernel", "codex", "runtime"]

    parity = []
    all_match = True
    for query in queries:
        original_ids = [h.memory_id for h in index.query(query, limit=5)]
        reloaded_ids = [h.memory_id for h in reloaded.query(query, limit=5)]
        matched = original_ids == reloaded_ids
        all_match = all_match and matched
        parity.append({
            "query": query,
            "original_ids": original_ids,
            "reloaded_ids": reloaded_ids,
            "matched": matched,
        })

    payload = {
        "memory_db": str(Path(args.memory_db)),
        "output": str(output),
        "items_indexed": len(items),
        "queries": queries,
        "parity_checks": parity,
        "parity_ok": all_match,
        "recovered_from_corrupt_index": recovered_from_corrupt_index,
    }
    print(json.dumps(payload, ensure_ascii=True))

    if not all_match:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
