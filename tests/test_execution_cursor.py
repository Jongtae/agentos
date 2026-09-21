import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts" / "validate_execution_cursor.py"
SPEC = importlib.util.spec_from_file_location("validate_execution_cursor", PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def _comment(**overrides):
    cursor = {
        "schema": "agentos-execution-cursor/v1",
        "generation": 1,
        "epic_issue": 386,
        "main_sha": "a" * 40,
        "contracts": {
            "AGENTS.md": "b" * 40,
            "docs/goal-execution-contract.en.md": "c" * 40,
            "docs/pa1-parallel-delivery.en.md": "d" * 40,
        },
        "completed_children": [387, 388],
        "current": [{
            "issue": 389,
            "pr": 403,
            "head_sha": "e" * 40,
            "state": "final_review_required",
            "next_action": "obtain final-head review",
        }],
        "waiting": [{"issue": 393, "waiting_for": [389, 391, 392]}],
        "owner_validation_pending": [],
        "protocol": {"issue": 410, "status": "active"},
    }
    cursor.update(overrides)
    return f"{module.MARKER}\n\n```json\n{json.dumps(cursor)}\n```\n"


def test_valid_cursor_comment_parses():
    cursor = module.parse_cursor_comment(_comment())
    assert cursor["generation"] == 1
    assert cursor["current"][0]["pr"] == 403


@pytest.mark.parametrize(
    "text,match",
    [
        ("no marker", "marker"),
        (_comment(generation=0), "generation"),
        (_comment(main_sha="abc"), "main_sha"),
        (_comment(completed_children=[387, 387]), "unique"),
        (
            _comment(
                completed_children=[389],
                current=[{"issue": 389, "pr": 403, "head_sha": "e" * 40, "state": "review", "next_action": "review"}],
            ),
            "overlap",
        ),
    ],
)
def test_invalid_cursor_comment_is_rejected(text, match):
    with pytest.raises(ValueError, match=match):
        module.parse_cursor_comment(text)
