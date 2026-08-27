# Where a new convention lives

**HISTORICAL — superseded.** Describes machinery deleted by the 2026-08-25/26 harness reset. Do not cite as live; see [README.md](README.md).

Pointer-loaded per [ADR-002](../decisions/ADR-002-static-vs-dynamic-context-budget.md).
`AGENTS.md` § *Where new conventions live* keeps the rule and the self-check;
this file holds the placement table, the self-correcting property, and the
auto-heal tooling.

This project is multi-provider: the host steers Codex, Cursor, Aider, Claude
Code, and Cowork sessions against the same repo. **`AGENTS.md` is the
cross-provider standard** — every major coding agent reads it as canonical
project context.

## Placement table

| Convention type | Lives in |
|---|---|
| Cross-provider (any agent needs it) | `AGENTS.md` |
| Claude Code harness behavior | `CLAUDE.md` (which `@AGENTS.md` imports) |
| Cursor-specific | `.cursor/rules/*.mdc` or `.cursorrules` |
| Cowork-quirk (e.g., FUSE truncation) | `docs/reference/fuse-write-discipline.md` + a pointer |
| Codex-specific | `AGENTS.md` (Codex's canonical file already) |

Provider-specific files exist only for genuinely provider-specific rules —
harness behavior, harness quirks, harness-specific bootstrapping. They should
reduce to *pointers at `AGENTS.md`* plus a thin layer of harness-specific notes.

## The rule is self-correcting

If a future session adds a project-level convention to `CLAUDE.md` or agent
memory without also putting it in `AGENTS.md`, that session has drifted. Catch
it on review and pull the convention up to `AGENTS.md`; the provider-specific
file de-duplicates by replacing the content with a pointer.

## Auto-heal hook

Apply the `auto-iterate` skill when fixing recurring behavioral failures.

Run `python scripts/check_cross_provider_drift.py` from any provider. It scans
`CLAUDE.md`, `.cursorrules`, `.cursor/rules/*`, and `.codex/*` for substantive
sections that don't appear in `AGENTS.md`. Exits 2 with a fix prescription on
drift — move the section to `AGENTS.md`, or tag the heading
`[harness-specific]` / `[Claude Code only]` / `[Cursor only]`.

In Claude Code it fires automatically as a `PostToolUse` hook on Write/Edit of
any watched provider-specific file (`.claude/hooks/cross_provider_drift_guard.py`).
Cowork / Codex / Cursor sessions run the script manually after editing one of
those files.

Each drift recurrence ratchets the prevention layer — the same auto-iterate
pattern as the FUSE-truncation guard (`WebSite/HOOKS_FUSE_QUIRKS.md`).

**Worked example (2026-08-07).** A stale untracked `.codex/skills/` mirror was
found: missing `peer-agents`, with 12 of 32 skills diverged from canonical. Two
files disagreed about whether it should exist at all — `scripts/sync-skills.ps1`
said Codex reads `.agents/skills/` directly, while `AGENTS.md` said skills mirror
into `.codex/skills/`. That contradiction is exactly what this section exists to
prevent: one authoritative home, everything else a pointer.
