# Agent Village — web command center for live agent activity (design one-pager)

Date: 2026-07-19 · Source: host request · Status: design awaiting approval

## Problem Statement

How might we let the host see, from a phone, every AI agent and subagent
(Claude Code, Codex, Kimi, Cursor, …) currently working the TinyAssets repo —
where each one is in the file tree, what it's doing right now, and a live feed
of who did what — and let the host talk to any of them?

## Recommended Direction

A small standalone Python server (`command_center/`, stdlib-only) serving a
single-file mobile web app. The project tree renders as a top-down 2D village:
top-level directories are zones/buildings, each live agent is a sprite that
walks to the zone it's touching. Tap/hover a sprite → speech bubble with
provider, main-vs-subagent, current action, and file. Sidebar = merged live
event feed. Environment reacts: zones pulse on writes, day/night tint by clock.

- **State collector (server-side, polls every ~3s):**
  - `scripts/worktree_status.py --json` → active lanes, dirty state, branch.
  - `STATUS.md` Work table → claimed rows, provider names, ACTIVE heartbeats.
  - Filesystem mtime scan of main checkout + `../wf-*` worktrees (excluding
    `.git`, `node_modules`, `codex-tmp`, `__pycache__`) → "agent X is near
    file Y" + zone activity.
  - `.claude/projects/**/*.jsonl` transcript mtimes/tails → Claude Code
    liveness, current tool action, subagent (`agent-*`) sessions. Best-effort
    equivalents for `.codex/` / `.kimi/` runtime files if present.
  - `.agents/activity.log` tail + recent `git log` in each lane → feed events.
- **Server endpoints:** `GET /` (app), `GET /api/state` (JSON snapshot:
  agents, zones, events), `POST /api/talk` (message an agent). No WebSocket —
  the page polls `/api/state` every few seconds.
- **Talk to an agent:** tap sprite → chat sheet. Message is appended to
  `.agents/village-inbox/<agent>.md` (durable, agents can poll) and, if that
  provider's CLI is installed, dispatched headless via `scripts/peer_agent.py`
  with the reply shown in the sheet. Honest limit: cannot inject text into an
  already-running interactive session.
- **Phone access:** bind `0.0.0.0:8787`; phone opens `http://<LAN-IP>:8787`.
  Optional shared `--token`. No tunnel in MVP.

## Key Assumptions to Validate

- Liveness proxies (claims + mtimes + transcripts) are fresh enough that
  sprites feel alive — validate against a real multi-provider session.
- The repo root has 140+ entries; map must collapse quiet zones and show only
  active zones + a curated core set (`workflow/`, `scripts/`, `docs/`,
  `ideas/`, `WebSite/`, `tests/`, `.agents/`) plus one island per worktree.
- Subagent detection is Claude-Code-centric at first (transcript dirs); other
  providers initially appear as main sessions only.

## MVP Scope

1. Collector → `/api/state` JSON (agents, zones, events).
2. Single-file HTML/JS app: village map, sprites with speech bubbles, event
   feed sidebar, tap-to-talk sheet. Mobile-first.
3. `POST /api/talk` → inbox file + optional `peer_agent.py` dispatch.
4. Unit tests for parsers (STATUS.md rows, worktree JSON, transcript tail,
   mtime→zone mapping) + server smoke test.
5. Run instructions in module README; `python -m command_center` entry point.

## Not Doing (and why)

- No WebSocket/SSE — 3s polling is indistinguishable at this scale, far simpler.
- No route on `workflow/universe_server.py` / Cloudflare tunnel — couples a dev
  toy to the production MCP surface; revisit only if remote (off-LAN) access
  becomes a real need.
- No process introspection / injecting keystrokes into live sessions — fragile
  and platform-specific; inbox + headless dispatch covers the intent.
- No auth beyond shared token, no accounts, no history replay, no native app.
- No new dependencies (stdlib http.server; not FastAPI) — runs anywhere the
  repo runs.

## Open Questions

- Should talk-dispatch default to inbox-only (zero spend) or headless CLI
  (uses that provider's subscription budget)? Default proposal: inbox-only
  unless `--dispatch` flag is passed.
- Is `command_center/` top-level the right home, or `workflow/desktop/village/`
  next to the existing tray dashboard? Proposal: `workflow/desktop/` is
  tray/packaging code; this is a standalone dev surface → top-level
  `command_center/`.
- Worktree islands: include parked/draft lanes dimmed, or active lanes only?
  Proposal: active + dirty lanes only, to keep the map legible.

## Addendum 2026-07-19 — Universe layer ("the Sky Archipelago")

Host addition, approved same day: the village must also show the Workflow
**universes** (daemon-run minds), including live ones behind
`https://tinyassets.io/mcp`, and let the host chat with each universe's
daemon using that universe's own provider preset.

- **Visual:** floating islands above the village, one per universe, themed by
  genre (🏰 default). Each island shows the universe's persona name (per the
  active `universe-personification` openspec change — every surface talks AS
  the named mind, first person), daemon status (phase / words / accept rate),
  provider preset badge, and activity pulses from the universe's activity log.
- **Sources, in priority order:** (1) local universe data dirs via
  `workflow.storage.data_dir()` resolution + the
  `Workflow-live-data-snapshot/` prototype; (2) optional `--mcp-url` remote
  endpoint. Remote probing must be **tolerant**: the live surface is the
  legacy fat tool catalog today and becomes the 5-handle surface per the
  active `collapse-live-mcp-surface-to-5-handles` change — try both shapes,
  degrade gracefully to "remote unreachable".
