# Required Linux oracle restored through native Ubuntu Docker

September9,2026,23:22 UTC. Local host, not production. Selected runtime9e19a7b8
(documentation headf1910f78) plus the test-harness corrections described here.

Windows Docker Desktop startup failed at its inaccessible dockerInference
runtime socket. No Docker files, sockets, images, containers or settings were
deleted/reset to repair it. A non-overwriting quarantine of that exact socket
failed without moving it. Native Docker was already installed inside Ubuntu WSL:
`docker info --format '{{.ServerVersion}} {{.OSType}}'` reported29.1.3 linux.
Using that existing engine avoids the Desktop failure; Desktop remains unrepaired.

The feature worktree's .git pointer contains a Windows absolute admin path, so
the WSL invocation sets process-local paths; no git config or pointer file edits:

```
export GIT_DIR=/mnt/c/Users/Jonathan/Projects/TinyAssets/.git/worktrees/TinyAssets6
export GIT_WORK_TREE=/mnt/c/Users/Jonathan/.codex/worktrees/select-agent-models/TinyAssets
python3 scripts/linux_oracle.py -- -q <test files below> --tb=short -rs
```

Run from that feature cwd with `wsl -d Ubuntu --cd <feature-mounted-path> bash -lc`.
The first attempt printed exact9e19a7b8 but exposed two existing bootstrap bugs:

- Classic Docker builder silently ignored the Dockerfile's heredoc Python body.
  Image174cfad42dfd had a zero-byte requirements file and no pytest (verified via
  a throwaway `docker run --rm` with wc/python). The correction uses one normal
  Python command, requires nonempty requirements and verifies pytest in the image.
- Restoring the host's uid/gid onto /work made Git setup fail with “not in a git
  directory.” Copy now uses tar --no-same-owner, retaining container ownership,
  not a blanket safe.directory trust exception. .git is still excluded and the
  test copy gets its own fresh repository; host git state is untouched.

Corrected imagece0e83fb15a8 built successfully. Actual oracle49744 terminated
exit0: Python3.11.16, Git2.47.3, bubblewrap0.12.0, **454passed/1skipped in19.19s**.
The sole skip is the optional real-Codex credential fixture; POSIX/shared-reader
and bubblewrap cases run. This is the required container oracle, not the earlier
supplemental Ubuntu venv. No credentials were supplied to the container.

Files in the command:
tests/test_selected_model_authority.py tests/test_config.py
tests/test_open_serving_bind.py tests/test_provider_serving_binding.py
tests/test_provider_served_router.py tests/test_served_authority_shared_chain.py
tests/test_served_launch_accounting.py tests/test_serving_manifest_publication.py
tests/test_provider_assignment_manifest.py tests/test_model_discovery_capability.py
tests/test_discovery_snapshot.py tests/test_discovery_http.py
tests/test_catalog_decoders.py tests/test_model_policy.py
tests/test_api_key_http_provider.py tests/test_mirror_parity_gate.py.

Two bootstrap regression cases execute the actual Dockerfile Python payload and
check ownership/.git handling. Windows: `python -m pytest -q
tests/test_linux_oracle.py --tb=short` ->2passed in0.25s (0.23s after making the
test's fixture path quote-safe). Actual oracle70821 ->2passed in0.11s, no skips.
Ruff and diff checks pass. These small test-runner
changes are not independently reviewed yet; the selected async runtime already
has its separate exact-runtime approval. No public deployment or feature
completion claim follows from a green test environment.
