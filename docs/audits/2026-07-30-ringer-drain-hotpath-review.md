# Ringer Drain Hot-Path Independent Review

Date: 2026-07-30
Initial provider: Codex (`codex-gpt5-desktop`)
Required reviewer: opposite-provider Claude Code
Fallback: host-approved fresh-context Codex only after a documented Claude hard
limit
Source head: `a1a91b8b384a90dcca379e1cb9ab91405275ac46`
TinyAssets base: `00ade586c80ab96fd228419b959a8244a7b9dfb9`

## Verdict

**APPROVE** at exact folded planning commit
`7565ce641cc6f182c177e43df55bec65b05389f5`

Authenticated Claude Code 2.1.220 again exited 1 under the same documented
monthly-spend limit already preserved in the prior Ringer review. The first
fresh-context Codex CLI fallback exceeded its finite outer wrapper window
without producing a verdict; its two exact orphan reviewer processes were
stopped to prevent duplicate subscription burn. The host-approved independent
Codex reviewer then returned `ADAPT`.

### Blocking findings

1. The delta introduced two new requirement names under `MODIFIED`; they must
   be `ADDED` or replace the complete exact canonical requirements.
2. The no-foldback-diff scenario promised controller reconciliation that the
   implementation plan did not build and the current result grammar cannot
   represent safely.

### Important findings

- Mirror the PolyForm Shield clean-room boundary into design and acceptance
  tasks, not only the audit.
- Prove that a zero-match scoped worktree result grants no authority; the exact
  prepared lane and claim still require independent verification.

### Foldback

- The delta now uses `ADDED Requirements`.
- The unimplemented no-diff reconciliation scenario is removed, not guessed.
- The audit, design, tasks, and delta now require the clean-room and zero-match
  safety boundaries.

The independent reviewer re-checked the exact folded commit against Ringer,
TinyAssets code, the canonical coordination spec, and the strict validation
result. It confirmed the requirement classification, representable foldback
grammar, zero-match non-authority, and clean-room boundary are consistent and
left no planning or research blocker. TDD implementation may begin.

## Exact-head implementation review

**APPROVE** at exact implementation commit
`9d04ff9edd78d09439f2f0864e900ca64a0cba30`.

The independent reviewer found no correctness, regression, specification, or
clean-room issue. It confirmed that the provider prefilter is predicate- and
order-equivalent to the previous post-probe filter, while avoiding every
nonmatching worktree probe. It also confirmed that a PARTIAL continuation now
requires a fresh foldback PR from the current disposable worker and cannot
reuse the preceding implementation PR as its receipt.

Fresh reviewer evidence on 2026-07-30 (Windows): 152 focused tests passed in
3.22 seconds, Ruff was clean, strict OpenSpec validation passed, and
`git diff --check` passed.
