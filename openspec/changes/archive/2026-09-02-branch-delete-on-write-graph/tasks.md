# Tasks — branch-delete-on-write-graph

- [x] 1 `AutomationStore.list_for_branch(branch_def_id)` — every non-retired
      automation in any universe bound to the branch.
- [x] 2 `webhook_hooks.list_active_for_branch`, `scheduler.list_bound_to_branch`,
      `branch_versions.list_version_ids` (uncapped) and
      `branch_versions.versions_invoking` (published snapshots that invoke a
      branch by id or version).
- [x] 3 `api/branches.py` `_branch_dependents` + `_ext_branch_delete_own`:
      author gate (not-found envelope), dependents refusal naming
      automations / webhooks / schedules / subscriptions / goals (default,
      personal and legacy canonical stores) / invoking branches (current
      definitions and published snapshots; structured child-ref fields only),
      then `delete_branch_definition`. Registered as `delete_own_branch`. The
      legacy column is probed with PRAGMA, never guessed through an exception.
- [x] 4 `universe_server.py` and `engine_mcp_server.py`: `operation=delete` routed
      to `delete_own_branch`; `_WRITE_GRAPH_OPS`, error text and tool docstrings
      name it and the refusal.
- [x] 5 Tests (`tests/test_branch_delete_is_first_class.py`): own private deletes
      and is gone from the listing; patched branch still deletes; public deletes
      like any other; each dependent kind named and
      nothing deleted (automation, retired automation does not hold, webhook then
      revoke, schedule + subscription then unregister, default and personal
      canonical, current-definition invoker, snapshot invoker with the parent's
      definition gone, free-text mention is not a dependent, version ids uncapped
      past 500); non-author gets not-found even on a public branch; served
      surface exercised with the REAL handler under the bound identity, and a
      served test that reaches the guarded handler, not the raw one.
- [x] 6 Mutation-checked (see commit): author gate, public, each dependent kind,
      free-text mention, both surfaces routed to the unguarded handler.
- [x] 7 Founder's decision applied (2026-09-02): a public branch is a shape for
      copy/remix and runs nothing for others; no public refusal. Filed: foreign
      LIVE invocation of a public branch is contrary to the model (own change).
- [x] 8 Cross-family review: three rounds (the cap). Round 3 found the soul loop
      branch reader and the missing author filter on snapshot invokers; both applied
      without a fourth round, reported to the founder.
- [x] 9 Landed as #2763 (deployed 2026-09-02, production 5740994f); delta synced into
      `openspec/specs/live-mcp-connector-surface/spec.md`; archived.
- [ ] 10 Live proof: tiny deletes one of its probe branches from the app and it is
      gone from `read_graph target=branches`.
