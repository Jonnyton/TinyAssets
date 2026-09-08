# App cannot manage the automation attached to its heartbeat

**Filed:** 2026-09-08
**Verified:** Rendered production conversation read on 2026-09-08, messages through 01:10 PDT; this verifies the reported blocker, not the scheduler's underlying state.

## Source (verbatim)

Universe, 2026-09-08 01:09 PDT:

> I have your approval, but I’m still blocked: my request recorded your answer without granting automation controls.

> I verified automation `d25a356811d0405c8bc92ebc9601c68f` still prevents deleting my heartbeat. I need that automation removed or a management tool exposed. I haven’t confirmed its trigger is stopped, and I won’t ask you to approve the same removal again.

Universe, 01:10 PDT:

> I can delete branches. When I tried deleting my remaining heartbeat branch, the system refused because automation `d25a356811d0405c8bc92ebc9601c68f` is attached to it.

## Evidence and boundary

Read via `cua.getTab("1346517271", {browser:"2"})` at
`https://tinyassets.io/mcp/app`, in the existing owner conversation. The owner
asked that unused heartbeats be deleted at 01:07 PDT and approved removal of
the blocking automation at 01:09 PDT. The app reports deleting two older
heartbeat workers and its subconscious loop, but not its remaining heartbeat.

The app cannot establish whether the remaining trigger is stopped. Do not
interpret this as proof that it is enabled or firing. The missing capability
may be routing, discovery, or authority integration; root cause is not yet
verified. Inspect existing primitives before proposing a new one.

## Code re-verification, 2026-09-08

`rg -n 'automations|automation' tinyassets/engine_mcp_server.py
tinyassets/universe_server.py tinyassets/api/automations.py` confirms that the
canonical connector already routes `write_graph target=automation` to owner
controls (`create`, `pause`, `resume`, `delete`) and reads automation records.
The served engine wrapper instead rejects the automation target and its read
target description excludes automations. This is a surface-parity gap, not
absence of a scheduler primitive. The action-check script returned CLEAN for
`automations`, but that lexical result does not override this direct routing
evidence. A repair must preserve the existing owner/admin and revision checks;
it requires a reviewed public-surface/authority change before implementation.

The repair must give users reusable, owner-scoped automation controls, not
delete this private automation through an operator bypass or recreate deleted
workflows. During this inspection Codex sent no message and changed no live
workflow, automation, credential, or destination.

## Platform repair deployed, acceptance pending — 2026-09-08 19:59 UTC

PR #3447 deployed as `4a1877f0044a` via build 34271720339 and deploy 34271996544;
authenticated public canary and protected revision containment passed. The
served wrapper now exposes existing owner-scoped list/get/create/pause/resume/
delete controls, preserving ACL and revisions. This supersedes the code-level
missing-route finding above, not the unverified private trigger state.

At 20:19 UTC the owner-authorized new-tab route opened the same saved app
conversation, resolving the previous tab-ownership blocker. Sent exactly
`Retest your workflow checklist`. Its 13:20 PDT response confirms deploy
`4a1877f0044a` and says the automation is paused, its last scheduled run failed,
and future triggers are paused. It remains attached. The previous unknown
stopped-state finding is resolved by rendered readback; do not claim this turn
performed a pause, retirement, or cancellation. Live lifecycle mutations remain
unexercised (reviewed real-adapter tests cover the deployed route). Retain this
qualified follow-up until those controls are independently exercised; do not
replay the earlier approval or edit the private row ourselves.
