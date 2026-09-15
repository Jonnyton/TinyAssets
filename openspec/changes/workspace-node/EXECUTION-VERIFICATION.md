# Provisioning execution implementation evidence

September15,2026 UTC. Branch codex/execute-workspace-provisioning, based on
deployed main2c902151a47af974ff3269131bb83bea8f86c217. Reuses the now-clean
repair-resolver-pip-configuration worktree; PR3857 remains unchanged in history.
Reviewed execution amendment and Fable disposition copied into this lane before
code. No public route or checkout behavior has been enabled by this checkpoint.

## Manifest extraction checkpoint

Added read_provision_manifests to the existing staging/command module. It uses
workspace_fs.read_regular_file_beneath on the caller's held repository fd and
existing byte/text/Python/Node admitters. Fixed256KiB Python/4MiB Node input
bounds, strict UTF8, fixed non-secret reader failures, distinct missing lockfile,
immutable canonical plans/digests, no partial plan return. No new filesystem
reader, subprocess, network operation, credentials or private workflow edits.

RED: python -m pytest -q tests/test_workspace_manifest_reads.py --tb=short
returned10failed5skipped because the reader entry point was absent.
GREEN WindowsPython3.14.3: python -m pytest -q
tests/test_workspace_manifest_reads.py tests/test_workspace_resolver.py
tests/test_workspace_provision.py =>342passed5skipped1.83s. The skips are the
five genuine POSIX descriptor tests, not excused successful Windows coverage.
Ruff import/line formatting corrected; rerun before commit.

Actual WSL UbuntuPython3.12.3, installed pure-Python packaging26.2 read from the
existing Windows site-packages directory, no installs or external calls:

```text
wsl -d Ubuntu -- python3 -c "import sys, unittest; sys.path.append('/mnt/c/Users/Jonathan/AppData/Roaming/Python/Python314/site-packages'); import packaging; print('Python', sys.version.split()[0], 'packaging', packaging.__version__); suite=unittest.defaultTestLoader.loadTestsFromName('tests.test_workspace_manifest_reads'); result=unittest.TextTestRunner(verbosity=2).run(suite); sys.exit(not result.wasSuccessful())"
```

15tests passed0.010s, NO skips. Real POSIX tests prove held fd survives repository
rename/name replacement; leaf and ancestor symlinks refuse; traversal/absolute/
backslash paths refuse; FIFO/directory refuse without blocking; oversized file
refuses. Temporary files were under Linux /tmp, not under the repository.

This is actual Linux filesystem evidence, not bubblewrap/CI3.11/production
acceptance. WSL has no bwrap and the Docker Linux oracle remains unavailable
after its Inference socket startup failure; diagnostic peer87412 timed out.
Do not repeat an identical failed preflight or claim the required jail proof.
No push/PR/deploy for this incomplete execution lane. Before pushing the
runtime path, run scripts/linux_oracle.py with a functioning Docker engine and
the real resolver/isolation tests, plus independent exact-head review.

## Remaining implementation

September15 08:23UTC priority interruption: founder reports new live chat failure;
Patches paused this cloud lane to investigate Automatic selecting broken Claude
authentication. In-progress transport and command changes remain local/unpublished.
The registry core accepts only CONNECT443 to the three reviewed hosts, reuses
pin_address for all-address validation, dials numeric addresses, relays opaque
TLS bidirectionally with bounded buffers and one shared byte/connection/deadline
budget, and closes relays on cancellation. Linux-only Unix packet/SCM_RIGHTS
handoff admits one connected Unix stream, close-on-exec, closing malformed or
truncated descriptor lists. No host-network socket crosses to the downloader.

Actual WSL Ubuntu Python3.12.3 command:
`wsl -d Ubuntu -- python3 -m unittest -v tests.test_workspace_registry`
=>23tests pass0.231s/no skips. Local socket peers and injected DNS/pinned dial;
NO external registry traffic, real TLS verification, bubblewrap or checkout
integration proof. Includes actual descriptor-passing and /proc fd-leak checks.
Windows:14transport tests pass,9Linux-only skips,42parameterized subtests pass.

