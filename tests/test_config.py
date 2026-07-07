"""Tests for configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from hermes_github_app_plugin.config import load_config

PRIVATE_KEY = "[REDACTED PRIVATE KEY]\n"


def test_load_config_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_APP_CLIENT_ID", "123")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "456")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", PRIVATE_KEY)

    config = load_config()

    assert config.client_id == "123"
    assert config.installation_id == "456"
    assert config.installation_ids == {}
    assert config.private_key == PRIVATE_KEY


def test_load_config_from_hermes_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key_path = tmp_path / "app.pem"
    key_path.write_text(PRIVATE_KEY, encoding="utf-8")
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        f"""
github_app:
  client_id: 111
  installation_id: 222
  installation_ids:
    ExampleOrg: 333
    ExampleInfra: 444
  private_key_path: {key_path}
  app_slug: hermes-test-agent
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.delenv("GITHUB_APP_CLIENT_ID", raising=False)
    monkeypatch.delenv("GITHUB_APP_INSTALLATION_ID", raising=False)
    monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY_PATH", raising=False)

    config = load_config()

    assert config.client_id == "111"
    assert config.installation_id == "222"
    assert config.installation_ids == {"exampleorg": "333", "exampleinfra": "444"}
    assert config.installation_id_for_repo("ExampleOrg/example-repo") == "333"
    assert config.installation_id_for_repo("ExampleInfra/automation-config") == "444"
    assert config.installation_id_for_repo("Other/repo") == "222"
    assert config.app_slug == "hermes-test-agent"


def test_load_config_installation_ids_from_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_APP_CLIENT_ID", "123")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_IDS", "ExampleOrg=456,ExampleInfra=789")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", PRIVATE_KEY)
    monkeypatch.delenv("GITHUB_APP_INSTALLATION_ID", raising=False)
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    config = load_config()

    assert config.installation_id == "456"
    assert config.installation_id_for_repo("ExampleInfra/automation-config") == "789"
