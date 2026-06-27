---
title: Vault-only provider keys — removing GROQ/GEMINI/XAI from persistent droplet storage
date: 2026-04-24
author: navigator
status: active
status_detail: scoping note — open Qs for host before dev dispatch
related:
  - docs/design-notes/2026-04-22-secrets-vault-integration.md
  - deploy/workflow-env.template
  - deploy/docker-entrypoint.sh
  - deploy/compose.yml
  - .github/workflows/deploy-prod.yml
  - STATUS.md task #9
---

# Vault-only provider keys

## Problem

GROQ_API_KEY, GEMINI_API_KEY, XAI_API_KEY, and DO_API_TOKEN currently live in
`/etc/tinyassets/env` on the droplet. They persist on disk indefinitely. When a key
leaks (or a chat transcript captures it — the 2026-04-24 rotation trigger), the
remediation is a manual host chore: rotate the key in four places (provider
dashboard, GH Actions secrets, `/etc/tinyassets/env`, restart daemon). That chore
will recur on every rotation event for as long as keys live on disk.

The goal is to eliminate the chore by making keys non-persistent: they flow
into the container environment at deploy time (or reboot), from a source that
is already secured, and are never written to a file that survives a container
restart beyond what's strictly necessary.

**DO_API_TOKEN is a separate, simpler case.** It's an ops-only credential for
droplet management (resizing, snapshots, firewall rules). It should never be
on the droplet itself — an attacker who compromises the droplet gets no
additional lever. Remove it outright from `/etc/tinyassets/env`; keep it only in
GH Actions secrets (where it already lives for deploy-prod.yml). No boot-time
injection needed.

## What survives the change

