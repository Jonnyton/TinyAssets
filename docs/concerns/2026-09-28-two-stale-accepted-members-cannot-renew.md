---
severity: P2
title: Two stale accepted subscription members cannot renew each other
filed: '2026-09-28'
summary: _reconnect_manifest renews one member only when every OTHER member's custody verifies, so if two accepted members are stale at once, each renewal refuses because of the other and neither heals
---

# Two stale accepted subscription members cannot renew each other

**Filed:** 2026-09-28
**Source:** gpt-6-astra refute review of PR #4076 (head 8d3a3a21), finding 2b. Codex reproduced it: with accepted Claude and Codex custody both stale, two refresh passes produced four held renewals and healed neither.

`tinyassets/onboarding/serving.py` `_reconnect_manifest` checks each non-renewed member with `_current_bound_member_authority`. When two members are stale, the renewal of either one refuses on the other.

**Why this is not the #4076 fix:** today only one subscription kind stores a refreshable inline document (codex `auth_json_b64`), and #4076 renews at the moment of each rotation. That leaves the double-stale state reachable only through two independent failed renewals. It is still a wall once it happens: the owner's only way out is to re-deposit.

**Closure:** renew every stale accepted member in one publication, keeping ownership, grants and model access unchanged, with a regression test that makes two members stale at once.
