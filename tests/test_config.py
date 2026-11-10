"""Tests for configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from hermes_github_app_plugin.config import ConfigurationError, load_config

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


def test_token_broker_from_environment_ignores_missing_private_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_APP_CLIENT_ID", "123")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "456")
    monkeypatch.setenv("GITHUB_APP_TOKEN_BROKER", "nono")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_PATH", str(tmp_path / "missing.pem"))
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", PRIVATE_KEY)

    config = load_config()

    assert config.token_broker == "nono"
    assert config.private_key == ""
    assert config.private_key_source == "token broker: nono"
    assert config.client_id == "123"
    assert config.installation_id == "456"


def test_token_broker_from_hermes_yaml_ignores_private_key_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        f"""
github_app:
  client_id: "111"
  installation_id: "222"
  private_key_path: {tmp_path / "missing.pem"}
  token_broker: nono
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    config = load_config()

    assert config.token_broker == "nono"
    assert config.private_key == ""
    assert config.private_key_source == "token broker: nono"


def test_private_key_still_required_without_token_broker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_APP_CLIENT_ID", "123")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "456")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_PATH", str(tmp_path / "missing.pem"))

    with pytest.raises(ConfigurationError, match="private key file does not exist"):
        load_config()


@pytest.mark.parametrize("value", ["vault", "false"])
def test_unsupported_token_broker_from_environment_is_rejected(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("GITHUB_APP_CLIENT_ID", "123")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "456")
    monkeypatch.setenv("GITHUB_APP_TOKEN_BROKER", value)

    with pytest.raises(ConfigurationError, match="supported: nono"):
        load_config()


def test_unsupported_token_broker_from_hermes_yaml_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        'github_app:\n  client_id: "111"\n  installation_id: "222"\n  token_broker: vault\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    with pytest.raises(ConfigurationError, match=r"github_app\.token_broker.*supported: nono"):
        load_config()
