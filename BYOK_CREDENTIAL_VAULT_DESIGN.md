# DESIGN — Per-universe BYOK social-credential vault (v1 multi-tenant keystone)

> Canonical copy lives in the brain at
> `pages/design-proposals/design-byok-per-universe-social-credential-vault-v1.md`.
> Tracked to merge as **PR-176**. Slice 1 = the twitter effector (PR-173, Codex building now).

## Goal
Launch **v1 of the social-media management system**: any user makes a universe,
connects their OWN social accounts (bring-your-own-key), and runs outreach/content
branches that post as them, billed to their own accounts. Jonathan is **tenant #0**
(dogfooding `patch-loop-live`). It's a coincidence tenant #0's project is this platform.

**Endgame:** once v1 is proven and others can self-serve, point the outreach engine at
the product itself — "run your social media here: your universe, your keys, your account."
The manager acquires users by doing the thing it sells. Strictly gated behind "v1 proven."

## Why BYOK + per-universe (settled, not a choice)
- X **mandated BYOK on 2026-03-31**: every account posting via a third-party tool must
  use its OWN dev-app keys on every request. Platform-pays-OAuth model is dead for X.
- Pay-per-use makes per-user cost ~$5–30/mo; the user pays X directly, owns their cap.
- Net: **$0 platform social-API bill at scale**, no Enterprise contract, no shared
  2M-read cap — de-risked. Credentials are per-user, tied to each user's account.
- `/etc/workflow/env` is the **single-tenant v0 shortcut only**.

## Architecture
- **Per-universe encrypted credential vault** — secrets per universe, encrypted at rest,
  isolated, never logged/echoed/surfaced, redacted in evidence, rotation + revoke.
- **Connect-social-account (BYOK) primitive** — user (or a user-built branch) stores their
  own app keys for a sink (`x`, later `linkedin`/`bluesky`) into their universe's vault via
  MCP, **no repo access**. `connect` / `list` / `revoke`.
- **Per-actor resolver** (the thing PR-173 names) — effectors resolve `{sink, actor=running
  universe}` from the vault; **env fallback for the host universe only**.
- Effectors call `resolve(sink, actor)`, never a global secret. Reuse PR-122 authority +
  consent per-actor. Spend cap = the user's own X-account cap.

## Path to merge — independently mergeable slices
1. **twitter_post effector + per-actor resolver + env fallback** = PR-173 (Codex building now).
2. **Per-universe encrypted credential vault** (store + read API for the resolver).
3. **Connect-social-account MCP primitive** (`connect`/`list`/`revoke`, no repo access).
4. **Resolver reads vault first** (per-universe), env fallback only for host.
5. **Onboarding flow + multi-sink generalization** (LinkedIn, Bluesky, ...).

Implementer: Codex (auto-loop unreliable). Merge via the governed founder gate
(GitHub branch-protection interim until the signed merge-authorization primitive lands).

## Done = merged + working (acceptance / v1 launch gate)
A **second universe** (a test tenant, not the host) connects its own X app keys via the
`connect` primitive and posts as itself — billed to **that tenant's** X account, with **no
repo access** and **no shared secret**. That end-to-end pass launches v1.
