# Shipped Ideas

Short ledger connecting landed work back to the idea that produced it.

## Entries

- [2026-07-19] **Agent Village — web command center (`command_center/`).**
  Phone-accessible living map of every agent working the repo (Claude, Codex,
  Kimi, …) with tap-to-talk, universe sky-islands with daemon chat (local
  notes + live `converse`), a world zoom over live universes + the commons,
  and a hire-an-agent flow (peer-CLI dispatch / preset write). Origin:
  host request 2026-07-19 (owner: kimi); design + addenda in
  `ideas/2026-07-19-agent-village-command-center.md`. The originating
  `ideas/INBOX.md` entry was never committed to `origin/main` (INBOX has no
  2026-07 entries), so the design document is the surviving capture record.
  Landed in: PR #1489 (`220a1fc8`), recovered 2026-07-21 from an
  uncommitted checkout; `command_center/` plus 37 tests in
  `tests/command_center/`. Deferred inside the shipped slice: market-rate and
  hosted compute hiring ship as a labeled-disabled affordance, and real
  daemon-roster creation awaits platform roster writes.
- [2026-04-27] **fantasy_daemon/phases/ entry-point comment.** Each phase file
  now has a one-line header naming graph cycle + entry-point node.
  Origin: `ideas/INBOX.md` 2026-04-25 entry (navigator-audit, owner: dev-2).
  Landed in: commit `be5f9b6` — "fantasy_daemon/phases — cycle-map header +
  orient docstring fold". Note: capture was stale on filing; work was
  already complete at lead session start 2026-04-27.
