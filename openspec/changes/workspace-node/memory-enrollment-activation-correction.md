# Separate generic execution ownership from managed-memory activation

2026-09-20 UTC. Internal correction to the reviewed shared execution shape;
no new public API, storage columns, user/provider exception, or deployment flag.

## Reproduced release blocker

At05:22UTC, the same real storage call sequence on Windows created an ordinary
authenticated owner/universe run, marked it running, then called
`recover_in_flight_runs` in a fresh disposable temp data root.

- Main3a2257f2 (clean monitor docs tree ca42a79d, runs.py blob
  c20c0d180af8ee5883b0eb2e295fb9952b3825b3 identical to main):1 recovered,
  statusinterrupted.
- Cloud5700f60a:0 recovered, statusrunning. Automatic family enrollment made
  ordinary rows enter recovery exclusion before managed retirement/resume exists.

A second real call proved that merely disabling enrollment was unsafe: insert a
wholly unassociated row, mark cancelled, retain its exact provided execution
guard, request running with expectedqueued. It incorrectly became running;
`status_transaction` had limited expected-status checks to family members.
Six regression cases (queued/running recovery, four terminal resurrection cases)
failed before the correction and passed afterward.

## Implemented correction

`_insert_run_in_transaction` stamps a new managed root only when authenticated
identity AND current process-local, exact-database readiness are present.
The private ContextVar carrier is absent by default, nonserializable, process
and database-bound, and explicitly invalidated on retirement. Copied contexts
retain that same invalidated object. No production publisher ships: completed
verified startup/lifecycle integration is still required before installing it.
No kernel or resource verification is performed under the insertion writer.
This carrier grants neither invocation authority nor permission to skip fresh
kernel checks. Existing typed-parent inheritance/owner/epoch/fence rules stay.

Expected-status start/terminal transitions now apply whenever the actual held
run execution guard is present, independently of family association. Explicit
expected-state callers also retain their comparison. Prepared-admission recovery
exclusion stays intact; ordinary unactivated rows retain existing recovery.
Dark family tests explicitly model readiness instead of assuming authentication
activates managed memory. Their real nested/parallel inheritance and cancel
tests remain in the suite. The ordinary insertion differential test now compares
the ENTIRE row against its executable legacy implementation, not all-but-family.

## Minimal shared foundation extraction

The independently assembled foundation may take these exact runtime paths at
3f98a648 plus this correction and regenerated mirrors:

- tinyassets/runs.py
- tinyassets/graph_compiler.py
- tinyassets/api/runs.py
- tinyassets/workspace_family.py
- tinyassets/workspace_pool.py
- tinyassets/storage/run_execution_lock.py
- tinyassets/storage/run_input_admissions.py

Transitive implementation sequence is1b99c8c4,74d84f33,0c485fbd,af3156ba,
f13224a4,8547d522,3f98a648. File-lane39d69dda consumes the guarded invocation
and terminalization seam; it is not required merely to define those seams.
No node_sandbox/cgroup kernel/join/memory runtime/provision process, fixture or
bootstrap path is required by these seven snapshots. Do not replace them with
current full-tree snapshots, which include later dark integration. Root owns
isolated release assembly and exact-head cross-family review.

Correction tests include `test_workspace_family_activation.py` plus explicit
`workspace_family_test_support.py`; updated family run-context/transitions/
execution-guard tests and `test_run_transaction_insert.py` must accompany it.
Do not mistake test-only readiness publication for an actual startup publisher.

## Verification

Windows final focused activation/differential cohort:25passed, zero skips.
Existing family/inheritance/queued-winner/late-drain cohort:50passed, zero skips.
Final Linux working-tree oracle (Python3.11.16/git2.47.3/bwrap0.12.0):
**201passed, zero skips, 54.53s**, terminalexit0. Command:

```
python3 scripts/linux_oracle.py -- -q -rs --tb=short tests/test_workspace_family_activation.py tests/test_workspace_family.py tests/test_workspace_family_pool.py tests/test_workspace_family_run_context.py tests/test_workspace_family_transitions.py tests/test_workspace_family_execution_guard.py tests/test_workspace_execution_use_lifecycle.py tests/test_run_input_recovery.py tests/test_prepared_run_worker.py tests/test_branch_runner.py tests/test_run_provider_session.py tests/test_run_transaction_insert.py tests/test_run_execution_lock.py tests/test_run_execution_use.py
```

WSL invocation supplied exact GIT_DIR/GIT_WORK_TREE mappings for this Windows
linked worktree; no git metadata or source was rewritten for the oracle.
The suite includes real prepared invocation/provider settlement
without a family, cancellation, retired/other-root/process/unknown readiness,
copied-context retirement, prepared recovery exclusion and actual sandbox drains.
Ruff, plugin mirror rebuild, diff check and OpenSpec strict validation pass.

This is a release candidate correction, not cross-family approval, deployment,
managed-memory activation or ordinary live-app acceptance.
