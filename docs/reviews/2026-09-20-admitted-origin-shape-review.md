# Admitted origin recovery: recovered independent shape review

September20,2026 UTC. Fable peer96232 exited0 after486s against frozen
c66fa7f1079628d2f6f4f8359528cd58df260d36. Original peer20722 no longer existed;
its exact transcript had no verdict. This replacement completed normally.
Complete reviewer final follows. Root disposition is recorded separately below.

The dispatch-queue items belong to the coordinator's lanes. My constraints for this task are read-only, no dispatches, no subagents, this amendment only, so I am not re-dispatching or dropping them. The complete review follows.

**Verdict up front: the amendment's fact is necessary and minimal, but four points need tightening before build. VERDICT: ADAPT.**

## AGREE: the origin stamp and typed options are the missing fact

- **No existing persisted fact covers dispatch options.** The envelope schema at `tinyassets/storage/run_input_admissions.py:17` holds owner, universe, target pin or snapshot, digest, start marker and claim token only. The runs table at `tinyassets/runs.py:986` has actor, owner, inputs, thread, queue universe and worker ids, but no recursion or concurrency column. The direct path computes the effective limit in memory at `tinyassets/runs.py:5105` and passes it into a closure. The `recursion_limit_applied` event at `tinyassets/runs.py:4014` is written during invocation, after the marker, so it cannot serve an unstarted run.
- **No existing persisted fact identifies a direct origin.** Absence of a consumer correlation row is not proof of "direct": legacy deliveries and future origins also own runs rows, and the legacy startup exclusion at `tinyassets/runs.py:174` already fences every admitted row regardless of origin. A direct row has no durable adapter selector today. The stamp is the smallest one.
- **Consumer provenance already exists and the amendment correctly does not duplicate it.** The sibling's `conversation_run_admissions.run_id UNIQUE REFERENCES runs(run_id)` plus owner and universe, with selection, intent and context columns, is the durable correlation. Stamping `('canonical_consumer', 1, {})` is an adapter selector and tie-breaker, not a second copy of context. Cite that table rather than adding options for the consumer.
- **Actor is already persisted and enforced.** The worker refuses a prepared actor that differs from the runs row at `tinyassets/run_input_runtime.py:143`. Do not add actor to options.
- **Guard and CAS convergence hold as described.** The lock yields None on contention with no TTL takeover (`run_execution_lock.py:124`), the start CAS requires null marker and token, no cancel intent and unchanged status (`run_input_admissions.py:211`), zero rows returns without invoking (`run_input_runtime.py:173`), and started or ambiguous rows log and return (`run_input_runtime.py:175`). The other-process test in `tests/test_run_input_recovery.py` already encodes "free guard is not abandonment".
- **Provider rebinding does not depend on a request-scoped capability.** `provider_request_capability()` is consumed only by connection inference, universe intelligence and the middleware, not by the run_graph provider path. The explicit-principal session at `tinyassets/foreground_run_provider.py:133` checks founder home and branch author against the given principal, so a restart can rebind under the owner without a live request.
- **Typing and bounds are consistent.** `type(x) is int` refuses bool, matching `run_input_runtime.py:144`. Bind_provider runs after both transactions close (`run_input_runtime.py:187`). One nit: "public/runtime bounds" names two different bounds, the public 10 to 1000 at `tinyassets/api/runs.py:964` and the runtime positive-int rule. Pick one for the registry validator and write it down.

## DISAGREE_EVIDENCE: necessary corrections