Acquisition commands now use fixed namespace proxy http://127.0.0.1:3128 via
pip --proxy and npm --proxy/--https-proxy/--noproxy=. Offline commands remain
proxy-free. npm dependency scripts are allowed only offline with canonical
root-script-free manifests, per D3. Updated regressions first returned4failures
and44passes on old builders. After correction the combined registry/manifest/
resolver/provision suites returned356passes14POSIXskips42subtests. Added real
installed npm config-parser checks without network/install; npm normalizes the
proxy origin with a trailing slash, now explicitly accepted by those assertions.
Final combined Windows rerun:358passed14POSIXskips42subtests2.57s. Ruff passes;
plugin mirror445files and import probe pass. Official config reference:
https://docs.npmjs.com/cli/v11/using-npm/config/ (September15 read).

Still absent: namespace listener, broker process supervision and its inherited
descriptor lifecycle, checkout consent and byte reservations,
actual jailed pip/npm acquisitions and offline installs. No runtime caller is
wired; do not claim this core completes provisioning or open a rollout PR yet.

Task2.1 remains open until checkout uses extraction after connection-sourced
consent. Task2.2 still needs the reviewed registry broker/namespace relay,
acquisition-only proxy flags, validated second mount, workspace limits,
pre-wire byte reservation/reconciliation, separate offline install and truthful
publication evidence. Task2.3 needs real jailed pip/npm plus the user's rendered
cloud proof. Browser/system runtime and governed additional artifacts remain in
the overall goal. Parser/reader success is NOT provisioning success.

## Typed provisioning mounts — September 15, 2026

Built locally in node_sandbox.ProvisionMount and BwrapLauncher.for_provision.
The coordinator must supply held descriptors for distinct sibling scratch
directories outside the checkout; this object is not consent or public input.
Acquisition mounts canonical manifests read-only plus a writable private cache,
with no checkout. Offline installation requires a held checkout directory and
read-only manifest/cache binds. Every directory is fstat-validated before launch;
aliases, sockets/files/symlinks, closed/uninherited descriptors and extra offline
descriptors are refused. Fixed destinations only, no arbitrary bind paths and no
host-network flag. A provisioning launcher cannot be reused/rebound between stages.
The existing ordinary code/workspace launcher behavior remains unchanged.

09:27UTC Windows Python3.14: focused pytest17pass1POSIXskip13subtests; RuffPASS.
Actual WSL Ubuntu Python3.12.3: python3 -m unittest -q
tests.test_workspace_provision_mount =>18testsPASS0.056s/no skips, including real
directory descriptors and duplicate-inode refusal. These are filesystem/argv
proofs, NOT actual mount permissions, a bubblewrap launch or provisioning proof.
Initial broader sandbox cohort236pass18skip18.57s; final broader rerun at19:28UTC
after checkout-fd validation: pytest -q tests/test_node_sandbox.py
tests/test_node_sandbox_workspace.py tests/test_workspace_provision_mount.py
=>237pass18skip13subtests19.07s. Plugin mirror445files/import probe and Ruff pass.

Work was interrupted after09:27UTC; reinspection19:26UTC found precisely these
local edits intact. The old Docker version probe handle was gone, without a
captured terminal result; do not claim engine recovery or oracle success.
19:29UTC bounded docker info returned1: dockerDesktopLinuxEngine pipe absent;
no Docker Desktop/backend process present. Normal existing-installation start
requested, with no reset/deletion. Real-jail oracle is still pending.
19:41UTC correction: Docker Desktop is not required. The existing native Ubuntu
WSL Docker engine works. Windows worktree git pointers need process-local Linux
GIT_DIR/GIT_COMMON_DIR/GIT_WORK_TREE paths, not edits to the gitfiles. Command:
`wsl -d Ubuntu --cd /mnt/c/Users/Jonathan/.codex/worktrees/repair-resolver-pip-configuration/TinyAssets -- env GIT_DIR=/mnt/c/Users/Jonathan/Projects/TinyAssets/.git/worktrees/TinyAssets27 GIT_COMMON_DIR=/mnt/c/Users/Jonathan/Projects/TinyAssets/.git GIT_WORK_TREE=/mnt/c/Users/Jonathan/.codex/worktrees/repair-resolver-pip-configuration/TinyAssets python3 scripts/linux_oracle.py -- -q tests/test_workspace_provision_mount.py tests/test_node_sandbox.py tests/test_node_sandbox_workspace.py`
passed255tests/13subtests, zero skips,21.50s on e8952b37. Container Python3.11.16,
git2.47.3, bubblewrap0.12.0; actual existing jail tests executed. New provisioning
mount tests still prove descriptor/argv contracts, not an end-to-end install.
No Docker reset, deletion or host credential change. A bounded independent
Fable Docker diagnosis exited1 without a usable result; no verdict was received.
Native Docker makes that diagnosis unnecessary. This was not a PR3859 review.

