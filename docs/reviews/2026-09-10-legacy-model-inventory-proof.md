# Legacy model-source inventory correction

September10 2026, feature worktree afterf9652d00. Implements the first non-gating
finding from the approved e8d69c3b catalogue review. The response now identifies
its validated legacy source with provider_ref, server bind_key and configured
model_id, separately from options and actual execution receipts. HTTP gets the
owner-filtered immutable definition's fixed model; native remains empty/default.
The field is null if the legacy chain fails its closing fence. No new candidate,
price, permission, saved preference, inference or storage shape is introduced.

Two new real-binding/synthetic-HTTP tests cover legacy HTTP inventory and grant
revocation during discovery. Existing native-default test now checks this metadata.

```text
python -m pytest -q tests/test_model_options_api.py tests/test_model_catalogue_collection.py tests/test_model_options.py tests/test_model_options_composition.py tests/test_served_model_preferences.py tests/test_provider_serving_binding.py tests/test_mirror_parity_gate.py --tb=short --show-capture=no -rs
106 passed,2warnings in26.93s (Windows Python3.14)
```

Same seven files and flags through the actual Docker Linux oracle:
106 passed19.46s, zero skips.419 plugin mirrors/import, Ruff and diff checks pass.
The prior full picker group remains1053Windows/1055Linux; it predates this small
API correction and is not relabelled as an exact-head run. Review this correction
alongside the next access-confirmation composition before landing. No deployment.
