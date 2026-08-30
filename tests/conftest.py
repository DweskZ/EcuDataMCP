"""Test-only filesystem settings.

The development environment can deny pytest access to the usual Windows
``%LOCALAPPDATA%\\Temp\\pytest-of-*`` directory.  Keep the temporary files
used by the tests inside the repository instead; the directory is ignored by
Git and each test receives a unique child that is removed afterwards.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest) -> Iterator[Path]:
    root = Path(__file__).resolve().parents[1] / ".pytest-local"
    root.mkdir(exist_ok=True)
    path = root / f"test-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
