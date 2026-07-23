---
title: Acceptance Probe Catalog
date: 2026-04-20
last_swept: 2026-07-22
author: navigator
status: living doc — add validated probes here; remove if they go stale
---

# Acceptance Probe Catalog

Named, validated probes for testing the full System → Chatbot → User chain.
Each entry records the exact prompt, what it exercises, and the evidence of
its validation. Use these as reference probes for cutover acceptance, regression
checks, and new-connector verification.

> **Read this before trusting a `Validated:` line.** Those lines are claims about
> when a probe was *last checked*, not proof it is working *now*, and nothing
> re-checks them automatically. A probe can sit certified here while red in CI
> for days — PROBE-003 did exactly that. Current per-probe status is in
> § *Claim freshness sweep — 2026-07-22* at the end of this document. If you are
> here because a probe is red, check that section **first**: the probe itself may
> be the thing that broke.

---

## PROBE-001 — Full-stack smoke (cutover acceptance)

**Validated:** 2026-04-20 (DO-cutover acceptance mission)
**Source audit:** `docs/audits/user-chat-intelligence/2026-04-20-do-cutover-acceptance.md`
**Persona:** bare-curious-user (no persona framing; minimal context)
**Connector URL under test:** `https://tinyassets.io/mcp`
**Apex URL under test:** `https://tinyassets.io/` (Layer-1 wrapper requires HTTP 200)
**Rendered chatbot client:** Claude.ai, ChatGPT Developer Mode, or another
browser chatbot with the TinyAssets connector visibly installed. Record which
client produced the evidence.

### Prompt (paste verbatim)

```
hey i want to use the tool i set up to design a workflow for writing a research
paper on deep space population — can you walk me through it?
```

### What it exercises

| Layer | What's tested |
|---|---|
| System | MCP endpoint reachable via browser chatbot → Cloudflare Worker → tunnel → daemon |
| System | Apex site `/` returns HTTP 200 alongside the `/mcp` endpoint |
| Chatbot | `control_station` Hard Rule 10 (anti-fabrication): assume → tool-call → correct-if-wrong |
| Chatbot | Chatbot-assumes-TinyAssets directive (rule 7): no disambiguation picker |
| Chatbot | User-vocabulary discipline (rule 9): no engine-vocab in first response |
| User | Full pipeline recommendation grounded in real tool output, not fabrication |

### Green criteria

- Chatbot invokes at least one TinyAssets MCP tool (visible in thinking-block or response).
- Response references real daemon state (e.g., empty workspace, named primitives from actual tool output).
- Layer-1 wrapper confirms `https://tinyassets.io/` returns HTTP 200 while `/mcp` is green.
- No fabricated workflow JSON, no fabricated prior-session history.
- Settle time under 150s. (>150s with tool invocation = soft-yellow; >150s without tool invocation = suspected fabrication-mode.)
- Zero "Session terminated" errors.

### Red signals

- "Session terminated" on any tool call.
- Chatbot produces a workflow spec without invoking a tool.
- Chatbot claims prior-session context that was never established in this chat.
- No tool call at all (chatbot responded from memory only).
- Layer-1 wrapper reports apex `/` non-200 or unreachable while `/mcp` is otherwise green.
- Settle time >180s with no tool call confirmed.

### Baseline evidence

| Date | Condition | Settle (ms) | Result |
|---|---|---|---|
| 2026-04-19 | P0 outage (pre-fix) | >180,000 | RED — 3x Session terminated, 6-node JSON fabricated, hallucinated history |
| 2026-04-20 | Post-cutover | 116,000 | GREEN — live tool cycle, empty-workspace reported correctly, Hard Rule 10 held |

### When to use

- After any change to the Cloudflare Worker, tunnel config, or daemon deploy.
- After any `control_station` prompt edit.
- As the final acceptance gate before marking a cutover "done."
- As a regression check if Layer-1 canary is green but user-reports suggest broken behavior.

### Limitations

- Exercises the full path but not deeply (1 prompt, 1 tool call). For deep
  persona-specific validation, use the per-persona mission drafts.
- "Deep space population" topic is now known to the system; a future probe
  rotation may want a different topic to avoid any cached warm-path effects.
- **Single-URL architecture (2026-04-20):** this probe targets `tinyassets.io/mcp` only.
  The former dual-URL localization trick (green canonical + red `mcp.` = Worker OK, tunnel broken)
  is retired. Layer diagnosis now uses Cloudflare Worker logs + cloudflared tunnel logs
  (see `docs/ops/dns-tunnel-single-entry-cutover.md` § Observability).

---

## PROBE-002 — Layer-2 liveness (minimal)

