"""Tool schemas exposed to Hermes."""

from __future__ import annotations

from typing import Any

_JSON_BODY = {"type": "object", "description": "JSON body for the GitHub API request."}
_REPO = {"type": "string", "description": "Repository in OWNER/NAME form."}


def _schema(
    name: str, description: str, properties: dict[str, Any], required: list[str]
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required},
    }


GITHUB_APP_STATUS = _schema(
    "github_app_status",
    "Show configured per-agent GitHub App identity without revealing secrets.",
    {"repo": _REPO},
    [],
)

GITHUB_APP_VERIFY_IDENTITY = _schema(
    "github_app_verify_identity",
    (
        "Mint an installation token, call /app, and optionally probe repository access. "
        "Use before GitHub writes."
    ),
    {"repo": _REPO},
    [],
)

GITHUB_APP_API = _schema(
    "github_app_api",
    (
        "Call GitHub REST API using the configured GitHub App installation token. "
        "Prefer this over bare gh."
    ),
    {
        "method": {"type": "string", "description": "HTTP method, default GET."},
        "path": {
            "type": "string",
            "description": "GitHub API path, e.g. /repos/OWNER/REPO/issues.",
        },
        "repo": _REPO,
        "json_body": _JSON_BODY,
    },
    ["path"],
)

GITHUB_APP_GRAPHQL = _schema(
    "github_app_graphql",
    "Call GitHub GraphQL using the configured GitHub App installation token.",
    {
        "query": {"type": "string", "description": "GraphQL query."},
        "variables": {"type": "object", "description": "GraphQL variables."},
    },
    ["query"],
)

GITHUB_APP_CREATE_ISSUE = _schema(
    "github_app_create_issue",
    "Create a GitHub issue as the per-agent GitHub App bot.",
    {
        "repo": _REPO,
        "title": {"type": "string"},
        "body": {"type": "string"},
        "labels": {"type": "array", "items": {"type": "string"}},
        "assignees": {"type": "array", "items": {"type": "string"}},
    },
    ["repo", "title"],
)

GITHUB_APP_COMMENT_ISSUE = _schema(
    "github_app_comment_issue",
    "Comment on a GitHub issue as the per-agent GitHub App bot.",
    {"repo": _REPO, "number": {"type": "integer"}, "body": {"type": "string"}},
    ["repo", "number", "body"],
)

GITHUB_APP_CREATE_PR = _schema(
    "github_app_create_pr",
    "Create a pull request as the per-agent GitHub App bot.",
    {
        "repo": _REPO,
        "title": {"type": "string"},
        "head": {"type": "string", "description": "Head branch."},
        "base": {"type": "string", "description": "Base branch."},
        "body": {"type": "string"},
        "draft": {"type": "boolean"},
    },
    ["repo", "title", "head", "base"],
)

GITHUB_APP_COMMENT_PR = _schema(
    "github_app_comment_pr",
    "Comment on a GitHub pull request as the per-agent GitHub App bot.",
    {"repo": _REPO, "number": {"type": "integer"}, "body": {"type": "string"}},
    ["repo", "number", "body"],
)
