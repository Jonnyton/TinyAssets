# Research: CI on Auto-Generated PRs from External Services

**By:** cowork-vision (research agent dispatch)
**Date:** 2026-05-05T00:15Z
**Context:** Codex flagged at 23:46Z that PR #297/#307 land with empty `statusCheckRollup` (no CI checks fire). Substrate gap: checker keys without runtime evidence is half-blind merge approval. This research informs the eventual fix.

## Root Cause

GitHub's deliberate design: PRs created via `GITHUB_TOKEN` don't trigger downstream `pull_request` or `push` events — to prevent recursive workflows. This is the source of the "auto-change PRs land with no checks" problem.

## Canonical Patterns (Three Options)

### A. GitHub App Token instead of GITHUB_TOKEN (CLEANEST)
- App tokens BYPASS the "no trigger on bot PR" restriction
- Tokens are scoped per-app, per-installation
- Created via `actions/create-github-app-token@v1`
- **Used by:** Renovate, Dependabot, Anthropic Claude Code action
- **Tradeoff:** Requires GitHub App setup at org level; not in all GitHub plans

### B. Two-Tier `workflow_run` (SAFE FOR SECRETS)
- Tier 1 (on `pull_request`): Runs unprivileged tests; uploads artifacts
- Tier 2 (on `workflow_run`): Validates artifacts, accesses secrets, posts results
- **Used by:** Kubernetes components, GitHub Security Lab recommendation
- **Tradeoff:** More complex; requires artifact validation discipline

### C. `repository_dispatch` Workaround
- Bot workflow explicitly fires `createDispatchEvent` after creating PR
- Separate workflow listens for `repository_dispatch` → checks out PR → runs CI
- **Tradeoff:** Verbose; coordination between workflows

### AVOID: `pull_request_target` Without Guards
- Runs untrusted PR code with full secrets context
- Real exploits documented (Spotipy RCE, Timescale PgAI exfiltration)
- Only safe for jobs that don't checkout PR code

## Recommendation for Workflow

The **community-loop-watch.yml self-dispatch** that Codex observed already uses a similar pattern (workflow dispatch). The cleanest extension: configure the auto-change PR creator (per PR #248's `_post_github_json` path) to use **a GitHub App token instead of GITHUB_TOKEN**, so Workflow's standard CI workflows (`tests.yml`, `ruff.yml`, plugin mirror parity, etc.) fire automatically on auto-change PRs.

Concretely, the substrate change:
1. Create a GitHub App in the org (one-time setup, host-action)
2. Install it with `repo + actions: write + pull_request: write` permissions
3. Add `GITHUB_APP_ID` + `GITHUB_APP_PRIVATE_KEY` to repo secrets (host-action)
4. Modify `workflow/auto_ship_pr.py`'s GitHub call to mint app token via `actions/create-github-app-token@v1` and use it instead of the GitHub Actions default token
5. Verify PR creation now triggers `tests.yml` + `ruff.yml` + plugin mirror parity workflows

This gives reviewer keys (mine + Codex's) CI evidence to pair with substance review — closes the no-check gate Codex flagged.

## Identification Patterns (already used in Workflow)

Branch prefix `auto-change/*` is already used to identify loop-produced branches. This enables conditional CI behavior if needed (e.g., skip-irrelevant checks, run extra schema validation). Workflow's existing convention here is good.

## Security Caveats

- `pull_request_target` is the dangerous shortcut. Workflow should NOT use it.
- GitHub App tokens have 1-hour expiry — limits exfiltration window.
- Two-tier `workflow_run` requires schema validation on artifacts before secrets-bearing tier.

## Real-World References

- Renovate uses GitHub App tokens documented at https://docs.renovatebot.com/configuration-options/
- Dependabot's automerge pattern requires careful CI gating
- AWS Karpenter Issue #4525 documents the same problem class for community projects
- GitHub Community Discussion #65321 has multiple-year accumulation of users hitting this
- Anthropic Claude Code action design avoids the problem entirely by using comment-triggered workflows

## Recognized Ecosystem Gap

GitHub's official docs explain the restriction but don't prescribe a single recommended solution. Each approach has distinct ops burden. **No first-party "create a PR that will trigger CI safely" GitHub action exists.** This is the gap PR-007's reframe (per Codex 23:46Z) should address — adding the app-token path to Workflow's auto-ship-pr primitive becomes a substrate evolution that compounds for every loop-produced PR going forward.

## Sources

- GitHub Docs: Events that trigger workflows
- GitHub Security Lab: Preventing pwn requests
- GitHub Blog: pull_request_target and environment branch protections (Nov 2025)
- Renovate / Dependabot docs
- Spotipy + Timescale PgAI security advisories
- AWS Karpenter Issue #4525
- GitHub Community Discussion #65321
- peter-evans/create-pull-request action
- actions/create-github-app-token@v1

## Cross-references

- Codex's 23:46Z + 23:50Z observations on no-check gate
- PR #297 + PR #307 (both empty `statusCheckRollup`)
- PR-007 reframe (writer-lane liveness → schedule + auto-PR no-check class)
- pages/notes/loop-closed-cycle-self-improvement-pr-003-pr-297-2026-05-04.md (today's closed-cycle observation)
