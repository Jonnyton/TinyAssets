---
severity: Watch
title: Uptime/durability upgrades deferred by the slim-until-paying-users rule
filed: '2026-10-02'
summary: 'The founder''s rule "keep things slim till we have paying users" (2026-10-02) deferred five uptime and durability upgrades that target-architecture S1 specifies. Each has a known gap today, accepted on purpose. Revisit all five at the first paying user: escrow wrapping key, R2 provider diversity, the standby region and load balancer, Litestream after the cutover, and a pinned droplet host key.'
---

# Uptime/durability upgrades deferred by the slim rule

**Filed:** 2026-10-02 (lead decision, founder rule "keep things slim till we have paying users").
**Trigger to revisit:** the first paying user.

| Deferred upgrade | The gap accepted today | Upgrade | Rough cost |
|---|---|---|---|
| **Escrow wrapping key** | The host-key escrow (`scripts/host_key_escrow.py`) is plaintext in the private off-region bucket. Anyone who can read `escrow/` holds the keys themselves, not just sealed ciphertext: they can open sealed sessions and **forge billing-entitlement and app-ingress HMACs**. The readers are the droplet's per-bucket key (root, which already holds the keys), the DR drill's per-run read key, and DO account admins. | A founder-held wrapping key (age identity offline, recipient on the droplet), so the bucket holds only ciphertext. | $0; founder time |
| **Provider diversity** | Both backup copies (sfo3 and nyc3) and the escrow are on DigitalOcean Spaces. Losing the DO account loses all of them. | A Cloudflare R2 bucket as the off-region store. | ~$1-3/mo |
| **Warm standby + LB** | Recovery is restore-from-backup onto a fresh droplet: about 30-60 min, proven by the weekly drill. There is no automatic failover. | target-architecture S1b: a standby droplet in a second region, fenced promotion, and a Cloudflare LB detector. | $12-24/mo + ~$5/mo |
| **Continuous replication** | Platform-state RPO is about 1 h (hourly brain tier) and about 24 h for everything else (nightly). | Litestream for `.platform/` after the command-center cutover. Its design constraints are in `docs/design-notes/2026-10-02-litestream-platform-state.md`. | ~$0-3/mo |
| **Pinned host key** | Workflows trust `ssh-keyscan`. | `docs/concerns/2026-10-02-deploy-workflows-trust-ssh-keyscan.md`. | $0 |

## How to resolve

At the first paying user, take each row: ship it, or re-defer it with a recorded reason. Delete a
row when its upgrade ships. Delete the file when no rows remain.