No push/deploy. Exact-head cross-family review remains required before rollout.
Tasks2.1-2.3 stay open: listener/supervision,
consent/reservation/caller, actual pip/npm and rendered cloud use are unfinished.

19:55UTC real mount regression: two new Linux tests found bwrap preserves the
host manifest/cache/checkout fds after mount setup. Read-only pathname binds alone
are insufficient. Added an isolated post-mount Python bootstrap that consumes
mount fds before runner execution; standard IO stays intact. New real-jail tests
verify writable acquisition cache, read-only offline cache/manifests, usable
offline checkout, absent host fds/env and unavailable direct network.
Before fix:2failed18passed; after fix full Linux257passed13subtests/no skips21.41s.
Windows237passed20skips18.22s; Ruff and generated plugin445files/import pass.

Ordinary main8be980c6 launcher independently reproduced the surviving handle.
Shared fix isolated in codex/close-sandbox-mount-handles at75c7daf1; that safety
repair displaces provisioning integration. Its Fable5.1 review could not start:
CLI reports requested model unavailable or inaccessible, not proven quota.
Founder choice of available Claude reviewer is pending. This cloud copy and
all provisioning remain unpublished/unreviewed; no task closure or live claim.

## Namespace relay and real pip proof — September 15, 2026 20:24 UTC

Built the acquisition-namespace-only listener in workspace_registry_proxy.py.
Its private Unix packet control arrives as stdin; only namespace-local Unix
relay endpoints cross to the existing host registry broker. No host listener,
host network namespace, checkout mount, credential or connection grant is added.
Package children use DEVNULL stdin and close_fds. Connection/active bounds,
deadline, EOF revocation, bounded pumping and thread-start failure cleanup are
covered. The outer process supervisor and verified process-death contract remain
the production coordinator's responsibility; this library is not that caller.

Final five-file cohort (proxy, registry, provisioning mount, resolver, provision):
Windows `python -m pytest -q tests/test_workspace_registry_proxy.py tests/test_workspace_registry.py tests/test_workspace_provision_mount.py tests/test_workspace_resolver.py tests/test_workspace_provision.py`
=>366passed,25POSIXskipped,55subtests,2.19s. Same file arguments through the WSL
Linux oracle command above =>391passed,60subtests,zero skips,2.73s. Ruff passed.
An initial Linux run had389passes/two npm config-parser failures: the test used
/dev/null for both global and user config; npm rejects that double-load. Only
the test's global config fixture changed to a distinct empty file. Actual
acquisition/offline builder options remain intact; assertions were not weakened.

The explicit local script scripts/probes/workspace_registry_smoke.py downloaded
the existing hash-locked requirements fixture from public PyPI using real DNS,
address classification, pinned broker connections and end-to-end pip TLS. It
then terminated the acquisition/broker relays, verified manifest digest and
installed five wheels in a separate offline jail, running pytest9.1.1 there.
Command: `wsl -d Ubuntu -- docker run --rm --memory=2g --pids-limit=1024 --security-opt seccomp=unconfined -v /mnt/c/Users/Jonathan/.codex/worktrees/repair-resolver-pip-configuration/TinyAssets:/src:ro --workdir /src -e PYTHONDONTWRITEBYTECODE=1 tinyassets-linux-oracle:7693b1a8f805 python scripts/probes/workspace_registry_smoke.py`
Both explicit runs exited0; final receipt: namespace_acquisition=true,
broker_bytes=1926522,broker_connections=2,wheels=5,offline=true,pytest9.1.1.
No tenant data, production request or user workflow was used. The script is
manual proof, not a reusable production supervisor. Plugin mirror446/import
probe passed before the test-only npm fixture correction.

Still open: whole-process broker supervision, lease/consent/reservation/caller
integration, real npm installation, complete repository dependency closure,
browser runtime/preview and rendered cloud-user acceptance. Running pytest's
version is NOT running the repository's test suite: its global conftest needs
additional dependencies absent from this five-wheel fixture. Tasks2.1-2.3 stay
open. No rollout PR or production caller; shared sandbox repair3860 must land
with independent review first. Fable5.1 remains unavailable/inaccessible and
founder choice of another Claude model is unanswered.

