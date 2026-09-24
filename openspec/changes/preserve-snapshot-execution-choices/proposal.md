## Why

Immutable branch snapshots currently omit the user's branch-level model policy and concurrency budget. Reconstructing a pinned version loses those choices, and publishing an edit to only those choices can return the old version.

Reproduction on `ff1320d5` (`tests/test_branch_execution_choice_authoring.py`, report `output/execution-choice-authoring-result.md`) shows snapshot loss is the *last* of four gaps, not the only one: `branch_definitions` has no column for either field, build never reads them from the spec, patch exposes no setter, and fork does not inherit them. The landed snapshot preservation is therefore unreachable from any stored branch, and this change's own acceptance ("verify saved choices through an ordinary app-agent conversation") cannot pass. One intent — *an ordinary author sets a workflow-wide execution choice and it survives read, fork and publish* — so the persistence and authoring deltas extend this change rather than opening a second one.

## What Changes

- Add two additive nullable columns to `branch_definitions`: `default_llm_policy_json TEXT` and `concurrency_budget INTEGER`. NULL means unset/inherit, byte-identical to today. No backfill, no historical rewrite, no index.
- Read both from the build spec (top-level or nested `graph`) and inherit both on fork, alongside `state_schema`/`io_manifest`.
- Add two patch ops on the existing op table — `set_default_llm_policy` and `set_concurrency_budget`, `null` clears — modelled on `set_io_manifest`. Unknown ops keep refusing.
- Validate `concurrency_budget` to the compiler's actual contract (positive `int`, `bool` refused) and surface both choices on the read/describe path so an author can discover them.
- Include existing non-null default_llm_policy and concurrency_budget in new immutable snapshots and content identity (landed).
- Preserve all existing stored rows and unset-field hashes. No backfill of lost historical choices from mutable definitions.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `graph-execution-substrate`: branch-level execution choices are storable, authorable, readable, fork-inherited, and retained by immutable snapshots.

## Impact

`branch_definitions` schema + migration, its row writer/reader, the branch build/fork/patch/describe routes in `tinyassets/api/branches.py`, branch validation, the landed snapshot serializer, focused regressions and the plugin mirror. **No new top-level MCP tool and no new field name** — authoring rides the already-authorized `write_graph` branch build/patch surface; `check_primitive_exists action` is CLEAN for both op names. No new authority, provider connection, table, workflow, or public resume operation. Owner: root integrating Claude builder; one branch; one dedicated PR.
