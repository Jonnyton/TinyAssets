# Private-child authority pre-build review

2026-09-19 06:35–06:38 UTC. Claude Fable 5.1 (`claude-fable-5-1`), read-only
session 12420, 300-second bound, terminal exit 0 after 167 seconds. Scope was the
documented new authority rule over the in-progress RPC implementation based on
proposal `f001450f`, not exact-code release approval. Verdict: **ADAPT**.

The wrapper retained only the final Stop-hook reaffirmation. All substantive
assistant text was recovered from local transcript
`1af6215e-c0c9-4bac-84b7-9ef4199845bb.jsonl` in the Claude project directory for
the cross-user-delivery worktree. No provider/permission failure occurred.

## Full substantive review

> **DISAGREE_EVIDENCE** on one conjunct, otherwise the shape is right. Frozen snippets verified against the worktree: gate at `tinyassets/graph_compiler.py:2658-2666`, provenance at `tinyassets/runs.py:4314-4329`, ownership predicate at `tinyassets/api/source_channel.py:82-101`, and `parent_run_id` is threaded into the execution compile at `tinyassets/runs.py:3664`, so the run-row clause is satisfiable on real runs.
>
> **The gap: actor/owner confusion via the co-admin clause.** "Own" provenance is derived from the *running definition's author*, and the second clause of `_caller_provenance` grants it when that author is any current admin of the universe. The proposal then authorizes the child against `ctx.owner_user_id`, a different principal that is never compared with the parent's author. Concrete failure:
>
> - Universe U has co-admins A and B. A authors a parent branch with an `invoke_branch` ref to B's private, user-authored branch (author `B`, not `universe:U`).
> - B triggers a run of A's parent. Run row: actor `universe:U`, owner_user_id `B`, universe U, status running.
> - Provenance is "own" (A is admin, `runs.py:4325`). Proposed rule: child author `B` equals owner `B`, B is admin on U, run row matches, running. Authorized.
> - A's author-chosen spec pulls B's personal private branch into B's run and its outputs land in run state A can read as admin. This is the "co-admin guess" widening the brief rules out. The existing own-actor path never reached this, because `author == ctx.actor` only ever matched `universe:<id>`-authored branches, which are universe-scoped and already shared among admins.
>
> **Safer minimal rule (one added conjunct).** Add `definition_author: str = ""` to `BranchExecutionContext` at `graph_compiler.py:2616-2620`, populated from the same `_branch_author` value that already feeds provenance at both trusted construction sites, `runs.py:3469-3477` and `runs.py:4359-4367`. Then the new private-child case inside the existing `own` branch is:
>
> ```text
> author == ctx.owner_user_id != ""
> and ctx.definition_author == ctx.owner_user_id
> and universe_owner_actor(base, ctx.universe_id, ctx.owner_user_id)
> and persisted run(parent_run_id) matches actor, owner_user_id, universe_id and is running
> ```
>
> Meaning: the running definition and the child were both authored by the persisted run owner, who is still admin where it runs. That is exactly "owned or remixed workflows compose in your universe" and nothing more. It is transitive, since the child run's context is rebuilt from the child's author, which is the same owner. Remix stays covered because the fixture sets the remixer as author with `fork_from` pointing at the original.
>
> **Ordering and disclosure.** Keep fetch-raw, then metadata checks, then `from_dict`, as at lines 2647-2675. Run the two extra lookups only after the cheap conjuncts pass, and wrap the run-row read so any exception collapses to `_CHILD_UNAVAILABLE`. `universe_owner_actor` already fails closed. No private body is deserialized before authorization. The extra lookups add a small timing difference for "private child authored by owner" versus "absent". Later hardening, not a blocker.
>
> **Pre-build blockers**
> 1. Add the `definition_author == owner_user_id` conjunct above.
> 2. Uniform refusal around the new run-row read.
>
> **Later hardening**
> - The context docstring at `graph_compiler.py:2608-2609` says never re-derive from the mutable run record. The re-read is a narrowing freshness check only. Amend the docstring so a future reader does not "fix" it by removing the check.
> - `owner_user_id` can be resolved from the daemon owner at prepare time (`runs.py:1450-1453`). With the added conjunct that is safe. Without it, a daemon-owner co-admin becomes reachable.
> - Universes with no ACL rows read as "read", never admin, so private composition is refused there. Same as existing provenance, so no new hole, but it will surprise a public-universe owner.
> - Pin which statuses count as "running" for the row check.
>
> **Required tests.** The parametrized test at `tests/test_delivery_node_rpc.py:348-387` already covers revoked owner, missing and spoofed context owner, wrong actor, universe, run, missing run, public-foreign, terminal, and row owner changed. The nested test at lines 222-244 covers owned remix success and asserts the delivery source is the child's own run and placement. Add two cases: the co-admin scenario above must refuse, and an owner-authored parent plus owner-authored private child on a running row must return the definition. Run each new test against the unfixed tree and require red first.
>
> VERDICT: ADAPT

Final Stop-hook continuation reaffirms ADAPT and the added conjunct; it identifies
unrelated retention/memory review entries as outside this review's authority and
does not dispatch or implement anything.

## Disposition before implementation

Accept both blockers. The frozen context gains the actual compiled definition's
author (not an original contributor/fork attribution), populated at foreground
and resume construction. The new owner-private case requires that author, child
author and persisted owner all agree. No change to public-foreign or existing
own-actor rules. New run lookup errors fail uniformly; the only accepted source
status is exactly `running`. Re-reads narrow freshness and never manufacture
context authority. Add co-admin negative, owner-positive and lookup-error tests
before implementation; rerun complete RPC/invoke group on Windows and Linux.
Final exact-code approval and live acceptance remain outstanding.
