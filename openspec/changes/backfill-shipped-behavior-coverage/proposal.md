## Why

The full-coverage audit landed by PR #1616 proved the forward direction of these four canonical capabilities, but its reverse-direction pass found shipped behavior that no canonical OpenSpec requirement materially owns. Strict validation can therefore pass while contributors still redesign or remove live contracts unknowingly.

This first backfill wave takes the coordination-edge-free subset. It records current behavior only and leaves the thirteen contracts that overlap active credential, distributed-execution, OKF, connector, universe, Goal, wiki, uptime, or external-effect work to a dependent wave.

## What Changes

- Specify the accumulating, ordered multi-shot behavior and diagnostic limitation of `ASPEngine.validate_incremental`.
- Specify the current `tinyassets` installed GUI entry point; retain the already-canonical source-runtime and tunnel-opt-in limitations.
- Specify missing guard-artifact and project-skill-mirror checks, plus the shipped JSON forms of the four coordination diagnostics.
- Specify the domain-owned Branch-slug and episodic-coordinate registries without promoting them into persistent or thread-safe stores.
- Record the source/test evidence and exclusions for all four backfills in a durable audit map.
- Make no runtime, test, PLAN, public API, canonical-spec, or active-change edits in this proposal lane.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `constraint-evaluation`: Add the shipped cumulative multi-shot validation contract.
- `desktop-host-runtime`: Add the current installed GUI command contract.
- `development-coordination-runtime`: Add missing guard/mirror checks and machine-readable diagnostic output contracts.
- `domain-plugin-runtime`: Add domain Branch-slug and episodic-coordinate registry contracts.

## Impact

- **Behavior:** No runtime behavior changes. These deltas describe the code at `origin/main` `2190f65d`.
- **Canonical specs:** No direct edit in this proposal. Approved deltas sync into four existing capabilities when the change lands.
- **Verification debt:** `tests/test_desktop.py::TestPyprojectEntryPoints::test_has_gui_scripts` still expects the retired `workflow` GUI command; the source, current naming boundary, and package metadata use `tinyassets`. This lane records the stale test but does not touch the broadly claimed `tests/` tree.
- **Excluded work:** No packaged one-click installer, alternate ASP solver, persistent domain registry, provider/credential change, external-effect guarantee, or future platform target is introduced.
