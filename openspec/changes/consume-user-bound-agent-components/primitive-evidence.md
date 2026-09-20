# Primitive and premise checks — 2026-09-19

Environment: Windows, isolated `codex/governed-experience-consumer-shape`, main
source carried from the release lead's current deployment. This is design
research, not implementation or live acceptance.

Full PLAN was read in docview ranges 1–165, 166–350, 350–578 and 578–EOF.
OpenSpec list/status resolves repository-local paths; audit reports 37 existing
changes, 7 delivery WIP and no exact provider WIP. Founder explicitly requested
bounded coordinated parallel work; release lead moved monitoring to its own
release lane before assigning this proposal. No identity suffix evades WIP.

The primitive checker was run for `run_graph`, `create_binding`, `update_binding`,
`run_branch_version`, `bind`, `update`. It reported CLEAN, but direct source
inspection proves existing routing; this is a checker coverage limitation, not
proof of missing primitives. The proposal adds no duplicate top-level handle.

- `universe_server.py:621–656`: public agents and receiver-scoped bindings reads.
- `universe_server.py:1129–1165`: public Branch creation/remix/publish.
- `universe_server.py:1295–1360`: native agent publish/remix/import and binding
  create/update/provider/serving routing.
- `custom_agents.py:438–470`: reserved identity/provider fields and private
  payload content validation; existing configuration can hold versioned refs.
- `custom_agents.py:1013,1147`: binding creation and expected-revision update.
- `branch_versions.py:234`: immutable published snapshots.
- `api/runs.py:2171` and `runs.py:4950`: immutable-version execution into the
  current graph core. Public `run_graph` currently selects Branch definitions,
  not a dedicated version parameter; do not invent an advertised version action
  when adding an internal current-authority consumer call suffices.
- `api/runs.py:59`: foreground session binding to verified requester and home.
- `universe_intelligence.py:1018–1135`: current serving selection, model policy,
  history, sandboxed writer and default learning; canonical consumer seam.
- `onboarding/serving.py:107`: why arbitrary serving-definition rediscovery is
  unsafe; consumer binding must remain separate from credential serving binding.
- `onboarding/app_layout.js:16,146,291,343`: supported component boundary,
  receiver selection, private CAS application, native remix preservation.
- `agent_runtime_compiler.py:358` / `agent_runtime_plan_compiler.py:412`: existing
  native compiler descriptors, not evidence of an installed app/turn consumer.

Supporting no-change baseline in the sibling inventory worktree on identical
runtime files, September 19, Windows with Node present:

`python -m pytest -q tests/test_app_layout_controller.py tests/test_app_layout_bindings.py tests/test_custom_agents.py tests/test_agent_interchange.py`

68 passed in 7.27 seconds, zero skips, session 65458 exit 0. Not a proof of this
unimplemented adapter. It establishes reuse of the layout/definition/binding
substrate rather than a reason to replace it.

Read-only PR metadata for #3840 and #3842 says draft, inert project editing or
fixture preview, no authenticated-app module consumption and no whole-setup
replacement proof. No code from those private design lanes was edited or run.

Existing spec caveat: `universe-personification-and-relay/spec.md:46–76` still
describes Codex as unsupported and an old WebFetch-only tool policy, while the
current source and shipped uniform-engine work support more. This proposal's
added consumer requirement does not authorize restoring those old restrictions
or silently altering current authority. Lead should reconcile that stale
as-built text with already-deployed evidence in its own spec-sync work; it is
not an excuse for expanding this adapter proposal into an engine rewrite.
