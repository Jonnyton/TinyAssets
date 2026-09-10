# Shared picker prerequisites: local proof

September10 2026, local Windows and actual Docker Linux, before deployment.
Implements accepted model-picker-surface.md adaptations7 and9. No catalogue
endpoint or enabled UI is claimed by this patch.

- Predicate-specific owner/universe/serving query filters before LIMIT2; it
  distinguishes absent, unique and ambiguous without a general-list100 window.
  Both serving resolvers use it. A real bound native agent remains resolvable
  behind105 newer inactive bindings; two serving bindings are still refused.
- Legacy home readiness reads preferences inside the same BEGIN IMMEDIATE as
  activation. Explicit saved choice refuses; automatic/absent remain usable;
  corrupt preference and deleted home refuse. Failed activation leaves binding
  and preference unchanged. Non-home legacy serving remains independent.
- A standalone legacy database without onboarding tables remains usable; the
  readiness check does not bootstrap a home or reinterpret missing home as one.

Verification commands (same working tree):

```text
python -m pytest -q tests/test_provider_serving_binding.py tests/test_served_model_preferences.py tests/test_custom_agents.py tests/test_provider_served_router.py tests/test_model_preferences.py tests/test_onboarding_model_preferences.py tests/test_mirror_parity_gate.py --tb=short --show-capture=no -rs
```

Windows Python3.14:203passed,3skipped,25.82s. Two skips are POSIX admission/bwrap
covered by Linux; the actual Codex credential-backed integration is unconfigured.
Two framework deprecation warnings, no test failures.

Same test list through scripts/linux_oracle.py in Ubuntu/actual Docker,
Python3.11.16/git2.47.3/bwrap0.12.0:205passed,1skipped,22.63s. Only the actual
Codex integration is unconfigured. One framework deprecation warning.

Ruff passed on the four canonical changed Python/test files. Plugin generator
staged418 runtime files and import probe passed; mirror parity included above.
Initial test runs found an absent-home-table regression and a fixture timestamp
using the wrong SQLite type; both corrected before these final runs.

Independent exact implementation review remains required before landing.
The prior ADAPT383s is the pre-build shape review, not implementation approval.
No live provider call, catalogue/UI proof or deployed-SHA claim.
