# Production MCP Sweep — tinyassets.io/mcp — 2026-07-08

Read-only probes plus one `dry_run` write and one minimal `write_graph` call,
via raw MCP sessions (initialize → initialized → tools/call), text-only-client
perspective. Production serverInfo: `tinyassets 0.1.0`; six tools exposed
(`read_graph`, `write_graph`, `run_graph`, `read_page`, `write_page`,
`get_status`) — `run_graph` and `write_page` are new since the original
bug report.

## Previously filed bugs — status on production

| # | Filed bug | Status |
|---|---|---|
| 2 | `structuredContent`-only dark payloads (`get_status`, `read_graph target=status`, `read_graph target=goals` list mode, single-page `read_page`) | **FIXED.** Every probed surface now returns a populated text block alongside `structuredContent`. Goals list mode even degrades gracefully when empty ("No Goals match the filter yet…"). |
| 3 | `write_graph` blocked with bare "No approval received", no remediation path | **REGRESSED THE OTHER WAY — see P0 below.** The error is gone because the gate is gone. |
| 4 | Tool-description contract mismatches (narrating unreachable caveats) | Moot for the probed tools now that text blocks exist; re-review descriptions against the new six-tool surface. |

## New findings

### P0 — SECURITY: `write_graph` accepts anonymous writes with no approval gate
A minimal unauthenticated `write_graph target=goal` call **persisted a public
goal** on production: `goal_id 1a917636ae83`, name `probe-goal-do-not-create`,
author `anonymous`, visibility `public`. Confirmed persisted via a follow-up
`read_graph target=goals` query in a fresh call.

- Impact: the shared commons is anonymously writable — spam/abuse/defacement
  vector on the exact surface every universe reads designs from.
- The original bug asked for a *remediation path* on the approval error, not
  removal of the gate. Restore the gate with an actionable error (how to
  authenticate / request approval), keep anonymous read.
- **Cleanup needed:** delete goal `1a917636ae83` (admin). The probe stopped
  after one write; no further writes were attempted.

### P1 — Wiki subsystem down: `/data/wiki` Permission denied
Every `read_page` and `write_page` mode (single-page, search, dry_run) returns:
`"Wiki scaffold failed at /data/wiki: [Errno 13] Permission denied"` with hint
`"The volume must be writable by the daemon uid."` The whole wiki surface —
including bug filing itself — is unavailable on production. Likely a volume
ownership/uid mismatch in the deploy; the hint says exactly what to fix.
(Noted: error reporting here is exemplary — text block + machine-readable
error + actionable hint. This is the pattern the P0 fix should follow.)

### Nice-to-have observations
- `write_page` grew a `dry_run` flag and structured bug-report fields
  (`severity`, `repro`, `observed`, `expected`, `workaround`) — good surface,
  currently unreachable due to P1.
- Session lifecycle, SSE framing, and session-id handling all behaved
  correctly across ~10 sessions.
