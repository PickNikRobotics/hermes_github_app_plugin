"""Tests for GitHub App auth helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx

from hermes_github_app_plugin.auth import (
    GitHubAppAuth,
    InstallationToken,
    auth_metadata,
    requires_app_jwt,
)
from hermes_github_app_plugin.config import GitHubAppConfig

PRIVATE_KEY = "[REDACTED PRIVATE KEY]\n"


def test_auth_metadata_redacts_token() -> None:
    token = InstallationToken(
        token="ghu_ab...wxyz",
        expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        installation_id="456",
        client_id="123",
        app_slug="hermes-test-agent",
    )

    metadata = auth_metadata(token, repo="ExampleOrg/example-repo")

    assert metadata["auth_mode"] == "github_app"
    assert metadata["actor_expected"] == "hermes-test-agent[bot]"
    assert metadata["token"] == "ghu_…wxyz"


def test_request_includes_installation_token(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("jwt.encode", lambda *_, **__: "jwt-token")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/access_tokens"):
            return httpx.Response(
                201,
                json={"token": "ghu_installation_token", "expires_at": "2030-01-01T00:00:00Z"},
            )
        return httpx.Response(200, json={"full_name": "ExampleOrg/example-repo"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    config = GitHubAppConfig(
        client_id="123",
        installation_id="456",
        private_key=PRIVATE_KEY,
        private_key_source="env",
        app_slug="hermes-test-agent",
    )

    result = GitHubAppAuth(config, client=client).request(
        "GET", "/repos/ExampleOrg/example-repo", repo="ExampleOrg/example-repo"
    )

    assert result["result"] == {"full_name": "ExampleOrg/example-repo"}
    assert seen[0].headers["authorization"] == "Bearer jwt-token"
    assert seen[1].headers["authorization"] == "Bearer ghu_installation_token"
    assert json.loads(json.dumps(result))["auth"]["auth_mode"] == "github_app"


def test_app_request_uses_app_jwt(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("jwt.encode", lambda *_, **__: "jwt-token")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"slug": "hermes-test-agent"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    config = GitHubAppConfig(
        client_id="123",
        installation_id="456",
        private_key=PRIVATE_KEY,
        private_key_source="env",
        app_slug="hermes-test-agent",
    )

    result = GitHubAppAuth(config, client=client).app_request("GET", "/app")

    assert result["result"] == {"slug": "hermes-test-agent"}
    assert seen[0].url.path == "/app"
    assert seen[0].headers["authorization"] == "Bearer jwt-token"
    assert result["auth"]["auth_mode"] == "github_app_jwt"


def test_requires_app_jwt_detects_app_endpoints() -> None:
    assert requires_app_jwt("/app")
    assert requires_app_jwt("/app/installations")
    assert requires_app_jwt("https://api.github.com/app")
    assert not requires_app_jwt("/repos/OWNER/REPO")
