---
status: shipped
shipped_date: 2026-04-19
shipped_in: a4cb975  # Layer 1; subsequent layers in 4c02e31 (Row H GHA) + 964bc8d (Lane 4 revert-loop)
canonical_in: docs/ops/acceptance-probe-catalog.md (PROBE-001..009)
---

# Uptime Canary — Layered Design

**Date:** 2026-04-19
**Author:** navigator
**Status:** First draft. Responds to P0 public MCP outage (see postmortem: `docs/audits/2026-04-20-public-mcp-outage-postmortem.md`). Per host directive: "you can always test with the user to insure uptime."
**Lens:** chatbot-leverage + 3-layer chain. Canary gives the SYSTEM the same evidence the chatbot and user need to tell whether the platform is reachable. A layer-1 red IS a chain-break at System-layer; we need to know within 2 min, not 24 h.

---

## 1. Problem the canary solves

SUCCESSION.md §165 specifies a **weekly** cron pinging `tinyassets.io` + WHOIS expiry. The 2026-04-19 outage demonstrated:

- Public `tinyassets.io/mcp` was unreachable for an unknown window before host noticed it via live Claude.ai chat breakage.
- Weekly coarse-grained check could have missed the outage entirely if the window landed between pings.
- Existing pre-commit hooks (mirror parity, mojibake, ruff) do NOT exercise the public routing surface.
- localhost:8001 was healthy the whole time — *internal* health tells us nothing about the *public* surface the chatbot actually hits.

**Canary goal:** compress time-to-detect from "whenever host notices in a chat" to **≤4 min worst case** (two Layer-1 probes at 2-min cadence).

---

## 2. Two layers

### Layer 1 — curl-level probe (every 2 min, unconditional)

**What it exercises:** DNS resolution → TLS → Cloudflare edge → tunnel → FastMCP `/mcp` handler → `initialize` + `tools/list` round-trip.

**What it cannot catch:** Claude.ai-connector-specific failure modes (auth renewal loops, session TTL expiry, prompt-directive regressions that break chatbot behavior without breaking the raw MCP protocol).

**Shape:**

- Stdlib Python (`urllib.request` + `json`). **Zero third-party deps** — the canary must NOT break when pip state is dirty.
- POST to `https://tinyassets.io/mcp` with `jsonrpc:"2.0"` / `method:"initialize"` / standard capabilities payload.
- Expect: `200 OK` + parseable JSON-RPC response with matching `id` + `result.serverInfo`.
- Then POST `tools/list`; expect non-empty `tools[]` array with ≥1 known tool name (e.g., `get_status`).
- Total round-trip budget: 10 s hard cap.
- Exit code: `0` green / `2` dns-fail / `3` tls-fail / `4` http-non-200 / `5` json-parse / `6` missing-tools / `7` timeout.

**Runner:**

- Windows Task Scheduler recurring every 2 min (host is a Windows machine per env). Alternative: tray process spawns a thread.
- **Prefer Task Scheduler over tray thread** — tray process can itself die (the very thing the canary is trying to detect); out-of-process canary has no shared-fate with what it's monitoring.

**Log output:** append one line per probe to `.agents/uptime.log`:

```
2026-04-19T17:30:00-07:00 GREEN layer=1 url=tinyassets.io/mcp rtt_ms=412 tools=37
2026-04-19T17:32:00-07:00 RED   layer=1 url=tinyassets.io/mcp exit=2 reason=dns_nxdomain rtt_ms=5001
```

Single-line format so `grep RED .agents/uptime.log | tail -5` gives instant status.

### Layer 2 — Claude.ai user-sim probe (every hour when host browser is up)

**What it exercises:** Claude.ai connector auth path → MCP prompt-directive rendering → tool invocation → response round-trip → user-visible narrative quality. Catches auth-renewal, session-TTL, and prompt-regression failure modes invisible to curl.

**What it cannot do:** run without the shared CDP browser awake. Layer 2 is best-effort; Layer 1 is the safety net.

**Shape:**

