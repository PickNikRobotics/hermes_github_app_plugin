# Hermes GitHub App Plugin

Hermes plugin for using **per-agent GitHub App identities** instead of a human `gh`/SSH identity.

Each Hermes agent runs the same package but is configured with its own GitHub App:

```yaml
github_app:
  client_id: "Iv1.exampleclientid"
  installation_id: "987654"
  private_key_path: "~/.hermes/secrets/agent-github-app.private-key.pem"
  app_slug: "hermes-agent"
```

Environment variables with the same meaning are also supported:

- `GITHUB_APP_CLIENT_ID`
- `GITHUB_APP_INSTALLATION_ID`
- `GITHUB_APP_PRIVATE_KEY_PATH`
- `GITHUB_APP_PRIVATE_KEY` (PEM contents; useful for CI)

Repository access is controlled by the GitHub App installation scope in GitHub. If an agent should not access a repository, remove that repository from the GitHub App installation scope.

## Client ID vs. installation ID

`client_id` identifies the GitHub App registration. GitHub recommends using the GitHub App **client ID** as the JWT `iss` claim when authenticating as an app.

`installation_id` identifies one installation of that app on a specific user or organization account. It is required when exchanging the app JWT for an installation access token via `POST /app/installations/{installation_id}/access_tokens`.

In other words: `client_id` answers "which GitHub App is signing this JWT?" while `installation_id` answers "which installed copy of that app should this token act as?" The same GitHub App can have multiple installation IDs if it is installed on multiple accounts.

## Install

```bash
pip install hermes-github-app-plugin
hermes plugins enable github-app
hermes-github-app setup
hermes-github-app doctor --repo OWNER/REPO
```

`setup` walks through the required values one by one. Optional prompts are explicitly marked with `(optional)`:

```text
GitHub App client ID:
GitHub App installation ID:
GitHub App private key path:
GitHub App slug (optional):
```

For scripted installs, pass flags and skip the network verification until secrets are mounted:

```bash
hermes-github-app setup --non-interactive --skip-verify \
  --client-id Iv1.exampleclientid \
  --installation-id 987654 \
  --private-key-path ~/.hermes/secrets/agent-github-app.private-key.pem \
  --app-slug hermes-agent
```

`doctor` checks local installation state and, unless `--skip-network` is set, verifies that an installation token can be minted and the optional repository probe is reachable.

## CLI and wrappers

```bash
hermes-github-app setup
hermes-github-app doctor --repo OWNER/REPO
hermes-github-app status
hermes-github-app token --repo OWNER/REPO
hermes-github-app api --repo OWNER/REPO /repos/OWNER/REPO

gh-app --repo OWNER/REPO pr list -R OWNER/REPO
git-app --repo OWNER/REPO push origin my-branch
```

`gh-app` injects an ephemeral installation token as `GH_TOKEN` and `GITHUB_TOKEN` for the child `gh` process.
`git-app` injects a temporary askpass helper so HTTPS Git operations authenticate as the GitHub App installation token without writing credentials into the remote URL.

## Migrating existing Hermes skills and jobs

To keep agents from falling back to local human credentials, update existing GitHub-related Hermes skills, cron jobs, and subagent prompts with these rules:

- Use `github_app_*` tools for GitHub API operations when possible.
- Replace authenticated `gh ...` examples with `gh-app --repo OWNER/REPO -- ...`.
- Replace `git push` examples with `git-app --repo OWNER/REPO -- push ...`, or another HTTPS credential-helper flow backed by a freshly minted installation token.
- Do not use `gh auth status` as proof of write identity; it reports local `gh` credentials and may show a human account.
- Avoid SSH remotes for bot-managed worktrees. SSH uses local SSH keys, not the GitHub App token.
- Add a pre-write check with `github_app_verify_identity` or `hermes-github-app status --repo OWNER/REPO`.
- Avoid `@me` assumptions because the GitHub App bot is not the human operator.
- Require write summaries to include the returned `auth_mode`, `app_slug`, `installation_id`, repository, operation, and URL/path.

## Hermes tools

The plugin registers these tools:

- `github_app_status`
- `github_app_verify_identity`
- `github_app_api`
- `github_app_graphql`
- `github_app_create_issue`
- `github_app_comment_issue`
- `github_app_create_pr`
- `github_app_comment_pr`

All mutating tools return auth metadata showing App mode, installation ID, app slug, and target repository.
