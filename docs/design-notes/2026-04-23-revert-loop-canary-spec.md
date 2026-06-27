---
title: Revert-loop canary + provider_exhaustion repair class — Lane 4 spec
date: 2026-04-23
author: navigator
status: shipped
shipped_date: 2026-04-23
shipped_in: 964bc8d  # storage observability + Lane 4 revert-loop canary bundle
canonical_in: docs/ops/acceptance-probe-catalog.md PROBE-006
status_detail: spec; canary live (PROBE-006); provider_exhaustion repair-class wired in p0-outage-triage.yml
related:
  - docs/audits/2026-04-23-p0-auto-recovery-trace.md (the precipitating incident)
  - scripts/last_activity_canary.py (sibling canary)
  - .github/workflows/uptime-canary.yml (Layer-1a/1b/1c wire)
  - .github/workflows/p0-outage-triage.yml (repair-class wire)
  - pages/bugs/bug-023-daemon-disk-full-... (symptom BUG)
---

# Revert-loop canary + provider_exhaustion repair class

Lane 4 closes the gap the 2026-04-23 P0 exposed: auto-recovery handled disk
pressure per-cycle but the generator (sustained revert-loop) outran the
pruner. Upstream canary detects the generator and cuts it before symptom
cascade. Plus a companion repair class in `p0-outage-triage.yml` so the
canary's signal routes cleanly into existing auto-recovery infrastructure.

## Q1 — Signal source

**Decision: use `get_status.evidence.activity_log_tail` + `last_n_calls`.**

The activity log already carries the exact signal: "Draft: FAILED — provider
returned empty prose", "Commit: score 0.00 -- REVERT", "Commit: reverting
... - draft provider failed". These land per scene, timestamped to the
second. `get_status` exposes the tail + last_n_calls block already (per
`tinyassets/universe_server.py::get_status`). No new surface needed.

**Rejected alternative**: a new `/daemon/health` surface. Reasons:
- activity_log_tail already contains the ground-truth events.
- A new surface is new attack-surface + new plumbing to maintain.
- The canary's contract is "read what the daemon naturally emits" — same
  discipline as `last_activity_canary` (reads `daemon.last_activity_at`
  from `universe inspect`).

## Q2 — Detection shape

**Decision: N consecutive REVERT verdicts in time window T.**

The "Commit: ... - REVERT" / "Commit: reverting" verdict is the terminal
event of a failed scene cycle. Counting these is more reliable than
counting "Draft: FAILED" entries because:
- Draft-FAILED happens once per scene but may recover within-scene (retry
  logic, reroute). REVERT is the committed terminal verdict.
- Scenes that succeed produce "Commit: score X -- KEEP/MERGE" (not REVERT).
  Mixing success + fail in the window is cleanly detectable by counting
  only REVERTs.
- The 2026-04-23 trace pattern was explicitly REVERT-after-REVERT; this
  is the signal we want.

**Rejected alternative**: "Draft: FAILED" counter. Would also detect
revert-loop but adds noise from retry-succeeded cases and complicates
the false-positive math.

## Q3 — Values for N and T

**Decision: N=3 REVERTs within T=10min, WARN at N=5 within T=20min, CRITICAL.**

Start conservative to validate in prod before tightening:

| Trigger | N | T | Action |
|---------|---|---|--------|
| WARN | 3 REVERTs | 10 min | Pushover priority=0 to host + open p0-outage issue with `provider_exhaustion` signal. |
| CRITICAL | 5 REVERTs | 20 min | Auto-repair fires via p0-outage-triage (hard-stop worker + `.pause` + page priority=2). |

**False-positive risk analysis:**
- A single bad scene reverting once = 1 REVERT, safe (below N=3).
- Back-to-back complex-scene iterations with legitimate revert-and-retry
  pattern (the way the evaluator is designed to work) = might produce
  2-3 REVERTs naturally. Living activity log from earlier universes
  (`concordance` B54/B55 morning trace) showed ~1 REVERT per 15-20min
  under normal-failure conditions. 3 in 10min is 3x normal rate — safely
  separable from noise.
- Tuning discipline: surface N/T as env vars (`TINYASSETS_REVERT_CANARY_N`,
  `TINYASSETS_REVERT_CANARY_T_MIN`) so prod experience can adjust without
  code edits. Defaults above bake in the starting values.

