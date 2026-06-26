"""Hermes GitHub App plugin."""

from __future__ import annotations

from pathlib import Path

from . import schemas, tools
from .cli import main as cli_main
from .cli import register_cli

_TOOLSET = "github_app"
_TOOLS = (
    ("github_app_status", schemas.GITHUB_APP_STATUS, tools.github_app_status, "🤖"),
    (
        "github_app_verify_identity",
        schemas.GITHUB_APP_VERIFY_IDENTITY,
        tools.github_app_verify_identity,
        "✅",
    ),
    ("github_app_api", schemas.GITHUB_APP_API, tools.github_app_api, "🐙"),
    ("github_app_graphql", schemas.GITHUB_APP_GRAPHQL, tools.github_app_graphql, "📊"),
    (
        "github_app_create_issue",
        schemas.GITHUB_APP_CREATE_ISSUE,
        tools.github_app_create_issue,
        "📝",
    ),
    (
        "github_app_comment_issue",
        schemas.GITHUB_APP_COMMENT_ISSUE,
        tools.github_app_comment_issue,
        "💬",
    ),
    ("github_app_create_pr", schemas.GITHUB_APP_CREATE_PR, tools.github_app_create_pr, "🔀"),
    ("github_app_comment_pr", schemas.GITHUB_APP_COMMENT_PR, tools.github_app_comment_pr, "💬"),
)


def register(ctx: object) -> None:
    """Register Hermes tools, CLI, and bundled skill."""
    for name, schema, handler, emoji in _TOOLS:
        ctx.register_tool(  # type: ignore[attr-defined]
            name=name,
            toolset=_TOOLSET,
            schema=schema,
            handler=handler,
            emoji=emoji,
        )

    ctx.register_cli_command(  # type: ignore[attr-defined]
        name="hermes-github-app",
        help="Manage the Hermes GitHub App integration",
        setup_fn=register_cli,
        handler_fn=cli_main,
        description="Mint and verify per-agent GitHub App installation tokens.",
    )

    skill_path = Path(__file__).parent / "skills" / "github-app-workflow"
    if skill_path.exists():
        ctx.register_skill("github-app-workflow", skill_path)  # type: ignore[attr-defined]