**Validated:** code-fix landed 2026-04-28 (`_real_browser_probe` reimplemented as `claude_chat ask` subprocess + trace-block parser); still awaits host `--once` smoke + Task Scheduler `TinyAssets-Canary-L2` activation for live status. Freshness check 2026-05-01: `Get-ScheduledTask -TaskName TinyAssets-Canary-L2` returned no task. Original implementation (`lead_browser.navigate` + `claude_chat.send_and_wait`) referenced symbols that never existed — see `docs/design-notes/2026-04-19-layer2-canary-scope.md §Wiring runbook` for the recovery + API contract.
**Source script:** `scripts/uptime_canary_layer2.py` (canary) + `scripts/claude_chat.py` (subprocess driver — `cmd_ask` is the canonical entry point).
**Persona:** `uptime_canary` (dedicated automated persona; CDP profile at `C:\Users\Jonathan\.claude-ai-profile`).
**Connector URL under test:** `https://tinyassets.io/mcp`

### Prompt (paste verbatim)

```
Are you there? Call get_status and tell me the llm_endpoint_bound value.
```

### What it exercises

- MCP connector reachable from Claude.ai.
- `get_status` tool invocable (lowest-dep read-only tool).
- `evidence.llm_endpoint_bound` field readable and surfaced in response.

### Green criteria

- Chatbot invokes `get_status`.
- Response contains a reference to `llm_endpoint_bound` OR `endpoint` OR `bound` (case-insensitive).
- Settle time within normal range.

### Red signals

- No tool call (exit 10 — `tool_not_invoked`).
- Tool called but response empty (exit 11).
- Tool called but field not referenced in response (exit 12).
- Browser could not reach Claude.ai (exit 13).

### When to use

- Automated hourly Layer-2 canary (Windows Task Scheduler entry `TinyAssets-Canary-L2` invokes `python scripts/uptime_canary_layer2.py`). Currently UNWIRED on host as of 2026-05-01; host activates after `--once` GREEN smoke.
- Quick manual liveness check when Layer-1 is green but something feels wrong.

### Cross-host caveat

Layer-2 binds to host availability — the persona's CDP profile + browser run on the host machine. A long-term host-independent Layer-2 (e.g. Browserbase or hosted Playwright) is a separate follow-on; the *design intent* of PROBE-002 is "Layer-2 when host is up; SKIP otherwise."

> **⚠ STALE CLAIM CORRECTED 2026-07-22.** This section previously read "CI (GHA)
> runs the script every 5 min and exits 14 SKIP cleanly (no browser)." That is
> **not what happens.** In the `layer2-probe` job of
> `.github/workflows/uptime-canary.yml`, the probe exits **13
> (`RED_browser_load_error`)**, not 14 (`SKIP_lock_unavailable`) — confirmed on
> 5 of 5 runs sampled (`29888685398`, `29882421314`, `29878986733`,
> `29872629105`, `29863658078`). Because that step is `continue-on-error: true`
> and only exits non-zero for codes other than 0/14, the red is swallowed: it
> never fails the workflow and never pages anyone. **Net effect: Layer-2 has no
> CI coverage today, and the absence is invisible.** Observed cadence is also
> ~1 run/hour, not every 5 min (see PROBE-003 § *Cadence caveat*). A `codex`
> lane (`fix/layer2-probe-skip-detection`) is dispatched for the skip-detection
> fix; this catalog entry should be re-verified when it lands.

---

## PROBE-003 — Wiki gate + read (auto-heal pipeline integrity)

