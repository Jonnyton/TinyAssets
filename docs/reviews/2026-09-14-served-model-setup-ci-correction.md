# PR3844 required-suite correction

September 14 PDT / September 15 UTC. Required Linux job104193713720,
run34909511718, completed at23:59UTC with six new failures. PR3844 returned to
draft before updating. Nine other failures and two collection errors are existing
baseline entries; no quarantine or gate changes are part of this correction.

Four new model-access tests used the real provider router and accidentally
required a native CLI to be installed. On unchanged5e93143b, forcing
`tinyassets.providers.call.get_provider_router = lambda: None` and running
`pytest.main(['-q','tests/test_model_access_requests.py','--tb=short'])` reproduced
exactly the same four failures on Windows:10 passed,4 failed. This demonstrates
the dependency, not a production permission failure.

The fixture now supplies only a synthetic available-executor interface; actual
owner/custody/assignment/preference/readiness transactions remain real. Added
three cases for absent router, absent provider and unavailable executor: each
keeps the approved request pending and does not claim serving, even after access
publication succeeds. No runtime code or permission check changed.

One old served-removal test expected a generic list of allowed targets. Connection
discovery-only setup is now exposed, so its removal refusal is operation-specific.
The test still requires removal refusal and now checks that exact message.
The final failure was an unlinked new peer-output concern; added its README row.

Validation on Windows Python3.14:

- Router forced absent before collection, then model-access, served-ask and
  concern-index files: **100 passed in4.86s**, zero skips.
- `python -m pytest -q tests/test_model_access_requests.py tests/test_served_model_setup.py tests/test_served_model_preferences.py tests/test_provider_serving_binding.py tests/test_the_served_surface_can_actually_raise_these_asks.py tests/test_concerns_index_matches_the_directory.py --tb=short`:
  **178 passed in21.17s**, zero skips, two upstream deprecation warnings.
- Ruff on both changed test files and `git diff --check`: pass.

Fresh exact-head test-delta review and fresh Linux CI remain required. This
correction does not modify runtime, mirrors, model access, request consent or
the independent receipt-history follow-up.
