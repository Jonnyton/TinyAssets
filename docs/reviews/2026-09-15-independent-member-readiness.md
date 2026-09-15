# Independent member readiness during definition removal

Narrow follow-up to3847; base db60e9be. September15,2026 UTC, Windows.
One intent: losing one accepted HTTP definition during a readiness read must
not hide a different current accepted member from the rail or scheduler inventory.

Premise correction to Fable review18616: ordinary deletion AFTER binding already
works. The earlier _open_connection_id lookup raises PermissionError, which is
already member-local. Four real HTTP/mixed integration tests pass unchanged for
deletion and grant revocation. No runtime patch was justified by that premise.

However, deletion BETWEEN _open_connection_id and verify_open_grant_custody
raises UnknownServingProvider from the second definition lookup. Two deterministic
race tests fail at base: rail falsely requests a connection and scheduler inventory
omits the universe, despite another live accepted native member.

Implement the prior review's recommended per-member isolation more narrowly:
catch UnknownServingProvider alongside PermissionError in both inventory loops,
not every ValueError. Keep all member custody checks and fail closed when none
survive. Readiness grants no invocation/model permission. The strict legacy
execution resolver and selected-model admission are unchanged.

Tests use real fixture binding, HTTP grants and custody, synthetic catalogue
transport, no actual inference or user credentials. Both provider types are
checked with zero/all/one surviving members, wrong owner, ordinary deletion,
revocation and deterministic disappearance between reads.

Independent exact-head review, Linux CI and rollout verification remain required.
Local verification:69 tests pass, zero skips (one existing FastMCP deprecation
warning), running test_manifest_connection_inventory.py,
test_pending_requests_power.py, test_provider_serving_binding.py and
test_served_model_preferences.py together with python -m pytest -q. Ruff,
diff check and443-file plugin rebuild/import pass. Windows is supporting
evidence, not a substitute for CI.
No production workflow, grant or definition was removed. The only deletions in
tests are fixture-owned temporary provider metadata files. No schema migration.
Rollback via the existing release workflow to the preceding reviewed image if
readiness/inventory regresses; preserve all user data. The public live probe is
the original user's ordinary app retest, not deliberate deletion of their setup.