> **⚠ CURRENTLY RED — and the red is the probe, not the service.**
> Failing continuously since run `29452256324` (2026-07-15T21:31:53Z):
> **106 consecutive failed runs across ~6.4 days, zero green**, verified
> 2026-07-22 ~06:00Z. The live service is behaving **correctly** for every one
> of those runs. **Do not treat a red PROBE-003 as an outage** — read
> § *Known false-red history* below first. Full forensics:
> `docs/audits/2026-07-22-uptime-canary-false-red-incident.md` (PR #1513).

**Validated:** wiki canary script live since 2026-04-22; logs probes to `.agents/uptime.log`. Scheduled in CI 2026-04-26 — Layer-1e step in `.github/workflows/uptime-canary.yml`, alongside the other Layer-1 probes. **Reworked 2026-07-14** (`6f8cebc7`, PR #1449) after the server-side anonymous-write gate (#1441): the anonymous write-then-read roundtrip is impossible by design, so the probe asserts the gate itself plus the open read path.
**Current validity — NOT CURRENT.** The 2026-07-14 rework was already stale the next day. At 2026-07-15T20:54:19Z, `972d0cc3` moved the server contract again: pure-write MCP handles now answer **HTTP 401 + `WWW-Authenticate` pre-dispatch** (so MCP clients launch OAuth) instead of returning the in-band `status=rejected` / `auth_required=true` envelope the probe still asserts at `scripts/wiki_canary.py:232-237`. The 401 raises at the transport layer inside `post()` (`scripts/wiki_canary.py:199-205`), so the envelope assertion is now **unreachable against production** — realigning this probe is not a matter of editing the envelope check.
**Freshness stamp:** verified 2026-07-22 against live CI (`gh run list --workflow=uptime-canary.yml --limit 200`) and `origin/main`, where `6f8cebc7` is still the latest commit touching `scripts/wiki_canary.py`. **Remediation is NOT landed** — `git ls-remote --heads origin | grep -i canary` returns no fix branch. A `codex` lane owns the repair; see § *Known false-red history*.
**Cadence caveat:** the workflow is configured `cron: '*/5 * * * *'`, but observed delivery on 2026-07-22 was roughly **one run per hour** (12 runs spanned ~13.6 h) — GitHub deprioritizes cron schedules under load. Treat 5 minutes as a best case, not a guarantee, when reasoning about detection latency.
**Source script:** `scripts/wiki_canary.py`
**Persona:** `wiki-canary` (automated; client name `wiki-canary/1.0`)
**Connector URL under test:** `https://tinyassets.io/mcp`

### Invocation

```
python scripts/wiki_canary.py
python scripts/wiki_canary.py --url https://tinyassets.io/mcp --verbose
python scripts/wiki_canary.py --once --format=gha
```

Scope: auth-gated deployments only (production runs `UNIVERSE_SERVER_AUTH=optional`). A dev-mode server (`UNIVERSE_SERVER_AUTH=false`) leaves anonymous writes open by design, so the gate step reds with exit 6 there — that means "server is not auth-gated", not "wiki is down".

### What it exercises

| Layer | What's tested |
|---|---|
| System | MCP `initialize` handshake reaches the daemon. |
| System | Anonymous `write_page` is refused by the write gate. **⚠ The probe asserts the pre-`972d0cc3` in-band envelope (`status=rejected` / `auth_required=true`); the live server now refuses with HTTP 401 pre-dispatch instead. This assertion is what is failing.** |
| System | `read_page` returns the persisted canary draft `drafts/notes/uptime-probe.md` verbatim (reads stay open; catches wiki-read / storage-mount breakage, e.g. the readonly-volume class). **⚠ Not currently reached** — step 2 raises first, so the read half has had no live coverage since 2026-07-15. |
| User-impact | Auth policy integrity — an anonymous write silently persisting is a security regression; wiki reads staying open keeps discovery/remix live. |

### Green criteria

> **⚠ Unreachable as written (2026-07-22).** These are the criteria the probe
> *currently enforces*, not criteria the live server can currently satisfy. The
> second bullet describes a contract `972d0cc3` retired, so exit 0 is not
> attainable against production until the `codex` lane realigns the probe.

- Exit code 0.
- Anonymous `write_page` returns `status=rejected` with `auth_required=true` (no `isError`) — **retired contract; the server now answers HTTP 401 + `WWW-Authenticate` pre-dispatch.**
- `read_page` returns content matching `_CANARY_CONTENT` byte-for-byte — **still the correct criterion, but unexercised while step 2 fails first.**

### Red signals

- Exit 2 — MCP handshake failed (initialize or session establishment).
- Exit 6 — write-gate step failed. **Overloaded across seven raise sites spanning
  incompatible severities — see the table below before acting on it.**
- Exit 7 — wiki read failed or canary draft content mismatched.
- Exit 99 — unexpected error.

#### Exit 6 is overloaded — the seven things it can mean

`scripts/wiki_canary.py` raises `ToolCanaryError(6, ...)` from seven distinct
sites. They span "transient network blip" through "the public write surface is
open to anonymous writers." Line numbers are against `6f8cebc7` (current
`origin/main`).

| Site | Condition | Severity |
|---|---|---|
| `:199-205` — `post(..., step_code=6)` | Transport/HTTP error on `tools/call` — network, TLS, non-200. **Includes the HTTP 401 the current server correctly returns**, which is what fires today. | Ambiguous — noise *or* contract drift |
| `:207` | `write_page` returned no `result` | Write surface broken |
| `:211` | `isError=true` | Write surface broken |
| `:216` | No text content in the result | Write surface broken |
| `:220-222` | Result text is not JSON | Write surface broken |
| `:223-231` | **Anonymous `write_page` was ACCEPTED — the #1441 gate has regressed** | **P0 security regression** |
| `:232-237` | Envelope not `status=rejected` + `auth_required=true` | Contract drift |

Note the spread: a network blip and a live authentication bypass on the public
write surface are reported by the same integer.

#### How to tell which exit 6 you are looking at

**From the CI log alone, you cannot — verified 2026-07-22.** This is the single
most important operational fact about this probe.

`.github/workflows/uptime-canary.yml:212` invokes the probe without
`--format gha`, so `fmt` defaults to `log`. In `run_probe()`
(`scripts/wiki_canary.py:295-301`) the `ToolCanaryError` message is written only
to `_append_log(...)` → `LOG_PATH = <repo>/.agents/uptime.log`
(`scripts/uptime_canary.py:66`) — a file on the **ephemeral GHA runner**,
discarded when the job ends. `_emit_gha_kv("msg", exc.msg)` fires *only* when
`fmt == "gha"`. So the reason reaches neither stdout nor `$GITHUB_OUTPUT`.

The workflow does capture and echo the probe's stdout — but by then it holds
nothing discriminating. Verbatim, the *entire* captured output of run
`29894145473` (2026-07-22T05:34:15Z):

```
=== wiki canary (https://tinyassets.io/mcp) exit=6 ===
[wiki-canary] handshake OK sid='facc399f54664ac3b3ed6f1edfd65d1d'
```

An exit code, and a **success line from the preceding step**. The failure reason
is absent. That same string propagates into `msg_wiki` and into the P0 alarm
issue comment — so the alarm body for a six-day red streak reads "handshake OK".
Over the full run log, `grep -c Unauthorized` and `grep -c "HTTP 401"` both
return **0**.

**To disambiguate, run the probe yourself:**

```
python scripts/wiki_canary.py --url https://tinyassets.io/mcp --format gha
```

`--format gha` routes the message through `_emit_gha_kv`, which **prints to
stdout** (`scripts/wiki_canary.py:150-158`); the `msg=` line carries the
discriminating text (today: `HTTP 401 on tools/call: Unauthorized`). Without
that flag the reason is written only to a local `.agents/uptime.log`.

Until CI surfaces this, treat every `wiki=6` in a CI log as **undiagnosed** —
neither "known false red" nor "security regression" — and reproduce locally
before concluding either.

### Known false-red history

This probe has drifted out of alignment with the server **twice**, and both
times the drift presented as a P0 outage that did not exist. A reader hitting
`wiki=6` should check drift before checking the service.

| | Round 1 | Round 2 (current) |
|---|---|---|
| Server change | #1441 anonymous-write gate, deployed 2026-07-14 04:55Z | `972d0cc3` 401-pre-dispatch, 2026-07-15 20:54Z |
| Alarm issue | #1447 | **#1461** (still open) |
| Duration | ~18 h | **~6.4 days, ongoing** |
| False alarms | 16 | **109+** |
| Fix | `6f8cebc7` (PR #1449) | **not landed** |

The recurrence is the point. `6f8cebc7` fixed round 1 by hand-re-copying the new
contract into the probe; `git blame -L 220,240 scripts/wiki_canary.py` attributes
the now-stale lines **to that fix itself**. A hand-mirrored contract with no
shared fixture and no cross-check will drift again — and round 2 lasted 8×
longer than round 1, because by then the alarm channel had been trained to be
ignorable. Full forensics, including why the test suite stayed green throughout
(the fixtures assert the retired shape), are in
`docs/audits/2026-07-22-uptime-canary-false-red-incident.md` (PR #1513).

**Paired remediation lanes (in flight, not landed as of 2026-07-22):** a `codex`
lane owns `scripts/wiki_canary.py` + `.github/workflows/uptime-canary.yml` — the
401-contract realignment, the `--format gha` diagnostic fix, and any split of the
exit-6 codes. **When that lands, the exit-6 table and the "how to tell" section
above must be updated in the same pass.**

### Why this probe earns a catalog slot

BUG-028 demonstrated that a slug-normalization bug could silently break bug filing while the Layer-1 MCP handshake stayed green — the read half keeps that class covered. Post-#1441 the write half guards the auth boundary instead: a regression that silently re-opens anonymous writes would otherwise be invisible to every other probe.

### When to use

- After any change to wiki write/read tool handlers, slug normalization, or wiki storage backend.
- After any deploy that touches `_wiki_file_bug`, `write_page`/`read_page` routing, or the auth gate (`writes_require_identity` / `write_gate_rejection`).
- As a continuous P0 canary alongside PROBE-002.

### Limitations

- **Authenticated write-path persistence is NOT exercised.** Post-#1441 the probe
  asserts only that an *anonymous* write is refused; nothing confirms an
  *authorized* write actually persists. Restoring that coverage needs a canary
  service credential — tracked as a `host-decision` row in `STATUS.md`.
  Consequence: a regression that breaks authenticated wiki writes while leaving
  the gate and the read path intact is invisible to every probe in this catalog.
- **Scope is auth-gated deployments only** (see § *Invocation*). Against a
  dev-mode server the `:223-231` exit-6 row fires by design, which is why that
  row cannot be read as an unconditional security alarm.
- **The probe hand-mirrors a server contract.** There is no shared fixture
  between `scripts/wiki_canary.py` and the server, and no cross-check binding the
  canary's unit-test fixtures to the live response shape. That is the mechanism
  behind both entries in § *Known false-red history*.

---

## PROBE-004 — MCP tool-invocation end-to-end (handshake-vs-handler gap)

**Validated:** mcp_tool_canary script live since 2026-04-22; closes the gap flagged in canary task #6.
**Source script:** `scripts/mcp_tool_canary.py`
**Persona:** `mcp-tool-canary` (automated; client name `mcp-tool-canary/1.0`)
**Connector URLs under test:** `https://tinyassets.io/mcp` and `https://tinyassets.io/mcp-directory`

### Invocation

```
python scripts/mcp_tool_canary.py
python scripts/mcp_tool_canary.py --url https://tinyassets.io/mcp-directory
python scripts/mcp_tool_canary.py --url http://127.0.0.1:8001/mcp
python scripts/mcp_tool_canary.py --verbose --timeout 20
```

### What it exercises

| Layer | What's tested |
|---|---|
| System | `initialize` handshake (same as PROBE-002). |
| System | `notifications/initialized` (MCP-protocol mandatory before tool calls). |
| System | `tools/list` returns a non-empty tools array. |
| System | `tools/call` for the strongest advertised read-only probe returns valid JSON: legacy `universe action=inspect` requires `universe_id`; directory `get_workflow_status` requires `schema_version`. |

### Green criteria

- Exit code 0 — all four steps passed.

### Red signals

- Exit 2 — handshake failed (initialize error, network, TLS, non-200).
- Exit 3 — session establishment failed (no `mcp-session-id` header, or `notifications/initialized` POST errored).
- Exit 4 — `tools/list` failed or returned an empty tools array.
- Exit 5 — the selected probe `tools/call` failed or returned an invalid response (missing expected fields, `isError` set, etc.).

### Why this probe earns a catalog slot

`mcp_public_canary.py` (PROBE-001/002 layer) only probes `initialize`, which proves the daemon answers the MCP handshake but NOT that any tool handler actually works. The "handshake green, tool handler crashed" failure class would go undetected without this probe. Catches a distinct failure mode: handshake passes but a tool handler raises uncaught, an export is broken, or `universe_server.py` boot succeeds but a registered tool fails on first call.

### When to use

- After any code change to `universe_server.py` tool registration or handler bodies.
- After any deploy that adds/renames/removes MCP tools on either `/mcp` or `/mcp-directory`.
- As a continuous Layer-1.5 canary between handshake-only and full chatbot probes.

---

## PROBE-005 — Last-activity freshness (node execution liveness)

**Validated:** registration 2026-04-26 — script live since task #15 landed (tests at `tests/test_last_activity_canary.py`). Scheduled in CI as the `activity_probe` step in `.github/workflows/uptime-canary.yml`, after handshake + tool canaries pass. Cadence: configured `*/5 * * * *`, but observed delivery on 2026-07-22 was ~1 run/hour (see PROBE-003 § *Cadence caveat*).
**Source script:** `scripts/last_activity_canary.py`
**Persona:** `last-activity-canary` (automated; client name `workflow-last-activity-canary/1.0`)
**Connector URL under test:** `https://tinyassets.io/mcp`

### Invocation

```
python scripts/last_activity_canary.py
python scripts/last_activity_canary.py --url http://127.0.0.1:8001/mcp
python scripts/last_activity_canary.py --threshold-min 60 --verbose
```

Env override: `TINYASSETS_LAST_ACTIVITY_THRESHOLD_MIN` sets the default threshold (minutes).

### What it exercises

| Layer | What's tested |
|---|---|
| System | MCP `initialize` + `notifications/initialized` handshake. |
| System | `read_graph target=graph` (same inspect payload; the deprecated `universe` fat tool refuses anonymous calls since #1441) returns a `daemon.last_activity_at` timestamp. |
| System | The timestamp is fresh — within `--threshold-min` (default 30) of now. |
| User-impact | "MCP green but node execution stalled" failure class — exactly the live-2026-04-22 state before the cloud-side worker landed. |

### Green criteria

- Exit code 0.
- `daemon.last_activity_at` is within the threshold (FRESH).

### Red signals

- Exit 2 — `last_activity_at` exceeds the threshold (STALE — paged regardless of queue depth; persistent stale-but-empty IS pageable per script docstring).
- Exit 3 — daemon responded but no parseable `last_activity_at` (unexpected tool shape, null/malformed field).
- Exit 4 — handshake / connectivity failure (distinct exit so operators can tell stale-execution from dark-daemon at a glance; overlaps with PROBE-001 deliberately).

### Why this probe earns a catalog slot

PROBE-001/002 prove the daemon answers MCP. PROBE-004 proves a tool handler runs. NEITHER proves the daemon is doing actual work — node execution can stall while every probe above stays green. The 2026-04-22 cloud-worker outage is the worked example: green Layer-1, green tool calls, zero scenes shipped. This probe is the only one in the catalog that catches that class.

### When to use

- After any change to dispatcher, executor, or the cloud worker.
- As a continuous Layer-1.5 canary alongside PROBE-002.
- Investigating user reports of "the daemon is up but nothing's happening."

---

## PROBE-006 — Revert-loop detection (busy-broken pathology)

**Validated:** registration 2026-04-26 — script live since revert-loop spec landed; spec at `docs/design-notes/2026-04-23-revert-loop-canary-spec.md`. Scheduled in CI as the `revert_loop_probe` step in `.github/workflows/uptime-canary.yml`, after handshake + tool canaries pass. Cadence: configured `*/5 * * * *`, but observed delivery on 2026-07-22 was ~1 run/hour (see PROBE-003 § *Cadence caveat*).
**Source script:** `scripts/revert_loop_canary.py`
**Persona:** `revert-loop-canary` (automated; client name `revert-loop-canary/1.0`)
**Connector URL under test:** `https://tinyassets.io/mcp`

### Invocation

```
python scripts/revert_loop_canary.py
python scripts/revert_loop_canary.py --url http://127.0.0.1:8001/mcp
python scripts/revert_loop_canary.py --verbose
```

Env overrides:
- `TINYASSETS_REVERT_CANARY_N` — WARN threshold (default 3)
- `TINYASSETS_REVERT_CANARY_T_MIN` — WARN window minutes (default 10)
- `TINYASSETS_REVERT_CANARY_N_CRITICAL` — CRITICAL threshold (default 5)
- `TINYASSETS_REVERT_CANARY_T_CRITICAL` — CRITICAL window minutes (default 20)

### What it exercises

| Layer | What's tested |
|---|---|
| System | MCP handshake + `get_status.evidence.activity_log_tail` retrieval. |
| System | Terminal REVERT-verdict count within a sliding time window. |
| User-impact | "Daemon IS making progress but every scene REVERTs" — the 2026-04-23 P0 class (67 reverts on `concordance` before host noticed). |

### Green criteria

- Exit code 0 — REVERT count below WARN threshold.

### Red signals

- Exit 2 — WARN: ≥N_WARN REVERTs within T_WARN minutes (page priority=0).
- Exit 3 — CRITICAL: ≥N_CRIT REVERTs within T_CRIT minutes (trigger auto-repair via p0-outage-triage).
- Exit 4 — handshake / connectivity failure (distinct from stale/dark for diagnostics).
- Exit 5 — daemon responded but `activity_log_tail` absent / unparseable.

### Why this probe earns a catalog slot

The 2026-04-23 P0 revert-loop concern is currently top-of-STATUS. PROBE-001 (handshake) and PROBE-005 (last_activity) both stay GREEN during a revert-loop because the daemon IS making progress — it's just throwing every commit away. Only this probe catches the busy-broken state. Spec-driven (Q2 mandate: count terminal REVERT verdicts only; Draft-FAILED retry-recovers within-scene and was explicitly rejected as noise).

### When to use

- After any change to the commit pipeline, scoring rubric, or provider-routing code.
- As a continuous P0 canary — pair with PROBE-005 to cover both "stalled" and "busy-broken" failure modes.
- After provider-quota / model-config changes (a degraded provider is a leading indicator of revert cascade).

---

## PROBE-007 — DNS resolution canary (host-independent vantage)

**Validated:** registration 2026-04-27 — workflow live since `.github/workflows/dns-canary.yml` landed; runs every 15 min from GitHub Actions infra (out-of-band from the host machine).
**Source workflow:** `.github/workflows/dns-canary.yml`
**Persona:** automated GHA runner (uses `socket.gethostbyname` from a Python inline block; no script wrapper).
**Hostnames under test:** `tinyassets.io`, `mcp.tinyassets.io`.

### Invocation

Runs automatically on the `*/15 * * * *` cron schedule + manual `workflow_dispatch` from the Actions tab.

### What it exercises

| Layer | What's tested |
|---|---|
| System | DNS A-record (or CNAME chain) resolution for the canonical apex plus the Access-gated tunnel origin from a vantage independent of the host machine. |
| User-impact | Catches NXDOMAIN regressions invisible to host-local resolvers — exactly the 2026-04-19 P0 class where a Cloudflare tunnel reshuffle silently dropped the apex CNAME. |

### Green criteria

- Both `tinyassets.io` and `mcp.tinyassets.io` resolve to an IP from the GHA runner.
- TinyAssets exits 0; `overall=green` in step output.

### Red signals

- Either hostname fails to resolve (`socket.gaierror` or other exception).
- TinyAssets exits non-zero; `overall=red`.
- Two consecutive reds → opens GitHub Issue labeled `dns-red`.
- GREEN after open issue → comments RECOVERED + closes the issue.

### Why this probe earns a catalog slot

The 2026-04-19 P0 outage-postmortem (`docs/audits/2026-04-20-public-mcp-outage-postmortem.md`) §3 named "no out-of-band probe" as the load-bearing gap that allowed a 69-min silent outage. PROBE-001/002/004 all probe `/mcp` over HTTP; if the apex CNAME vanishes (NXDOMAIN), HTTP probes fail in distinguishable but similar-looking ways. PROBE-007 narrows diagnosis: a DNS-red without HTTP-red is a name-resolution / propagation issue; a DNS-red with HTTP-red corroborates a tunnel/dashboard-state regression. Distinct from `uptime-canary.yml` which probes Cloudflare-Worker-fronted HTTP — DNS-canary probes one layer below.

### When to use

- Continuous out-of-band tunnel-state monitoring (catches CNAME deletions during Cloudflare-dashboard automation sessions).
- Post-DNS-record-change verification (godaddy-ops + cloudflare-ops skills both reference this).
- Investigating user reports of "tinyassets.io is down" — first-look layer to differentiate DNS from HTTP from MCP-handler causes.

---

## PROBE-008 — LLM binding freshness canary

**Validated:** registration 2026-04-27 — workflow live since `.github/workflows/llm-binding-canary.yml` landed; runs every 6h from GitHub Actions.
**Source script:** `scripts/verify_llm_binding.py` (invoked from GHA workflow).
**Source workflow:** `.github/workflows/llm-binding-canary.yml`
**Connector URL under test:** `https://tinyassets.io/mcp`

### Invocation

Runs automatically on the `0 */6 * * *` cron + manual `workflow_dispatch`.

### What it exercises

| Layer | What's tested |
|---|---|
| System | Live daemon `get_status` call — `evidence.llm_endpoint_bound` field readable. |
| System | Field is NOT the literal string `"unset"` — daemon has at least one provider bound and reachable. |
| User-impact | "MCP green, tools call cleanly, but no LLM is bound" silent-failure class (token rotation expiry, codex CLI version drift, docker restart that lost env injection). |

### Green criteria

- Exit code 0 — `verify_llm_binding.py` confirms `llm_endpoint_bound != "unset"`.
- TinyAssets exits 0; `overall=green`.

### Red signals

- Exit non-zero — handshake failed or `llm_endpoint_bound == "unset"`.
- Two consecutive reds → opens GitHub Issue labeled `llm-binding-red`.
- GREEN after open issue → comments RECOVERED + closes.

### Why this probe earns a catalog slot

PROBE-002 (Layer-2 chatbot liveness) overlaps on the `llm_endpoint_bound` field semantically — but PROBE-002 routes via Claude.ai (chatbot vantage, hourly cadence, designed-only as of catalog filing) while PROBE-008 calls the daemon directly from GHA on a slow-drift cadence appropriate to binding regressions. Different vantage, different cadence, different failure-mode focus (binding drift, not chatbot-tool invocation). Closes the "host-machine offline = silent binding loss for hours" gap.

### When to use

- Continuous host-independent binding monitoring.
- After provider-token rotation, codex CLI upgrade, or any deploy that touches the daemon's provider env.
- Investigating user reports of "the daemon answered but said no LLM was bound" — confirms whether the report is current vs cached.

---

## PROBE-009 — Tier-3 OSS fresh-clone smoke

**Validated:** registration 2026-04-27 — workflow live since `.github/workflows/tier3-oss-clone-nightly.yml` landed; runs nightly from GitHub Actions.
**Source workflow:** `.github/workflows/tier3-oss-clone-nightly.yml`
**Source script:** `scripts/tier3_smoke.py` + `scripts/import_graph_smoke.py` (called inside the workflow).
**Persona:** automated GHA runner simulating a fresh tier-3 OSS contributor path.

### Invocation

Runs automatically on the `17 7 * * *` cron (07:17 UTC daily) + manual `workflow_dispatch`.

### What it exercises

| Layer | What's tested |
|---|---|
| System | `git clone --depth 1` of the repo on a fresh GHA runner (no cache, no host artifacts). |
| System | `python -m venv .venv` + `pip install -e .` succeeds from `pyproject.toml` alone. |
| System | `import workflow` works at top level after install. |
| System | `scripts/tier3_smoke.py` structural smoke + `scripts/import_graph_smoke.py` import-graph smoke (catches missing-symbol / dropped-file regressions at package import). |
| System | `pytest tests/smoke/ -x` — fast smoke-test subset green on a fresh clone. |
| User-impact | AGENTS.md Forever Rule "tier-3 OSS contributors `git clone` and run cleanly" — directly probes the contributor onboarding surface. |

### Green criteria

- All 6 workflow steps (clone, venv, install, top-level import, structural smoke, import-graph smoke, smoke pytest) exit 0.
- TinyAssets conclusion = success.

### Red signals

- Any step exits non-zero.
- Failure path opens GitHub Issue labeled `tier3-broken` with the failing commit SHA + run URL.
- No auto-recovery / auto-close — issue stays open until manual triage + fix-forward (debug order documented in the workflow body).

### Why this probe earns a catalog slot

Per `docs/audits/2026-04-20-public-mcp-outage-postmortem.md` §6: "Highest-priority post-canary addition: tier-3 OSS clone nightly probe. That surface is just as public as the MCP connector and has zero monitoring today — the project is one bad commit away from 'fresh contributors silently bounce because pip install -e . fails.'" PROBE-001..008 all probe the running daemon; PROBE-009 alone probes the contributor onboarding surface. Catches dirty-tree commits, missing files, broken pyproject.toml, dropped symbols, and import-graph regressions that running-daemon probes cannot see.

### When to use

- Continuous monitoring of the OSS-contributor entrypoint (passive — fires nightly).
- After any commit that touches `pyproject.toml`, package layout, top-level imports, or `__all__` declarations.
- Before merging structural refactors (manual `workflow_dispatch` to run the smoke against a PR's HEAD before the daily cron).

---

## Borderline scripts — intentionally not catalogued

These canary-adjacent scripts exist in the repo but do NOT earn standalone catalog slots per the audit's admission criteria. Listed here so future audits can confirm their omission is intentional, not accidental.

| Script | Why no slot |
|---|---|
| `scripts/uptime_canary.py` | Thin wrapper around `mcp_public_canary.probe_result` that adds local-log persistence and production apex `/` HTTP-200 coverage. Same surface as PROBE-001 — duplicating it as a slot would double-count. The wrapper is the Task-Scheduler-invoked form; PROBE-001 is the user-invocable form. |
| `scripts/uptime_alarm.py` | Escalation **action**, not a probe. Tails `.agents/uptime.log` and emits alarm lines. Note: per task #20, prod alarm log moved to `/var/log/tinyassets/uptime_alarms.log` (env-overridable). |
| `scripts/selfhost_smoke.py` | Time-bounded Row-F acceptance script (48h offline trial — hour 1, 24, 47). Default mode targets the canonical endpoint and confirms the public direct tunnel origin is Access-gated (401/403). `--internal-parity` preserves the old parity comparison only for internal/service-token tunnel paths. Not a steady-state public probe; once Row F closes, this script is archived. |
| `.github/workflows/p0-outage-triage.yml` | Escalation **action**, not a probe. Auto-fired by `uptime-canary.yml` on CRITICAL alarm; runs forensics + opens triage issue. Same shape as `uptime_alarm.py` (action, not green/red signal). |
| `.github/workflows/dr-drill.yml` | Quarterly disaster-recovery rehearsal triggered by `workflow_dispatch` only. Acceptance-test-as-CI rather than steady-state probe; same family as `selfhost_smoke.py`. STATUS Work table tracks drill cadence. |

A "post-fix clean-use evidence" verification primitive (AGENTS.md Quality Gates) also has no automated probe today. This is intentional: the primitive is evidence-gathering against real-user traces, not a parseable green/red script.

---

## Claim freshness sweep — 2026-07-22

Every `Validated:` line in this catalog is a **claim about the past** that
silently becomes a claim about the present when an on-call reader uses it to
decide whether a red probe is real. Nothing re-checks them. PROBE-003 sat
certified as "Reworked 2026-07-14" while red for six days.

This is a point-in-time sweep, not a standing guarantee. Environment: live
GitHub Actions history + `origin/main` @ `6f8cebc7`, Windows host, 2026-07-22
~06:00Z.

| Probe | Verdict | Evidence |
|---|---|---|
| PROBE-001 | **Unverifiable by script** — by design | Manual rendered-chatbot probe; no automated signal exists. Source audit `docs/audits/user-chat-intelligence/2026-04-20-do-cutover-acceptance.md` is present. Last live validation **2026-04-20 (~3 months stale)**; the Baseline-evidence table is history, not currency. Needs a fresh `ui-test` run to re-certify. |
| PROBE-002 | **STALE — corrected in place** | Claimed CI "exits 14 SKIP cleanly"; actually exits **13 `RED_browser_load_error`** on 5/5 sampled runs, swallowed by `continue-on-error: true`. Separately re-verified: `Get-ScheduledTask -TaskName TinyAssets-Canary-L2` → **still not registered** on the host, so the 2026-05-01 "UNWIRED" note remains accurate. |
| PROBE-003 | **STALE — corrected in place** | 106 consecutive CI failures since 2026-07-15T20:38:50Z; last green run `29449080825`. Contract drift vs `972d0cc3`. Remediation not landed. |
| PROBE-004 | **Still true** | `tool=0` green in every sampled `uptime-canary` run; `scripts/mcp_tool_canary.py` present. |
| PROBE-005 | **Still true** (cadence clause corrected) | `activity=0` green in every sampled run; `scripts/last_activity_canary.py` present. |
| PROBE-006 | **Still true** (cadence clause corrected) | `revert=0` green in every sampled run; `scripts/revert_loop_canary.py` present. |
| PROBE-007 | **Still true**, cadence claim partial | `dns-canary.yml` 5/5 recent runs `success`. Claimed "every 15 min"; observed gaps of 1.1–3.4 h — same GHA cron-throttling caveat as PROBE-003. |
| PROBE-008 | **Still true** | `llm-binding-canary.yml` 5/5 recent runs `success`; `scripts/verify_llm_binding.py` present. |
| PROBE-009 | **Still true** | `tier3-oss-clone-nightly.yml` 5/5 recent runs `success`; both referenced scripts present. |

**Summary: 6 of 9 verified still true, 2 stale and corrected here, 1
unverifiable by construction.** The two stale entries (PROBE-002, PROBE-003) are
both *monitors that hand-mirror a contract they do not share with the thing they
monitor* — the same structural defect, found twice, and in both cases the probe
failed silently rather than loudly.

---

## Adding new probes

A probe earns a catalog entry when:
1. It has been run live (not just designed) against the production endpoint.
2. It has at least one green baseline AND one red baseline (or a documented pre-fix red state).
3. Its green/red criteria are parseable without human judgment.

Draft probes (designed but not yet live-validated) may be kept in the
mission-draft files until they earn a live run.
