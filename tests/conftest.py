"""Shared test isolation: never read the developer's real Hermes config or GitHub App env."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "isolated-hermes-home"))
    for name in list(os.environ):
        if name.startswith(("GITHUB_APP_", "GITHUB_API_URL")):
            monkeypatch.delenv(name)
    for name in ("HTTPS_PROXY", "https_proxy"):
        monkeypatch.delenv(name, raising=False)
