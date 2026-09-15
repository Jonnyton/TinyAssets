# Automatic source recovery — September 15, 2026

Priority: founder's live chat fails on an accepted source's sign-in error.
This interrupts the paused workspace provisioning lane; no user workflow edits.

Shape review: Claude Fable 5.1, peer process40817, exit0 after381s. Result ADAPT:
use bounded process-local owner/universe/source/custody-scoped demotion at plan
time, not persistent authority state or a native-turn replay. Clear on success;
changed credential custody is a new key. Preserve explicit choices. Original
artifact: output/automatic-auth-recovery-shape-fable.md in the lead worktree.
Its final message omitted the earlier detailed review; exact-head implementation
review must inspect the actual complete diff before landing.

Implementation contract:
- Adapter normalizes its closed authentication signal into a generic typed error.
- Router records only the exact served authority's metadata, never credentials,
  raw provider error text, host-global authentication or another user's health.
- A bounded, locked, expiring in-process hint moves recently failed sources after
  other already-eligible sources for NEW Automatic plans. It grants nothing.
- Explicit current/saved order stays exact. All-unhealthy remains retryable;
  no permanent lockout. No preference, grant, model-access or workflow writes.
- Current-turn unknown-effects, journal and capacity fallback remain unchanged.
- Existing model-picker labels explain demotion without disabling manual choice.
- New successful same-custody inference clears its hint. Restart/expiry loses
  advisory memory and may retry; durability/multi-worker sharing is deferred.

Acceptance: typed failure preserved, no same-turn replay; next Automatic request
uses an eligible alternative; explicit selections still attempt their source;
owner/universe/base/source/custody isolation; bounded expiry and success clearing;
no authority expansion; real rendered app reply after deployment.

Built on deployed base2c902151a47a. September15 Windows Python3.14 focused
verification: pytest -q tests/test_source_health.py
tests/test_served_model_preferences.py tests/test_provider_stream_and_classify.py
tests/test_model_options.py tests/test_model_catalogue_collection.py
tests/test_app_model_picker.py tests/test_provider_served_router.py
tests/test_served_failure_notice.py tests/test_conversation_failure_history.py
=>270passed,4skipped,44.64s. Final picker wording edit followed by
pytest -q tests/test_app_model_picker.py =>50passed,8.47s.
Four Windows skips are not Linux proof; CI required.
Ruff check and plugin build/import probe passed. No real-user auto recovery proof.

Round2 Fable5.1 exact-head review APPROVE at d2b77b84a7a6654a1cf32925bff2a0f776720e26,
356s; independent two-case auth integration test passed. No blocking findings.
Additional queue/capacity/order/composition tests148pass,8.52s. CI identified a
stale generated-asset receipt for the edited app HTML; only its normalized hash
is refreshed. No mark geometry, pixels, generator or app behavior changed in
this follow-up. This review note moves into the existing review-artifact home.
Final unchanged-runtime head confirmation, required Linux CI, deployment and
rendered Automatic recovery proof remain pending. The original founder's request was
recovered through a temporary explicit Codex choice without changing saved Auto.

Rollback: revert this implementation through the normal PR/deploy pipeline if
Automatic chooses outside authority, explicit order changes, or error rates rise.
There is no schema migration or credential write to reverse. Rollback loses only
advisory process memory and restores previous routing; retain conversation records.

Post-live non-blocking observations are tracked in
../concerns/2026-09-15-automatic-source-health-followups.md. Do not expand the
MVP or weaken its effect fence to address them.
