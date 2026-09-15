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
