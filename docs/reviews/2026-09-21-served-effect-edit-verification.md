# Served effect editing verification

Date: 2026-09-21 UTC. Environment: Windows isolated
wf-served-effect-edit-parity, base7fdf6a70, root project venv Python.

Opus builder92912 timed out600s and its process tree was terminated. No final
author test claim is adopted. Its source/tests/mirror edits remain; root reviewed
them and independently ran the two affected files:35passed/zero skips.
Root then completed null-clearing parity (canonical create/update both accept
null), added that persisted-row case, and corrected the touched stale approval
comment. No runtime authority or schema changed. Exact-head Claude review pending.

`python -m pytest -q tests/test_served_effect_edit_parity.py tests/test_engine_mcp_write_graph_patch.py tests/test_engine_mcp_server.py tests/test_served_workspace_node_authoring.py tests/test_served_workspace_build_surface.py tests/test_served_workspace_consent_not_self_grantable.py tests/test_engine_mcp_source_channel.py tests/test_authenticated_external_call_effector.py tests/test_workspace_end_to_end.py`

Result:191passed,14skipped in21.58s. Skips require Linux coverage; not green
cross-platform proof. Initial `python scripts/linux_oracle.py -- <same test set>`
could not connect to Docker's Linux engine; root starts it via Docker Desktop CLI.
Linux result, required CI, deployment and ordinary app acceptance still owed.

Ruff checked engine_mcp_server and both changed tests: passed. Plugin runtime
build:496files/import probe passed. Pre-build strict OpenSpec validation passed.

Acceptance remains: the app agent edits its own existing workflow's declarations
and uses the result without replacing the branch. Operators do not edit it.