## Real npm install and public trust bundle — September 15, 2026 20:35 UTC

Expanded the explicit manual registry smoke to `--ecosystem python|node`.
The npm fixture uses the existing site lockfile's picocolors1.1.1 resolved URL
and SHA512 integrity. Acquisition copies canonical/digest-checked manifests
to a fresh private /tmp prefix because npm ci extracts node_modules; it does
not write the canonical mount or access the checkout. Offline installation
uses a different checkout jail, RO cache, no proxy or inherited broker channel.
The fixture is platform test data, not a user workflow or either app-owned PR.

Two normal npm runs timed out. A separately labelled diagnostic with retries
disabled exposed `UNABLE_TO_GET_ISSUER_CERT_LOCALLY`; broker had one connection,
4638bytes and no admission/transport failure. The jail omitted Debian's public
CA bundle. Added one fixed, non-redirected read-only bind of
/etc/ssl/certs/ca-certificates.crt for acquisition ONLY. No /etc directory,
private keys, ambient CA override, host network or TLS-verification disablement.
New shape tests failed twice before the fix; both pass after. Real jail tests
parse CA roots, refuse write-open, confirm no private directory and absence
from the offline stage. Normal code-node mount behavior is unchanged.

With that fix the NORMAL npm command (diagnostic=false) exits0:
namespace_acquisition=true,broker_bytes=8872,broker_connections=1,
ecosystem=node,offline=true,executed=picocolors1.1.1. The check resolves the
package specifically from /workspace/node_modules and executes its API.
Normal Python proof also exits0:1926527bytes,2connections,pytest9.1.1.
Use the Docker command above, adding `--ecosystem node` or `--ecosystem python`.
Official npm semantics checked: https://docs.npmjs.com/cli/v11/commands/npm-ci/
and https://docs.npmjs.com/cli/v11/commands/npm-cache/. Runtime actually tested
is Debian Node20.19.2/npm9.2.0 in the oracle image, not npm11/production proof.

Final seven-file cohort uses the five files above plus tests/test_node_sandbox.py
and tests/test_node_sandbox_workspace.py. Windows589pass/42POSIXskips/58subtests,
23.78s; same WSL Linux oracle631pass/63subtests/zero skips,23.74s. Ruff, plugin
mirror446files/import probe passed. No concurrent source changes during copy.

This closes the local npm acquisition/offline proof gap, not task2.2 or2.3.
Next: the actual production supervisor with bounded drains, process-tree
termination, broker DNS deadline and revocation; then consent/lease/byte-ledger
caller integration before publication. No production caller or rollout added.
The shared descriptor repair3860 remains draft75c7daf1 and review held.

## Killable registry process — September 15, 2026 20:48 UTC

Implemented workspace_registry_process as a private, single-use subprocess.
It starts with an empty allowlisted environment, isolated Python, disabled
bytecode/core dumps, closed unrelated descriptors and a separate process group.
Only the acquisition jail receives its Unix control channel. The existing
registry classifier/relay remains authoritative. Receipt output is capped at
4096 bytes and strictly validated; failure, cancellation, malformed or uncertain
completion retains the maximum byte reservation. Closing verifies process exit,
including a test-injected blocked DNS thread, and receipt-drain termination.
This component does not itself reserve ledger bytes or supervise the acquisition
jail's aggregate resources. Those remain coordinator obligations.

The manual smoke now uses this process instead of parent-owned broker threads.
Using the Docker command above with --ecosystem node passed:8870bytes,
1connection, offline picocolors1.1.1 API execution. --ecosystem python passed:
1926740bytes,2connections, offline pytest9.1.1. Real public DNS/TLS/downloads,
separate offline jails, no production data or private workflow changes.

Final cohort adds tests/test_workspace_registry_process.py to the seven files
above. Windows python -m pytest -q with those eight paths:614passed,
51POSIXskips,58subtests,23.76s. Same paths through scripts/linux_oracle.py
(WSL command above):665passed,63subtests,zero skips,24.96s. The process tests
cover actual isolated child startup, inherited environment/fd exclusion,
oversized output, nonzero exit, cancellation/deadlines and a deliberately
blocked resolver. The last case is injected, not a claim of real libc DNS
failure. Ruff passed; generated plugin447files and import probe passed.

