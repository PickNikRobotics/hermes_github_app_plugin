"""Configuration loading for the Hermes GitHub App plugin."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigurationError(RuntimeError):
    """Raised when GitHub App configuration is missing or invalid."""


@dataclass(frozen=True)
class GitHubAppConfig:
    """Per-agent GitHub App configuration."""

    client_id: str
    installation_id: str
    private_key: str
    private_key_source: str
    app_slug: str | None = None
    github_api_url: str = "https://api.github.com"


def hermes_home() -> Path:
    """Return the configured Hermes home directory."""
    return Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser()


def config_path() -> Path:
    """Return the Hermes config.yaml path."""
    return hermes_home() / "config.yaml"


def _read_yaml_file() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return dict(data) if isinstance(data, Mapping) else {}


def _read_config_yaml() -> Mapping[str, Any]:
    data = _read_yaml_file()
    section = data.get("github_app", {})
    if isinstance(section, Mapping):
        return section
    return {}


def write_github_app_config(values: Mapping[str, Any]) -> Path:
    """Merge GitHub App values into ~/.hermes/config.yaml and return the path written."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _read_yaml_file()
    section = data.get("github_app")
    if not isinstance(section, dict):
        section = {}
        data["github_app"] = section
    for key, value in values.items():
        if value in (None, "", (), []):
            section.pop(key, None)
        else:
            section[key] = value
    # Remove legacy local allowlist keys if setup rewrites an older config.
    section.pop("allowed_repos", None)
    section.pop("allowed_owners", None)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, default_flow_style=False), encoding="utf-8"
    )
    return path


def _read_private_key(section: Mapping[str, Any]) -> tuple[str, str]:
    inline_key = os.environ.get("GITHUB_APP_PRIVATE_KEY") or str(section.get("private_key", ""))
    if inline_key:
        return inline_key.replace("\\n", "\n"), "GITHUB_APP_PRIVATE_KEY"

    key_path_raw = os.environ.get("GITHUB_APP_PRIVATE_KEY_PATH") or str(
        section.get("private_key_path", "")
    )
    if not key_path_raw:
        raise ConfigurationError(
            "missing GitHub App private key: set GITHUB_APP_PRIVATE_KEY_PATH, "
            "GITHUB_APP_PRIVATE_KEY, or github_app.private_key_path"
        )
    key_path = Path(key_path_raw).expanduser()
    if not key_path.exists():
        raise ConfigurationError(f"GitHub App private key file does not exist: {key_path}")
    return key_path.read_text(encoding="utf-8"), str(key_path)


def load_config() -> GitHubAppConfig:
    """Load plugin configuration from environment variables and Hermes config.yaml."""
    section = _read_config_yaml()
    client_id = os.environ.get("GITHUB_APP_CLIENT_ID") or str(section.get("client_id", ""))
    installation_id = os.environ.get("GITHUB_APP_INSTALLATION_ID") or str(
        section.get("installation_id", "")
    )
    if not client_id:
        raise ConfigurationError(
            "missing GitHub App client ID: set GITHUB_APP_CLIENT_ID or github_app.client_id"
        )
    if not installation_id:
        raise ConfigurationError(
            "missing GitHub App installation ID: set GITHUB_APP_INSTALLATION_ID "
            "or github_app.installation_id"
        )
    private_key, private_key_source = _read_private_key(section)
    return GitHubAppConfig(
        client_id=client_id,
        installation_id=installation_id,
        private_key=private_key,
        private_key_source=private_key_source,
        app_slug=os.environ.get("GITHUB_APP_SLUG") or section.get("app_slug"),
        github_api_url=os.environ.get("GITHUB_API_URL")
        or str(section.get("github_api_url", "https://api.github.com")).rstrip("/"),
    )