- User-sim persona `uptime_canary` (new minimal persona — one-liner: "briefly verifies the TinyAssets MCP is responding").
- Single turn: persona says "Are you there? Call get_status and tell me the provider_routed field."
- Expect: chatbot invokes `get_status` MCP tool + returns a body mentioning `provider_routed`.
- Pass = tool was called AND response parsed. Fail = tool not called, OR error, OR empty.
- Runs hourly IF `scripts/browser_lock.py status` shows the lock is available AND no higher-priority mission is in flight.
- Log to `.agents/uptime.log` with `layer=2`.
- **Measure response settle time.** Record the `ask` wall time on every probe; emit as `settle_ms=<n>` in the log line. Soft-signal feeds the fabrication-detection rule below.

**Runner:** a thin scheduler entry that checks the browser lock before claiming; if busy, skip this hour's probe (NOT fail — skip).

**Soft-signal augmentation (post-P0 probe 2026-04-19): fabrication detection via abnormal settle time.**

Per `docs/design-notes/2026-04-19-degraded-mode-fabrication.md` §5, degraded-mode fabrication produces responses that settle ~3x slower than tool-mediated responses (~150-180s+ vs ~10-60s) because the chatbot generates the artifact from scratch rather than narrating a tool result. Fold as a soft-signal code:

- `exit=8` (soft) — response settled but took >150s. Interpretation: possible fabrication mode. NOT an alarm by itself.
- **Alarm rule:** two consecutive `exit=8` from the same probe AND Layer 1 green concurrently → distinct Concerns entry: `CHATBOT FABRICATION SUSPECT — layer-2 slow-settle <N>, layer-1 green. Possible silent MCP degradation with chatbot compensation.` The Layer-1-green requirement is load-bearing — if Layer 1 is red, the slow response is already explained by the known outage and no additional diagnostic applies.

Adds ~0.1 dev-day to canary first-draft scope.

---

## 3. Alarm shape

On **two consecutive Layer-1 reds** (≥4 min outage), automation writes one line to `STATUS.md` Concerns:

```
[YYYY-MM-DD HH:MM] PUBLIC MCP OUTAGE — layer-1 canary red <N>min, exit=<code>, reason=<short>. Investigate via `.agents/uptime.log`.
```

Per host-managed STATUS.md rule (`feedback_status_md_host_managed.md`): **automation writes ONLY to Concerns**, never deletes. Host curates the clearing. Duplicate-outage suppression: if the last non-resolved STATUS.md Concerns line already carries `PUBLIC MCP OUTAGE`, do not append a second one — just update the timestamp on the existing line.

**Layer-2 reds do NOT alarm STATUS.md automatically** — too many false-positive paths (browser lock held by other work, mission collision, user-sim bug). Instead Layer-2 reds get logged and the lead reviews on next turn. A Layer-2 sustained red over 3+ consecutive hours WITH Layer-1 still green is a distinct diagnostic (points at connector auth/prompt regression, not infra).

### Escalation table

| Signal | Action |
|---|---|
| 1 Layer-1 red | Log only. Could be one-off transient. |
| 2 consecutive Layer-1 reds (≥4 min) | Write STATUS.md Concerns line. Lead investigates. |
| 5+ consecutive Layer-1 reds (≥10 min) | Update Concerns line with updated duration; no second entry. |
| Layer-2 red, Layer-1 green | Log only. Lead reviews on next active turn — connector layer issue. |
| Layer-2 red 3+ hrs, Layer-1 green | Distinct Concerns entry: `CONNECTOR DEGRADED — layer-2 red <N>hrs, layer-1 green. Likely auth/session/prompt regression.` |
| Both red | Combine into one STATUS.md line with both layer indicators. |

---

## 4. What does NOT belong in the canary (scope discipline)

- **No self-healing.** Canary observes + alarms. Remediation is human/dev work. Auto-restart-the-tray tempting; deferred to a future design call with better blast-radius analysis.
- **No full-test-suite gate.** The canary is a liveness probe, not a correctness probe. If `tools/list` returns a corrupted tool description, that's a different monitor (spec drift / contract test).
- **No SLA math, no dashboards, no pages.** First-draft writes to a log + STATUS.md. That's enough for a single-host project at current scale. Dashboards come when there's more than one host to page.
- **No authentication by the canary.** The probe hits the public unauthenticated MCP initialize path. Auth-layer probing is Layer 2's job via real Claude.ai session. The curl path intentionally stays lowest-common-denominator.
- **No pre-launch load-test.** That's Track J (per `docs/design-notes/2026-04-18-full-platform-architecture.md` §10). Canary is continuous liveness; load-test is pre-ship scale validation. Different surfaces.

