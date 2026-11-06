"""Tests for GitHub App auth helpers."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from hermes_github_app_plugin.auth import (
    GitHubAppAuth,
    InstallationToken,
    auth_metadata,
    repo_from_path,
    requires_app_jwt,
)
from hermes_github_app_plugin.config import NONO_PHANTOM_TOKEN, GitHubAppConfig

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
        installation_ids={},
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
        installation_ids={},
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


def test_request_chooses_installation_id_for_repo_owner(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("jwt.encode", lambda *_, **__: "jwt-token")
    token_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/access_tokens"):
            token_paths.append(request.url.path)
            installation_id = request.url.path.split("/")[-2]
            return httpx.Response(
                201,
                json={
                    "token": f"ghu_token_{installation_id}",
                    "expires_at": "2030-01-01T00:00:00Z",
                },
            )
        return httpx.Response(200, json={"full_name": "ExampleInfra/automation-config"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    config = GitHubAppConfig(
        client_id="123",
        installation_id="456",
        private_key=PRIVATE_KEY,
        installation_ids={"exampleinfra": "789"},
        private_key_source="env",
        app_slug="hermes-test-agent",
    )

    result = GitHubAppAuth(config, client=client).request(
        "GET", "/repos/ExampleInfra/automation-config"
    )

    assert token_paths == ["/app/installations/789/access_tokens"]
    assert result["auth"]["installation_id"] == "789"
    assert result["auth"]["repository"] == "ExampleInfra/automation-config"


def test_repo_from_path_infers_rest_repo_paths() -> None:
    assert repo_from_path("/repos/OWNER/REPO/issues") == "OWNER/REPO"
    assert repo_from_path("https://api.github.com/repos/OWNER/REPO") == "OWNER/REPO"
    assert repo_from_path("/installation/repositories") is None


def _broker_config() -> GitHubAppConfig:
    return GitHubAppConfig(
        client_id="123",
        installation_id="456",
        private_key="",
        installation_ids={"exampleinfra": "789"},
        private_key_source="token broker: nono",
        app_slug="hermes-test-agent",
        token_broker="nono",
    )


def _fail_on_network(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"unexpected network call in token broker mode: {request.url}")


def test_broker_installation_token_makes_no_network_call() -> None:
    client = httpx.Client(transport=httpx.MockTransport(_fail_on_network))
    auth = GitHubAppAuth(_broker_config(), client=client)
    before = datetime.now(timezone.utc)

    token = auth.get_installation_token(repo="ExampleInfra/automation-config")

    assert token.token == NONO_PHANTOM_TOKEN
    assert token.installation_id == "789"
    assert token.app_slug == "hermes-test-agent"
    assert token.client_id == "123"
    assert token.token_broker == "nono"
    assert timedelta(hours=1) <= token.expires_at - before < timedelta(hours=1, minutes=1)
    # The brokered token is cached like a minted one, so repeat calls stay offline too.
    assert auth.get_installation_token(repo="ExampleInfra/automation-config") is token


def test_broker_create_jwt_returns_placeholder_without_signing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_signing(*_: object, **__: object) -> str:
        raise AssertionError("token broker mode must not sign with a private key")

    monkeypatch.setattr("jwt.encode", fail_if_signing)
    client = httpx.Client(transport=httpx.MockTransport(_fail_on_network))

    assert GitHubAppAuth(_broker_config(), client=client).create_jwt() == NONO_PHANTOM_TOKEN


def test_broker_request_sends_placeholder_and_reports_broker() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"full_name": "ExampleInfra/automation-config"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = GitHubAppAuth(_broker_config(), client=client).request(
        "GET", "/repos/ExampleInfra/automation-config"
    )

    assert len(seen) == 1
    assert seen[0].url.path == "/repos/ExampleInfra/automation-config"
    assert seen[0].headers["authorization"] == "Bearer nono-phantom-github-app"
    assert result["auth"]["installation_id"] == "789"
    assert result["auth"]["token_broker"] == "nono"
    assert result["auth"]["token"] == "nono…-app"


def test_broker_app_request_sends_placeholder() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"slug": "hermes-test-agent"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = GitHubAppAuth(_broker_config(), client=client).app_request("GET", "/app")

    assert seen[0].headers["authorization"] == "Bearer nono-phantom-github-app"
    assert result["auth"]["token_broker"] == "nono"


def test_auth_metadata_without_broker_reports_null_token_broker() -> None:
    token = InstallationToken(
        token="ghu_ab...wxyz",
        expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        installation_id="456",
        client_id="123",
        app_slug=None,
    )

    assert auth_metadata(token)["token_broker"] is None
