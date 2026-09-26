## REMOVED Requirements

### Requirement: Authority-owner exits commit canonical authority atomically
**Reason**: This requirement governs the fleet-era `background_branch_authority_owners` /
`background_branch_bindings` / `background_branch_attempts` store — the layer that issued
background authority from prepared bindings and owner fences. Authority for background work now
derives from the universe's CURRENT serving assignment at run time (the ADDED requirement
"Background execution authority derives from the current serving assignment at run time" in this
spec), so there is no owner, binding, or attempt fence to transition atomically; the 16 remaining
`background_branch_bindings` rows authorize a retired staging principal and are retired
explicitly, not migrated.
**Migration**: Slice 2 of `design.md`: a one-shot migration marks every remaining row `retired`
with reason `fleet_era_activation_layer_retired_2026-08-29` and logs the count; the store modules
(`tinyassets/background_branch_authority*.py`, `tinyassets/storage/background_branch_authority*.py`)
and their tests are deleted, and the three tables are dropped in a later commit of the same PR once
grep proves no daemon reader. `validate_worker_runtime_in_transaction` is pruned from
`storage/provider_work_authority.py`; the rest of that module stays (foreground-load-bearing).
