"""CLI commands and gh/git wrappers for GitHub App identity."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, NoReturn

import httpx

from .auth import GitHubAppAuth, auth_metadata
from .config import ConfigurationError, load_config, write_github_app_config


def register_cli(parser: argparse.ArgumentParser) -> None:
    """Register `hermes hermes-github-app ...` subcommands."""
    subparsers = parser.add_subparsers(dest="github_app_command", required=True)

    setup = subparsers.add_parser("setup", help="Interactively configure GitHub App auth")
    setup.add_argument("--repo", help="Optional OWNER/REPO to verify after setup")
    setup.add_argument(
        "--non-interactive", action="store_true", help="Read values from flags/env only"
    )
    setup.add_argument("--client-id", help="GitHub App client ID")
    setup.add_argument("--installation-id", help="GitHub App installation ID")
    setup.add_argument("--private-key-path", help="Path to GitHub App private key PEM")
    setup.add_argument("--app-slug", help="Optional GitHub App slug, e.g. my-agent")
    setup.add_argument(
        "--skip-verify", action="store_true", help="Write config without minting a token"
    )

    doctor = subparsers.add_parser("doctor", help="Run installation and auth diagnostics")
    doctor.add_argument("--repo", help="Optional OWNER/REPO access probe")
    doctor.add_argument("--skip-network", action="store_true", help="Skip GitHub network checks")

    status = subparsers.add_parser("status", help="Verify GitHub App configuration and identity")
    status.add_argument("--repo", help="Optional OWNER/REPO access probe")

    token = subparsers.add_parser("token", help="Print an installation token")
    token.add_argument("--repo", help="Optional OWNER/REPO metadata tag")
    token.add_argument("--json", action="store_true", help="Print JSON metadata and token")

    api = subparsers.add_parser("api", help="Call a GitHub REST API path")
    api.add_argument("path", help="GitHub REST API path, e.g. /repos/OWNER/REPO")
    api.add_argument("--method", default="GET")
    api.add_argument("--repo", help="Optional OWNER/REPO metadata tag")
    api.add_argument("--data", help="JSON request body")


def main(args: argparse.Namespace | None = None) -> int:
    """Run the plugin CLI."""
    if args is None:
        parser = argparse.ArgumentParser(prog="hermes-github-app")
        register_cli(parser)
        args = parser.parse_args()

    try:
        command = args.github_app_command
        if command == "setup":
            return _setup(args)
        if command == "doctor":
            return _doctor(args.repo, skip_network=bool(args.skip_network))
        if command == "status":
            return _status(args.repo)
        if command == "token":
            return _token(args.repo, json_output=bool(args.json))
        if command == "api":
            body = json.loads(args.data) if args.data else None
            return _api(args.method, args.path, repo=args.repo, body=body)
        raise ConfigurationError(f"unknown command: {command}")
    except (ConfigurationError, httpx.HTTPError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def gh_app_main() -> NoReturn:
    """Entry point for `gh-app` wrapper."""
    args = sys.argv[1:]
    if not args or args[0] in {"-h", "--help"}:
        print("usage: gh-app [--repo OWNER/REPO] [--] <gh args...>")
        print("Runs gh with GH_TOKEN/GITHUB_TOKEN set to a GitHub App installation token.")
        raise SystemExit(0)
    _, child_args = _extract_repo(args)
    config = load_config()
    token = GitHubAppAuth(config).get_installation_token()
    env = os.environ.copy()
    env["GH_TOKEN"] = token.token
    env["GITHUB_TOKEN"] = token.token
    raise SystemExit(subprocess.call(["gh", *child_args], env=env))


def git_app_main() -> NoReturn:
    """Entry point for `git-app` wrapper with temporary askpass credentials."""
    if len(sys.argv) <= 1 or sys.argv[1] in {"-h", "--help"}:
        print("usage: git-app [--repo OWNER/REPO] [--] <git args...>")
        print("Runs git with a temporary askpass helper backed by a GitHub App token.")
        raise SystemExit(0)
    _, child_args = _extract_repo(sys.argv[1:])
    config = load_config()
    token = GitHubAppAuth(config).get_installation_token()
    with tempfile.TemporaryDirectory(prefix="git-app-") as temp_dir:
        askpass = Path(temp_dir) / "askpass.sh"
        askpass.write_text(
            "#!/bin/sh\n"
            'case "$1" in\n'
            "*Username*) printf '%s\\n' 'x-access-token' ;;\n"
            f"*Password*) printf '%s\\n' '{token.token}' ;;\n"
            "*) printf '\\n' ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        askpass.chmod(0o700)
        env = os.environ.copy()
        env["GIT_ASKPASS"] = str(askpass)
        env["GIT_TERMINAL_PROMPT"] = "0"
        raise SystemExit(subprocess.call(["git", *child_args], env=env))


def _setup(args: argparse.Namespace) -> int:
    """Interactively write GitHub App configuration."""
    print("Hermes GitHub App setup")
    print("Required values are unmarked. Optional prompts include '(optional)'.")
    values = {
        "client_id": _value_or_prompt(
            args.client_id,
            "GitHub App client ID",
            env="GITHUB_APP_CLIENT_ID",
            required=True,
            non_interactive=bool(args.non_interactive),
        ),
        "installation_id": _value_or_prompt(
            args.installation_id,
            "GitHub App installation ID",
            env="GITHUB_APP_INSTALLATION_ID",
            required=True,
            non_interactive=bool(args.non_interactive),
        ),
        "private_key_path": _value_or_prompt(
            args.private_key_path,
            "GitHub App private key path",
            env="GITHUB_APP_PRIVATE_KEY_PATH",
            required=True,
            non_interactive=bool(args.non_interactive),
        ),
        "app_slug": _value_or_prompt(
            args.app_slug,
            "GitHub App slug (optional)",
            env="GITHUB_APP_SLUG",
            required=False,
            non_interactive=bool(args.non_interactive),
        ),
    }
    key_path = Path(str(values["private_key_path"])).expanduser()
    if not key_path.exists():
        raise ConfigurationError(f"private key file does not exist: {key_path}")
    _warn_private_key_permissions(key_path)
    written = write_github_app_config(values)
    print(f"Wrote GitHub App config to {written}")
    if args.skip_verify:
        print("Skipped verification. Run `hermes-github-app doctor --repo OWNER/REPO` next.")
        return 0
    return _doctor(args.repo, skip_network=False)


def _doctor(repo: str | None, *, skip_network: bool) -> int:
    """Run local and optional network diagnostics."""
    checks: list[tuple[str, bool, str]] = []
    checks.append(("hermes-github-app command installed", True, sys.argv[0]))
    for command in ("gh", "git", "gh-app", "git-app"):
        path = shutil.which(command)
        checks.append((f"{command} on PATH", path is not None, path or "not found"))

    try:
        config = load_config()
        checks.append(("GitHub App config loaded", True, "client_id and installation_id present"))
        key_source = Path(config.private_key_source).expanduser()
        if config.private_key_source == "GITHUB_APP_PRIVATE_KEY":
            checks.append(("private key loaded", True, "inline environment variable"))
        else:
            checks.append(("private key file exists", key_source.exists(), str(key_source)))
            checks.append(
                (
                    "private key file permissions",
                    _private_key_permissions_ok(key_source),
                    _mode(key_source),
                )
            )
        if not skip_network:
            auth = GitHubAppAuth(config)
            token = auth.get_installation_token(force_refresh=True)
            checks.append(("installation token minted", True, token.redacted))
            app_result = auth.app_request("GET", "/app")["result"]
            checks.append(("/app API reachable", True, str(app_result.get("slug", "ok"))))
            if repo:
                repo_result = auth.request("GET", f"/repos/{repo}", repo=repo)["result"]
                checks.append(
                    ("repository access verified", True, str(repo_result.get("full_name", repo)))
                )
    except Exception as exc:
        checks.append(("GitHub App auth/config", False, str(exc)))

    success = all(ok for _, ok, _ in checks)
    for name, ok, detail in checks:
        marker = "✓" if ok else "✗"
        print(f"{marker} {name}: {detail}")
    if success:
        print(
            "Doctor passed. GitHub App identity is ready."
            if not skip_network
            else "Local doctor passed."
        )
        return 0
    print("Doctor found issues. Fix the failed checks above and rerun.", file=sys.stderr)
    return 1


def _status(repo: str | None) -> int:
    config = load_config()
    auth = GitHubAppAuth(config)
    token = auth.get_installation_token(force_refresh=True)
    app = auth.app_request("GET", "/app")["result"]
    repo_probe = auth.request("GET", f"/repos/{repo}", repo=repo)["result"] if repo else None
    print(
        json.dumps(
            {
                "success": True,
                "auth": auth_metadata(token, repo=repo),
                "app": app,
                "repository_probe": repo_probe,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _token(repo: str | None, *, json_output: bool) -> int:
    config = load_config()
    token = GitHubAppAuth(config).get_installation_token()
    if json_output:
        print(json.dumps({"token": token.token, "auth": auth_metadata(token, repo=repo)}, indent=2))
    else:
        print(token.token)
    return 0


def _api(method: str, path: str, *, repo: str | None, body: dict[str, Any] | None) -> int:
    result = GitHubAppAuth(load_config()).request(method, path, repo=repo, json_body=body)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _value_or_prompt(
    value: str | None,
    label: str,
    *,
    env: str,
    required: bool,
    non_interactive: bool,
) -> str:
    """Return a provided/env value or prompt for it."""
    resolved = value or os.environ.get(env, "")
    if resolved:
        return resolved.strip()
    if non_interactive:
        if required:
            raise ConfigurationError(f"missing required value: {label} (or {env})")
        return ""
    resolved = input(f"{label}: ").strip()
    if required and not resolved:
        raise ConfigurationError(f"missing required value: {label}")
    return resolved


def _private_key_permissions_ok(path: Path) -> bool:
    if not path.exists():
        return False
    mode = stat.S_IMODE(path.stat().st_mode)
    return mode & 0o077 == 0


def _warn_private_key_permissions(path: Path) -> None:
    if not _private_key_permissions_ok(path):
        print(
            f"warning: {path} is readable by group/other ({_mode(path)}). "
            "Run `chmod 600 <key>` to lock it down.",
            file=sys.stderr,
        )


def _mode(path: Path) -> str:
    if not path.exists():
        return "missing"
    return oct(stat.S_IMODE(path.stat().st_mode))


def _extract_repo(args: list[str]) -> tuple[str | None, list[str]]:
    repo: str | None = None
    child_args: list[str] = []
    iterator = iter(args)
    for arg in iterator:
        if arg == "--repo":
            repo = next(iterator, None)
            if repo is None:
                raise ConfigurationError("--repo requires OWNER/REPO")
        elif arg.startswith("--repo="):
            repo = arg.split("=", 1)[1]
        elif arg == "--":
            child_args.extend(iterator)
            break
        else:
            child_args.append(arg)
    if not child_args:
        raise ConfigurationError("missing command to run")
    return repo, child_args


if __name__ == "__main__":
    raise SystemExit(main())
