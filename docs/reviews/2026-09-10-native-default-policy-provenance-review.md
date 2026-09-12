# Independent native-default and provenance review

September10 2026. Claude reviewed exact e8adb973 against e1077ac5, read-only,
without delegation or edits. Session42541 exited0 after363s, VERDICT: APPROVE.
Reviewer independently ran tests/test_native_model_authority.py:12 Windows passes.
No required corrections; no extra review round dispatched.

The wrapper output was a stop-hook recap. The substantive review was recovered
from the assistant text in local transcript
`C:/Users/Jonathan/.claude/projects/C--Users-Jonathan--codex-worktrees-select-agent-models-TinyAssets/1baff324-e34f-49f4-869d-80f9de0aa577.jsonl`.

## Verified scope

- Native discovery bypass preserves exact owned custody, member validation and
  transactional budget admission; vault removal refuses with zero provider calls.
- Async admission still compares agent and full selected chain when no HTTP
  recheck callback exists. Explicit allowlists, including empty, retain precedence.
- Unsupported explicit native IDs were already refused before this patch.
- Contradictory incoming plan/selection refuses; real fallback uses the same
  plan's next candidate and does not create a contradictory pair.
- Input header v2 uses exact keys/types; v1 stays unknown without byte rewriting.
  Budget reads of optional SelectedModel remain guarded.

## Nongating follow-ups, retained for the production consumer

1. AgentModelPlan defaults provenance to unknown without cross-checking policy
   shape. Reviewer DISAGREE_CONCERN: a producer must not silently forget or
   mislabel the source. The subsequent pure capture helper emits current/saved
   explicitly, including for automatic choices, but it is not yet a producer.
2. HTTP agent inference with a native default refuses only after the request
   allowance is sealed, not during preparation. No inference occurs; move this
   refusal earlier before enabling mixed HTTP/native continuation. Native first
   choices keep native execution; unsupported whole-turn replay stays prohibited.
3. The routing-ceiling correction also permits the resolved provider on the
   legacy no-selection path to differ from the structural writer anchor. Reviewer
   AGREE: this is same-owner and follows the approved shape, not native-only.
4. Budget admission's empty native model id is implicit in the snapshot authority.
   Sound while legacy resolution refuses manifests and explicit native ids refuse
   preparation. An explicit default marker would remove this reliance later.
5. Older readers cannot read new v2 input headers on rollback. They fail loudly
   with JournalUnavailable; never reinterpret these rows as executable defaults.

The later pure preference-conversion commit4e28d18a is outside this review's
exact scope and needs review with real consumer integration. Neither commit is
deployed. Public readiness, catalogue production, ingress and UI remain open.
