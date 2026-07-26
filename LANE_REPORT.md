# Goal handoff red-main lane

Classification: **stale-test**.

Causal landing: `14ae6c35afe87f8b156c3a0b9ae40b70619430c6`
(`feat: harden branch access authority §3/4/5 + authenticated-subject
migration (2.9/2.10) (#1797)`). That landing intentionally replaced
environment-only branch authority with credential-derived request subjects.
The ordered goal-handoff runtime contract remains current; this test's branch
builder retained the superseded `UNIVERSE_SERVER_USER`-only setup.

Fix: authenticate the fixture through `authenticate_request("tester")` and
grant the goal/gate scopes used by the mixed-surface scenario. No runtime or
canonical mirror files changed; mirror parity is N/A.

Green evidence:

- Original named test: `1 passed in 3.90s`.
- Mutation check: removing the credential setup restores the original
  `KeyError: 'branch_def_id'` failure at `extensions.build_branch`.
- Full `tests/test_goals_ladder_shape.py`: `8 passed in 6.22s`.
- Covered branch-authority module: `29 passed in 5.93s`.
- `python -m ruff check tests/test_goals_ladder_shape.py`: `All checks passed!`.

An optional broader `tests/test_goals_surface.py` probe exposed separate
pre-existing red-main failures from the same landing (legacy unauthenticated
branch helpers and goal-ledger actor wiring); this scoped lane does not alter
those contracts.

Pushed fix SHA: `a329c313224a2859f94824649f6d30193c579331`.

LANE_RESULT: done - stale auth setup corrected; ordered handoff test and scoped gates are green.