---

## 5. File layout

| Path | Purpose |
|---|---|
| `scripts/uptime_canary.py` | Layer-1 implementation. Stdlib-only. Invoked by Task Scheduler. |
| `scripts/uptime_canary_layer2.py` | Layer-2 implementation. Uses existing `claude_chat.py` runner + browser_lock + user-sim `uptime_canary` persona. |
| `scripts/uptime_alarm.py` | Reads `.agents/uptime.log` last N lines, applies escalation table, mutates STATUS.md Concerns line iff threshold crossed. Invoked by Task Scheduler as a separate job (do not couple to the probe itself — fail-loudly if the probe fails; alarm logic stays decoupled). |
| `.agents/uptime.log` | Rolling log. Rotates at 10 MB; keeps last 30 days. |
| `.claude/agent-memory/user/personas/uptime_canary/` | Minimal persona for Layer 2. |
| Windows Task Scheduler entries | `TinyAssets-Canary-L1` (every 2 min), `TinyAssets-Canary-L2` (hourly), `TinyAssets-Alarm` (every 2 min). |

---

## 6. First-draft implementation scope

~0.5–1 dev-day:

- Layer-1 probe script (~80 LOC stdlib Python + test with mock HTTP server).
- Alarm script (~60 LOC + STATUS.md-edit helper borrowed from `scripts/concerns_resolve.py` patterns).
- Task Scheduler XML export checked into `scripts/windows-task-scheduler/` so it's reproducible on a fresh host install.
- README in `scripts/` for how to install the scheduled tasks.

Layer 2 defers to **second commit** — pairs with persona creation + user-sim mission harness adaptation. ~0.5 dev-day incremental.

---

## 7. Risks + mitigations

- **Canary false positives from Cloudflare blips.** Mitigation: 2-consecutive-red threshold already absorbs transient (≤2 min) blips.
- **Canary false negatives from cached DNS at host resolver.** Mitigation: pass `--dns-server 1.1.1.1` to the stdlib probe where supported, OR run a secondary probe from a GitHub Actions runner every 5 min as an independent vantage point.
- **STATUS.md churn from automated writes.** Mitigation: single-line updates-in-place, not appends; host can delete the line once resolved; alarm script is idempotent.
- **Canary itself dies silently.** Mitigation: the Task Scheduler "last run result" is itself monitorable; add a weekly cron (SUCCESSION.md §165 already has one) that checks `.agents/uptime.log` has entries within the last hour. Canary-of-the-canary; keep it simple.
- **Scheduled-task drift across OS reinstall.** Mitigation: XML export stored in-repo; install doc in `scripts/` README.

---

## 8. What this design note does NOT decide

- Whether the canary also monitors `tinyassets.io` root (landing page) — trivially cheap to add as a third probe; recommend yes for ~10 more LOC. Not load-bearing for P0.
- Whether Layer 2's persona runs on the host's CDP browser or a headless profile. Recommend: host CDP while user-sim exists; migrate to headless when we have a 24/7 server host.
- GitHub Actions independent vantage point. Worth adding; defer to a follow-up commit (~0.25 dev-day).
- Whether alarm writes go to a Slack/webhook as a future path. Not today; a file-based STATUS.md alarm is enough for current scale.

---

## 9. Success criteria

When this canary ships:

1. A regression like the 2026-04-19 NXDOMAIN outage is detected and alarmed in STATUS.md within ≤4 min.
2. `.agents/uptime.log` gives the lead a one-grep view of current + recent liveness.
3. The probe survives tray crashes, cloudflared crashes, and Python-venv rebuilds (stdlib-only requirement).
4. Layer 2 validates the chatbot-visible connector path at a cadence sufficient to catch prompt-directive regressions within 1 hour of introduction.
5. Install procedure is documented in-repo and reproducible on a fresh Windows host without host recall.
