"""Tests for Hermes plugin registration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hermes_github_app_plugin import register


class FakeContext:
    def __init__(self) -> None:
        self.tools: list[str] = []
        self.cli_commands: list[str] = []
        self.skills: list[tuple[str, Path]] = []

    def register_tool(self, *, name: str, **_: Any) -> None:
        self.tools.append(name)

    def register_cli_command(self, *, name: str, **_: Any) -> None:
        self.cli_commands.append(name)

    def register_skill(self, name: str, path: Path) -> None:
        self.skills.append((name, path))


def test_register_adds_tools_cli_and_skill() -> None:
    ctx = FakeContext()

    register(ctx)

    assert "github_app_status" in ctx.tools
    assert "github_app_create_pr" in ctx.tools
    assert ctx.cli_commands == ["hermes-github-app"]
    assert ctx.skills[0][0] == "github-app-workflow"
