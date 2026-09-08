# Request rail refresh erases an owner's in-progress reply

Verified 2026-09-08 20:39 UTC in the rendered returning-user app conversation,
deploy last reported by the app as `4a1877f0044a`. A reply typed into the open
webhook repair request was visibly present; clicking Send reply returned
"Type something to send." and the draft was gone. Refilling and immediately
sending succeeded once and queued the exact owner-style scope question. No
permission was accepted, denied, cleared or muted.

Source recheck (`rg` and `scripts/docview.py lines`) of
`tinyassets/onboarding/app.html`: `refreshRail` runs every 15 seconds and always
calls `renderRail`; that renderer clears the whole host and reconstructs all
field controls. Thus any refresh loses live field values, feedback and checkbox
state even if the requests did not change. This affects user answers and secret
entry as well as this observed nonsecret reply. The source supports the refresh
mechanism; no browser trace captured the exact timer tick for this incident.

Repair should preserve unchanged request controls and focus across polling and
unrelated list changes, but discard drafts when the corresponding request's
meaning changes or it is removed. Keep secret values only in their existing DOM
controls; no persistence, logging, rehydration cache or stale grant acceptance.
Use the current request when deciding, not a stale retained authority snapshot.
Add executable rendering regressions and independent cross-family review before
landing. This is a generic app interaction bug, not a private workflow repair.

Independent review completed: [Claude shape review](../reviews/2026-09-08-request-rail-refresh-shape-claude.md),
ADAPT with no pre-build blocker. The server has no request revision today;
immutable content, session clearing and stale-response protection are required.
No runtime fix has been implemented yet. Existing Windows request-panel baseline
tests passed 40 tests; those tests do not cover refresh draft preservation.
