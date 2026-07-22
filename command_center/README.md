# Agent Village — the command center

Watch every AI agent working on your project as a sprite walking a living
village — from your phone, your laptop, or anything with a browser.

```
python -m command_center
# → http://localhost:8787
# → on your phone (same network): http://<this-machine's-LAN-IP>:8787
```

Zero config, stdlib only, no build step. Run it in any repo; it watches the
folder it runs in.

## What you see

- **The village (zoom 0).** Your repo's directories are buildings. Every live
  agent — Claude Code, Codex, Kimi, and any other CLI with session logs — is
  a sprite that walks to the building it's working in. Subagents are smaller
  and stay near their parent. Idle agents drift to the campfire; claimed-but-
  quiet work waits at the notice board; stale worktrees get rain clouds in
  the harbor. Buildings glow and smoke when files are being written.
- **The sky.** Your universes (daemon-run minds) float as islands: persona
  name, word count, provider preset (`config.yaml`), alive/dormant dot.
- **The world (zoom 1).** Everything publicly viewable on the platform
  endpoint — live universes with accept rates and the commons feed — via the
  5-handle MCP surface (`read_graph` / `read_page` / `get_status`). Unreachable
  → an honest note, never fabricated islands.
- **The crier.** A live event feed: who arrived, who edited what, commits
  (with fireworks), claims, notes. Tap 📜 on mobile; pinned on desktop.
- **Time travel.** ⏪ scrubs back through the last few minutes of snapshots.

## Talk to anyone

- **Tap a sprite** → chat sheet. Your note lands in
  `.agents/village-inbox/<agent>.md` — agents read it on their next check-in.
  With `--dispatch`, it's also sent to that provider's CLI (claude/codex) on
  its own subscription budget, and the reply comes back into the sheet.
- **Tap a universe** → chat with its daemon. Local universes get a
  `notes.json` entry in the engine's own schema (read at the next scene
  boundary) or a pinned note if asleep. Live universes use the platform's
  `converse` tool (needs sign-in — see `--mcp-token`).

## Hire agents for a universe

On any universe sheet: pick an engine, a task, and a count.

- **Dispatch** spawns real peer CLI sessions (`scripts/peer_agent.py`
  contract) on the provider's own budget — they walk into the village as new
  sprites and report into the universe's chat thread.
- **Set as engine** rewrites the universe's `config.yaml` `preferred_writer`
  preset.
- **Hosted / market capacity** shows disabled with an honest "coming" note —
  that stack is still being built; nothing here fakes it.

## Flags

| Flag | Default | What it does |
|---|---|---|
| `--host` | `0.0.0.0` | bind address (LAN = phone can reach it) |
| `--port` | `8787` | bind port |
| `--token` | — | require `?token=` on every request; share URL prints at startup |
| `--dispatch` | off | also send agent talk to provider CLIs (spends their budget) |
| `--interval` | `3` | seconds between state polls |
| `--directory-url` | `https://tinyassets.io` | platform base for the world view (`''` = offline) |
| `--mcp-url` | — | override the full MCP endpoint |
| `--mcp-token` | `$WORKFLOW_MCP_TOKEN` | Bearer token for platform writes (converse etc.) |

## Sharing tips

- `?present=1` — chrome-free view for screenshots/streams.
- `?zoom=world` — open straight into the world view.
- `?universe=<id>` — deep-link a universe's chat sheet.
- PWA manifest included: "Add to Home Screen" on your phone.

## Where the signals come from

| Signal | Source |
|---|---|
| Claude Code sessions | `~/.claude/projects/*/*.jsonl` tails (tool actions, subagent sidechains) |
| Codex sessions | `~/.codex/sessions/**/rollout-*.jsonl` |
| Kimi sessions | `~/.kimi-code/session_index.jsonl` + session `agents/` dirs |
| Claimed work | `STATUS.md` Work table |
| Worktree islands | `scripts/worktree_status.py --json` |
| Event feed | `.agents/activity.log`, git logs, file mtimes |
| Local universes | `data_dir()` + sibling snapshots (`u-*` OKF bundles) |
| Live universes/commons | the 5-handle MCP at `--directory-url` |

Everything is read-only except talk/hire, and every probe degrades to absence
instead of erroring. If a sprite is wrong, the raw truth is always the file
it came from.

## Tests

```
python -m pytest tests/command_center/ -q
python -m ruff check command_center/ tests/command_center/
```

Design doc: `../ideas/2026-07-19-agent-village-command-center.md`.
