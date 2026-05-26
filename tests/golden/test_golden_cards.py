"""Golden-file tests: each fixture jsonl should render to a stored expected card JSON."""

import json
from pathlib import Path

import pytest

from feishu_bot_claude_win.rendering.turn import JsonlEvent, group_into_turns, render_turn_to_card

FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXPECTED_DIR = Path(__file__).parent / "expected"



def _load_or_write_golden(name: str, actual: dict, write: bool = False) -> dict | None:
    """Load expected/<name>.card.json; if write=True or missing, write the actual."""
    EXPECTED_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPECTED_DIR / f"{name}.card.json"
    if write or not path.exists():
        path.write_text(json.dumps(actual, ensure_ascii=False, indent=2), encoding="utf-8")
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", [
    "turn_simple",
    "turn_with_read",
    "turn_with_bash_long",
    "turn_with_subagent",
])
def test_golden_card(name, request):
    """Render fixture jsonl and compare to expected golden JSON."""
    fixture = FIXTURES_DIR / f"{name}.jsonl"
    events = list(JsonlEvent.load_file(fixture))
    turns = group_into_turns(events)
    assert turns, f"{name}: no turns produced"
    actual = render_turn_to_card(turns[-1], project_name="test-project")

    if request.config.getoption("--update-golden", default=False):
        _load_or_write_golden(name, actual, write=True)
        return

    expected = _load_or_write_golden(name, actual, write=False)
    if expected is None:
        pytest.fail(f"No golden file for {name}. Auto-created — re-run to verify.")
    assert actual == expected, (
        f"{name}: rendered card differs from golden.\n"
        f"Run with --update-golden to accept the new output."
    )