Iterate on N/T once the canary has been live through 7+ days of normal
operation. If WARN fires more than ~2x/week with no real issue, raise N
or widen T.

## Q4 — Wire point

**Decision: Layer-1d in `uptime-canary.yml`, standalone `revert_loop_canary.py` script.**

Add as sibling to existing Layer-1a handshake / 1b tool / 1c last_activity.
Single script `scripts/revert_loop_canary.py` with the detection logic
(stdlib only, same discipline as `last_activity_canary.py`). Exit codes
per existing canary convention:

- 0 — OK (fewer than N=3 REVERTs in T=10min window)
- 2 — WARN (3-4 REVERTs in window; page priority=0)
- 3 — CRITICAL (≥5 REVERTs in 20min window; trigger auto-repair)
- 4 — handshake/connectivity failure (fall-through; overlaps with
      mcp_public_canary but lands a distinct code for diagnostics)

The `combine` step in `uptime-canary.yml` picks worst-of across all
Layer-1* probes; no change to that logic needed — existing combine already
handles exit codes correctly by max.

**Rejected alternative**: standalone workflow. Would double the cron cadence,
add new GHA-secret plumbing, and fracture the "one canary at 5-min cadence"
invariant. Sibling-step under uptime-canary is strictly simpler.

## Q5 — Interaction with `last_activity_canary.py`

**Decision: separate canaries, explicitly opposite predicates.**

They cover different failure modes:
- `last_activity_canary`: activity stale (no work in N min) → "daemon
  is dark but claiming to be up."
- `revert_loop_canary`: activity fresh AND failing (many REVERTs in N min)
  → "daemon is busy-broken."

Both read from `get_status.evidence` but interpret different fields:
- last_activity reads `daemon.last_activity_at` via `universe inspect`.
- revert-loop reads `activity_log_tail` + `last_n_calls` via `get_status`.

They're not modes of the same canary — the predicate for "busy-broken" is
the negation of "daemon is dark", and a single script hiding both behind a
`--mode` flag would muddy the interface. Keep separate.

**Coupling**: Layer-1c (last_activity) fires means "no activity at all."
Layer-1d (revert-loop) fires means "wrong kind of activity." Both firing
simultaneously is a contradiction — surface that as a distinct CRITICAL
class if it happens (flag as corrupted-signal; likely indicates the
activity_log_tail is stale, not the work state).

## Q6 — Repair branch for `p0-outage-triage.yml`

**Decision: new class `provider_exhaustion`, auto-repair via hard-stop + .pause + page.**

Extend `scripts/triage_classify.py` to detect the canary's signal in the
pre-restart diag bundle. Signal: presence of `REVERT ... - draft provider failed`
pattern in recent activity log entries (diag already includes `journalctl
tinyassets-daemon -n 80`, should also include activity log tail — tiny
change to the diag capture step).

New class returned by classifier:

```json
{
  "class": "provider_exhaustion",
  "auto_repairable": true,
  "manual_only": false,
  "evidence": "N=5 REVERTs in last 20min in activity log; all with 'draft provider failed' cause"
}
```

Repair branch action in `p0-outage-triage.yml` after `disk_full` branch:

```yaml
- name: Repair — provider_exhaustion (hard-stop worker + .pause + page host)
  id: repair_provider_exhaustion
  if: steps.classify.outputs.class == 'provider_exhaustion'
  run: |
    echo "::warning::provider_exhaustion detected — halting worker + paging host"
    ssh -i ~/.ssh/do_deploy -o BatchMode=yes \
        "${DO_SSH_USER}@${DO_DROPLET_HOST}" \
        "docker stop workflow-worker 2>&1; \
         touch /data/universes/concordance/.pause 2>&1; \
         echo 'worker halted + pause set'"
    # Pushover priority=2 — host decision needed before resume
    python scripts/pushover_page.py \
        --title 'P0 provider_exhaustion — worker halted' \
        --message 'Revert-loop canary fired. Worker stopped. Daemon paused. Fix provider stack before resume.' \
        --priority 2
```

**Distinct from disk_full** — different repair. disk_full prunes the
Docker layer cache (a symptom); provider_exhaustion halts the generator (a
cause). The 2026-04-23 trace explicitly shows this is the right design:
if provider_exhaustion had been a class on 2026-04-23, it would have
fired once (not three times), broken the loop, and host would have
received a single priority=2 page instead of three priority=0 auto-recoveries
that individually succeeded but collectively failed.

