---
name: github-app-workflow
description: Use per-agent GitHub App identity for Hermes GitHub operations.
version: 0.1.0
author: Hermes GitHub App Plugin Contributors
---

# GitHub App Workflow

Use this skill for GitHub operations from Hermes agents that are configured with a per-agent GitHub App.

## First-time setup

Run `hermes-github-app setup` to write `github_app` config into `~/.hermes/config.yaml`. The setup walkthrough marks optional values with `(optional)`; the required values are GitHub App client ID, installation ID, and private key path.

After setup, run `hermes-github-app doctor --repo OWNER/REPO` to verify console scripts, config loading, private-key permissions, token minting, and repository access. Use `--skip-network` only for container/image builds where secrets or network access are not available yet.

## Rules

1. Prefer `github_app_*` plugin tools for GitHub API operations.
2. Prefer `gh-app` over bare `gh` from the terminal.
3. Prefer `git-app` or HTTPS/App-token credentials over SSH for GitHub writes.
4. Do not rely on `gh auth status` as proof of the desired identity; it often reports the human account.
5. Verify App mode before writes with `github_app_verify_identity` or `hermes-github-app status --repo OWNER/REPO`.
6. Do not use `@me` assumptions; the actor is the app bot, not a human user.
7. Expect comments, PRs, and API writes to appear as `<app-slug>[bot]`.
8. Treat the GitHub App installation scope as the repository access boundary. The plugin does not maintain a separate local repository/owner allowlist.

## Updating existing Hermes skills

Patch any GitHub-related skill, cron prompt, or subagent instruction that mentions `gh`, `git push`, GitHub SSH remotes, or `@me` assumptions:

- Replace bare `gh ...` examples with `gh-app --repo OWNER/REPO -- ...` when the command needs GitHub authentication.
- Replace `git push` examples with `git-app --repo OWNER/REPO -- push ...`, or document an equivalent HTTPS credential-helper flow that uses a freshly minted installation token.
- Add a pre-write verification step: `github_app_verify_identity` or `hermes-github-app status --repo OWNER/REPO`.
- Do not treat `gh auth status` as proof of the write identity. It reports local `gh` credentials and may be a human account.
- Remove or flag SSH remote examples for bot-managed worktrees. SSH uses local SSH keys, not the GitHub App installation token.
- Replace `@me` queries with explicit usernames, teams, or repository-scoped queries because the app bot is not the human operator.
- Require final write summaries to include `auth_mode`, `app_slug`, `installation_id`, `repository`, operation, and URL/path.

For subagents, include the same rules in the delegated prompt because subagents run in separate sessions and may not inherit the parent agent's assumptions.

## Verification

Before reporting success for a write, include:

- repository
- operation
- URL or API path
- `auth_mode: github_app`
- app slug if known
- installation ID
