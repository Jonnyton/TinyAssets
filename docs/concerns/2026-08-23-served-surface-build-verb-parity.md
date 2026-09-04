# P1 - The served user-owned branch lifecycle is not yet generic

**Filed:** 2026-08-23
**Re-verified:** 2026-09-03 against `a62086de`
**Severity:** P1
**Area:** user-owned branch lifecycle / served authority

## Capability audit

The ordinary connector and the bound-universe surface now expose most of the
create, inspect, edit, run, and delete lifecycle. The user or the user's bound
universe agent is the actor throughout; a maintainer lane has no authority to
exercise these primitives against a live user branch.

| Lifecycle verb | Existing primitive | Current authority behavior |
|---|---|---|
| Create | `write_graph target=branch operation=create` -> `build_branch` | Requires a credential-validated subject; the server derives `author` from that subject. The served wrapper forces the new branch private and strips caller-supplied author/approval/fork authority. |
| Inspect | `read_graph target=branches` and `target=branch` | `branches` lists the caller's own rows; an exact private branch is readable only by its author and otherwise uses the same not-found envelope as an absent branch. Public commons shapes remain readable by design. |
| Edit | `write_graph target=branch operation=patch` -> `patch_branch` | Author-gated and transactional. The served wrapper exposes an allowlisted subset of effect-free self-edit operations and refuses publish/visibility/fork authority. |
| Run | `run_graph` -> `run_branch` | Requires write access to the target universe and branch readability; a foreign private branch is indistinguishable from missing. The bound surface pins the universe and binds the verified founder identity. |
| Delete | `write_graph target=branch operation=delete` -> `delete_own_branch` | Author-only, authority-safe not-found for every non-author, and refused with named dependents before deletion. Public and private owner-authored branches follow the same rule. |

Isolated verification on 2026-09-03:

- `python -m pytest -q tests/test_branch_read_authority.py tests/test_branch_mutation_authority.py tests/test_branch_run_read_check.py` -> 56 passed.
- `python -m pytest -q tests/test_branch_delete_is_first_class.py tests/test_engine_mcp_write_graph_patch.py tests/test_engine_mcp_server.py -k 'delete or read_graph_branches or read_graph_reads_one_branch or served_write_graph or run_graph_refuses_foreign_private_branch or run_graph_names_the_cap or run_graph_binds_its_admission or served_allowlists'` -> 49 passed, 72 deselected.

No live user branch was used as a fixture or mutated during this audit.

## Remaining capability gaps

1. **Branch ownership is actor-scoped, not universe-scoped.** A branch record has
   an author but no explicit universe binding. A principal administering more
   than one universe can therefore address their private branches from either
   bound universe. The served `graph_id` pin does not close that gap because
   branch resolution is still author-based. An explicit branch-to-universe
   binding is the pre-multi-user authority gate.
2. **The bound-agent lifecycle is not generally available.** Served `write_graph`
   and `run_graph` remain behind `TINYASSETS_ENGINE_RUN_GRAPH_UNIVERSES`; the
   allowlist is deliberately dark for universes that have not been vetted.
3. **Concurrent edits can lose updates.** `patch_branch` is all-or-nothing for
   one request, but the served surface has no expected revision / compare-and-
   swap guard between inspect and edit.
4. **Run submission still lacks required-input preflight.** That distinct P2 is
   tracked in `2026-09-03-run-submission-accepts-missing-required-inputs.md`.
   It composes after universe/branch authorization and before admission; it does
   not authorize Patches to create, repair, run, retain, revert, or delete a
   user's branch.
5. **As-built lifecycle truth is fragmented.** Owner-only deletion is explicit
   in `live-mcp-connector-surface`; visibility/ownership is in
   `identity-auth-and-access-control`; run behavior is in
   `graph-execution-substrate`; create/inspect/edit do not yet have one
   canonical lifecycle requirement tying the same user-scoped authority across
   both served surfaces.

The earlier concern also named publish/remix, connection deposit, consent, and
serving-control parity. Those are outside this five-verb lifecycle audit and
remain owned by their dedicated concerns or OpenSpec changes; this re-audit
does not mark them resolved.

## Acceptance-criteria audit

- The missing-input concern now uses an isolated maintainer-owned universe for
  negative and lifecycle tests. Live proof is performed by the user or bound
  universe agent against that actor's own disposable branch, with only the
  sanitized outcome retained.
- `served-agent-build-run` task 5.5 still proposes a live cross-universe refusal
  probe and a tracked conversation log. Cross-universe authority negatives
  belong in isolated test custody, not a live user's universe; any retained
  rendered proof must omit branch identifiers and content.
- `run-provider-authority` task 2.3 still pins live proof to one specific private
  branch and one external action. Its owner must replace that public fixture
  reference with generic owner-driven proof and a sanitized capability receipt.
- The canonical owner-delete scenarios are correctly scoped: the author calls
  delete on their own branch, while non-author denial is proved without using a
  live user branch as a maintainer fixture.

These findings do not authorize Patches to edit either active owner lane. They
are handoff requirements for those owners when the changes resume.

## Delivery boundary

The active `served-agent-build-run` change is not an admissible implementation
lane in its current form: it is unclassified, has 21 unchecked tasks, lacks its
OpenSpec-recognized delta-spec and `design.md` artifacts, and exceeds the
current 12-task delivery ceiling. The delivery audit already has four admitted
changes, so Patches must not mint another change or edit an owner lane to bypass
the WIP wall.

When a legitimate slot and owner exist, re-propose the smallest reversible
slice. The hard-to-reverse branch-to-universe storage/authority shape requires
OpenSpec design before code. Acceptance must use isolated test custody, then a
rendered conversation in which the user or bound universe agent performs its
own disposable create/inspect/edit/run/delete lifecycle. A maintainer may
observe and record only a sanitized outcome; a user branch is never a platform
deliverable or maintainer-owned fixture.
