"""Tests for CLI setup and doctor helpers."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import yaml

from hermes_github_app_plugin import cli

PRIVATE_KEY = "[REDACTED PRIVATE KEY]\n"


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
    (hermes_home).mkdir()
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