**Interaction with `disk_full` repair:** if both classes fire in the same
diag bundle, provider_exhaustion is PRIORITY (addresses cause). Update
`triage_classify.py` priority order: env_unreadable > tunnel_token >
provider_exhaustion > disk_full > oom > image_pull_failure >
watchdog_hotloop > unknown. Rationale: cause-addressing repairs outrank
symptom-addressing repairs.

## Test strategy

Six test surfaces:

1. **`scripts/revert_loop_canary.py` unit tests** with fixture activity_log_tail
   inputs covering: 0 REVERTs (OK), 2 REVERTs in window (OK, below threshold),
   3 in 10min (WARN), 5 in 20min (CRITICAL), 3 in 20min (below WARN at
   strict rate but within critical window — confirms math), malformed
   activity log (exit 3).

2. **Classifier unit tests** (`scripts/triage_classify.py`) with diag
   bundles containing: 5 recent REVERTs + draft-failed pattern →
   `provider_exhaustion`; 5 REVERTs + no draft-failed → `unknown`;
   `disk_full` AND `provider_exhaustion` signals both present →
   `provider_exhaustion` (cause wins).

3. **Integration test** with synthetic activity log + canary → exit code.
   Reuse the `last_activity_canary.py` test scaffolding pattern.

4. **Workflow dispatch dry-run.** Fire `p0-outage-triage.yml` with a mock
   `provider_exhaustion` issue label and verify repair step runs without
   actually SSHing (use repo-level `DRY_RUN=1` env check, similar pattern
   to dr-drill).

5. **End-to-end in local dev.** Spin up the daemon with a pinned-failing
   provider (e.g., pin codex to an invalid model), let 3 REVERTs fire,
   verify canary exits 2; let 5 more fire, verify exit 3 + auto-repair
   simulation halts worker.

6. **False-positive test.** Simulate normal operation with ~1 REVERT per
   15-20min (the baseline observed in prod). Canary should run 100 times
   without exit 2. If exit 2 fires, tune N/T or the predicate.

## Rollout plan

1. Ship `scripts/revert_loop_canary.py` + unit tests (independent of
   tinyassets/classifier).
2. Wire as Layer-1d in `uptime-canary.yml` (WARN-only, no auto-repair yet).
   Run in WARN-only mode for 7 days. Collect false-positive rate.
3. Add `provider_exhaustion` class to `triage_classify.py` + the repair
   step to `p0-outage-triage.yml`. Still gated: repair fires only if
   `TINYASSETS_REVERT_AUTO_REPAIR=on`. Off by default.
4. After 7 days of clean WARN signal, flip `TINYASSETS_REVERT_AUTO_REPAIR=on`
   on prod. Canary now fires CRITICAL → p0-outage-triage → auto-halt +
   page.
5. Add env-var tunables (`TINYASSETS_REVERT_CANARY_N`,
   `_T_MIN`) to support operational experimentation without redeploys.
6. Remove the `TINYASSETS_REVERT_AUTO_REPAIR` gate after 14 days clean
   operation post-rollout. Make CRITICAL → auto-repair the default.

## Dev scope estimate

| Piece | Effort |
|---|---|
| `scripts/revert_loop_canary.py` + tests | ~3h |
| Layer-1d wire in uptime-canary.yml | ~1h |
| `provider_exhaustion` class in triage_classify.py + tests | ~2h |
| Repair branch in p0-outage-triage.yml | ~1h |
| Integration tests + dry-run verification | ~2h |
| Rollout via staged `_AUTO_REPAIR` flag | ~1h |
| Total | ~10h |

Claimable as a single dev sprint. Prereqs: #8 BUG-023 storage observability
landed (gives `storage_inspect` surface to cross-check); bundle shipped
(providers registered cleanly — without this, canary will fire nonstop as
soon as any call hits empty-prose, which would be correct behavior but a
terrible first-ship experience).

## Related

- The 2026-04-23 trace auto-recovery doc — this spec's precipitating incident.
- BUG-023 — symptom-layer fix (storage discipline); Lane 4 is the
  cause-layer fix.
- `last_activity_canary.py` — sibling detector for the opposite failure mode.
- `chatbot-builder-behaviors` chatbot-facing doc — chatbot writers should
  also surface "provider exhausted" class to users when they see the
  same patterns in get_status.evidence mid-session.
