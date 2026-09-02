# Design — branch delete on write_graph

## The question a delete has to answer

"Would anything that is not mine break?" and "would anything of mine break
silently?" The floor is cross-user only; the second is courtesy the owner
deserves because the surface cannot show dependents any other way.

## What depends on a branch definition (verified in code, Codex D2/D3)

| Reader | Depends on | On delete |
|---|---|---|
| runs (`runs.branch_def_id`, no FK) | historical id | benign: reads work, re-run by id is not-found |
| automations (`automations.branch_def_id`, no FK) | the live definition at each due run | **breaks**: `automation_error`, retries, eventual pause — an active automation degrading asynchronously |
| canonical goal bindings (`canonical_bindings.branch_version_id`, legacy `goals.canonical_branch_version_id`) | a version; `invoke_branch_version` maps it back to the definition and loads it | **breaks** version-based invocation |
| other branches' `invoke_branch_spec.branch_def_id` / `invoke_branch_version_spec.branch_version_id` | the live definition (`_authorize_child_ref` reloads it each execution) | **breaks** the invoking graph; for a PUBLIC branch the invoker may be another user's |
| remix lineage (`parent_def_id`) | nothing live (remix copies the snapshot) | benign: the parent silently disappears from lineage reads |
| `branch_versions` rows | nothing; they are self-contained snapshots | benign — and every `patch_branch` mints two, so they must NOT count as publication |

## Rules

1. Author only, not-found envelope otherwise (also for public branches, so
   existence is not confirmed by the refusal).
2. `visibility == "public"` → `branch_is_public`. Remediation that actually
   works: patch `set_visibility private`, then delete (patch snapshots no longer
   block, so the sequence completes).
3. Dependents → `branch_has_dependents` with `{automations: [...], goals: [...],
   branches: [...]}`. Automations are scanned in every universe (a branch is
   author-scoped, an automation in any universe bound to it is a dependent).
   Goals: any canonical binding on any of the branch's versions. Branches: the
   author's own, private included, scanned by the two structured child-ref
   fields — never by free-text mention.
4. Otherwise `delete_branch_definition` (hard delete of the definition row).

## Not done here

- Cascade/retire of dependents: the owner does it through the existing
  operations (automation delete, goal set_canonical unset, branch patch), which
  keeps each of those authority checks where they already live.
- A soft delete/archive: the founder's direction is a real delete; git-style
  recovery is a separate ask if it ever comes.
