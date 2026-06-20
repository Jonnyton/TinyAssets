# Bot identity setup

The community patch loop must use a GitHub identity that is separate from `@Jonnyton`. The bot may create branches, open PRs, and enable auto-merge, but it must not be able to satisfy the founder code-owner review gate or administer the repository.

## GitHub App setup

Create a GitHub App owned by the account or organization that controls `Jonnyton/Workflow`.

Settings:

- Webhook: disabled.
- Repository access: only `Jonnyton/Workflow`.
- Repository permissions:
  - Contents: Read and write.
  - Pull requests: Read and write.
  - Metadata: Read-only, implicit.
- Do not grant Administration, Actions write, Secrets, Members, or Checks write.

After creating the App:

1. Install it on `Jonnyton/Workflow` only.
2. Record the App ID and installation ID.
3. Generate a private key and place it on the droplet at `/etc/workflow/github-app-private-key.pem` with `root:root` ownership and `0600` mode.
4. Create `/etc/workflow/github-app-token-refresher.env` with:

```bash
GITHUB_APP_ID=<app-id>
GITHUB_APP_INSTALLATION_ID=<installation-id>
GITHUB_APP_PRIVATE_KEY_FILE=/etc/workflow/github-app-private-key.pem
WORKFLOW_GITHUB_PR_CAPABILITIES_REPO=Jonnyton/Workflow
```

Then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now github-app-token-refresher.timer
sudo systemctl start github-app-token-refresher.service
sudo systemctl restart workflow-daemon.service
```

The refresher writes this value into `/etc/workflow/env` through `deploy/install-workflow-env.sh`:

```json
{"Jonnyton/Workflow":"<installation-token>"}
```

## Branch protection pairing

Run `scripts/setup-secure-merge-gate.sh` with a GitHub identity that has repository administration permission. The bot identity must not be an admin and must not be listed in `.github/CODEOWNERS`.

Expected merge behavior:

1. The bot opens a PR and may enable auto-merge.
2. Required checks must pass.
3. `@Jonnyton` must approve the exact current head because `.github/CODEOWNERS` owns every path.
4. A new push dismisses the approval and requires re-review.
