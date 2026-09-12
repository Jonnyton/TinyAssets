# Saved preferences — independent cross-family review

September 10, 2026. Author Codex; independent reviewer Claude, through the
subscription peer CLI with a read-only brief, no delegates/worktrees/full suite.
Scope: versioned preference codec, canonical SQLite CAS, signed-in app ingress.
This is a working-tree slice review, not unchanged-head approval for the entire
feature branch or a claim that model selection is deployed.

## Shape review

Session26681 completed ADAPT in257s. Reviewed before storage/routes were built;
only the pure codec/tests were implemented concurrently. Agreed: canonical DB,
owner/universe key, atomic generation compare, deletion discovery, existing named
identity gate, no implicit authority and unchanged legacy binding. Corrections:

- Use the streaming bounded-body helper followed by strict UTF-8 JSON with
  duplicate-key rejection; do not use permissive `_read_small_json`.
- Decode corrupt/unknown-version stored rows before testing generation.
- Distinguish home storage failure from missing home. Shared `_read_home` gains
  opt-in `raise_errors`; its previous callers retain existing behavior.

All applied. Policy null/reset/delete is not accepted. Optional deletion
retention concern was addressed after the implementation review below.

## Implementation review

Session6583 completed **APPROVE** in318s. It independently ran31 app-route tests
on Windows Python3.14.3 (2.5s), read canonical code/mirrors, and agreed with codec
validation, CAS/corruption holds, transaction-local home/tombstone fence,
identity/origin/body scope, unpowered access, no provider authority and deletion
sweep. Two nonblocking concerns:

1. **PLAN provenance.** The brief said “main” but meant this goal's primary
   worktree branch, not Git's local/remote main. Verified source:
   `git -C C:/Users/Jonathan/.codex/worktrees/0a7f/TinyAssets show d43de2ca:PLAN.md`
   contains the exact September9 paragraph at the provider section. The owner
   explicitly requested subscription/local priority, best-eligible OpenRouter
   ranking, visible actual model and editable defaults/fallback order in this
   conversation. This carries forward that user-approved design. It is not a
   new decision smuggled into preferences; origin/main still has the older rule.
2. **Former-home retention.** Adopted the suggested one-line addition to existing
   `PERSON_KEYED_DESPITE_UNIVERSE`, keyed by owner_user_id. The real deletion test
   now seeds current and former home preferences for A, and B's own preferences;
   both A rows disappear, B remains. This small post-review correction follows
   the review recommendation and is rerun in Windows/Linux tests. No third
   review round or exact-head reapproval is claimed.

Raw artifacts remain in local output/model-preferences-{shape,implementation}-
result.md. The implementation verdict is quoted accurately: APPROVE with the
two concerns above; the reviewer reported no correctness defect in this slice.
Broader feature activation still requires its own final unchanged-head review,
CI, authenticated deployment evidence and ordinary rendered app use.
