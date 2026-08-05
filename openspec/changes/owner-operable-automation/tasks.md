## 1. Decide and build the owner repair path

- [ ] 1.1 Choose between the three shapes in `design.md` (Trigger primitive /
      owner-fired slice / documented `run_graph` route) and record the decision
      with its accounting answer: does an owner-fired run consume provider
      invocations and the destination action cap, and does it emit a terminal
      receipt? Do NOT re-propose a bare `run_once` verb — it was rejected
      2026-08-05 as redundant with `run_graph`.
- [ ] 1.2 Test-first, implement the chosen shape owner-scoped and
      revision-fenced, refusing non-owners non-oracularly.

## 2. Stop the surface asserting things about itself that are untrue

- [ ] 2.1 Test-first, bind the set of values `next_action` can emit to the set of
      operations the handler accepts, so drift fails the build. Regression case:
      health emitted `run_once` with no such operation and an assistant reported
      a queued job to the owner.
- [ ] 2.2 Test-first, make `resume` on an already-active automation return a
      typed "nothing changed" rather than an unqualified success.

## 3. Substrate primitives

- [ ] 3.1 Expose Trigger through canonical handles (create/inspect/fire/cancel)
      bound to a published Branch version.
- [ ] 3.2 Make `effects` patchable on an existing node, preserving that node's
      edges; or document the supported route at the point of use.
- [ ] 3.3 State the remix/rebind lineage constraint where an owner would hit it.
- [ ] 3.4 Enforce node `timeout_seconds`, or reject the field at authoring time.

## 4. Acceptance

- [ ] 4.1 Prove each item through a rendered chatbot conversation on the live
      connector, typed as a user — the same route that found every one of them.
      Direct MCP calls are supporting evidence only.
