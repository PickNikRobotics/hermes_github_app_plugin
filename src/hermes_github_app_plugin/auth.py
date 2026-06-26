"""GitHub App JWT and installation-token handling."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import jwt

from .config import GitHubAppConfig

_MIN_REDACT_LENGTH = 8


@dataclass(frozen=True)
class InstallationToken:
    """GitHub App installation token plus metadata."""

    token: str
    expires_at: datetime
    installation_id: str
    client_id: str
    app_slug: str | None

    @property
    def redacted(self) -> str:
        """Return a safe representation for logs/tool output."""
        if len(self.token) <= _MIN_REDACT_LENGTH:
            return "***"
        return f"{self.token[:4]}…{self.token[-4:]}"


class GitHubAppAuth:
    """Mint and cache short-lived installation access tokens."""

    def __init__(self, config: GitHubAppConfig, client: httpx.Client | None = None) -> None:
        self._config = config
        self._client = client or httpx.Client(timeout=20)
        self._cached_token: InstallationToken | None = None

    @property
    def config(self) -> GitHubAppConfig:
        return self._config

    def create_jwt(self) -> str:
        """Create a GitHub App JWT for installation-token exchange."""
        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + 9 * 60, "iss": self._config.client_id}
        encoded = jwt.encode(payload, self._config.private_key, algorithm="RS256")
        return str(encoded)

    def get_installation_token(self, *, force_refresh: bool = False) -> InstallationToken:
        """Return a valid installation token, refreshing when near expiry."""
        if (
            not force_refresh
            and self._cached_token is not None
            and self._cached_token.expires_at > datetime.now(timezone.utc) + timedelta(minutes=5)
        ):
            return self._cached_token

        response = self._client.post(
            f"{self._config.github_api_url}/app/installations/"
            f"{self._config.installation_id}/access_tokens",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.create_jwt()}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        response.raise_for_status()
        data = response.json()
        expires_at_raw = str(data["expires_at"])
        expires_at = datetime.fromisoformat(expires_at_raw.replace("Z", "+00:00"))
        token = InstallationToken(
            token=str(data["token"]),
            expires_at=expires_at,
            installation_id=self._config.installation_id,
            client_id=self._config.client_id,
            app_slug=self._config.app_slug,
        )
        self._cached_token = token
        return token

    def app_request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call a GitHub App endpoint using the app JWT.

        Endpoints like `GET /app` authenticate as the GitHub App itself and
        reject installation access tokens. Repository and user endpoints should
        continue to use `request()`, which authenticates as the installation.
        """
        url = (
            path if path.startswith("http") else f"{self._config.github_api_url}/{path.lstrip('/')}"
        )
        response = self._client.request(
            method.upper(),
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.create_jwt()}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json=json_body,
            params=params,
        )
        response.raise_for_status()
        return {
            "auth": {
                "auth_mode": "github_app_jwt",
                "client_id": self._config.client_id,
                "app_slug": self._config.app_slug,
                "installation_id": self._config.installation_id,
            },
            "status_code": response.status_code,
            "result": response.json() if response.content else {"ok": True},
        }

    def request(
        self,
        method: str,
        path: str,
        *,
        repo: str | None = None,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call the GitHub REST API using the installation token."""
        token = self.get_installation_token()
        url = (
            path if path.startswith("http") else f"{self._config.github_api_url}/{path.lstrip('/')}"
        )
        response = self._client.request(
            method.upper(),
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token.token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json=json_body,
            params=params,
        )
        response.raise_for_status()
        parsed = response.json() if response.content else {"ok": True}
        return {
            "auth": auth_metadata(token, repo=repo),
            "status_code": response.status_code,
            "result": parsed,
        }

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call GitHub GraphQL API using the installation token."""
        token = self.get_installation_token()
        response = self._client.post(
            f"{self._config.github_api_url}/graphql",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token.token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={"query": query, "variables": variables or {}},
        )
        response.raise_for_status()
        return {
            "auth": auth_metadata(token),
            "status_code": response.status_code,
            "result": response.json(),
        }


def auth_metadata(token: InstallationToken, *, repo: str | None = None) -> dict[str, str | None]:
    """Build safe auth metadata for tool responses."""
    actor = f"{token.app_slug}[bot]" if token.app_slug else None
    return {
        "auth_mode": "github_app",
        "client_id": token.client_id,
        "app_slug": token.app_slug,
        "installation_id": token.installation_id,
        "actor_expected": actor,
        "repository": repo,
        "token": token.redacted,
        "expires_at": token.expires_at.isoformat(),
    }
