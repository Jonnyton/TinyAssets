# Original consumer release candidate — 2026-09-20 UTC (not deployed)

Historical evidence for the original `d2ab8b7a` candidate, preserved below.
The isolated release assembly and current dependency/verification disposition
are recorded in `release-integration.md`; original ancestry is not its release scope.

This checkpoint completes the existing candidate's public route, model DATA
bridge, actual reply attribution, keyed app transport/history deduplication and
trusted selection controls. It is NOT an independently releasable whole branch:
the branch also contains inherited, unpublished shared execution foundations.
Do not push all ancestry as a consumer-only release.

## Review map

- `consumer_runtime.py`: authenticated existing `converse` and owner-scoped
  `read_graph(conversation_turn)` admit the SAME reserved common run, never a
  second writer. Missing keyed request refuses without effects. Replay finds
  stable intent before today's defaults/history. Public source requires existing
  explicit receiver-owned Branch remix; no author substitution or creator grant.
- `storage/conversation_run_admissions.py`, `conversation_store.py`: original
  canonical scope/fences, two-store projection and minimal retained dedupe remain.
  Actual producer receipt is frozen only for the provable declared output writer.
- `providers/work_candidate_data.py`, `foreground_run_provider.py`,
  `workflow_agent.py`, `agent_turn_coordinator.py`: original preference DATA feeds
  finite fitted candidate orders, never a converse authority carrier. Each next
  model gets fresh ordinary run authorization while preserving the same journal.
  Authentication and uncertain effects hold; capacity may advance. Existing
  strict carrier checks are not loosened. Compiler retries do not replenish order.
- `providers/graph_reply_execution.py`, `graph_compiler.py`, provider router:
  per-node reported answer identity, never a global last-model slot; ambiguous
  combined outputs and unknown reported model remain honestly unknown.
- `onboarding/app.html`: original keyed request is saved before effects, then
  status/replay repair observes the same run. History-first and status-first
  rendering dedupe the actual canonical pair. Legacy no-selection chat is intact.
- `onboarding/app_layout.js`: the fixed App design dialog, outside movable user
  layout, shows separate conversation compatibility/selection. Explicit select,
  disable and previous-selection rollback use current owner, original revision,
  existing binding mutation and exact read-back. Uncertain writes never replay.
  Unrelated private configuration is preserved. Rollback memory is visit-local;
  an older public design can always be explicitly inspected and selected again.

## Required shared foundation, not consumer-owned experiments

Direct imports: `run_input_runtime.py` (prepared execution, dispatch),
`storage/run_input_admissions.py` (immutable same-run envelope),
`storage/run_execution_lock.py`, the guarded run insertion/invocation/terminal CAS
hooks in `runs.py`, and their reset/account-erasure classifications. This tree
contains worker checkpoints 28b1a4a3, af3156ba, f13224a4, 39d69dda, 1e035411 and
5ef93df6 (the last is the consumer cherry-pick of common 76804605).

Current `runs.py` hooks inherit `workspace_family.py` and pool/family lifecycle
integration. Review/release that coherent common foundation first; do not strip
the guards or fake managed-family support to make a consumer-only patch smaller.
The later execution-use/RPC-drain checkpoint 3f98a648 is NOT in this tree yet and
must be integrated by the release lead with the foundation before final release
verification. File custody/public intake, cgroup bootstrap/probe scripts and
experimental containment deployment are NOT consumer runtime dependencies merely
because they are present in this branch's ancestry. No cgroup activation is made.

The approved origin-recovery amendment is separately lead/file-lane owned.
Static `prepare_admitted_consumer` and `settle_admitted_consumer` exports are ready
for that one registry. They resolve original canonical/envelope owner scope, use
captured preference DATA and build explicit-principal provider sessions outside
SQL writers. V1 always used recursion limit100 and no concurrency override;
neither the strict request nor component accepted either override. Those are now
explicit versioned v1 semantics, not mutable runtime defaults or model pins.
This candidate has no guessed origin columns or consumer-specific boot queue.
It still needs integration to the file lane's common registry before claiming
restart-complete behavior.

## Proof and remaining release gates

Actual public-route integration creates a foreign public Branch, uses the real
existing lineage-preserving `write_graph` remix/publish, selects its receiver-owned
version and executes one reserved run. Its engine tool executes once, capacity
switches A to B in the same journal, and exact-key replay/status produces one
durable founder/reply pair with actual reported model evidence. Deterministic
provider transport fixtures are not live provider acceptance.

Trusted-control red-first Node execution failed because `turnComponent` was
absent, then passed after implementation. It exercises select, preserve private
config, disable, rollback, revision conflict, lost read-back, no duplicate write
and collaborator-update refusal. The three-file JS-control/keyed-send checks
(7 tests) passed on Windows, zero skips, before consolidated regression runs.

Consolidated 15-file cohort on September 20 UTC: **150 passed, zero skips** on Windows
Python 3.14 (94.51s) and Linux Python 3.11 (142.83s), running the same test paths:
`test_consumer_selection`, `test_conversation_run_admissions`,
`test_consumer_run_envelope`, `test_consumer_prepared_scope`,
`test_consumer_public_turn`, `test_work_candidate_data`,
`test_work_consumer_model_bridge`, `test_graph_answer_execution`,
`test_graph_reply_execution`, `test_workflow_http_agent`,
`test_agent_turn_coordinator`, `test_app_consumer_controls`,
`test_app_consumer_turn`, `test_app_layout_controller`, `test_app_layout_bindings`
(all under `tests/`, `.py`, `python -m pytest -q`). Linux used the working tree
read-only under `/src`, no network, no cache writes, the established immutable
oracle image `sha256:1b69d8536490285c7c7a13f1efe53ebe847696a99ae567dbbd2b9761ee0c530a`.
Plugin rebuild/import probe, scoped ruff and strict change validation passed.

Additional existing app/model-preference/controller cohort: Windows177/0 skips,
61.50s; existing graph policy/run provider/session/authority cohort Windows148/0
skips,28.36s. Their same combined seven-file Linux cohort passed325/0 skips in
94.62s. Paths: `test_onboarding_app`, `test_served_model_preferences`,
`test_app_consumer_controls`, `test_app_layout_controller`,
`test_graph_compiler_provider_chain_propagation`, `test_run_provider_session`,
`test_provider_work_authority`.

Origin-review correction: a new lost-callback status test first observed `held`
instead of `completed`. Owner-authorized status now converges only the terminal
projection; dispatch and provider calls are forbidden by the regression. The
earlier contract's callback/replay-only wording is superseded accordingly.
One intermediate assertion incorrectly expected a different fixture's message
(`hello` instead of the actual unchanged intent); corrected to compare the
original intent, not change product output. A separate adapter test changes the
global recursion default after admission and verifies explicit v1 100/None.
Post-correction public-route/envelope/real model-bridge cohort passed28/0 skips
on Windows (25.26s) and matching Linux (29.98s). No unchanged full cohort was
rerun merely to relabel the small correction.

Independent exact-head implementation review, shared-foundation integration,
common unstarted-origin recovery, hosted CI, protected deployment and ordinary
two-owner rendered acceptance remain release gates. Wider arbitrary UI/foreign
harness/setup portability remains open. No private user design was edited.
