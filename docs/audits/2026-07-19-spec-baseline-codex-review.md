# Codex cross-family review — spec-out-existing-platform baseline

- **Date:** 2026-07-19 (review ran against worktree `openspec-sdd-baseline`,
  branch `worktree-openspec-sdd-baseline` = origin/main + baseline commit)
- **Reviewer:** Codex (`scripts/codex_review.py`, read-only), opposite-provider
  gate per AGENTS.md § Project Skills / CLAUDE.md § Calling Codex via MCP
- **Scope:** the 14 as-built capability specs (delta + synced main), the
  AGENTS.md SDD convention section, the Hard Rule #12 handle edit
- **Verdict:** `adapt` — all findings addressed in the same branch

## Findings and dispositions

1. **(blocker) Paid-market spec overstated authenticated identity.**
   Escrow actor resolution rides `engine_helpers._current_actor()`, which
   falls back to `UNIVERSE_SERVER_USER` on authless paths; `market.py`
   `_resolve_escrow_actor` builds host on-behalf rights on top of it.
   *Disposition:* spec requirement amended with an explicit as-built
   security limitation; new P2 STATUS.md Concern filed (escalates the
   2026-06-30 residual F5, which had classed the fallback as
   attribution-only). Behavioral fix deliberately NOT made in this
   docs-lane; it needs its own change.
2. **(blocker) `openspec/config.yaml` generator context taught obsolete
   architecture** (nonexistent `workflow/` package, five-handle surface
   omitting `converse`). *Disposition:* rewritten against as-built truth;
   now points at `openspec/specs/` as the authority.
3. **(minor) Personification spec overstated provider support + sandbox.**
   Codex provider refuses every sandboxed turn (`ProviderError`), so
   `claude-code` is the only engine that can serve `converse`; the sandbox
   is deny-enumerated policy, not a true allowlist. *Disposition:* engine
   requirement + sandbox requirement rewritten; fail-closed Codex scenario
   added.
4. **(minor) Handle contract internally inconsistent** (spec's "exactly
   seven" vs canary's six-required + optional `get_status`). *Disposition:*
   requirement now states both layers: server advertises 7; drift guard
   requires 6 and permits `get_status`.
5. **(blocker) Baseline not merge-green** — `tests/test_mcp_public_canary.py`
   red on main (fixture omitted `converse`). *Disposition:* fixture,
   docstring, `--assert-handles` help, and success suffix corrected in this
   branch (no runtime behavior change; `CANONICAL_HANDLES` already enforced
   `converse`); suite green post-fix (13 passed incl.
   `test_universe_server_five_handles.py`).

External-source spot-checks by the reviewer (OKF v0.1 reserved-file
handling, RFC 9728 PRM discovery) confirmed the specs' claims.

Verbatim verdict: preserved in the PR body for `spec-out-existing-platform`.
