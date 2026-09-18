# Cloud dependency execution candidate

September18,2026 UTC. Isolated branch codex/cloud-runtime-mvp-20260918 combines
the previously local installer ed7ddf17, current main64e29743 and sandbox
prerequisite75c7daf1 without merge conflicts. No deployment or browser acceptance
is claimed. The original worktrees and user projects remain untouched.

## Fresh evidence

Windows/Python3.14: `python -m pytest -q` over test_workspace_provision_execution,
test_workspace_provision_process, test_workspace_registry,
test_workspace_registry_process, test_workspace_registry_proxy,
test_workspace_resolver, test_workspace_effector, test_workspace_tree_usage,
test_workspace_provision_mount, test_sandbox_mount_handles,
test_node_sandbox_workspace, test_workspace_manifest_reads and
test_effects_at_node_time:463 passed,122 platform skips,58 subtests passed29.74s.

Native WSL Docker, Python3.11.16/git2.47.3/bubblewrap0.12.0:
`python3 scripts/linux_oracle.py -- -q` with the same13 test-file paths:
583 passed,2 Windows-only skips,70 subtests passed35.36s on05549379.
This stable-tree rerun had no copy warning. An earlier combined run exposed
an invalid test assertion: unrelated descriptors collected during the test made
the process-wide count fall49 to24. Tests now compare descriptor identities
and reject new leaked handles while permitting unrelated handles to close.
No runtime resource guard was weakened.

The real composed smoke command was:
`wsl -d Ubuntu -- docker run --rm --memory=2g --pids-limit=1024 --security-opt seccomp=unconfined -v /mnt/c/Users/Jonathan/.codex/worktrees/cloud-runtime-mvp-20260918/TinyAssets:/src:ro --workdir /src -e PYTHONDONTWRITEBYTECODE=1 tinyassets-linux-oracle:7693b1a8f805 python scripts/probes/workspace_provision_smoke.py`.
Result: both ecosystems installed and executed, pytest9.1.1 and picocolors1.1.1;
1,935,373 broker bytes charged; original manifests preserved; root script not run.
The container limit is diagnostic containment, not a production workspace cgroup.

Focused changed-module Ruff and `git diff --check` pass.
`python packaging/claude-plugin/build_plugin.py` stages450 files and import-probe
passes with a clean tree. Fresh unchanged sandbox75c7daf1 independently passed
229 Windows tests/18 skips and247 Linux tests/no skips using its three-file cohort.

## Review map and release boundary

- Consent, all-manifest admission, fresh maximum reservation and publication:
  tinyassets/effectors/workspace.py.
- Held-descriptor, bounded manifest/storage reads: workspace_fs.py and
  workspace_resolver.py.
- Credential-free, address-pinned CONNECT broker and killable lifecycle:
  workspace_registry.py, workspace_registry_proxy.py, workspace_registry_process.py.
- Two supervised stages, revocation before offline code and preserved manifests:
  workspace_provision_execution.py and workspace_provision_process.py.
- Mount descriptors and namespace boundaries: node_sandbox.py.
- Root-run cancellation propagation: graph_compiler.py, engine_mcp_server.py and
  effectors/__init__.py.

Existing Fable execution-shape assessment is retained in
2026-09-15-provisioning-execution-shape-fable.md. Exact-head basic-safety review,
required hosted checks, deployed revision/canary and ordinary rendered app use
remain release gates. Parent coordinates review and deployment.

No runtime memory cap is relaxed. Browser executable/library provision,
attributable memory containment, actual desktop/phone captures and a usable
preview remain open. This candidate does not complete private PR3840/3842 or
the user's background-self work. Resource warnings and scheduled activity/revert
monitor defects remain separate; no old worker fleet was restarted.
