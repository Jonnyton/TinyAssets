# Loop fault-class inventory + self-heal map

**Author:** Cowork session, 2026-05-02. Written after diagnosing the 9-hour 502 outage.
**For:** Codex assistant — this is your post-recovery backlog. Each class is one substrate patch lane.

The 2026-05-02 outage exposed that "live MCP up" + "canary firing" doesn't mean the loop is durable — it just means *one* fault class (image-not-in-GHCR) wasn't covered. There are many more. This inventory ranks them by likelihood × impact and proposes detection + recovery for each. Top items first.

Format per class:
- **Class name** — what breaks
- **How it manifests** — what the user/canary sees
- **Detection** — how we know it happened (existing or proposed probe)
- **Auto-recovery** — what fires without human (existing or proposed)
- **Manual recovery** — runbook step when auto fails
- **Status** — already-covered / partially-covered / GAP

---

## Tier 1 — must cover (likely + high impact)

### 1. Deploy chain — image not in GHCR for HEAD SHA
- **Manifests:** deploy-prod fails at `docker pull: not found`. Daemon stays on previous image OR gets dropped if compose was already torn down.
- **Detection:** existing — deploy-prod step exits 1 with the specific error in logs.
- **Auto-recovery:** GAP. Existing rollback uses :latest only when previous-image capture is empty. **Patch in flight via `loop-uptime-recovery.diff`** (Cowork handoff) — fall back to :latest when SHA tag missing.
- **Manual recovery:** trigger build-image first, then deploy-prod with explicit image_tag.
- **Status:** PATCH READY in COWORK_HANDOFF_2026-05-02-loop-uptime/.

### 2. Wiki→branch circuit open (WORKFLOW_BUG_INVESTIGATION_GOAL_ID unset)
- **Manifests:** `wiki action=file_bug` returns clean but no `Investigation` section. Bug just sits there. Loop never fires.
- **Detection:** GAP. No probe exists for "is auto-trigger enabled."
- **Auto-recovery:** N/A — config issue, can't auto-fix.
- **Manual recovery:** runbook in COWORK_HANDOFF_2026-05-02-loop-uptime/loop-circuit-close.runbook.md.
- **Patch proposal:** Add `auto_trigger_enabled: bool` to `get_status()` response. `community-loop-watch.yml` reads it and pages if False. ~30 LOC. **Codex: dispatch as `LOOP-PROBE-002` or similar.**
- **Status:** GAP — needs probe primitive.

### 3. Cloudflare tunnel disconnected (cloudflared service stopped)
- **Manifests:** apex `tinyassets.io/mcp` returns 502 (Worker → tunnel timeout). Direct probe to `mcp.tinyassets.io/mcp` returns connection refused or CF-issued 521/523/525.
- **Detection:** existing uptime-canary catches the 502 at apex. But it doesn't distinguish tunnel-vs-daemon.
- **Auto-recovery:** GAP. p0-outage-triage restarts daemon container, doesn't restart cloudflared service.
- **Manual recovery:** SSH + `sudo systemctl restart cloudflared`.
- **Patch proposal:** extend p0-outage-triage to also `sudo systemctl restart cloudflared` if first restart attempt fails. Two-line change to existing workflow. **Codex: scope ~1h.**

### 4. Provider exhaustion at candidate_discovery (BUG-038)
- **Manifests:** branch run fails with `provider_exhausted` mid-execution. Castles II live branch `28479d8ddfb44488` hit this.
- **Detection:** existing — `extensions action=run_status` shows `failed` with reason.
- **Auto-recovery:** GAP. Should retry with next provider in fallback chain after backoff.
- **Manual recovery:** rerun branch when daily quota resets, OR adjust provider router config.
- **Patch proposal:** add `runtime_recovery_strategy` field to BranchDefinition with values `fail_fast | fallback_chain | retry_with_backoff`. Default `fallback_chain`. 2-3 day dev. **Codex: this is in the existing STATUS Concerns — pickup if not in someone else's lane.**
- **Status:** open BUG-038. Lane likely Codex's.

