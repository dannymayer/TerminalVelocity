from __future__ import annotations

import shutil
from pathlib import Path

import pytest

STATE_ROOT = Path(".pytest-state")


@pytest.fixture
def state_dir(request: pytest.FixtureRequest) -> Path:
    path = STATE_ROOT / request.node.name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    yield path
    if path.exists():
        shutil.rmtree(path)
