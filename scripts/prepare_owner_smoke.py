#!/usr/bin/env python3
"""Create NEW synthetic smoke folders; print commands without starting AgentOS."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shlex

NOTE = """# Launch review
This is synthetic test data, not a real project.
Decision: publish the local preview after the owner smoke test.
Owner: Demo User. Deadline: 2030-01-15.
Open question: does the saved result remain available after restart?
"""


def prepare(root: Path, port: int, environ: dict[str, str]) -> dict:
    if not 1024 <= port <= 65535:
        raise ValueError("Choose an unprivileged port between 1024 and 65535.")
    names = [key for key, value in environ.items() if value and (
        key == "AGENTOS_DATA" or key.startswith("AGENTOS_DRIVE_")
        or key in ("AGENTOS_ISOLATED_ENGINE_URL", "AGENTOS_PUBLIC_ACCESS_TOKEN"))]
    if names:
        raise ValueError("Use a clean shell without inherited AgentOS integration/state settings; no values were read from files.")
    root = Path(os.path.abspath(root.expanduser()))
    # No parents=True or exist_ok=True: never reuse/overwrite another installation.
    root.mkdir(mode=0o700)
    for name in ("state", "reference", "workspace"):
        (root / name).mkdir(mode=0o700)
    note = root / "reference" / "launch.md"
    with note.open("x", encoding="utf-8") as stream:
        stream.write(NOTE)
    note.chmod(0o600)
    command = shlex.join(["agentos", "start", "--host", "127.0.0.1", "--port", str(port), "--data", str(root / "state")])
    return {"root": str(root), "state": str(root / "state"),
            "reference": str(root / "reference"), "workspace": str(root / "workspace"),
            "start_command": command, "restart_command": command,
            "evidence": "synthetic_setup_only", "service_started": False,
            "provider_calls": 0, "private_data_copied": False,
            "limitations": "Not an OS sandbox or live-model test. Do not import private data or enable automatic memory writes."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="New directory; parent must exist. Existing roots are refused.")
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args()
    try:
        result = prepare(args.root, args.port, dict(os.environ))
    except (OSError, ValueError) as exc:
        # Never dump the environment, provider config, or raw OS error payload.
        print(json.dumps({"error": type(exc).__name__, "service_started": False,
                          "next_action": "Use a new root with an existing parent, an unprivileged port, and a clean AgentOS environment."}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