### 5. Universe SQLite locked (concurrent write contention)
- **Manifests:** all MCP tool calls return `database is locked` error. Wiki writes fail. Loop stalls because branch definitions can't be loaded.
- **Detection:** GAP. Existing canaries don't detect this — they probe MCP handshake which doesn't touch SQLite.
- **Auto-recovery:** GAP. `SqliteSaver` is correctly used (per Hard Rule 1) but has no contention recovery.
- **Manual recovery:** restart daemon (releases all locks).
- **Patch proposal:** add a SQLite write-canary to community-loop-watch.yml that does a no-op write to a `_canary` row. If it fails, page. ~50 LOC, fits in scripts/community_loop_watch.py.

### 6. Loop content drift — change_loop_v1 modified or deleted
- **Manifests:** `extensions action=describe_branch branch_def_id=fd5c66b1d87d` returns "branch not found" or returns a different graph than expected. Bug filings auto-trigger but the run does the wrong thing.
- **Detection:** GAP. No drift probe.
- **Auto-recovery:** GAP. There's no canonical export of the loop's branches.
- **Manual recovery:** re-author from scratch (lossy).
- **Patch proposal:** TWO-PART. (a) `extensions action=export_branch branch_def_id=<>` returns serializable JSON/YAML — see `branch-export-import-spec.md` in this folder. (b) Periodic snapshot to git: nightly cron exports `change_loop_v1` + canonical-bound branches to `wiki/pages/branches/<id>.yaml` for version control. Daily diff = drift signal. ~3 day dev for both parts.
- **Status:** GAP — partly covered by branch-export-import-spec.md (next file in this folder).

---

## Tier 2 — should cover (less likely but high impact when they hit)

### 7. /etc/workflow/env mode flip (env file becomes unreadable by daemon user)
- **Manifests:** daemon starts but reads no env, runs with bare defaults, MCP returns wrong universe data.
- **Detection:** existing — deploy-prod has `Assert /etc/workflow/env readable by daemon user` step. Catches at deploy time.
- **Auto-recovery:** existing — `deploy/install-workflow-env.sh` is the atomic mutator (no more sed -i + chown + chmod chain).
- **Manual recovery:** `chown root:workflow /etc/workflow/env && chmod 640`.
- **Status:** COVERED — Fix A landed `bc079a0`.

### 8. CF Access service token rotated
- **Manifests:** Worker can no longer auth to tunnel origin. apex `tinyassets.io/mcp` returns 401/403 from Worker (instead of forwarding).
- **Detection:** GAP. Worker logs show 401 but no canary checks Worker→origin auth.
- **Auto-recovery:** GAP.
- **Manual recovery:** mint new service token in Cloudflare Zero Trust dashboard, update Worker secrets via wrangler.
- **Patch proposal:** add `Verify CF Access gates direct URL` step to uptime-canary that expects 403 from `mcp.tinyassets.io` direct. If it returns ANYTHING ELSE (e.g. 200, or Worker auth error code), page. Existing deploy-prod already has this check at line ~245 — just promote it to canary cadence.

### 9. GHCR auth expired (PAT for image push expired)
- **Manifests:** build-image fails at the push step. No new images. Eventually combined with class #1 = total deploy lockout.
- **Detection:** existing — build-image step exits 1.
- **Auto-recovery:** GAP — token rotation is human.
- **Manual recovery:** mint new GHCR PAT, update repo secret.
- **Patch proposal:** add a monthly secrets-expiry-check workflow that probes GHCR auth (already have secrets-expiry-check.yml — just verify it covers GHCR).
- **Status:** PARTIAL — secrets-expiry-check.yml exists; verify coverage.

### 10. PROBE-002 / Layer-2 canary broken (`lead_browser.navigate` doesn't exist)
- **Manifests:** Layer-2 canary exits SKIP cleanly in CI (no browser env), so never produces a real GREEN signal. Loop appears healthy but nothing actually exercises the user-facing browser path.
- **Detection:** existing — but produces false-green.
- **Auto-recovery:** N/A.
- **Manual recovery:** patch landed in 2026-04-27 (`scripts/uptime_canary_layer2.py:192-263`); needs ops wiring (Windows Task Scheduler) to actually run.
- **Status:** PARTIAL — code fix landed; Task #32 in STATUS may already be closed; verify.

### 11. Daemon OOM
- **Manifests:** docker container restart loop. Eventually compose.yml gives up if restart cap hit.
- **Detection:** existing — community-loop-watch reads recent activity; if no activity in 30min, pages.
- **Auto-recovery:** existing — workflow-watchdog.timer monitors + restarts.
- **Manual recovery:** scale up droplet OR investigate the leak.
- **Status:** COVERED — workflow-watchdog.service / .timer.

