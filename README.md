# Hermes GitHub App Plugin

Hermes plugin for using **per-agent GitHub App identities** instead of a human `gh`/SSH identity.

Each Hermes agent runs the same package but is configured with its own GitHub App:

```yaml
github_app:
  client_id: "Iv1.exampleclientid"
  # Optional default used when a command cannot infer OWNER/REPO.
  installation_id: "987654"
  # Optional owner-specific installation IDs for apps installed in multiple orgs.
  installation_ids:
    ExampleOrg: "123456"
    ExampleInfra: "987654"
  private_key_path: "~/.hermes/secrets/agent-github-app.private-key.pem"
  app_slug: "hermes-agent"
```

Environment variables with the same meaning are also supported:

- `GITHUB_APP_CLIENT_ID`
- `GITHUB_APP_INSTALLATION_ID`
- `GITHUB_APP_INSTALLATION_IDS` (JSON object or `OWNER=ID,OWNER2=ID2` mapping)
- `GITHUB_APP_PRIVATE_KEY_PATH`
- `GITHUB_APP_PRIVATE_KEY` (PEM contents; useful for CI)
- `GITHUB_APP_TOKEN_BROKER=nono` (no private key in this environment; see [Running inside nono](#running-inside-nono-token-broker-mode))

Repository access is controlled by the GitHub App installation scope in GitHub. If an agent should not access a repository, remove that repository from the GitHub App installation scope.

## Client ID vs. installation ID

`client_id` identifies the GitHub App registration. GitHub recommends using the GitHub App **client ID** as the JWT `iss` claim when authenticating as an app.

`installation_id` identifies one installation of that app on a specific user or organization account. It is required when exchanging the app JWT for an installation access token via `POST /app/installations/{installation_id}/access_tokens`.

In other words: `client_id` answers "which GitHub App is signing this JWT?" while `installation_id` answers "which installed copy of that app should this token act as?" The same GitHub App can have multiple installation IDs if it is installed on multiple accounts. Configure `installation_ids` when one app is installed in multiple organizations; the plugin chooses an owner-specific ID from `--repo OWNER/REPO` or `/repos/OWNER/REPO` REST paths and falls back to `installation_id` when no repository owner is available.

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
  --installation-id-for ExampleOrg=123456 \
  --installation-id-for ExampleInfra=987654 \
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

## Running inside nono (token broker mode)

[nono](https://nono.sh) can run the agent in a sandbox that never holds the GitHub App private key. Enable broker mode with `GITHUB_APP_TOKEN_BROKER=nono` or `github_app.token_broker: nono`:

```yaml
github_app:
  client_id: "Iv1.exampleclientid"
  installation_ids:
    ExampleOrg: "123456"
  token_broker: nono
```

```bash
hermes-github-app setup --token-broker nono --client-id Iv1.exampleclientid --installation-id 987654
```

In broker mode the plugin reads no private key; `private_key_path` and `GITHUB_APP_PRIVATE_KEY*` are ignored. Installation tokens are not minted locally. The plugin sends the placeholder `nono-phantom-github-app` as its token, and nono's supervisor, outside the sandbox, handles the real credentials:

- Its TLS-intercepting proxy replaces the `Authorization` header on requests to `api.github.com`, `uploads.github.com`, and `github.com` with an installation token chosen by owner from the request path. Git HTTPS uses the same token as Basic `x-access-token`.
- The app JWT is injected for exactly `GET /app`.

What this means for agents:

- `github_app_*` tools, `hermes-github-app api`, `gh-app`, and `git-app` work unchanged; the placeholder flows through.
- Plain `git push` over HTTPS and plain `gh` also work, because the proxy injects credentials into those requests. Keep remotes HTTPS. SSH remotes use local SSH keys and are not covered.
- The agent cannot obtain a real token, by design. `hermes-github-app token` prints the placeholder with a note on stderr.
- `client_id` is still required in broker mode. It is non-secret and is reported in auth metadata.
- `hermes-github-app doctor` shows a `token broker` check and an `HTTPS_PROXY set` check. If the proxy variable is missing, the agent is not running inside nono and no credentials will be injected.

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

## Releasing to PyPI

The package is built with Hatchling and publishes through the `CD` GitHub Actions workflow using PyPI Trusted Publishing / OIDC. The workflow listens to all pushed tags but only builds and publishes when the tag matches:

```text
^[0-9]+\.[0-9]+\.[0-9]+$
```

The tag must also match `project.version` in `pyproject.toml`.

Before the first release, configure PyPI Trusted Publishing for this repository and workflow:

- PyPI project name: `hermes-github-app-plugin`
- Owner/repository: this GitHub repository
- Workflow name: `cd.yaml`
- Environment name: `pypi`

Release example:

```bash
git tag 0.3.0
git push origin 0.3.0
```

Tags like `v0.1.0`, `0.1`, or `0.1.0rc1` will not publish.

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
