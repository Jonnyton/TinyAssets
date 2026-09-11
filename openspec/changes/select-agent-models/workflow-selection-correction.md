# Workflow selection must compose with accepted model authority

September 11, 2026, 20:25 UTC. Correction proposal and reproduced blocker;
not an approved authority design or an implemented fix.

## User capability and ownership

Users must be able to choose the main serving provider, and independently
choose a provider/model for an individual agent, workflow or task. Their cloud
universe builds and manages those projects. This development task repairs the
general platform, never the private definitions or the universe's project plan.
Permission to use a particular reviewer/model is not a requirement to use it.

## Reproduction beyond a mocked guard

`tests/test_run_provider_session.py::test_accepted_native_model_manifest_preserves_foreground_execution`
has default and provider-pinned variants. Both use the existing synthetic vault,
real bind_serving_provider, real set_serving readiness and authenticated run
admission/compiler/router plumbing. Neither mocks assignment lookup, readiness
or the failing guard. Binding reaches ready with a real manifest digest. The
workflow definition remains unchanged. Both fail before the provider receives
a call; the existing legacy one-call/once-settled control passes.

Command (Windows Python3.14, September11 around20:21UTC):

`python -m pytest -q tests/test_run_provider_session.py -k 'accepted_native_model_manifest or launches_active_serving_provider' --tb=short`

Result: 2failed,1passed,19deselected,6upstream deprecation warnings in4.73s.
Full changed-file follow-up: `python -m pytest -q
tests/test_run_provider_session.py --tb=short --show-capture=no` returned
2failed,20passed,38upstream deprecation warnings in9.07s. Only the two new
regressions fail; all existing cases pass. This is a local synthetic test,
not evidence of live user execution.

September11 20:33UTC follow-up adds real scheduler eligibility, parameterized
over legacy/model-access binding. The legacy case passes; the manifest case
successfully enables serving but list_serving_universes returns an empty list.
The same complete-file command now reports3failed/21passed/38upstream warnings
in9.08s, zero skips. This is not a background-project test: it exercises the
platform's authoritative universe inventory used by its generic coordinator.
Underlying refusal is `model selection authority is not active`, wrapped into
a misleading connect-provider failure by the foreground session/compiler.
Ruff on the changed test passes. Linux verification attempted from an isolated
archive plus this exact test file; Docker's Linux engine was unavailable before
any test started. The archive is not a completed Linux verification.

## Reverified integration boundaries

- `provider_serving_binding._current_serving_authority` rejects all manifest
  assignments. Keep that legacy fail-closed boundary; do not erase it globally.
- `_current_selected_member_authority` validates an accepted connection member,
  not its model selection or permission to launch a particular operation.
- Foreground `_admit` and `_authorize_attempt` still use the legacy helper and
  require the declared providers to match one assignment provider. Background
  `_authorize_launch` repeats that restriction before its activation/lease and
  attempt-budget checks. Those lifecycle checks must survive the correction.
- `list_serving_universes` also calls the legacy helper and catches its refusal,
  silently omitting enabled manifest universes. AssignedQueueConsumer.poll_once
  uses this list for automation submission and heartbeat publication. Thus
  background work can disappear before reaching the per-attempt authority path.
  Correct serving-intent inventory/readiness separately from actual launch
  admission; do not add remote discovery inside each SQL inventory read.
- Both workflow wrappers pass only the one-use invocation carrier to the
  router, not validated model selection. The router clears caller-injected
  `ModelConfig.selected_model`; setting that field alone is intentionally not
  an authority repair. Do not replace the carrier with a caller-made authority.
- A work receipt has one provider, binding and custody digest. Its identity and
  SQL unique constraint are one `(universe, work kind, work id)`; separate nodes
  cannot obtain independent full-budget receipts under invented work IDs.
- The carrier derives provider from that receipt. Model selection must be bound
  to the exact reserved invocation and checked before launch/settlement, not
  attached later as ordinary configuration.
- Native model validation currently accepts only provider default (empty model
  ID). Merely enabling a second subscription cannot establish an explicit Opus
  selection. Native explicit-model discovery/executor propagation remains part
  of the broader feature, not something this guard repair can claim to solve.

## Proposed correction shape and pre-build decisions

Use the existing authority store and operation lifecycle. The work-level
receipt/claim remains the aggregate invocation/token/cost budget and immutable
subject fence. Each invocation selects a currently accepted member under that
same work budget, preserving exact custody, assignment generation, requested
role, operation, executor and model/cost constraints. Refresh remote discovery
outside SQLite/admission locks, then revalidate its source and authority under
the launch fence. Main choice must not be changed to route a child invocation.

Before authority implementation, specify and review the exact versioned
receipt/reservation representation for a work-level aggregate plus per-attempt
member/model facts. It must preserve existing persisted receipts, one-use
carrier provenance, settlement ownership, cancellation and recovery. No union
of per-provider maxima, multiplied per-node allowances, fabricated run IDs or
new unbounded fallback authorization. Legacy receipt parsing remains legacy.
This is a real storage/authority decision, not a one-line provider-name change.

For ordinary agent-accessible main switching, reuse existing agent_binding
operations and owner confirmation where access/spending would expand. The
served wrapper currently omits them. A preference change within already
authorized scope must not masquerade as a new connection/approval request.
Generic pending-request answers cannot be reported as an executed switch.
No new top-level tool or developer-console requirement is proposed.

Primitive checks for bind_serving_provider/set_serving returned CLEAN, but
direct `git show origin/main:tinyassets/api/custom_agents.py` and
`tinyassets/universe_server.py` prove both handlers and mappings already exist.
The diagnostic's negative result is not primitive truth; reuse these actions.

## Required proof before release

Real binding/activation followed by foreground and background execution must
cover no pin, explicit same-source model, independent second source, mixed-node
parallel work and an explicitly empty fallback list. Verify that saved/main
choices and private definitions do not change. Also cover stale/foreign/revoked
members, custody rotation, cost/model exclusion, aggregate exhaustion across
sources, stopped activation, cancelled runs and once-only settlement/recovery.
Each refusal must identify its true class without disclosing secrets.
Verify the configured universe remains in scheduler polling after model access
is enabled. An available selected member must not depend on the structural
anchor's unrelated credential, while revoked/disabled work still cannot launch.

The currently requested additional model-release review exception is unanswered;
the previous three-round cap is not waived by goal continuation. These tests
and this proposal do not count as a fourth review. Runtime/storage implementation
awaits the required correction-shape review. After implementation and release
gates, verify the live deployment and ask only `Retest your workflow checklist`.
The app must confirm usable general capabilities; its own project completion
is neither taken over nor substituted as this task's implementation.
