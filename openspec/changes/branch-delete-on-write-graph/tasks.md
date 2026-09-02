# Tasks — branch-delete-on-write-graph

- [x] 1 `AutomationStore.list_for_branch(branch_def_id)` — every non-retired
      automation in any universe bound to the branch.
- [x] 2 `api/branches.py` `_branch_dependents` + `_ext_branch_delete_own`:
      author gate (not-found envelope), public refusal, dependents refusal naming
      automations / goals (canonical bindings on any version, legacy column too) /
      the author's own invoking branches (structured child-ref fields only), then
      `delete_branch_definition`. Registered as `delete_own_branch`.
- [x] 3 `universe_server.py` and `engine_mcp_server.py`: `operation=delete` routed
      to `delete_own_branch`; `_WRITE_GRAPH_OPS`, error text and tool docstrings
      name it.
- [x] 4 Tests (`tests/test_branch_delete_is_first_class.py`): own private deletes
      and is gone from the listing; patched branch still deletes; public refused
      then deletable after set_visibility private; automation / goal / child
      invocation dependents named and nothing deleted; non-author gets not-found
      even on a public branch; served surface exercised with the REAL handler
      under the bound identity, not a stub.
- [x] 5 Mutation-checked: no author gate, public deletes, dependents ignored (each
      kind), served/universe routed to the unguarded handler.
- [ ] 6 Cross-family review round 2 (Codex) before push; land; sync this delta into
      `openspec/specs/live-mcp-connector-surface/spec.md`; archive.
- [ ] 7 Live proof: tiny deletes one of its probe branches from the app and it is
      gone from `read_graph target=branches`.
