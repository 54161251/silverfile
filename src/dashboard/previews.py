"""Sample returns for the dashboard, computed live by P2's Computation agent from the golden tests.

These are read-only previews of the form and provenance view while the full pipeline is being
integrated. They are labelled as test data and never appear in the returns list.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.agents.computation import compute_return

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "tests" / "golden"


def golden_previews() -> list[dict]:
    previews = []
    for path in sorted(GOLDEN_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        state = data.get("state", {})
        result = compute_return(state)
        previews.append({"name": data.get("name", path.stem), "description": data.get("description", ""),
                         "state": state, "lines": result["lines"], "open_questions": result["open_questions"]})
    return previews
