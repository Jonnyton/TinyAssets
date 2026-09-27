---
severity: P2
title: The uptime canary cannot reach green for a no-universe principal, and unknown never closes the alarm
filed: '2026-09-27'
summary: since #3880 the revert-loop probe reports `legacy_evidence_unavailable` (exit 5) for the canary principal, so `overall` is always `unknown`; the alarm sink closes a p0-outage issue only on literal green, so #2824 stayed open for 23 days and community-loop-watch went red on 196 of 200 runs while the public MCP was up
---

# The uptime canary cannot reach green for a no-universe principal

**Filed / verified:** 2026-09-27 02:10 UTC, from the `uptime-canary.yml`
and `community-loop-watch.yml` run logs (read-only). **Severity:** P2. Real
outages still page, because red outranks unknown in
`scripts/uptime_observations.py`. What is lost is recovery and the
green signal.

## Evidence

- Latest canary runs (e.g. 36287461527, 02:04 UTC): handshake, tool,
  activity and wiki probes all exit 0. The revert-loop probe exits 5 with
  `get_status payload has no evidence block; top-level keys: ['about',
  'active_host', 'daemon', 'first_contact', ...]`. Sampled runs back to
  2026-09-25 show `OVERALL: unknown` on every one.
- `scripts/revert_loop_canary.py` (the `evidence = payload.get("evidence")`
  branch) deliberately classifies that shape as
  `legacy_evidence_unavailable`. That rule came in with #3880 (2026-09-18,
  "distinguish missing monitoring from measured outages"). The canary
  principal has no universe, so it never gets an evidence block.
- `uptime-canary.yml`'s alarm sink returns early on any `overall` other than
  `red` or `green` ("unknown result; no issue mutation or page"). Literal
  green is the only recovery path, and it cannot happen.
- Effect: P0 issue #2824 ("Public MCP outage", opened 2026-09-04) was never
  auto-closed. `community-loop-watch.yml` reads open p0-outage issues, so it
  was red on 196 of its last 200 runs; its last green was 2026-09-04. The
  canary workflow itself shows `success` 100 of 100 times while its verdict is
  `unknown`.
- The lead closed #2824 by hand on 2026-09-27 02:18 UTC with this evidence.
  The next real outage will open a new issue that cannot auto-close either.

## Shape of a fix (not done here)

Either the recovery rule accepts "every probe that can measure is green, and
the only unknown is the declared `legacy_evidence_unavailable`", or the
revert-loop probe gets evidence it can read for a principal with no
universe. This is monitoring design. It was found during the 2026-09-27
pipeline review and deliberately not changed in that lane.
