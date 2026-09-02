## Why

The founder's universe asked, in the app on 2026-09-02, whether it can delete
branches. It cannot: `write_graph target=branch` exposes `create/remix/patch/publish`
on the universe surface and `create/patch` on the served build surface, while an
author-gated `delete_branch` has existed for months behind the deprecated
`extensions` tool. Tiny counted 106 branches in its universe, most of them probes
it built while working around platform bugs, and can only "keep a shortlist of
which ones we want gone once delete exists".

The rule this sits under (founder, 2026-08-30/31): inside your universe you are
god; the ONLY platform invariant is not affecting other users.

## What changes

- `write_graph target=branch operation=delete` on BOTH surfaces (universe/app and
  served build), as an operation under the pinned `write_graph` handle — no new
  advertised tool, the same move that made `get_branch` first-class.
- A new guarded handler `delete_own_branch` (the old `delete_branch` stays on the
  deprecated tool, unchanged): author-gated with the not-found envelope; deletes a
  public branch like any other (a public branch is a shape others copy or remix,
  it runs nothing for them — founder, 2026-09-02); refuses a branch
  that anything still depends on — automations bound to it in any universe, goals
  whose canonical binding points at one of its versions, the author's other
  branches that invoke it by id or version — naming every dependent so the owner
  can delete or re-point them first. Internal patch snapshots are not dependents.
- `AutomationStore.list_for_branch`.
- The tool text on both surfaces names the operation and the refusal.

## Impact

- Affected specs: `live-mcp-connector-surface` (ADDED requirement).
- Affected code: `tinyassets/api/branches.py`, `tinyassets/automations.py`,
  `tinyassets/engine_mcp_server.py`, `tinyassets/universe_server.py`, plugin
  mirror.
- Hard delete of the definition row only; runs keep their historical
  `branch_def_id` (benign, no FK), versions keep their snapshots.
- Cross-family review: Codex REJECTED the first cut (dangling automations, an
  impossible public→private→delete remediation because every patch mints a
  version, served tests that never reached the real handler, no change dir) and
  the second (webhooks, schedules, subscriptions, personal canonicals and
  snapshot invocations missing from the dependents; a 500-version cap; a broad
  exception guard; an overstated spec). This is the third cut, built to both.
- The founder's model of a public branch is recorded in `design.md`; the
  runtime's allowance for foreign LIVE invocation of a public branch is contrary
  to it and is filed for its own authority change.
