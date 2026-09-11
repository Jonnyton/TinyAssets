# Workflow selection must compose with accepted model authority

September 11, 2026, 20:25 UTC. Correction proposal and reproduced blocker;
The initial proposal below is superseded by the reviewed disposition immediately
below. Runtime integration remains unfinished.

## September11 reviewed implementation decisions

The owner's one extra independent review completed in336s, verdict ADAPT.
Full recovered verdict: docs/reviews/2026-09-11-workflow-model-authority-extra-review.md.
The wrapper saved a later stop-hook recap; the actual review was recovered from
that same invocation's transcript, not by dispatching another review. No tests
were run by the reviewer. This approves the adapted shape, not unimplemented code.

Adopt its typed aggregate design: ProviderUniverseWorkReceipt version4 adds
authority_scope and manifest_digest. Manifest scope has no provider, provider
binding, credential or parent-binding fields (all null); assignment generation,
digest, owner, universe, immutable work subject/claim and aggregate ceilings remain.
Provider scope preserves all legacy semantics. Versions1–3 retain exact wire
documents and reject new fields. ProviderWorkBinding remains provider-specific.
Never fill required legacy columns with a fictional provider or credential.

Reservation version3 will persist exact selected member/binding/custody,
assignment/manifest, model/executor and discovery/cost evidence, covered by the
existing carrier seal. Receipt SQL must support nullable provider-binding columns
through an atomic migration preserving dependent claim/reservation rows and FKs;
old binaries fail closed on new records. No new work IDs or per-provider budget
stores. Reserve/arm revalidate current assignment AND exact selected member.
Replay compares the full selection/fence, not only tokens/cost. Router selection
comes only from sealed authority; caller config never grants execution.

Budget clarification: preserve aggregate arithmetic and ALSO sum charged tokens,
cost and invocation count for each member, not merely check each request against
the member maximum. Use explicit aggregate authorized ceilings where present,
otherwise conservative common ceilings; do not synthesize a union of maxima.
Pre-launch refusals release reservations. A launched failure still consumes its
actual/indeterminate allowance; it is not relabelled pre-launch to fund fallback.
The compiled authorized retry/fallback plan must fit a finite shared work budget;
one-call-per-node is not a sufficient allowance for requested retries. No fresh
full budget per retry or invented identity is permitted.

First implementation step is the inert version4 record and strict parsing tests;
it cannot issue/launch work until the migration and validated store/caller paths
are integrated. Then version3 reservations/carriers, shared admission, both
foreground/background callers and router. Preserve cancellation/recovery and
independent members after anchor revocation. Native explicit model discovery and
executor propagation are still required for the requested all-available-models
selector; a provider-default-only menu is not that MVP.

Owner September11 priority: ship the usable model-selector MVP now, including
seeing the answering source and selecting from all available authorized models.
Do not let unrelated workflow-project or diagnostic lanes delay this release.
Keep the broader goal and fallback/default requirements; this priority is not
permission to deploy the existing workflow regressions or fabricate model names.

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

The owner explicitly answered **Allow one additional review** on September11.
That review is now complete: ADAPT336s, disposition at the top of this file.
No further review is authorized by that exception. No unimplemented runtime
or rollout is approved by the shape verdict.
After implementation and release
gates, verify the live deployment and ask only `Retest your workflow checklist`.
The app must confirm usable general capabilities; its own project completion
is neither taken over nor substituted as this task's implementation.

## Inventory integration correction — September 11, 22:21 UTC

## Version4 aggregate receipt implementation — September11 23:00UTC

### Receipt storage migration verified — September11

The receipt table now supports an aggregate manifest without a provider anchor.
The atomic migration preserves existing authority JSON, claims, reservations,
indexes and triggers; interrupted copies/drop/rename roll back, concurrent opens
are idempotent, and unfamiliar or malformed schemas refuse without discarding
data. The foreign-key setting is restored on success and failure. No public
issuer emits manifest receipts and a stored inert manifest still cannot claim
launch authority through the legacy path.

Windows Python3.14: `python -m pytest -q tests/test_provider_work_authority.py
--tb=short --show-capture=no` passes101cases in5.69s, zero skips, including9 new
migration cases. Ruff and canonical plugin mirror/import pass. The expanded
run/consumer/background command below remains50passed/2failed in11.70s: both
known native-manifest foreground launch failures, no additional failures. This
is local migration evidence, not Linux, release review or live readiness.

Implemented the reviewed inert receipt representation and strict serialization.
Manifest receipts preserve the existing aggregate identity, subject and budget,
while refusing every provider/member/credential/parent field. Provider-bound
legacy wire documents remain unchanged. No store schema or launch path emits
this version yet; no migration, model selection or production readiness claim.

WindowsPython3.14: `python -m pytest -q tests/test_provider_work_authority.py
--tb=short --show-capture=no` passes92cases in5.22s, zero skips. Includes27 new
manifest/strictness cases (full fixture-backed legacy coverage also remains).
Ruff, strict OpenSpec validation and canonical plugin mirror/import pass.
Expanded real run/consumer/background group remains50passed/2failed in11.63s,
42dependency warnings, zero skips. Both known native-manifest foreground launch
failures remain; do not conceal them with the92record tests. No Linux proof yet.

### Earlier inventory evidence

The scheduler inventory now uses the existing accepted-member validator for
manifest enrollments, preserving the legacy validator for legacy enrollments.
It re-reads enrollment after admission, accepts any still-current member without
depending on the anchor credential, and makes no remote discovery request or
invocation/receipt. This is an internal caller correction, not a new storage or
launch-authority representation and not completion of workflow selection.

WindowsPython3.14 command:
`python -m pytest -q tests/test_run_provider_session.py -k 'background_scheduler or scheduler_inventory' --tb=short --show-capture=no`
passes5cases in1.42s, zero skips: legacy/manifest inventory, pause, credential
rotation and an independent member surviving anchor rotation. Synthetic vault
fixtures only; no live credential or user configuration changed.

`python -m pytest -q tests/test_run_provider_session.py tests/test_assigned_queue_consumer.py tests/test_background_budget_finalization_e2e.py --tb=short --show-capture=no`
reports50passed/2failed/42dependency warnings in14.29s, zero skips. The two failures
remain the explicit/default foreground-manifest release blockers, not hidden or
xfail cases. Ruff and plugin mirror/import pass. No Linux/review/deployment claim.