### 12. Disk full on droplet
- **Manifests:** wiki writes fail. SQLite WAL grows. Eventually daemon crashes.
- **Detection:** existing — workflow-disk-watch.service / .timer.
- **Auto-recovery:** existing — workflow-prune.service / .timer.
- **Manual recovery:** SSH + investigate which dir grew.
- **Status:** COVERED.

---

## Tier 3 — nice-to-have (less likely or lower impact)

### 13. GHA scheduled workflow auto-disabled (60-day repo inactivity)
- **Manifests:** uptime-canary stops running. No issues filed during outages.
- **Detection:** GAP — meta-canary for "did the canary itself run."
- **Auto-recovery:** N/A — needs human re-enable.
- **Manual recovery:** GH Actions UI → enable workflow.
- **Patch proposal:** community-loop-watch reads its own last-run timestamp from GH API. If gap > 1h, page via Pushover (which doesn't depend on GH).

### 14. Subscription auth bundle expired/rotated
- **Manifests:** Codex/Claude provider calls fail at runtime. `WORKFLOW_CODEX_AUTH_JSON_B64` decoded but expired.
- **Detection:** GAP — only surfaces during a real run, not at deploy time.
- **Auto-recovery:** GAP — falls back to API-key providers if `WORKFLOW_ALLOW_API_KEY_PROVIDERS` allows, but Hard Rule 3 + project_subscription_only_provider_default forbid that as default.
- **Manual recovery:** re-export Codex auth bundle, re-encode, update repo secret, redeploy.
- **Patch proposal:** add a periodic auth-validity probe that does a no-op subprocess `codex exec "echo test"` and checks for auth errors in stderr.

### 15. Multiple identical p0-outage issues spam (no dedup)
- **Manifests:** during a sustained outage, every 5min the canary opens a new issue. After hours, hundreds of issues.
- **Detection:** see issues list grow.
- **Auto-recovery:** existing — `concurrency: group: p0-triage-${{ github.event.issue.number }}` per-issue concurrency, but new issue numbers each time defeat this.
- **Manual recovery:** close duplicate issues.
- **Patch proposal:** uptime-canary checks for existing open `p0-outage` labeled issues before opening a new one. If one exists, comment on it with new evidence instead.

---

## Cross-cutting recommendations

1. **Probe diversity matters.** Today most canaries are HTTP-level (handshake, tool-invocation). The fault classes that bit hardest (image-not-in-GHCR, env file mode, SQLite contention) all SUCCEEDED at HTTP-level until they didn't. **Add probes at every layer:** registry, env, sqlite, disk, provider-auth, branch-content.

2. **Self-heal != restart.** Most existing self-heal IS restart-the-container. But several fault classes (#1, #3, #5, #6, #14) aren't restart-fixable. Self-heal needs to be class-aware. Promote p0-outage-triage from "always restart" to "classify fault → run class-specific recovery."

3. **Each fault class deserves a memory entry.** Codex agent memory at `.claude/agent-memory/<your-name>/` should accumulate "I saw fault X, recovery Y worked / didn't" so future sessions skip the redo.

4. **Top-3 priority order for Codex backlog:**
   - Class #1 deploy fallback (patch READY)
   - Class #2 wiki→branch probe (~30 LOC, 1h dev)
   - Class #3 cloudflared restart in p0-triage (~10 LOC, 30min dev)

5. **Loop fault classes also include LOOP CONTENT.** The substrate-vs-content split means the loop can fail not just because primitives broke, but because the user-authored branch graph itself is bad. That's where the export/import primitive (next file) becomes critical — it lets us version control the content and detect drift.

## What I (Cowork) didn't include

- **Threat model / adversarial faults.** Someone deliberately spamming file_bug, exfiltrating wiki contents, etc. Different threat — needs `project_privacy_via_community_composition` + abuse-response design. Out of scope for an uptime fault inventory.
- **Performance degradation that isn't a hard fault.** "Loop completes but takes 10x longer" — needs separate observability/SLO design.
- **Cost-runaway scenarios.** Provider bills exploding because a feedback loop went runaway. Adjacent to abuse-response.

These deserve their own audits. Codex: file as separate STATUS Concerns when you're ready.
