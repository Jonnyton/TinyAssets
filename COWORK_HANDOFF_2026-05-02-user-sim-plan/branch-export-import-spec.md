# Branch export / import primitive — spec

**Status:** spec, ready for navigator review then dev pickup.
**Author:** Cowork session, 2026-05-02.
**Motivation:** Today `change_loop_v1` (`fd5c66b1d87d`) and every other user-authored branch lives only in the universe SQLite at `.author_server.db`. If the SQLite is destroyed, corrupted, or re-initialized, the loop content vanishes. There is no canonical export, no version control, no fork-and-replay path. This is the largest "loop content drift" risk per `loop-fault-classes.md` Tier-1 #6.

**For:** Codex assistant pickup (or whoever picks up Tier-1 #6).

## Why this matters

Three problems the substrate solves at once:

1. **Disaster recovery.** If Mark's universe SQLite is lost, change_loop_v1 has to be re-authored from scratch. Lossy and slow.
2. **Community redesign / forking.** The "community-driven loop" promise is that anyone can fork the loop's branches and propose alternatives. Without export/import, "fork" means copy-typing a branch graph by hand from chatbot inspection — not feasible.
3. **A/B comparison + version control.** "Which version of the loop is best" can only be answered if branch versions are durable, comparable, and re-deployable. Export to file makes git-versioning + diffs trivial.

Plus a fourth, longer-term:

4. **OSS contribution path.** Tier-3 contributors (Ilse persona) want to hack on the loop. Without export, they can't see or modify it. With export, the canonical loop ships in `wiki/pages/branches/canonical/` as YAML files, contributors fork by editing, propose via PR, and the import primitive tests the proposal end-to-end.

## Surface

Two new MCP actions on the existing `extensions` tool. Both are additive — no existing surface changes.

### `extensions action=export_branch`

```
extensions action=export_branch
  branch_def_id=<id>            # required
  format=yaml|json              # optional, default yaml
  include_runs_history=false    # optional, default false (only structure, not run data)
  visibility=public|private     # optional, default private (controls whether export
                                #   is safe to share — strips ACLs/secrets if public)
```

Returns:

```json
{
  "branch_def_id": "fd5c66b1d87d",
  "format": "yaml",
  "checksum_sha256": "<sha256 of payload>",
  "exported_at": "2026-05-02T18:30:00Z",
  "exported_by": "<actor_id>",
  "schema_version": 1,
  "payload": "<the export — yaml string or json structure>",
  "size_bytes": 4827,
  "visibility": "private",
  "warnings": []   // e.g. "stripped 2 ACL entries because visibility=public"
}
```

Errors:
- `not_found` if branch_def_id doesn't exist in the active universe
- `permission_denied` if caller lacks read on the branch
- `format_invalid` if format isn't yaml or json

### `extensions action=import_branch`

```
extensions action=import_branch
  payload=<the export string>     # required
  format=yaml|json                # required (must match)
  checksum_sha256=<expected sha>  # optional but recommended
  on_id_conflict=mint_new|replace|fail   # optional, default mint_new
  on_validation_failure=reject|reject_with_diagnostics  # optional, default reject_with_diagnostics
  dry_run=true                    # optional, default true (validate but don't write)
```

Returns:

```json
{
  "imported_branch_def_id": "<new id or original>",
  "id_action": "minted_new" | "replaced" | "preserved",
  "validation": {
    "valid": true,
    "warnings": [],
    "errors": [],
    "collision_classes_checked": 19
  },
  "dry_run": true,
  "delta_from_original": {
    "node_count_changed": 0,
    "edge_count_changed": 0,
    "schema_changed": false
  },
  "would_have_been_canonical_for_goals": ["G123"],
  "next_step_hint": "Re-run with dry_run=false to commit the import."
}
```

Errors:
- `format_mismatch` payload doesn't parse
- `checksum_mismatch` payload SHA doesn't match expected
- `validation_failed` with diagnostics
- `id_conflict_blocked` when on_id_conflict=fail and id already exists
- `permission_denied` if caller lacks write on the universe

## Export format (schema_version=1)

YAML chosen as default because it's diff-friendly and human-editable. Key structure:

```yaml
schema_version: 1
branch_def_id: fd5c66b1d87d
name: change_loop_v1
description: |
  Canonical patch-investigation loop. Picks up wiki bug filings,
  routes through investigator pool, gates, coding team, ship/observe.
authored_by: <actor_id>
created_at: 2026-04-22T14:00:00Z
last_modified_at: 2026-05-02T03:15:00Z

# Goal bindings (which Goals this branch is bound to + canonical status)
goal_bindings:
  - goal_id: G_bug_investigation
    canonical: true
    bound_at: 2026-04-22T14:30:00Z

# State schema — typed fields the branch reads/writes during execution
state_schema:
  bug_payload:
    type: object
    required: true
    fields:
      bug_id: string
      title: string
      component: string
      severity: string
      kind: string
      observed: string
      expected: string
      repro: string
  patch_packet:
    type: object
    fields:
      minimal_repro: string
      root_cause: string
      test_plan: string
      implementation_sketch: string
  gate_1_verdict:
    type: enum
    values: [approve, reject, revise]

# Nodes — each is a step in the branch graph
nodes:
  - node_id: intake_router
    type: router
    description: "Classify bug payload and route to investigator pool"
    config:
      route_by: bug_payload.kind
      routes:
        bug: investigator_pool_bug
        feature: investigator_pool_feature
        design: investigator_pool_design

  - node_id: investigator_pool_bug
    type: parallel_invoke
    description: "Run Claude+Codex investigators in parallel on bug-class items"
    config:
      branches:
        - branch_def_id: investigator_claude_v2
          provider: claude-flagship
        - branch_def_id: investigator_codex_v2
          provider: codex-flagship
      merge: vote_majority

  # ... more nodes ...

# Edges — control flow
edges:
  - from: intake_router
    to: investigator_pool_bug
    condition: bug_payload.kind == "bug"
  - from: investigator_pool_bug
    to: gate_1_review
  # ... more edges ...

# Validation hints (for validate_branch)
validation:
  expected_collision_classes_clean: 19
  performance_budget_seconds: 1800

# Provenance
provenance:
  exported_from_universe: <universe_id>
  parent_branch_def_id: null   # this is canonical; no parent
  fork_lineage: []             # if this is a fork, ancestor IDs go here
```

## Implementation

### Files to create / modify

- `workflow/api/branches.py` — new `_export_branch` + `_import_branch` handlers; wire into the `branches()` dispatcher
- `workflow/branches.py` — new `BranchDefinition.to_export_dict()` + `BranchDefinition.from_export_dict()` methods
- `workflow/universe_server.py` — extend `extensions` @mcp.tool to accept the new actions
- `tests/test_branch_export_import.py` — round-trip tests + edge cases
- `packaging/claude-plugin/...` — auto-rebuilt mirror (run `python packaging/claude-plugin/build_plugin.py`)

### Round-trip invariant

`import(export(branch))` must produce a branch byte-identical to the original (same node graph, same state schema, same validation behavior). The `checksum_sha256` field exists to prove this — a round-trip's checksum must match.

### ID strategy on import

Three options, controlled by `on_id_conflict`:

- **`mint_new`** (default): import always mints a new branch_def_id. Original survives. Used for forks and A/B tests.
- **`replace`**: import overwrites the branch with the original ID. Goal bindings preserved. Used for "restore from backup" scenarios — DESTRUCTIVE if not careful, requires explicit confirm.
- **`fail`**: import errors if the original ID already exists. Used for "first-time import" scenarios.

### Validation chain on import

Every import passes through `validate_branch` (including the 7 new collision classes from BUG-044) before being written. If validation fails, the import is rejected with full diagnostics in `validation.errors[]`. No partial writes.

### Visibility / privacy

Public exports (visibility=public) strip:
- ACL entries (who can edit / who can run)
- Provider-specific secrets (any `config.secret_ref` keys)
- Authored-by attribution at node level (top-level authored_by stays)
- Universe-internal node IDs that reference other branches (replaced with `<placeholder>`)

The strip pass is recorded in `warnings[]` so the exporter sees what was removed.

Private exports (visibility=private, default) keep everything and are only safe to share within the same universe / trusted recipient.

## Round-trip tests

Tests (in `tests/test_branch_export_import.py`):

1. **Round-trip identity**: export → import (mint_new) → re-export → checksum match
2. **Replace semantics**: export → modify YAML node → import (replace) → verify branch updated
3. **Fail-on-conflict**: import with on_id_conflict=fail when ID exists → expect `id_conflict_blocked`
4. **Validation rejection**: import a YAML with a known collision class → expect `validation_failed` with that class in errors
5. **Visibility strip**: export with visibility=public → verify ACLs and secrets removed, warnings populated
6. **Cross-universe**: export from universe A, import to universe B → branch present in B with new ID
7. **Schema-version mismatch**: import a YAML with schema_version=99 → expect `format_mismatch` (or `schema_version_unsupported`)
8. **Goal binding preservation**: import a branch that was canonical for a Goal → verify the binding survives in the target universe (or fails informatively if Goal doesn't exist there)
9. **Fork lineage**: export → import (mint_new) → verify exported.branch_def_id appears in imported.provenance.fork_lineage
10. **Large branch**: round-trip a 50-node branch → memory bounded, completes in <2s

## Nightly version-control snapshot

Once the primitive lands, add a scheduled job (existing `extensions action=schedule_branch` infrastructure):

- Every 24h, export every Goal-canonical branch via `extensions action=export_branch visibility=public`
- Write the export to `wiki/pages/branches/canonical/<branch_def_id>.yaml`
- Commit + push the wiki repo

Result:
- `git log wiki/pages/branches/canonical/fd5c66b1d87d.yaml` shows the canonical loop's evolution
- A drift between the SQLite branch and the latest export = signal something changed without going through approved revision flow
- Backup-restore works: clone the wiki, `import_branch` each YAML, universe is restored

## Dev estimate

- Spec review (navigator): 2h
- `_export_branch` impl + tests: 4-6h
- `_import_branch` impl + tests (more complex due to ID strategy + validation chain): 8-10h
- Visibility strip pass: 2-3h
- Plugin mirror + universe_server.py wiring: 1h
- Nightly snapshot scheduler: 2-3h
- Documentation: 2h

Total: ~3-4 days for full implementation, including tests.

Recommend slicing: Slice 1 = export only (yaml format, private only); Slice 2 = import (mint_new only, dry_run only); Slice 3 = import side effects (replace / fail / non-dry-run); Slice 4 = visibility=public + nightly snapshot. Each slice independently shippable.

## Cross-references

- `loop-fault-classes.md` Tier-1 #6 (the motivating fault class)
- `docs/design-notes/2026-05-02-validate-branch-primitive.md` (the validation chain this depends on — BUG-044)
- AGENTS.md Hard Rule 12 (no destructive git ops; this primitive's "replace" semantic needs analogous safety)
- `project_almost_correct_functions_are_dangerous` (memory) — rigorous round-trip tests prevent the silent-corruption class
- `wiki action=write` + `wiki action=promote` (the wiki side of the nightly snapshot)
- `extensions action=validate_branch` (gate every import goes through)
- `goals action=set_canonical` (preserve canonical status across import)

## Non-goals

- **Not a UI.** This is a substrate primitive. The "user clicks Export Branch" UI is downstream — chatbot would call `extensions action=export_branch`, render the YAML in a code block, save to file via OS-level handoff.
- **Not a migration tool.** Cross-version SQLite migrations are separate. This primitive assumes the target universe's schema is compatible with the export's schema_version.
- **Not a sync engine.** No real-time bidirectional sync between universes. Just one-shot export and one-shot import.