Provider classes raise `ProviderUnavailableError` when their key is absent
(fail-loud, Hard Rule #8). The daemon starts normally; affected providers are
simply unavailable. Claude/codex/ollama keep working. This is the correct
degraded-but-alive posture.

`docker-entrypoint.sh` checks that at least one of `{CLOUDFLARE_TUNNEL_TOKEN,
SUPABASE_DB_URL, TINYASSETS_IMAGE}` is set before allowing the container to
start — these three never move to vault (they're structural, not rotatable
secrets). The entrypoint sentinel check is unaffected.

## The hard problem: reboot resilience

The three free-tier provider keys (GROQ/GEMINI/XAI) enable the full 6-provider
fallback chain. If those keys are absent after a reboot (e.g. droplet reboots
during an outage, no human online), the daemon starts but falls back to
claude/codex/ollama only — reduced but alive. This is acceptable per the
uptime invariant.

The question is: where do the keys live between deploys, and what reads them
at reboot?

## Three options

### Option A — GH Actions deploy-time injection (recommended for now)

**How it works:** `deploy-prod.yml` already SSHs the droplet with `DO_SSH_KEY`.
The deploy job adds a step that writes GROQ/GEMINI/XAI from GH Actions secrets
directly into `/etc/tinyassets/env` (replacing the current manual provision).
The keys never live in the repo; they live in GH Actions secrets (same trust
boundary they're already in post-rotation). On reboot without a new deploy,
the keys remain in `/etc/tinyassets/env` until explicitly purged.

**Upside:** zero new infrastructure. No vault service needed on the droplet.
Host rotates a key by updating the GH Actions secret + triggering a deploy
(or the next normal deploy picks it up). One place to update.

**Downside:** keys still persist on the droplet filesystem in `/etc/tinyassets/env`
between deploys. The file is `root:workflow 640` so it's not readable by
attackers without root, but it exists on disk. This doesn't achieve "no key
on disk" — it achieves "one place to rotate instead of four."

**Verdict:** this is a meaningful improvement (rotation chore goes from
4-step to 1-step) with no new moving parts. If the goal is purely to
eliminate the ops chore (not to eliminate disk persistence), Option A is
the right answer.

### Option B — Bitwarden self-hosted machine unlock (true vault-on-boot)

**How it works:** a Bitwarden-compatible CLI (Vaultwarden self-hosted, or
the official `bw` CLI against Bitwarden cloud) is installed on the droplet
with a machine account. A long-lived session token is stored at a restricted
path (e.g. `/etc/tinyassets/bw-session`). `deploy/load-boot-secrets.sh` runs
at compose-up time: it calls `bw list items --session $(cat /etc/tinyassets/bw-session)`,
extracts GROQ/GEMINI/XAI, and injects them into the container environment
via `--env` flags on `docker compose up`. No keys ever touch `/etc/tinyassets/env`.

**Upside:** genuinely no provider keys on disk. Rotation = one vault edit
propagates everywhere on next reboot/deploy.

**Downside:** the session token IS on disk (`/etc/tinyassets/bw-session`). The
security gain vs. Option A is: a compromised droplet gets the session token
(scoped to read the vault) rather than the raw keys. For free-tier API keys
whose worst-case breach is provider account compromise (not financial
catastrophe), this is marginal improvement over Option A at significant
operational complexity: Vaultwarden self-host adds a new service to maintain
(updates, auth, backups), or Bitwarden cloud adds a $3/mo machine account.

**Also:** if Bitwarden is unreachable at boot (service outage, network issue),
keys are unavailable → providers all fail → daemon boots with claude/codex/ollama
only. That's fine per the uptime invariant, but it introduces a new external
dependency in the boot path.

**Verdict:** disproportionate complexity for the threat model of free-tier API
keys. Consider if these keys ever become high-value (paid-tier Gemini, etc.).

### Option C — GH OIDC → cloud secrets manager (AWS SSM / DO Spaces KMS)

**How it works:** GH Actions OIDC federation → AWS SSM Parameter Store or
Doppler or similar. Deploy job fetches fresh secrets at each deploy, writes
them to the droplet. At reboot, a systemd unit uses a stored cloud credential
to fetch fresh secrets before starting compose.

**Upside:** no secrets on disk; cloud-native; audit trail.

**Downside:** adds AWS/Doppler dependency; new infra to provision and pay
for; OIDC federation requires one-time setup; the stored cloud credential at
reboot is itself a secret that must live somewhere (same bootstrapping
problem as Option B). Overkill for free-tier API keys.

**Verdict:** reject. Too much new surface for the threat model.

## Recommendation

**Phase 1 (ship now, dev task):** Option A + DO_API_TOKEN removal.

1. Remove DO_API_TOKEN from `/etc/tinyassets/env` + `workflow-env.template` entirely.
2. Add a deploy-prod.yml step that writes GROQ_API_KEY, GEMINI_API_KEY,
   XAI_API_KEY from GH Actions secrets into `/etc/tinyassets/env` on the droplet
   (SSH step, same as the existing `sed -i` pattern for TINYASSETS_IMAGE). Follow
   with `chown root:workflow + chmod 640` + readability assertion (existing pattern).
3. Remove manual provider-key provisioning from the ops runbook.
4. Add a pre-commit invariant or CI lint that checks `workflow-env.template`
   for any of {GROQ_API_KEY, GEMINI_API_KEY, XAI_API_KEY, DO_API_TOKEN} and
   fails if they appear with a non-empty value (prevent accidental re-introduction).

**Phase 2 (deferred, host decision):** If any provider key becomes high-value
(real-money quota at risk), revisit Option B (Bitwarden machine account).
Until then, Option A's "one place to rotate" is the correct tradeoff.

## What dev needs to implement

**Files:** `.github/workflows/deploy-prod.yml` (new inject-provider-keys step),
`deploy/workflow-env.template` (remove DO_API_TOKEN + provider keys, add
comments noting they're injected by deploy), pre-commit hook or CI check for
drift prevention.

**Not needed:** no changes to `deploy/docker-entrypoint.sh` (env vars arrive
via env_file at compose time, same path as today), no changes to provider
classes (they still read `os.environ.get`), no new scripts.

**Key invariant:** after the deploy step writes keys, the same `chown + chmod
640 + sudo -u workflow test -r` assertion that already exists for
TINYASSETS_IMAGE must gate the provider-key write. Re-use the existing pattern.

**Reboot behavior (no new deploy):** keys persist in `/etc/tinyassets/env` between
deploys as today. The improvement is that rotation requires only updating
4 GH Actions secrets (GROQ/GEMINI/XAI + CLOUDFLARE_API_TOKEN) + triggering
a deploy. No SSH manual edit. No drift between GH secrets and droplet state.

## Open Qs for host (before dev dispatch)

**Q1 — GH Actions secret names:** Current secrets include DO_SSH_KEY,
DO_SSH_KEY_BACKUP, CLOUDFLARE_API_TOKEN. Are GROQ_API_KEY, GEMINI_API_KEY,
XAI_API_KEY already seeded in GH Actions secrets, or do they need to be added
before the deploy step can inject them? (If yes, host adds them; dev can add
the step with a conditional `if: env.GROQ_API_KEY != ''` so a missing secret
is a silent skip, not a deploy failure.)

**Q2 — Rotation timing:** after dev ships the deploy step, will host rotate
all three provider keys once to validate the end-to-end path before removing
the manual `/etc/tinyassets/env` edit from the ops runbook? This is the
acceptance test for the whole change.

**Q3 — Bitwarden session token (future):** if Option B is ever revisited,
where should the machine session token live on the droplet? `/etc/tinyassets/bw-session`
(root:workflow 640, same pattern) seems right. Noting for future reference.

**Q4 — TINYASSETS_PIN_WRITER:** if all three free-tier providers are absent at
boot (unreachable vault or keys not yet injected), the writer chain falls
through to ollama-local. Is that an acceptable degraded posture during the
transition period, or should there be a warning log that surfaces "provider
keys not yet deployed" distinctly from "provider in cooldown"? (Probably
worth a one-line log in deploy-prod.yml after the inject step confirms success.)

## Summary of changes

| Component | Today | After |
|---|---|---|
| GROQ/GEMINI/XAI on droplet | Manual provision in `/etc/tinyassets/env` | Written by `deploy-prod.yml` each deploy |
| DO_API_TOKEN on droplet | Present in `/etc/tinyassets/env` | Removed entirely |
| Rotation chore | Edit 4 places + SSH + restart | Update GH Actions secret + next deploy |
| Keys on disk between deploys | Yes (same as today) | Yes (until Option B if warranted) |
| Provider fail-loud behavior | Unchanged | Unchanged |
| Reboot with no human online | All 6 providers up | All 6 providers up (keys still in env file) |
