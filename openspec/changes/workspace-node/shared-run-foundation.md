# Minimal shared execution foundation

2026-09-20 UTC. Release assembly under the existing reviewed workspace/run shape,
not a new proposal, public capability, managed-memory activation or completion.

## Exact provenance and scope

Clean base: merged main `3a2257f221bd1faa543f15a0590896232dd42d93`.
Only these seven canonical runtime paths were extracted from the unpublished
checkpoint `3f98a648` (the initial staged blobs were compared directly and matched):

- `tinyassets/runs.py`
- `tinyassets/graph_compiler.py`
- `tinyassets/api/runs.py`
- `tinyassets/workspace_family.py`
- `tinyassets/workspace_pool.py`
- `tinyassets/storage/run_execution_lock.py`
- `tinyassets/storage/run_input_admissions.py`

Then only the runtime/test correction diff from unpublished `676f5438` was
applied. The latter's current full `workspace_family.py` was NOT copied, because
it carries a later quiescence helper outside this foundation. Plugin mirrors are
rebuilt from these seven canonical files, not copied from either wider branch.
The provenance SHA checks correctly report the two source checkpoints are not
main; they are source references, not deployment or review claims.

Imported focused tests cover execution guard/use, family lifecycle and pool,
supplied-guard prepared execution, original input-envelope validation/recovery,
and full-row differential insertion. Activation tests deliberately publish only
simulated readiness. The original execution ownership/use shape reviews are
retained unchanged in this change directory and still say ADAPT, not exact-head
approval. `memory-enrollment-activation-correction.md` carries the independent
cloud builder's fresh blocker evidence and correction provenance.

No file custody/source/read/export API, common dispatch worker/registry,
canonical consumer, cgroup join/kernel/allocator, new launcher/AS limit,
provisioning/bootstrap process, experimental fixture or production configuration
is imported. Module imports and initial focused tests found no additional runtime
dependency. The prepared-admission module is present for the existing recovery
predicate; this release adds no caller which admits such work.

## Contract and activation boundary

One run-keyed host-local OS guard owns actual execution and guarded status
transitions. The derivative execution-use receipt only pins that same guard's
lifetime through code-node and real RPC-drain scopes; it cannot start, settle or
release a run. Owner retirement closes new pins and drains entered scopes before
descriptor/registry release. Terminal family checks remain effect authority.

Expected-status start/terminal CAS applies even when a provided guard protects a
run with no resource family. A delayed loser never overwrites a terminal winner.
Cancellation does not wait for the lifetime guard. A free guard is not proof an
unstarted queued handoff was abandoned; existing prepared admissions remain
excluded from legacy age/process-local recovery.

Managed root enrollment additionally requires current process-local,
exact-database readiness. This foundation has NO production publisher of that
readiness. Ordinary authenticated runs therefore retain NULL family association
and their established restart recovery. Private owner/universe fields alone do
not switch them into incomplete managed lifecycle. Retired/copied/wrong-root
readiness refuses, not a fall-through to a guessed family. Fully verified startup,
kernel retirement/resume and memory activation remain the cloud lane's work.

## Verification and remaining gates

Before activation correction, the isolated extraction passed51 tests with one
POSIX-only skip on Windows. After correction, the activation/family/RPC/insertion
six-file Windows cohort passed69 with zero skips in28.44s. Final matched broader
cohort on September20 passed **206, one POSIX-only fork skip on Windows** (79.17s)
and **207, zero skips on Linux** (148.40s). These are local code evidence, not
daemon deployment or live-app capability proof. Commands use `python -m pytest
-q -rs --tb=short` and these paths:

```
tests/test_workspace_family_activation.py tests/test_workspace_family.py
tests/test_workspace_family_pool.py tests/test_workspace_family_run_context.py
tests/test_workspace_family_transitions.py tests/test_workspace_family_execution_guard.py
tests/test_workspace_execution_use_lifecycle.py tests/test_run_input_recovery.py
tests/test_prepared_run_worker.py tests/test_branch_runner.py
tests/test_run_provider_session.py tests/test_run_transaction_insert.py
tests/test_run_execution_lock.py tests/test_run_execution_use.py
tests/test_run_input_admissions.py
```

Linux used the identical working tree mounted read-only at `/src`, cache and
bytecode writes disabled, no network, under the existing oracle image
`sha256:1b69d8536490285c7c7a13f1efe53ebe847696a99ae567dbbd2b9761ee0c530a`,
Python3.11. Windows used Python3.14. Regenerated plugin/import probe, all changed
canonical/test Python ruff, diff whitespace and strict workspace change validation
passed. Exact-head cross-family review and hosted CI are still required.

Required release work: root independently reviews this narrow assembled diff,
dispatches exact-head cross-family review, runs hosted gates, verifies deployment
and ordinary existing workflow behavior, and syncs ONLY these demonstrated
requirements. Do not archive or check off the wider workspace/provisioning change.
Next file/consumer layers consume this shared ownership foundation separately.
