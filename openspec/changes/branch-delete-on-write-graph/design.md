# Design — branch delete on write_graph

## The question a delete has to answer

"Would anything that is not mine break?" and "would anything of mine break
silently?" The floor is cross-user only; the second is courtesy the owner
deserves because the surface cannot show dependents any other way.

## What reads a branch definition (verified reader by reader, Codex rounds 1-2)

| Reader | Depends on | On delete |
|---|---|---|
| runs (`runs.branch_def_id`, no FK) | historical id | benign: reads work, re-run by id is not-found |
| automations (`automations.branch_def_id`, no FK) | the live definition at each due run | **breaks**: `automation_error`, retries, eventual pause |
| active webhooks (`webhook_hooks`, `revoked_at IS NULL`) | token → `branch_def_id` at every delivery | **breaks**: hook stays active, every delivery fails |
| active schedules / subscriptions (`branch_schedules`, `branch_subscriptions`, `active = 1`) | `branch_def_id` at fire time | **breaks** |
| canonical goal bindings — default (`canonical_bindings`), personal (`goal_canonicals`), legacy (`goals.canonical_branch_version_id`) | a version; `invoke_branch_version` maps it back to the definition and loads it | **breaks** version-based invocation |
| other branches' CURRENT definitions: `invoke_branch_spec.branch_def_id` / `invoke_branch_version_spec.branch_version_id` | the live child (`_authorize_child_ref` reloads it each execution) | **breaks** the invoking graph |
| other branches' PUBLISHED SNAPSHOTS with the same fields | the live child, reloaded at execution of the snapshot | **breaks** — even after the parent's current definition stopped naming the child |
| remix lineage (`parent_def_id`) | nothing live (remix copies the snapshot) | benign: the parent disappears from lineage reads |
| this branch's own `branch_versions` rows | nothing; self-contained snapshots | benign — and every `patch_branch` mints two, so they must NOT count as publication |
| `background_branch_bindings` | a pinned version snapshot, executed immutably | benign |

## Rules

1. Author only, not-found envelope otherwise (also for public branches, so
   existence is not confirmed by the refusal).
2. `visibility == "public"` → `branch_is_public`. Remediation that actually
   works: patch `set_visibility private`, then delete (patch snapshots do not
   block, so the sequence completes when the branch is otherwise dependency-clean).
3. Dependents → `branch_has_dependents` with `{automations, webhooks, schedules,
   subscriptions, goals, branches}`, each a list of ids the owner can act on
   through operations that already exist. Automations, webhooks, schedules and
   subscriptions are scanned in every universe (a branch is author-scoped; a
   binding in any universe is a dependent). Goals: all three canonical stores,
   over the branch's version ids read uncapped. Branches: the author's own
   current definitions plus every active published snapshot of any branch, by
   the two structured child-ref fields — never by free-text mention.
4. Otherwise `delete_branch_definition` (hard delete of the definition row).

## A product decision, recorded

Making a public branch private is the owner's right today (`set_visibility`
checks nothing), and a foreign graph that invoked it while public fails
closed at its next run (`_authorize_child_ref` permits a private child only
to its author). Delete after that adds nothing: the foreign invoker was
already cut off by the visibility change, which is the existing contract of
public branches — they run at their owner's pleasure, and remixing (which
copies) is how another user takes a durable dependency. Codex asked for this
to be an explicit decision rather than an accident; it is recorded here and
flagged to the founder. If the founder wants public branches to be
un-withdrawable while anyone invokes them, that is a change to `set_visibility`,
not to delete.

## Not done here

- Cascade/retire of dependents: the owner does it through the existing
  operations (automation delete, hook revoke, schedule unregister, goal
  set_canonical unset, branch patch), which keeps each authority check where
  it already lives.
- A soft delete/archive: the founder's direction is a real delete.