Tasks2.1-2.3 remain open. Next is acquisition/offline process coordination and
connection-sourced consent, lease/byte reservation and publication integration.
No production caller, push, rollout or new independent review in this checkpoint.

## Acquisition/offline jail supervisor — September 15, 2026 21:03 UTC

Added workspace_provision_process.run_provision_stage. It accepts only the
typed bubblewrap provisioning launcher, requires a started broker for acquisition
and refuses a broker for offline installation. Trusted stage code applies the
existing workspace rlimit helper before running. Parent reuses bounded drains,
the process-tree RSS reader and verified whole-jail termination. Combined jail
plus broker RSS, cumulative output, deadline, cancellation and a required trusted
storage measurement are checked. Measurement failures refuse rather than disable
the guard. Every acquisition result closes/reaps the broker; stage failure keeps
the maximum transfer charge, including a failure found after output drains finish.
RegistryBrokerProcess.finish now accepts a tighter caller deadline so finalizing
a broker cannot wait for its longer independent timeout. Unconfirmed jail or
drain death propagates SandboxTerminationError, not a publishable normal result.

This is still an internal component, not a public command executor or permission
grant. Storage/cancellation callbacks must be bounded server-owned operations;
the caller must supply held-handle measurements, consent, ledger reservation and
lease ownership. The manual smoke's path-based fixture measurement is explicitly
not that production callback. Returned stdout/stderr are bounded internal data,
not public evidence and not safe to emit verbatim from user package logs.

Real tests prove a detached setsid child actually starts (host /proc marker
observed), then is absent after cancellation. Additional coverage: isolated
environment and descriptors, offline network exclusion, actual rlimit values,
failure to apply limits stops code, output floods on both streams, timeout,
storage/RSS bounds and measurement refusal, launch failure, broker revocation,
conservative charge and broker finalization under the stage deadline.

The manual pip/npm smoke now uses the supervisor for BOTH phases. Same Docker
command as above with --ecosystem node exits0:8871bytes,1connection,offline
picocolors1.1.1. --ecosystem python exits0:1926478bytes,2connections,offline
pytest9.1.1. TLS remains verified. No production data, credentials or workflows.

Final nine-file cohort adds tests/test_workspace_provision_process.py to the
eight paths in the preceding checkpoint. Same Windows pytest command:
617passed,80POSIXskips,58subtests,24.90s. Same WSL Linux oracle command:
697passed,63subtests,zero skips,27.06s. Ruff passed; plugin448files/import probe
passed. No source/mirror edits during the Linux snapshot or test execution.

Next integration details reverified at this checkpoint: checkout's insertion
point is after checked staging deletion and before reconcile/publish/register.
Connection access_mode must come from connection_access_mode(resource), never
the packet. workspace_pool.reserve_operation_bytes exists, but its idempotent
operation id returns the existing (possibly downward-reconciled) amount: a new
download attempt must not reuse an old receipt as a fresh maximum reservation.
Resolve that against the caller's existing intent/attempt lifecycle. No bounded
held-dirfd tree-size helper was found in workspace modules; one is needed for
the required storage callback, including failure/entry/time bounds. Ordinary
effect checkout currently has no cancellation callback; connect the existing
run cancellation lifecycle rather than silently supplying False.

Tasks2.1-2.3 remain open. No rollout, independent review, production caller or
claim that browser dependencies/preview now work. Shared repair3860 still gates
landing, and the requested review-model/extra-round decisions remain unanswered.

## Held-handle storage meter — September 15, 2026 21:11 UTC

Implemented workspace_fs.measure_tree_beneath, reusing the existing no-follow
child-directory opener and depth bound. It starts from the held root, reopens
dot relative to that fd for an independent directory offset, streams entries,
never follows symlinks or opens file contents, verifies child inode/device and
closes handles/iterators on every exit. It counts max(apparent,allocated) bytes;
hard links may count twice conservatively. It returns bound+1 when already over,
or a fixed error for incomplete/unknown measurement. Iteration is deadline-bound;
it does not claim to interrupt a blocked kernel filesystem syscall or provide
an atomic snapshot/kernel quota. A final stable scan after writer exit is required.

