# Pre-reset reference docs (archived 2026-08-26)

These four files were recovered from an uncommitted checkout that was 826
commits behind `main`. They existed **nowhere else** — not on any remote, not in
history — and `AGENTS.md` cited two of them as live pointers for months while the
files themselves were never committed. That is why they are preserved.

They are archived rather than restored to `docs/reference/` because **every one
of them describes machinery the 2026-08-25/26 harness reset deleted.** Filed as
live reference they would read as current instruction, and a reader cannot tell a
stale reference from a live one.

| File | Describes | Status |
|---|---|---|
| `parallel-dispatch.md` | The `STATUS.md` claim board, the 8-step session-start ritual, `claim_check.py`, stale-claim reaping | All deleted |
| `convention-placement.md` | Cross-provider convention placement and the `check_cross_provider_drift.py` auto-heal hook | Hook deleted; two providers now, both read `AGENTS.md` |
| `fuse-write-discipline.md` | FUSE write + git-plumbing rules for Cowork sessions | Cowork out of scope |
| `project-files.md` | Repo map keyed to three living files, `CLAUDE_LEAD_OPS.md`, `.claude/agents/*.md`, `provider_context_feed.py` | Two living files now; the rest deleted |

Read them as a record of how the harness worked before the reset, not as
instructions. Live equivalents: `AGENTS.md`,
`docs/reference/delivery-flow.md`, `docs/reference/quality-gates.md`,
`docs/reference/executable-gates.md`.
