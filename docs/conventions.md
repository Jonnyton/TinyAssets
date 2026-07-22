# Conventions

## Files

- Keep `AGENTS.md`, `PLAN.md`, and `STATUS.md` short enough to scan quickly.
- Push durable reasoning into `docs/design-notes/`.
- Push formal accepted decisions into `docs/decisions/`.
- Use `INDEX.md` files to keep note graphs connected.
- Use `docs/exec-plans/` for larger multi-step delivery maps.
- Use `ideas/` for stray ideas that are not yet ready for the work board.

## Naming

- Design notes: `YYYY-MM-DD-topic.md`
- ADRs: `ADR-###-topic.md`
- Specs: `feature-or-change-name.md`
- Execution plans: `YYYY-MM-DD-topic.md` or `topic.md`

## Linking

- Every new durable note should be linked from at least one index page.
- Prefer explicit Markdown links.
- Add sideways links between related notes, not just parent links.

## Verification Language

- `current:` means verified in the current environment.
- `historical:` means true when last checked, not revalidated now.
- `contradicted:` means current evidence says the older claim is no longer true.
- `unknown:` means not yet checked or not confidently reconstructable.

## Large Documents

- Use `python scripts/docview.py` before any raw whole-file read of large
  Markdown, text, or JSON artifacts.
- If `docview.py` says a result is too large, narrow the query again.

## MCP Actions Reference

- New MCP actions and field additions are catalogued in `docs/mcp-actions/`.
- When a chatbot encounters an unexpected response field or a new action verb,
  check `docs/mcp-actions/` before assuming a schema error.
- The directory holds dated session records, not a maintained index page. Read
  the directory listing rather than entering through any single note.

## Frontmatter `status:` field

Reverse-engineered from the in-tree convention (Task #18 audit, 2026-04-28). Documents what the codebase already does so future audits don't re-litigate the format.

**Where it applies:**
- `docs/design-notes/*.md` — REQUIRED (top-level only; `proposed/` is a separate, ungated directory).
- `docs/specs/*.md` — REQUIRED (excludes `INDEX.md`).
- `docs/exec-plans/active/*.md` and `docs/exec-plans/completed/*.md` — present in some, encoded by directory placement.
- `docs/audits/*.md` — OPTIONAL, descriptive (not lifecycle). Audits are event-records; a minority carry a bespoke `status:` describing the audit's role ("read-only discovery audit", "diagnostic record", etc.). Don't retrofit lifecycle values onto audits.

**Compliance is measured, never quoted here.** Run `python scripts/check_frontmatter_status.py` for the current counts and the full list of non-compliant files; `--check` exits 1 on any violation in a REQUIRED directory.

> This section used to hardcode "80/80 notes carry it" and "32/32 specs carry it," measured once on 2026-04-28. By 2026-07-22 the real numbers were 90/124 and 38/51 — the claims had been wrong for weeks and nothing made them expire loudly. A correct-but-expired fact reads exactly like a current one. Per `AGENTS.md` § Truth And Freshness, a verification claim carries its command; here the command *is* the claim, so it cannot go stale. Do not reintroduce a hardcoded count.

**Five lifecycle values** (use exactly one):

| Value | Meaning |
|---|---|
| `active` | Work is in flight or upcoming. No newer doc supersedes. STATUS.md may cite it. |
| `shipped` | Work landed. Body or git history references the landing commit. |
| `superseded` | Newer doc replaces this one. **Pair with `superseded_by:` field** holding the relative path to the successor. |
| `research` | Exploratory thinking; no implementation intent and no STATUS row claims it. |
| `historical` | Captures past state for posterity (incident postmortem, retired-with-stamp doc, pre-rename architecture). |

`check_frontmatter_status.py` rejects any other value. If a sixth lifecycle value is genuinely needed, add it to this table **and** to `LIFECYCLE_VALUES` in that script in the same commit — divergence between the two is exactly the drift this section exists to stop.

**Format:** bare value, body details optional (e.g. `status: shipped` plus a `**Status:**` line in the body referencing the landing commit). Compound forms like `status: shipped: <date>` are NOT the convention — date detail goes in the body.

**Tie-breakers** (applied during the 2026-04-28 audit pass):
- If STATUS.md cites the doc as host-decision-pending → `active`. (Consumption pattern trumps internal status.)
- If git log is silent and no STATUS row references it → `research`.
- "Almost shipped" with one open item → `active` with a body note explaining what's open.
- False-shipped is worse than false-active. When uncertain, classify `active`.

**Companion fields:**
- `superseded_by: <relative-path-from-repo-root>` — required when `status: superseded`. Path must resolve. May be a YAML list when more than one document replaces this one; every path in the list must resolve.
- `status_detail: <free-text>` — optional. Used by some notes to add nuance under a lifecycle value.

## Gate-branch shape

- Standalone gate branches (`gate_investigation_v1`, `gate_review_v1`, etc.)
  emit a uniform verdict shape so conditional-edge routing works generically
  and chatbots converge on one consumer contract.
- Verdict enum: `pass` / `send_back` / `reject` / `hold` / `rollback`.
- See `docs/conventions/gate-branch-shape.md` for the full contract,
  per-verdict required fields, worked example, and forward-compat plan
  with the unified Evaluator type.
