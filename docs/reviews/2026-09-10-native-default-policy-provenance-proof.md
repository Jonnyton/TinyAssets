# Native defaults and policy provenance — implementation evidence

September 10, 2026, local feature checkout `codex/select-agent-models`, base
`e1077ac5`. Not deployed and not public activation proof.

Implements three required corrections from the reviewed preference-consumption
shape: accepted native defaults bypass HTTP discovery without fabricated model
facts; the runner rejects contradictory incoming selection/plan pairs; version2
journal input headers preserve policy provenance separately from saved generation.
Strict version1 headers remain readable with unknown provenance and are not
rewritten. The table/round schema version remains1; only input JSON is versioned2.

Native budget admission additionally needed its existing manifest predicate to
recognize an accepted default backed by an owned subscription snapshot. All
binding, assignment, custody and generation checks remain. Explicit allowlists
(including empty) still constrain routing. Unsupported explicit native IDs refuse.

## Reproducible checks

Windows Python3.14:

```text
python -m pytest -q tests/test_provider_served_router.py tests/test_selected_model_authority.py tests/test_native_model_authority.py tests/test_agent_turn_journal.py tests/test_interactive_http_agent.py tests/test_model_capacity.py tests/test_model_policy.py tests/test_universe_intelligence.py --tb=short -rs
317 passed, 3 skipped in 32.73s
```

Actual Linux oracle, Python3.11.16/git2.47.3/bubblewrap0.12.0, same working tree:

```text
python3 scripts/linux_oracle.py -- -q tests/test_provider_served_router.py tests/test_selected_model_authority.py tests/test_native_model_authority.py tests/test_agent_turn_journal.py tests/test_interactive_http_agent.py tests/test_model_capacity.py tests/test_model_policy.py tests/test_universe_intelligence.py --tb=short -rs
319 passed, 1 skipped in 32.06s
```

Windows skips: POSIX concurrent-reader admission, bubblewrap sandbox, and the
unconfigured real Codex account integration. Linux runs the first two and skips
only real-account Codex. Synthetic owned custody and recording providers are not
an actual provider-account run. Native fixtures seed serving internally while
public readiness integration is unfinished.

The initial new journal refusal tests assumed a table had been initialized even
though validation correctly stopped before opening storage. Corrected test setup;
the subsequent 96-case journal run and both combined runs pass. The initial
native test found and drove the budget predicate correction above.

`python -m ruff check` on all ten changed canonical/test files: pass.
`python packaging/claude-plugin/build_plugin.py`:416 files, import probe pass.
`git diff --check`: pass (existing generated HTML line-ending warning only).

Independent exact implementation review is pending. Real catalogue production,
saved/current choice ingress, readiness activation, clickable controls, general
non-home support, full native model discovery and rendered live proof remain
unfinished. The separate full-reset inventory concern and its two failing
integration tests are not included in these passing groups or this patch.
