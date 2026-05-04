#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REQUIRED = {
    'docs/reference/preview-release-candidate-checklist-v1.md': [
        'Preview Release Candidate Checklist v1',
        'scripts/acceptance_checks.sh',
        'scripts/final_signoff.sh',
        'setup -> ai>',
    ],
    'docs/reference/preview-release-note-template-v1.md': [
        'Preview Release Note Template v1',
        'Channel: `preview`',
        'Ubuntu 24.04 downstream',
        'Included artifacts',
    ],
    'docs/reference/release-artifact-manifest-contract-v1.md': [
        'Release Artifact Manifest Contract v1',
        '`channel`',
        '`artifacts.review_snapshot`',
        'milestone-bundle',
    ],
}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    for rel, patterns in REQUIRED.items():
        content = (root / rel).read_text(encoding='utf-8')
        for pattern in patterns:
            if pattern not in content:
                print(f'missing pattern in {rel}: {pattern}', file=sys.stderr)
                return 1
    print('preview release contract validation: PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
