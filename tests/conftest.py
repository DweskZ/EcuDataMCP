"""Test-only filesystem settings.

The development environment can deny pytest access to the usual Windows
``%LOCALAPPDATA%\\Temp\\pytest-of-*`` directory.  Keep the temporary files
used by the tests inside the repository instead; the directory is ignored by
Git and each test receives a unique child that is removed afterwards.
"""

from __future__ import annotations

import asyncio
import shutil
import socket
import sys
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


@pytest.fixture(autouse=True)
def _offline_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve every host to a public address instead of asking real DNS.

    Downloads go through the SSRF guard, which resolves the host name before
    pytest-httpx intercepts the request. Without this, ~300 tests needed a
    working resolver, and a slow lookup blew a test's timeout (the BVG
    concurrency test failed once on a CI runner). Tests that care about the
    resolved address patch socket.getaddrinfo themselves, which overrides
    this stub.
    """

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


@pytest.fixture(autouse=True)
def _fresh_module_locks() -> Iterator[None]:
    """Give every helpers module fresh asyncio locks for each test.

    An asyncio.Lock binds to the first event loop that has to wait on it; the
    source clients keep module-level locks (and dicts of locks), and
    pytest-asyncio runs each test in a new loop, so a lock contended in one
    test raised "bound to a different event loop" in the next. Production has
    a single loop, so this is a test-isolation concern only.
    """
    for name, module in list(sys.modules.items()):
        if not name.startswith("helpers.") or module is None:
            continue
        for attr, value in list(vars(module).items()):
            if isinstance(value, asyncio.Lock):
                setattr(module, attr, asyncio.Lock())
            elif isinstance(value, dict) and value and all(
                isinstance(v, asyncio.Lock) for v in value.values()
            ):
                for key in value:
                    value[key] = asyncio.Lock()
    yield