Tests cover repeat scans/offsets, held-root rename and replacement, directory
link and inode swaps, symlinks to large outside files, broken links/FIFO without
blocking, sparse/hardlinked files, exceeded byte/time/depth bounds, fd cleanup
and private-name-safe errors. Real acquisition and offline jails each write a
file past their storage bound; the real meter observes it and the supervisor
terminates the jail, retaining full broker charge for interrupted acquisition.

The manual smoke now uses held-handle measurements, replacing its path walker.
Found and fixed an important integration premise: npm acquisition extracted
node_modules under /tmp, which was outside the measured cache. Its fixed private
prefix is now /provision/cache/npm-acquire, still without checkout access, so
expanded package bytes count too. This remains test-probe composition, not the
production caller. Other private tmpfs usage and kernel disk quotas remain the
documented best-effort resource-control residual; do not call this a quota.
Real normal npm proof exits0:8872bytes/1connection/offline picocolors1.1.1;
Python exits0:1926764bytes/2connections/offline pytest9.1.1. Commands as above.

Final eleven-file suite is the preceding nine plus tests/test_workspace_fs.py
and tests/test_workspace_tree_usage.py. Windows python -m pytest -q:626passed,
141skips,58subtests,22.48s. Same WSL Linux oracle command with -q -rs:
765passed,2skips,63subtests,28.52s. Both Linux skips explicitly test off-POSIX
refusal (test_workspace_fs.py441 and1020), not unexecuted Linux jail coverage.
Ruff and plugin448files/import probe passed; no edits during oracle copying.

Cancellation source reverified: runs.is_cancel_requested reads run_cancels,
and runs.py3619/5246 passes a root-run closure to compile_branch. The code-node
adapter receives it, but workspace effector dispatch currently does not. Thread
that existing predicate through the effect wrapper/adapter; do not query the
universe's distinct workspace database or invent an always-false callback.
No consent/reservation/caller integration, task closure, rollout or new review.

## Root-run cancellation plumbing — September 15, 2026 21:18 UTC

The existing compile_branch should_cancel closure now flows through the compiled
effect wrapper, dispatch_node_effects, workspace adapter and effector into
_checkout. It remains an internal callable, never a packet/state field. Other
adapter argument contracts are unchanged; legacy callers retain None. The
checkout does not yet start provisioning or consume this callback in a git
worker. Its purpose is to supply the forthcoming installer with the actual
root-run cancellation signal instead of reading the universe's distinct database.

Added one immediate guard: if the owner cancelled while the model/node was
producing its delta, the effect wrapper raises the existing NodeCancelledError
before dispatching any pending effect. It uses the existing cancellation-check
policy; predicate exceptions are logged and retried on later checks rather than
inventing cancellation. The existing run classifier recognizes this exception.

Tests execute a compiled graph and confirm exact callback identity reaches the
workspace adapter; forwarding through the real adapter/effector to checkout is
tested separately with real stored connection/grant/consent checks. A packet's
should_cancel field cannot replace the host callback. Another compiled graph
cancels as the provider returns: no adapter call, fired effect or dispatch charge
occurs, and the exception retains the graph node identity. This is not yet proof
of a live provisioning run stopping after user cancellation.

Final nine-file cohort: tests/test_effects_at_node_time.py,
tests/test_workspace_effector.py, tests/test_cancel_reaches_the_running_child.py,
tests/test_workspace_run_wiring.py, tests/test_graph_compiler_failed_event.py,
tests/test_graph_compiler_reducer_law.py, tests/test_workspace_provision_process.py,
tests/test_workspace_tree_usage.py, tests/test_workspace_registry_process.py.
Windows python -m pytest -q with these paths:289passed,60skips,24.36s (229
dependency deprecation warnings). Same WSL scripts/linux_oracle.py command with
-q -rs:347passed,2off-POSIX-test skips,23.65s,one dependency deprecation warning.
An earlier oracle invocation named nonexistent tests/test_graph_compiler.py and
collected NOTHING; it is not evidence. The corrected command used the existing
compiler regression files above. Ruff and plugin448files/import probe passed.

No source/mirror edits during oracle copying. No new independent review, push,
deployment, public provisioning call or task closure. Next: consent, reservation,
stage composition and truthful publication. Preserve original npm manifest files
when composing offline installation; the diagnostic fixture's canonical rewrite
is not permission to rewrite an arbitrary user's repository. Verified process
death must remain a prerequisite for success/publication through the effector's
existing error/cleanup wrappers, not just inside the isolated stage helper.
