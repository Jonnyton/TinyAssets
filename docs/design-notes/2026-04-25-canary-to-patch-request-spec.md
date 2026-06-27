---
status: superseded
superseded_by: docs/design-notes/2026-04-25-canary-to-patch-request-spec-v2.md
---

# Canary → patch_request Seam — Design Spec

**Date:** 2026-04-25
**Author:** navigator
**Status:** Design spec. Lead routes implementation as dispatch.
**Roadmap reference:** Phase C item 14 in `docs/design-notes/2026-04-25-primitive-shipment-roadmap.md` — "the smallest closed-loop MVP unlock."
**Convergence:** at end of Phase C, this seam plus existing canary infrastructure plus the bug-investigation canonical (Mark's branch + roadmap items P5/P6) closes the auto-heal loop end-to-end for the auto-detect → patch-packet → manual-merge case.

---

## 1. Trigger surfaces

Five canary scripts already log to `.agents/uptime.log` + `.agents/uptime_alarms.log`. Each has a documented exit-code ladder. Failures map to patch_request `kind` + `failure_class` deterministically.

| Canary | Script | Failure type → patch_request kind | failure_class |
|---|---|---|---|
| **PROBE-001 — public MCP handshake** | `scripts/mcp_public_canary.py` | exit 1 = malformed init → `bug` | `mcp_init_malformed` |
| | | exit 2 = unreachable → `uptime` | `endpoint_unreachable` |
| | | exit 3 = jsonrpc error → `bug` | `mcp_jsonrpc_error` |
| **PROBE-002 — Layer-2 deeper init** | `scripts/uptime_canary_layer2.py` | RED (deep init failure) → `uptime` | `mcp_layer2_red` |
| | | SOFT_YELLOW → suppressed (no patch_request; see §3) | — |
| **PROBE-003 — wiki write-roundtrip** | `scripts/wiki_canary.py` | exit 2 = handshake fail → `uptime` | `wiki_handshake` |
| | | exit 6 = write fail → `bug` | `wiki_write_failed` |
| | | exit 7 = read mismatch → `bug` | `wiki_roundtrip_mismatch` |
| **PROBE-004 — MCP tool list** | `scripts/mcp_tool_canary.py` | non-zero = tool-list/discover failure → `bug` | `mcp_tool_discovery` |
| **revert_loop_canary** | `scripts/revert_loop_canary.py` | CRITICAL = sustained revert loop → `uptime` | `revert_loop` |
| | | WARN = single-run regression → `bug` | `single_revert` |

**Exclusions:** `last_activity_canary.py` is a heartbeat; no patch_request route — it's noise without a clear failure surface. `install_canary_task.ps1` is a Windows scheduler installer, not a probe.

**Existing infrastructure assumed:**
- `_append_log` from `scripts/uptime_canary.py` — uniform log writer; reused via cross-import (already pattern in `wiki_canary.py`).
- Each canary already classifies its failure into an exit code ladder; no new classification logic needed at the canary level.

---

## 2. patch_request frontmatter shape

Reuse existing `_wiki_file_bug` primitive. Pass via the standard `kind` + `tags` + structured fields. The canary-specific provenance lives in `tags` + `observed`/`expected` body, NOT in new frontmatter columns — keeps the file_bug primitive unchanged.

**File path:** `pages/bugs/BUG-NNN-<slug>.md` (today's behavior; FRESH-B kind=routing taxonomy split is independent and doesn't gate this).

**Frontmatter (existing fields filled by canary):**

```yaml
---
bug_id: BUG-NNN                    # server-assigned via _next_bug_id
title: <canary_name>: <failure_class> on <surface>
component: <surface>               # e.g., "tinyassets.io/mcp", "wiki", "revert-loop"
severity: <P0|P1|P2 — see §4>
kind: <bug|uptime>                 # see §1 mapping
tags: source:canary, canary:<canary_name>, failure_class:<failure_class>
first_seen_date: <today UTC>
---
```

**Body (canary fills):**

```markdown
## Observed
<canary's stderr message + exit code>

## Expected
<canary's success contract — pulled from canary's own docstring exit-codes table>

## Repro
python scripts/<canary_name>.py [args used]

## Evidence
- Canary exit_code: <int>
- Timestamp (UTC): <iso>
- RTT (ms): <int if applicable>
- Probe URL / target: <url-or-target>
- Tail of .agents/uptime_alarms.log around event:
  ```
  <last 5 lines>
  ```
- Last green probe (if any): <iso timestamp from .agents/uptime.log>
```

**Wire-shape (chatbot-equivalent invocation):**

```python
from workflow.universe_server import _wiki_file_bug

_wiki_file_bug(
    component="tinyassets.io/mcp",
    severity="P0",
    title=f"PROBE-001: endpoint_unreachable on {url}",
    kind="uptime",
    observed=stderr_message,
    expected="MCP initialize round-trip returns serverInfo + protocolVersion",
    repro=f"python scripts/mcp_public_canary.py --url {url}",
    workaround="",
    tags=f"source:canary,canary:mcp_public_canary,failure_class:endpoint_unreachable",
    force_new=False,  # let dedup/cosign handle re-fires; see §3
)
```

`force_new=False` is load-bearing. The existing `_wiki_file_bug` similarity check (Jaccard ≥ 0.5) handles the most common dedup case (same canary + same failure_class fires twice). Server returns `status: similar_found` with a cosign hint; canary uses that response per §3.

---

## 3. Throttling + dedup

Two layers, both reusing existing primitives:

### Layer 1 — canary-side throttle file

Each canary maintains a small JSON state file at `.agents/canary_state/<canary_name>.json`:

```json
{
  "last_filed": {
    "endpoint_unreachable": {
      "bug_id": "BUG-042",
      "filed_at": "2026-04-25T14:30:00Z",
      "cosign_count": 3
    }
  }
}
```

**Throttle rule:**
- For each `(canary_name, failure_class)` pair, the canary writes at most **one new patch_request per 6 hours** unless severity escalates from P1/P2 to P0 (then file immediately).
- Within the 6h window, repeated failures of the same kind invoke `cosign_bug` against the existing `bug_id` instead of filing a new one. Cosign body: just an updated timestamp + the latest evidence tail. This naturally surfaces "this has been failing for hours" via the cosign_count growth.
- After 6h elapse OR canary returns green for ≥30 minutes, the throttle expires; next failure files fresh.

### Layer 2 — server-side dedup (existing)

`_wiki_file_bug` already runs Jaccard similarity (≥0.5 threshold) against open bugs at filing time. Returns `{"status": "similar_found", "similar": [...]}` with a cosign hint when a close-enough open bug exists.

**Canary handles `similar_found` response:**
1. Pick top match (highest similarity).
2. Call `cosign_bug bug_id=<top.bug_id> reporter_context="<latest evidence tail>"`.
3. Update local state file: `last_filed[failure_class] = {bug_id: top.bug_id, ...}`.
4. Treat as "re-fire of known failure," not a new bug.

This combination means: even if the canary state file is wiped or a different canary host fires the same probe, the server-side dedup catches the duplicate and routes to cosign automatically. Layer 1 is an optimization to avoid unnecessary server round-trips; Layer 2 is the safety net.

**Severity-escalation override:** if a probe was filed at P1/P2 and re-fires at P0 within the throttle window, file a NEW patch_request with `force_new=True` and tag `severity_escalation:from-P2-to-P0`. Don't cosign at lower-priority — escalation deserves visibility.

---

## 4. Severity mapping

| Surface affected | Default severity | Notes |
|---|---|---|
| **Public MCP unreachable** (PROBE-001 exit 2) | **P0** | Forever Rule violation — tier-1 chatbot users blocked. |
| **Wiki write fails** (PROBE-003 exit 6) | **P0** | Auto-heal pipeline broken — chatbots can't file bugs (per memory `project_wiki_is_uptime_surface`). |
| **Wiki roundtrip mismatch** (PROBE-003 exit 7) | **P0** | Data-loss risk — silent corruption pattern (BUG-028 class). |
| **Sustained revert loop** (revert_loop CRITICAL) | **P0** | Prior P0 incident class (2026-04-23). |
| **Layer-2 deeper init red** (PROBE-002 RED) | **P1** | MCP works but degraded; chatbot may see partial functionality. |
| **MCP jsonrpc error** (PROBE-001 exit 3) | **P1** | Endpoint reachable, server-internal error. Could be transient. |
| **MCP malformed init** (PROBE-001 exit 1) | **P1** | Protocol version mismatch likely; not a full outage. |
| **MCP handshake fail** (PROBE-003 exit 2) | **P1** | Wiki transport intact but handshake broken — narrow scope. |
| **Tool discovery fails** (PROBE-004 non-zero) | **P1** | Some tools may still work; investigation needed. |
| **Single-run regression** (revert_loop WARN) | **P2** | Not yet a loop; precursor signal. Often false-positive. |
| **Layer-2 SOFT_YELLOW** | (suppressed) | Not a failure — soft signal only. No patch_request. |

**Severity is a label, not a routing decision.** All canary-filed patch_requests today run through the same Phase A gate-series once Phase A lands. P0 may eventually trigger fast-track auto-merge under uptime emergency (per primitive-shipment roadmap §5 Phase D auto-merge gate philosophy); not in this seam's scope.

---

## 5. Closure path

A canary-filed patch_request has three close conditions, in order of preference:

1. **Auto-close on sustained green** (preferred). When the same canary returns green continuously for **M = 30 minutes**, the canary calls a closure routine: append a comment to its open bug ("Closed: <canary_name> green since <iso>; auto-resolved.") and update the bug page status to `fixed (auto-resolved)`. This handles the "transient flake" class — most common case.
2. **Manual close via fix-merged signal**. When a PR commits with `Fixes: BUG-NNN` or `Closes: BUG-NNN` in the message body and merges, a (future) post-merge hook updates the bug to `fixed (commit-sha)`. This handles the "real fix landed" class. **Not in this seam's scope** — it's Phase D infrastructure (post-merge attribution + status updates). Spec acknowledges the dependency without building it here.
3. **Manual close by human/navigator**. Standard wiki edit. Always available.

**Idempotency:** if a canary tries to auto-close a bug that's already manually closed, the operation is a no-op (status already `fixed`). If the canary tries to file a new bug for a failure class that's still in throttle window AND the prior bug is closed, file fresh — closed bugs don't suppress new filings.

**Watch-window relationship:** auto-close does NOT bypass the post-fix watch window from AGENTS.md "post-fix clean-use evidence." A bug auto-closed at minute 30 stays under watch until subsequent canary-green observations confirm clean over a longer horizon. The canary's local state file tracks watch-window status; it just stops re-filing.

---

## 6. Wiring — where the trigger lives

**Recommendation: thin module per canary, NOT a centralized watchdog.**

Each canary script imports a shared helper module (`scripts/canary_patch_request.py` — new, ~80 lines) and calls it on failure detection:

```python
# at end of canary main(), in the failure path:
from canary_patch_request import file_or_cosign

file_or_cosign(
    canary_name="mcp_public_canary",
    failure_class="endpoint_unreachable",
    severity="P0",
    component="tinyassets.io/mcp",
    title=f"PROBE-001: endpoint_unreachable on {url}",
    observed=stderr_message,
    expected="MCP initialize round-trip returns serverInfo + protocolVersion",
    repro=f"python scripts/mcp_public_canary.py --url {url}",
    evidence={"exit_code": 2, "rtt_ms": rtt_ms, "url": url},
)
```

**Why per-canary, not centralized:**
1. **Scope-locality.** Each canary already knows its surface, expected behavior, and failure mapping. A central watchdog would have to re-parse `.agents/uptime_alarms.log` and re-derive what each canary already knows. Lossy translation.
2. **No race window.** With per-canary wiring, the patch_request fires within the same process that detected the failure — no lag, no missed events between log-write and central reader pickup.
3. **Backward-compat with existing canary contracts.** Each canary keeps its current exit-code-on-failure behavior intact (tray watchdog still gets the signal). Patch_request filing is additive — canary becomes a slightly-fatter binary, exits with the same codes.
4. **Fewer moving parts.** No central watchdog daemon to keep alive. Each canary self-contains the seam.
5. **Composability with future canaries.** When a new canary script is added (e.g., `scheduler_canary.py`), it imports the same helper. No need to update a central allow-list.

**Shared helper responsibilities** (`scripts/canary_patch_request.py`):
- Read/write the per-canary state file at `.agents/canary_state/<canary_name>.json`.
- Apply the throttle rule from §3 Layer 1.
- Call `_wiki_file_bug` (or its equivalent live MCP endpoint via stdlib HTTP — canaries are stdlib-only per their docstrings).
- Handle `similar_found` response → call `cosign_bug`.
- Handle `success` response → update local state file with new bug_id.
- Provide `auto_close_if_green(canary_name, green_for_seconds=1800)` for closure.

**Failure mode of the seam itself:** if the wiki MCP is down (the very surface the canary is testing), the patch_request call will fail. Spec: catch + log to `.agents/uptime_alarms.log` with marker `PATCH_REQUEST_FAILED reason=...`. The tray watchdog already escalates persistent alarms. Don't retry-loop in the canary — the next canary tick will retry naturally.

**One subtle wiring decision: which MCP endpoint do canaries call?** PROBE-001 fails *because* the public MCP endpoint is down. Filing patch_request against the same down endpoint = filing fails. Two options:
- **(A)** Canaries call the local daemon endpoint (`http://127.0.0.1:8001/mcp`), which is more likely up than the public surface. Reasonable default.
- **(B)** Canaries probe the same surface they're testing. Self-fulfilling failure when the surface is down.

**Spec recommends (A)**, with fallback to local logging if local daemon also unreachable. Canaries running on the daemon host already have local-port access.

---

## 7. Open questions

1. **Throttle-state-file persistence under daemon restart.** If `.agents/canary_state/<canary_name>.json` is wiped (clean-room install, manual reset), the canary will re-file after a fresh failure even within the original 6h window. Server-side dedup catches it, but local state loss = one extra cosign per failure_class per restart. Acceptable, or do we persist to a more durable location?

2. **Severity escalation memory window.** Spec says re-fire at P0 from P1 within the throttle window files a new bug. But what if the original bug was cosigned to P0 by a human between filings? Today no mechanism for human-edited severity to update the canary's local state. Should canary re-read the open bug's current severity before filing-or-cosigning? Adds a round-trip but more accurate.

3. **`source:canary` tag namespace.** Today's `tags` field is comma-separated free-form. Spec uses `source:canary, canary:<name>, failure_class:<class>`. Worth formalizing as a tag namespace convention now? Or let it grow organically and formalize in v2?

4. **Auto-close vs. watch-window collision.** Spec auto-closes after 30min green, but post-fix watch-window from AGENTS.md is conceptually multi-day. The auto-close marks bug status `fixed` at minute 30, but watch is still active. This is fine if downstream readers respect the watch tag, but creates a UX where a "fixed" bug might re-open if the watch fails. Cleaner: introduce a `closed-watching` status distinct from `fixed`?

5. **Canary that probes the auto-heal loop itself.** Once this seam ships, we should canary it — periodically inject a synthetic failure into a no-op canary that the seam catches and files. Otherwise we won't know if the seam itself is broken. Out of scope for #57 dispatch, but worth a follow-up task.

---

## 8. References

- Existing canary scripts: `scripts/mcp_public_canary.py`, `scripts/uptime_canary.py`, `scripts/uptime_canary_layer2.py`, `scripts/wiki_canary.py`, `scripts/mcp_tool_canary.py`, `scripts/revert_loop_canary.py`.
- Log surface: `.agents/uptime.log`, `.agents/uptime_alarms.log` (today's WATCHDOG_RESTART pattern is the precedent for structured event lines).
- File_bug primitive: `tinyassets/universe_server.py:13102` (`_wiki_file_bug`), `:13025` (`_wiki_cosign_bug`).
- Probe catalog: `docs/ops/acceptance-probe-catalog.md`.
- Roadmap: `docs/design-notes/2026-04-25-primitive-shipment-roadmap.md` Phase C item 14.
- v1 vision: `docs/design-notes/2026-04-25-self-evolving-platform-vision.md` §3 (auto-heal as canary trigger surface).
- Memory load-bearing: `project_wiki_is_uptime_surface`, `project_always_up_auto_heal`, `project_file_bug_dedup_at_filing`, `project_bug_investigation_general_dispatch`, `feedback_uptime_top_priority`.
- Convergence — when this seam fires + Phase A gates run + Mark's bug-investigation canonical produces a packet, the closed-loop MVP runs end-to-end.
