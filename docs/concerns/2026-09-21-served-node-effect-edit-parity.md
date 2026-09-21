# Served creation and editing differ for effect declarations

Observed September21 2026UTC on5394efd, ordinary primary-app five-control test.
App20:56PDT says existing node effects cannot be edited, so it builds a new
branch. This is separate from the accepted original five controls/model edit.

Source verification on5394efd: engine_mcp_server._SERVED_PATCH_UPDATE_NODE_ALLOWED
permits prompt_template/source_code/display_name/llm_policy only; create/add_node
sanitize effect declarations. Canonical api.branches._apply_node_updates already
accepts effects and workspace. This is a served create/edit asymmetry, not proof
the canonical primitive is absent. The served guard documents a real prior
approval-hash reactivation safety issue; do NOT simply add effects to its
allowlist or widen provider/receiver authority to make a test pass.

Queued scope: determine how owners can safely change existing effect/workspace
declarations using the same validation, approval invalidation and execution-time
authority as creation. Check already available structural editing routes first.
If a platform change is needed, public-surface/authority shape review precedes
implementation. No new operation or private workflow change is authorized by
the app's report itself. Acceptance: app agent changes its own existing workflow
without rebuilding it, under unchanged credentials and receiver consent; invalid
or foreign edits refuse atomically. General resource-policy queue remains open.
