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

Task2.1 remains open until checkout uses extraction after connection-sourced
consent. Task2.2 still needs the reviewed registry broker/namespace relay,
acquisition-only proxy flags, validated second mount, workspace limits,
pre-wire byte reservation/reconciliation, separate offline install and truthful
publication evidence. Task2.3 needs real jailed pip/npm plus the user's rendered
cloud proof. Browser/system runtime and governed additional artifacts remain in
the overall goal. Parser/reader success is NOT provisioning success.
