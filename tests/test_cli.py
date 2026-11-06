"""Tests for CLI setup and doctor helpers."""

from __future__ import annotations

import argparse
from pathlib import Path

import httpx
import pytest
import yaml

from hermes_github_app_plugin import cli
from hermes_github_app_plugin.auth import GitHubAppAuth
from hermes_github_app_plugin.config import NONO_PHANTOM_TOKEN, GitHubAppConfig

PRIVATE_KEY = "[REDACTED PRIVATE KEY]\n"

BROKER_CONFIG = """
github_app:
  client_id: Iv1.exampleclientid
  installation_id: 987654
  token_broker: nono
"""


def _write_hermes_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> Path:
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir(parents=True, exist_ok=True)
    (hermes_home / "config.yaml").write_text(body, encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    return hermes_home


def _setup_args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "github_app_command": "setup",
        "client_id": "Iv1.exampleclientid",
        "installation_id": "987654",
        "installation_id_for": [],
        "private_key_path": None,
        "app_slug": None,
        "non_interactive": True,
        "repo": None,
        "skip_verify": True,
        "token_broker": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_setup_non_interactive_writes_config_and_skips_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    hermes_home = tmp_path / ".hermes"
    key_path = tmp_path / "app.pem"
    key_path.write_text(PRIVATE_KEY, encoding="utf-8")
    key_path.chmod(0o600)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    args = argparse.Namespace(
        github_app_command="setup",
        client_id="Iv1.exampleclientid",
        installation_id="987654",
        installation_id_for=[],
        private_key_path=str(key_path),
        app_slug="hermes-test-agent",
        non_interactive=True,
        repo=None,
        skip_verify=True,
    )

    assert cli.main(args) == 0

    data = yaml.safe_load((hermes_home / "config.yaml").read_text(encoding="utf-8"))
    assert data["github_app"] == {
        "client_id": "Iv1.exampleclientid",
        "installation_id": "987654",
        "private_key_path": str(key_path),
        "app_slug": "hermes-test-agent",
    }
    assert "Skipped verification" in capsys.readouterr().out


def test_setup_prompts_mark_optional(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    hermes_home = tmp_path / ".hermes"
    key_path = tmp_path / "app.pem"
    key_path.write_text(PRIVATE_KEY, encoding="utf-8")
    key_path.chmod(0o600)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    responses = iter(["Iv1.exampleclientid", "987654", str(key_path), ""])
    prompts: list[str] = []

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return next(responses)

    monkeypatch.setattr("builtins.input", fake_input)
    args = argparse.Namespace(
        github_app_command="setup",
        client_id=None,
        installation_id=None,
        installation_id_for=[],
        private_key_path=None,
        app_slug=None,
        non_interactive=False,
        repo=None,
        skip_verify=True,
    )

    assert cli.main(args) == 0

    optional_prompts = [prompt for prompt in prompts if "optional" in prompt]
    assert len(optional_prompts) == 1
    assert all("(optional)" in prompt for prompt in optional_prompts)
    assert "Required values are unmarked" in capsys.readouterr().out


def test_doctor_skip_network_reports_local_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    hermes_home = tmp_path / ".hermes"
    key_path = tmp_path / "app.pem"
    key_path.write_text(PRIVATE_KEY, encoding="utf-8")
    key_path.chmod(0o600)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        f"""
github_app:
  client_id: Iv1.exampleclientid
  installation_id: 987654
  private_key_path: {key_path}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(cli.shutil, "which", lambda command: f"/usr/bin/{command}")

    assert cli._doctor(None, skip_network=True) == 0

    output = capsys.readouterr().out
    assert "✓ GitHub App config loaded" in output
    assert "✓ private key file permissions: 0o600" in output
    assert "Local doctor passed" in output


def test_api_routes_app_paths_to_app_jwt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class FakeAuth:
        def __init__(self, config: object) -> None:
            self.config = config

        def app_request(
            self, method: str, path: str, json_body: dict[str, object] | None = None
        ) -> dict[str, object]:
            return {"status_code": 200, "result": {"path": path, "method": method}}

        def request(self, *args: object, **kwargs: object) -> dict[str, object]:
            raise AssertionError("installation-token request should not be used for /app")

    monkeypatch.setattr(cli, "load_config", object)
    monkeypatch.setattr(cli, "GitHubAppAuth", FakeAuth)

    assert cli._api("GET", "/app", repo=None, body=None) == 0

    output = capsys.readouterr().out
    assert '"status_code": 200' in output


def test_api_routes_repo_paths_to_installation_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class FakeAuth:
        def __init__(self, config: object) -> None:
            self.config = config

        def app_request(self, *args: object, **kwargs: object) -> dict[str, object]:
            raise AssertionError("app JWT request should not be used for repo APIs")

        def request(
            self,
            method: str,
            path: str,
            repo: str | None = None,
            json_body: dict[str, object] | None = None,
        ) -> dict[str, object]:
            return {"status_code": 200, "result": {"path": path, "repo": repo, "method": method}}

    monkeypatch.setattr(cli, "load_config", object)
    monkeypatch.setattr(cli, "GitHubAppAuth", FakeAuth)

    assert cli._api("GET", "/repos/OWNER/REPO", repo="OWNER/REPO", body=None) == 0

    output = capsys.readouterr().out
    assert '"repo": "OWNER/REPO"' in output


def test_setup_non_interactive_writes_owner_installation_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hermes_home = tmp_path / ".hermes"
    key_path = tmp_path / "app.pem"
    key_path.write_text(PRIVATE_KEY, encoding="utf-8")
    key_path.chmod(0o600)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    args = argparse.Namespace(
        github_app_command="setup",
        client_id="Iv1.exampleclientid",
        installation_id="987654",
        installation_id_for=["ExampleOrg=111", "ExampleInfra=222"],
        private_key_path=str(key_path),
        app_slug="hermes-test-agent",
        non_interactive=True,
        repo=None,
        skip_verify=True,
    )

    assert cli.main(args) == 0

    data = yaml.safe_load((hermes_home / "config.yaml").read_text(encoding="utf-8"))
    assert data["github_app"]["installation_ids"] == {
        "exampleorg": "111",
        "exampleinfra": "222",
    }


def test_setup_token_broker_writes_config_without_private_key_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale_key = tmp_path / "stale.pem"
    hermes_home = _write_hermes_config(
        tmp_path,
        monkeypatch,
        f"github_app:\n  private_key_path: {stale_key}\n",
    )
    monkeypatch.setattr(
        "builtins.input", lambda prompt: pytest.fail(f"unexpected prompt: {prompt}")
    )

    assert cli.main(_setup_args(token_broker="nono", app_slug=None)) == 0

    section = yaml.safe_load((hermes_home / "config.yaml").read_text(encoding="utf-8"))[
        "github_app"
    ]
    assert section == {
        "client_id": "Iv1.exampleclientid",
        "installation_id": "987654",
        "token_broker": "nono",
    }


def test_setup_token_broker_rejects_private_key_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    key_path = tmp_path / "app.pem"
    key_path.write_text(PRIVATE_KEY, encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))

    assert cli.main(_setup_args(token_broker="nono", private_key_path=str(key_path))) == 1

    assert "cannot be combined with --token-broker" in capsys.readouterr().err
    assert not (tmp_path / ".hermes" / "config.yaml").exists()


def test_setup_rejects_unsupported_token_broker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))

    assert cli.main(_setup_args(token_broker="vault")) == 1

    assert "supported: nono" in capsys.readouterr().err


def test_setup_without_broker_clears_stale_token_broker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key_path = tmp_path / "app.pem"
    key_path.write_text(PRIVATE_KEY, encoding="utf-8")
    key_path.chmod(0o600)
    hermes_home = _write_hermes_config(tmp_path, monkeypatch, BROKER_CONFIG)

    assert cli.main(_setup_args(private_key_path=str(key_path))) == 0

    section = yaml.safe_load((hermes_home / "config.yaml").read_text(encoding="utf-8"))[
        "github_app"
    ]
    assert "token_broker" not in section
    assert section["private_key_path"] == str(key_path)


def test_doctor_token_broker_skip_network_checks_proxy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_hermes_config(tmp_path, monkeypatch, BROKER_CONFIG)
    monkeypatch.setenv("HTTPS_PROXY", "http://nono-proxy.test:8080")
    monkeypatch.setattr(cli.shutil, "which", lambda command: f"/usr/bin/{command}")

    assert cli._doctor(None, skip_network=True) == 0

    output = capsys.readouterr().out
    assert "✓ token broker: nono" in output
    assert "✓ HTTPS_PROXY set: set" in output
    assert "private key" not in output
    assert "Local doctor passed" in output


def test_doctor_token_broker_without_proxy_hints_not_inside_nono(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_hermes_config(tmp_path, monkeypatch, BROKER_CONFIG)
    monkeypatch.setattr(cli.shutil, "which", lambda command: f"/usr/bin/{command}")

    assert cli._doctor(None, skip_network=True) == 1

    output = capsys.readouterr().out
    assert "✗ HTTPS_PROXY set: not set; agent does not appear to be running inside nono" in output


def test_doctor_token_broker_network_checks_send_placeholder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_hermes_config(tmp_path, monkeypatch, BROKER_CONFIG)
    monkeypatch.setenv("HTTPS_PROXY", "http://nono-proxy.test:8080")
    monkeypatch.setattr(cli.shutil, "which", lambda command: f"/usr/bin/{command}")
    seen_auth: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert not request.url.path.endswith("/access_tokens"), "broker mode must not mint"
        seen_auth.append(request.headers["authorization"])
        if request.url.path == "/app":
            return httpx.Response(200, json={"slug": "hermes-test-agent"})
        return httpx.Response(200, json={"full_name": "OWNER/REPO"})

    class BrokerAuth(GitHubAppAuth):
        def __init__(self, config: GitHubAppConfig) -> None:
            super().__init__(config, client=httpx.Client(transport=httpx.MockTransport(handler)))

    monkeypatch.setattr(cli, "GitHubAppAuth", BrokerAuth)

    assert cli._doctor("OWNER/REPO", skip_network=False) == 0

    assert seen_auth == [f"Bearer {NONO_PHANTOM_TOKEN}"] * 2
    output = capsys.readouterr().out
    assert "✓ installation token brokered by nono" in output
    assert "✓ /app API reachable: hermes-test-agent" in output
    assert "✓ repository access verified: OWNER/REPO" in output


def test_token_command_in_broker_mode_prints_placeholder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_hermes_config(tmp_path, monkeypatch, BROKER_CONFIG)
    args = argparse.Namespace(github_app_command="token", repo=None, json=False)

    assert cli.main(args) == 0

    captured = capsys.readouterr()
    assert captured.out == f"{NONO_PHANTOM_TOKEN}\n"
    assert "the nono proxy injects it" in captured.err