1. **Nomination must read the admissions table, not the file scan.** The only rotating scan in the five-minute loop is `reconcile_run_files` at `tinyassets/run_file_retention.py:61`, which walks `run_file_operations` by operation cursor. Hooking nomination there never nominates a direct run without files and makes file presence the de facto origin discovery, which the amendment forbids. Require a separate query over unstarted, stamped admission rows joined to queued runs, with its own run-id cursor and the same cadence and limit.
2. **Adapter prepare runs in an empty context, so principals must be explicit.** Dispatch submits via a fresh `Context()` at `run_input_runtime.py:247`, and `prepare` is called at line 138 before `identity_context` is set at line 187. Ambient `current_identity()` refuses when unbound (`middleware.py:812`), which is the safe direction. But the direct adapter must not reach `prepare_foreground_run_provider` at `foreground_run_provider.py:1064`, which rebinds a request-carried session. State as a MUST that both adapters take owner, universe and actor from the envelope and runs row, as `validate_prepared_turn` does, and construct the explicit-principal session inside bind_provider.
3. **One registry adapter for both foreground and recovery.** The amendment stamps constants at intake but leaves foreground dispatch free to pass a bespoke closure. That creates two definitions of one adapter, and the sibling's foreground `_dispatch` already builds its own prepare and settled closures. Require that foreground dispatch selects the same static registry entry by kind and version. This also decides where the legacy refusal lives: if every dispatch goes through the registry, legacy rows are held everywhere, and the consumer's same-key re-request path must go through it too rather than around it.
4. **Restrict `('direct', 1)` to depth-0 runs with no workspace family.** Child runs route to the child pool (`runs.py:5104`) and their recovery needs family evidence (`runs.py:204`), while the admitted worker always submits at depth 0 (`run_input_runtime.py:246`). Intake must refuse to stamp direct for a row with a family root, and the adapter must refuse it on reload.

## DISAGREE_CONCERN: optional post-MVP

- **Cross-origin conflict rule for direct.** Add the symmetric refusal: direct refuses when a consumer correlation row exists for the run. Cheap, and it closes the mis-stamp race between two adapters with different provider sessions.
- **Consumer terminal projection is still callback-or-same-key only.** In the sibling, `project_terminal` is reached only from `_observe_or_repair`, which fires from the settled callback or a same-request-key re-send. `read_turn` performs no repair. A crash between run completion and the done callback leaves the reply unprojected unless the same key is resent. That is the "notification as sole projection" the amendment forbids. Out of this amendment's unstarted scope, but file it as a concern against the consumer lane so "existing recovery mechanism" is not accepted as proven.
- **Direct intake must reserve, not prepare.** `_prepare_run` already initializes events and lineage once (`runs.py:3538`), and the worker initializes again after the CAS (`run_input_runtime.py:188`). The direct intake should follow the consumer's reserve shape. Build constraint, not a shape defect.
- **Consumer default recursion limit is not stamped.** With options `{}` the consumer recovers with whatever the default is at restart. Stamping the effective default uniformly is cheaper than explaining the exception, but the consumer builder agreed to `{}` and users cannot choose it, so this is low priority.

No scan or adapter boundary in the current code executes under the daemon's principal. The risk is entirely in the unbuilt direct adapter, and correction 2 fences it.

VERDICT: ADAPT

## Root disposition — September20,05:23UTC

Accepted for implementation: explicit immutable origin/options are the missing
fact; use a bounded admissions-table nomination query independent of file
presence, one allowlisted adapter for initial/recovery/same-key dispatch, and
explicit persisted owner/universe/actor in the empty worker context. Provider
binding remains outside writers. Direct intake reserves without initialization
effects before start CAS. Direct-versus-consumer correlation mismatch refuses.
Original accepted effective recursion/concurrency options must remain exact;
do not replace them with defaults or impose a new recovery-only limit.

Point4 is partially accepted: direct v1 must not submit nested child work to
the root pool, but a family root is not proof of a child invocation. Root read
cloud runs.py1530–1607 and5789–5847; ordinary authenticated runs currently get
root family(run_id,epoch1). Files verified _get_executor instead uses actual
invocation_depth>=1 for child selection. Direct v1 therefore accepts depth0,
no parent, and either no family or a valid self-root family; malformed/foreign
root and actual child provenance refuse. Do not forbid managed root workflows
or bypass lifetime/family authority. Cloud's generic activation correction
remains a release dependency, not an origin-specific exception.

Consumer callback-loss observation is a required release check, not silently
deferred. Consumer confirmed status currently only observes; it is adding
owner-authorized idempotent terminal projection repair with no dispatch/provider
effects and a lost-callback regression. Captured execution defaults must not
change on recovery. Files and consumer coordinate existing envelope/correlation
and named adapter exports rather than duplicate state or a second registry.

Current worker catch invokes terminal settlement after preparation errors;
unknown/legacy origin validation must remain held before that generic failure
path, as the amendment specifies. Final implementation, regressions, independent
exact-head review and deployed/app acceptance remain outstanding.
