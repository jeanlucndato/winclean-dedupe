"""Add the source tree to the test import path."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture(autouse=True)
def disable_host_system_exclusions_for_isolated_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep temporary test fixtures scannable even on Windows under AppData."""
    monkeypatch.setattr("dupe_sweep.finder.protected_paths", lambda: [])
