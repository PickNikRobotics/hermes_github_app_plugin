"""Hermes tool handlers for GitHub App operations."""

from __future__ import annotations

import json
from typing import Any

import httpx

from .auth import GitHubAppAuth, auth_metadata, requires_app_jwt
from .config import ConfigurationError, load_config


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


def _error(exc: Exception) -> str:
    return _json({"success": False, "error": str(exc), "error_type": type(exc).__name__})


def _auth() -> GitHubAppAuth:
    return GitHubAppAuth(load_config())


def _handle_errors(fn: Any, *args: Any, **kwargs: Any) -> str:
    try:
        return _json({"success": True, **fn(*args, **kwargs)})
    except (ConfigurationError, httpx.HTTPError, KeyError, ValueError) as exc:
        return _error(exc)


def github_app_status(params: dict[str, Any], **_: Any) -> str:
    """Return GitHub App config status without printing secrets."""

    def run() -> dict[str, Any]:
        config = load_config()
        return {
            "configured": True,
            "client_id": config.client_id,
            "installation_id": config.installation_id,
            "app_slug": config.app_slug,
            "private_key_source": config.private_key_source,
            "github_api_url": config.github_api_url,
            "scope_management": "github_app_installation",
        }

    return _handle_errors(run)


def github_app_verify_identity(params: dict[str, Any], **_: Any) -> str:
    """Mint a token and verify App identity/repository access."""

    def run() -> dict[str, Any]:
        repo = _repo(params)
        auth = _auth()
        token = auth.get_installation_token(force_refresh=True)
        app = auth.app_request("GET", "/app")
        repo_probe = auth.request("GET", f"/repos/{repo}", repo=repo) if repo else None
        return {
            "auth": auth_metadata(token, repo=repo),
            "app": app["result"],
            "repository_probe": repo_probe,
        }

    return _handle_errors(run)


def github_app_api(params: dict[str, Any], **_: Any) -> str:
    """Call the GitHub REST API using the configured GitHub App."""

    def run() -> dict[str, Any]:
        method = str(params.get("method", "GET"))
        path = str(params["path"])
        repo = _repo(params)
        body = params.get("json_body")
        json_body = body if isinstance(body, dict) else None
        auth = _auth()
        result = (
            auth.app_request(method, path, json_body=json_body)
            if requires_app_jwt(path)
            else auth.request(method, path, repo=repo, json_body=json_body)
        )
        return result

    return _handle_errors(run)


def github_app_graphql(params: dict[str, Any], **_: Any) -> str:
    """Call GitHub GraphQL using the configured GitHub App."""

    def run() -> dict[str, Any]:
        variables = params.get("variables")
        return _auth().graphql(
            str(params["query"]), variables if isinstance(variables, dict) else None
        )

    return _handle_errors(run)


def github_app_create_issue(params: dict[str, Any], **_: Any) -> str:
    """Create an issue using the GitHub App identity."""

    def run() -> dict[str, Any]:
        repo = _required_repo(params)
        body: dict[str, Any] = {"title": str(params["title"])}
        if params.get("body") is not None:
            body["body"] = str(params["body"])
        labels = params.get("labels")
        if isinstance(labels, list):
            body["labels"] = labels
        assignees = params.get("assignees")
        if isinstance(assignees, list):
            body["assignees"] = assignees
        return _auth().request("POST", f"/repos/{repo}/issues", repo=repo, json_body=body)

    return _handle_errors(run)


def github_app_comment_issue(params: dict[str, Any], **_: Any) -> str:
    """Comment on an issue or PR using the GitHub App identity."""

    def run() -> dict[str, Any]:
        repo = _required_repo(params)
        number = int(params["number"])
        return _auth().request(
            "POST",
            f"/repos/{repo}/issues/{number}/comments",
            repo=repo,
            json_body={"body": str(params["body"])},
        )

    return _handle_errors(run)


def github_app_comment_pr(params: dict[str, Any], **kwargs: Any) -> str:
    """Comment on a pull request using the GitHub App identity."""
    return github_app_comment_issue(params, **kwargs)


def github_app_create_pr(params: dict[str, Any], **_: Any) -> str:
    """Create a pull request using the GitHub App identity."""

    def run() -> dict[str, Any]:
        repo = _required_repo(params)
        body = {
            "title": str(params["title"]),
            "head": str(params["head"]),
            "base": str(params["base"]),
            "body": str(params.get("body", "")),
            "draft": bool(params.get("draft", False)),
        }
        return _auth().request("POST", f"/repos/{repo}/pulls", repo=repo, json_body=body)

    return _handle_errors(run)


def _repo(params: dict[str, Any]) -> str | None:
    value = params.get("repo")
    return str(value) if value else None


def _required_repo(params: dict[str, Any]) -> str:
    repo = _repo(params)
    if not repo:
        raise ValueError("repo is required and must be in OWNER/NAME form")
    return repo
