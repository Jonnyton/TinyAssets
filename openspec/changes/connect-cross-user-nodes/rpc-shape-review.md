# Fable RPC shape review � recovered full assistant text

Reviewed proposal commit: f001450fcaa4105c00b164a175339fb382b71267.
September 19, 2026; local Windows, read-only source/design review.
Command: primary `scripts/peer_agent.py claude --model claude-fable-5-1
--timeout 240 --cwd <cross-user-delivery/TinyAssets> --prompt-file
output/delivery-rpc-shape-fable-brief.md --out output/delivery-rpc-shape-fable.md`.
Execution session 32068 exited 0 after 213 seconds. No tests or live actions.
The wrapper retained only the final Stop-hook note; the substantive assistant
block below was recovered from the same review's identified transcript:
`C:/Users/Jonathan/.claude/projects/C--Users-Jonathan--codex-worktrees-cross-user-delivery-TinyAssets/9ae6eeb0-7596-40c3-ae04-0214a90277a5.jsonl`.
Only assistant text was selected; thinking/tool payloads were not retained.
Candidate unchanged; sole peer slot released to root. Shape approval is not
implementation, exact-code, deployment or two-owner acceptance approval.

## Substantive review (verbatim)

**Assessment: trusted in-node JSON delivery, RPC-first slice**

Read the proposal and every cited range. RPC-first over the existing sandbox RPC, reusing the existing acceptance transaction and adding no top-level tool, is the smallest independently useful slice. Two items below are pre-build must-dos; the rest is later hardening.

**1. Authority versus attribution: AGREE**

- No code node reaches the invoker unless provenance is already `own`. `graph_compiler.py:2024` refuses everything else before `_validate_source_code`, and provenance is derived from the persisted run row, not a parameter (`runs.py:4347`, `runs.py:4297`, admin clause at `runs.py:4322`). A `provenance == own` delivery gate would be a second definition of the same fact. Correct to omit.
- Link authority is a row, not a definition. `storage/receiver_links.py:288` selects the link by `(link_id, owner_id, universe_id)`, and the link binds `branch_def_id` plus the placement id. `api/receiver_links.py:180` validates `node_id` against `graph_nodes`, so `link.node_id` is the placement, not the reusable definition. Copied or remixed definition content cannot choose a link. Only the owner's explicit wiring to that exact placement reaches a receiver. A remix is a new branch with the ledger actor as author (`api/branches.py:2533`), so links never carry across a fork. Approval fields never authorize (`api/branches.py:204`). Requiring `link.branch_def_id == running branch id` and `link.node_id == graph_node_id` is precise enough.
- Precision the proposal leaves implicit and must pin: the principal handed to `_owned_link` is the source run row's `owner_user_id` column (`runs.py:1503`), not `execution_context.actor`, which is `universe:<id>` on scheduled runs (`runs.py:4308`). Assert `universe_owner_actor(base, ctx.universe_id, owner_user_id)` and `link.universe_id == ctx.universe_id`. Co-admin-authored branches will fail `_owned_branch` (`api/receiver_links.py:92`). That matches the direct path, so it is not a new restriction.
- The running branch id must come from the compiled definition at the builder, because a nested `invoke_branch` child is a different definition. The proposal's "nested invoke retaining child run identity" test covers this. Name the source in the design.

**2. Occurrence identity: AGREE, with a smaller-seam note**

- `derive_effect_key` (`idempotency.py:43`) is a pure canonicalizer with no store. Reusing it for the stored occurrence string is fine. Excluding content is right, since the request digest already carries content.
- Smaller seam already present: the digest at `storage/deliveries.py:163` includes `source_run_id`. A legacy direct row under a derived key has `source_run_id=None`, so its digest differs and `:177` raises `OccurrenceConflict` with no new check. The reverse, a direct send hitting a node row, conflicts the same way. Keep the explicit `source_run_id IS NULL` refusal only as a named error, not as new machinery. Nothing smaller than `UNIQUE(sender, universe, link, occurrence)` at `:42` plus that digest exists.
- Non-blocking simplification: `link_id` already pins branch and placement (`storage/receiver_links.py:40`), so `placement_id` inside `item_fingerprint` duplicates the row key. Harmless. The required set is domain tag, source run, user occurrence.
- Receipt: `_receipt` (`storage/deliveries.py:113`) exposes no occurrence field. Leave it unchanged.
- Rejected seams are correctly rejected. `idempotent_by_step` is check-then-set in a separate database (`idempotency.py:287`). The handoff key puts content in identity (`handoffs/models.py:244`). The effect chain is once per placement.

**Pre-build basic-safety items (must be in the slice)**

- **No ambient principal on the node path.** `deliver_output` enters through `_owner_write` and `_principal()`, which reads request identity (`api/receiver_links.py:18`). A scheduled run has none, or a stale one. The factored service must take explicit owner, universe, branch id, placement, and source run, with the same author-store-first lock order (`api/receiver_links.py:56`).
- **Exact kwargs allowlist at the alias.** The invoker forwards `**kwargs` verbatim (`graph_compiler.py:1929`, `:1944`). For the delivery alias, refuse any key outside `link_id`, `occurrence_id`, `outputs` before dispatch. The proposal states this. Pin the set.
- **Cancel check inside the RPC handler.** The parent polls `should_cancel` only between reads (`node_sandbox.py:2785`), not in `_rpc_reply_line` (`:2415`). Check it at the top of the delivery handler so a cancelled run cannot open a new receiver run. Post-acceptance cancellation cannot undo. Agree.

**Later, non-blocking hardening**

- **Write settlement.** `fired` is what the effect chain saw (`effectors/__init__.py:649`). The RPC delivery is not an effect, so a run whose only external act is a delivery gets `reclassify_read` (`:1049`). Simplest fix is `settle_write(source_run_id)` after the acceptance commit. The docstring at `:1043` calls that the strict side. Only engine-admitted runs are affected.
- **Sender-side limits.** Receiver admission (`api/deliveries.py:91`) is the cross-user gate and is preserved. `MAX_RPC_CALLS` (`node_sandbox.py:126`) bounds per-node calls. Adequate for this slice.
- **Replay across resume.** Same run id gives the same key and is idempotent. A new run is a new delivery by design. Consistent with "no automatic resend of ambiguous work".

VERDICT: APPROVE

## Final Stop-hook continuation (verbatim)

The bounded review is complete and its constraints forbid the other lanes: read-only, no dispatch, no edits, no other worktrees. The running dispatch is this review's own output slot, the vanished entries would need a re-dispatch I am barred from, and the finished file lives in a different worktree outside this task's scope. Nothing further to advance here.

VERDICT: APPROVE