- **Chat:** tap the persona → chat sheet. Local universes: append a user note
  to that universe's `notes.json` (daemons read notes at scene boundaries;
  the reply surfaces from the universe's activity/output log into the chat
  view). Remote: MCP write handle when reachable.
- **Compute onboarding is explicitly NOT built** (host note 2026-07-19; see
  `ideas/2026-07-15-democratized-compute-stack.md` — still host-decision /
  spec-review stage). The island UI reserves a "runs on" slot that will show
  the compute contributor once that stack lands; today it shows local/remote.
  No compute-onboarding assumptions are baked into the collector.

## Addendum 2026-07-19b — Product surface + zoom levels

Host addition, same day: this is not only a personal dev tool. Any user runs
it against **their** setup (their project folders, their universes), reaches
it from the website, and can **zoom out** to a world view of everything
publicly viewable across all universes.

- **Zoom 0 — Village:** the local repo + the user's own universes (local data
  dirs + their configured MCP endpoint). Full interactivity (talk, feed).
- **Zoom 1 — World:** a constellation of all publicly viewable universes
  (public directory on the platform endpoint, `--directory-url`, default
  `https://tinyassets.io`). Read-only public profile/activity; chat stays on
  Zoom 0 (your own daemons). Probe is tolerant: unknown/unreachable directory
  → honest "world unreachable" state, never fabricated islands.
- **Runs anywhere:** the server is CWD-relative with zero config; any user
  clones, runs `python -m command_center` in their repo, opens the URL on
  their phone. Repo name auto-detected from git. PWA manifest so it can be
  added to a phone home screen. The website links to setup instructions;
  the https-site → http-local mixed-content wall means the local instance
  serves its own app (the website cannot embed it directly).
- **Later, not now:** hosted multi-tenant version, OAuth-bound embodiment
  per `universe-personification`, embedding the world view on tinyassets.io
  itself once the 5-handle surface lands.

## Addendum 2026-07-19c — Commons, branches, automations, market

Host addition, same day: the world view must show the **whole commons space**,
not just live activity — workflow automations (dispatcher/queue state), market
activity (bids, settlements), and all public branches/universes.

- **Recon findings** (explore agent, 2026-07-19): no plain-HTTP universe API
  exists — everything is MCP. The live surface at `https://tinyassets.io/mcp`
  advertises the 5 handles + `get_status`, and the legacy fat tools
  (`universe`, `extensions`, …) are hidden but **still callable**. So a
  minimal stdlib MCP JSON-RPC client (`command_center/mcp_client.py`) speaks
  to both today's surface and tomorrow's.
- **Data map:** `universe action=list` → public universes;
  `universe action=daemon_overview` → per-universe dispatcher/queue/bids/
  settlements/gates/run_state (the automations + market feed);
  `get_status` → platform health; branch listing probed tolerantly.
  `universe action=give_direction` delivers chat notes to live daemons
  (writes may be scope-gated; errors surface honestly).
- **Local note writes match the engine schema:** `notes.json` entries follow
  `workflow/notes.py` (`source:"user"`, `category:"direction"`,
  `status:"unread"`, epoch `timestamp`) — daemons can consume them directly.
- **Provider preset per universe** comes from `<universe>/config.yaml`
  (`preferred_writer`, `allowed_providers`) — shown as the island's badge;
  daemon chat runs on that preset, not the village's.
- **Visual:** Zoom 1 world = constellation of public universes + a market
  square (open bids / recent settlements ticker) + automation status
  (dispatcher windmills) + commons branch cards. All sections render only
  from real returned data; unreachable → honest empty state.

## Addendum 2026-07-19d — Hire an agent for a universe

Host addition, same day: from any universe card a user can create agents for
that universe — from any available LLM: their own linked providers, hosted
compute capacity, or market-rate capacity; as many as they can handle plus
market.

- **Reality check (2026-07-19):** the live surface is now the 5 handles +
  `get_status` + `converse` (the openspec collapse landed; legacy fat tools
  are hard-disabled for anonymous connections). Reads are open; writes
  (converse, write_graph universe/agent creation) need OAuth. Hosted/market
  compute is still unbuilt (addendum 2026-07-19b, democratized-compute idea).
- **What "hire" means today (honest slice):**
  - *Your own linked providers:* the server discovers installed provider CLIs
    (`claude`, `codex`, `kimi`, `gemini`, …) via PATH probing and lists them
    as hireable engines.
  - *Hire = dispatch:* `POST /api/hire` spawns that CLI as a peer agent
    (`scripts/peer_agent.py` contract) on a task brief for the chosen
    universe — real work on that provider's own budget, N at a time
    (`count`), results mirrored into the universe's village chat thread.
  - *Reassign the daemon's engine:* for local universes, hire can also write
    `<universe>/config.yaml` `preferred_writer` — the universe's own daemon
    then runs on the chosen preset at its next run.
  - *Market-rate / hosted capacity:* visible in the picker as a disabled,
    labeled "coming with the compute market" option — never a fake button.
  - *Live universes:* with `--mcp-token`, hire routes through the OAuth'd
    write handles; without it, the UI says sign-in is required.
- **Later:** real daemon-roster creation once the platform exposes roster
  writes; market-rate hiring once the compute market ships.
