# Isolated consumer release integration

September 20, 2026 UTC. This is preparation for exact-head review, not a merged,
deployed or real-user acceptance claim. The original consumer checkout is preserved.

## Dependency inventory and provenance

Base is the separately reviewed shared-foundation candidate `f65ceeb9` (draft
PR 3888). The source consumer checkpoint is `d2ab8b7a`. Neither is claimed landed;
the primitive SHA checks report both as unpublished, as expected. This isolated
branch does not merge the original consumer's experimental ancestry.

- From `d2ab8b7a`: only its canonical consumer/public-route/model-bridge/app delta,
  plus the actual required `consumer_selection`, `storage/conversation_reset`,
  `storage/conversation_run_admissions`, scoped reset and account-erasure paths.
  Storage/selection/reset source history is `2ca96c52`, `2bd644d3`, `96646657`.
  Focused tests and the existing consumer proposal/review evidence are preserved.
- From file-lane checkpoint `5292b378`: exactly `run_input_origin.py`,
  `run_input_origins.py`, `run_input_runtime.py`, and the origin-column extension
  to `storage/run_input_admissions.py`, with pure validator/common-worker tests.
  The separate admitted cursor, boot and 5-minute maintenance nomination is
  integrated into the existing server loop without file-retention imports.
- From common classifier checkpoint `59ca33f6`: only the pure read-only
  `classify_admission_observation` function and its focused tests. Its receiver
  status use is specified in this change's relay delta before public exposure.
- Plugin mirrors are regenerated from this assembled source, not copied from
  an unpublished branch. The compiler receives only the `d2ab8b7a` response
  observer delta; foundation code-node/RPC execution-use scopes remain intact.

The original runtime prerequisites remain owned by the foundation: exact held
run guard, provided-guard start/terminal CAS, prepared initialization/invocation,
and ordinary recovery when managed activation is absent. This consumer does not
publish managed readiness or change resource-family/pool/guard implementation.

No file custody, source/export API, `run_input_direct` backend, sandbox change,
cgroup join/kernel/allocator, launcher/provisioning experiment or production
configuration is included. The registry's direct adapter is a static lazy import,
not a dependency of canonical consumption. A missing installed adapter now raises
typed `OriginHeld` before executor submission; it cannot appear as successful work.

## Integrated contract

New canonical admission stamps `canonical_consumer`, version 1, canonical `{}`
options atomically with the existing reserved run. Initial submission, exact-key
replay and restart nomination call the same `dispatch_initial_run`. Its static
adapter resolves named `prepare_admitted_consumer` / `settle_admitted_consumer`
exports, checks canonical correlation and current authority under the same guard,
and constructs explicit-principal provider binding outside SQL writer locks.
Consumer v1 recursion remains 100 and concurrency override None; captured model
preference DATA is not a pinned model or inherited provider authority.

The shared scanner nominates only known, queued, entirely unstarted admissions.
Unknown/legacy/corrupt origin and either start-marker component are never proof
that effects can replay. Owner-authorized status uses the common metadata-only
classifier to expose held/recovery-required state without changing run status.
Terminal callback loss is repaired only by the existing idempotent conversation
projection on authorized read; no callback is the sole durability mechanism.

## Verification

Initial isolated 7-file consumer/storage/model/origin cohort: Windows Python
3.14, 105 passed, zero skips, 47.25 seconds. Integrated dispatcher/common-worker/
actual-model-journal cohort: 35 passed, zero skips, 24.90 seconds. Shared held
observation/public-status cohort: 33 passed, zero skips, 11.46 seconds.

The extended actual public-handle test starts from another creator's public
Branch, uses the existing explicit remix/publish operations, and selects the
receiver-owned version. It covers both initial dispatch and crash after durable
admission before submission: independent nomination in a fresh context, one tool
effect, capacity fallback within one journal, and one exact reply with reported
model evidence. In the restart case the callback is deliberately lost; ordinary
status alone repairs one founder/reply pair before any resend. Started/partial
markers, invalid/missing adapters and missing canonical correlation stay held.
Provider transports here are deterministic fixtures, not live provider proof.

The original `release-candidate.md` dates are corrected to September 20 UTC;
its test claims remain historical evidence for the preserved original tree.
Final matched 27-file cohort on September 20, 2026 UTC: **606 passed, zero skips**
on Windows Python 3.14 (237.80 seconds) and **606 passed, zero skips** on Linux
Python 3.11 (306.41 seconds). Windows used `python -m pytest -q -rs --tb=short`;
Linux used that same cohort with `-p no:cacheprovider`, working tree mounted
read-only at `/src`, bytecode disabled and no network in immutable oracle image
`sha256:1b69d8536490285c7c7a13f1efe53ebe847696a99ae567dbbd2b9761ee0c530a`.
Only pre-existing asyncio deprecation warnings appeared on Windows. Paths:

```
tests/test_consumer_selection.py
tests/test_conversation_run_admissions.py
tests/test_consumer_run_envelope.py
tests/test_consumer_prepared_scope.py
tests/test_consumer_public_turn.py
tests/test_work_candidate_data.py
tests/test_work_consumer_model_bridge.py
tests/test_graph_answer_execution.py
tests/test_graph_reply_execution.py
tests/test_workflow_http_agent.py
tests/test_agent_turn_coordinator.py
tests/test_app_consumer_controls.py
tests/test_app_consumer_turn.py
tests/test_app_layout_controller.py
tests/test_app_layout_bindings.py
tests/test_onboarding_app.py
tests/test_served_model_preferences.py
tests/test_graph_compiler_provider_chain_propagation.py
tests/test_run_provider_session.py
tests/test_provider_work_authority.py
tests/test_scoped_identity_reset.py
tests/test_run_input_erasure.py
tests/test_run_input_runtime.py
tests/test_run_input_origin.py
tests/test_run_input_observation.py
tests/test_consumer_origins.py
tests/test_workspace_execution_use_lifecycle.py
```

This includes the full ordinary model/app selection baseline, reset/account
erasure, run-provider authority and actual RPC execution-use lifetime regression.
All 24 canonical plugin mirrors match byte-for-byte; rebuilt plugin/import probe,
all changed Python ruff checks, diff whitespace and strict change validation pass.

## Remaining release gates and scope

Root owns final assembled-diff/exact-head cross-family review, hosted CI, verified
deployment, canonical spec sync and ordinary two-owner rendered app acceptance.
No external review, push or merge is performed by this builder. Full arbitrary
UI, foreign harness and complete setup portability remain open. No user's private
workflow or background-self project was built or repaired as an operator shortcut.
