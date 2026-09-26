## Tasks

- [x] 1. Record the BEFORE baseline as a test fixture: the engine
  `write_graph.__doc__` digest and length, and the total description chars across
  `SERVED_ENGINE_MCP_TOOLS`, so byte-preservation and the saving are both provable
  against a pinned number rather than a remembered one.
- [x] 2. Split the engine `write_graph` docstring in place: `connections`,
  `code_nodes` and `workspaces` move verbatim into module-level chapter constants;
  the resident description keeps purpose, the `operation` catalogue, the FILE
  INPUTS exact shape, the delivery / custody / webhook / recurring-work
  one-liners, the no-effect parity note and `Args:`.
- [x] 3. Add the resident chapter index to the description: each chapter name, one
  line on when to fetch it, and the exact `read_graph` call that returns it.
- [x] 4. Add `served_tool_guidance(handle)` returning resident description +
  every chapter in documented order, and assert it is byte-equal to task 1's
  baseline.
- [x] 5. Add `target="handbook"` to the engine `read_graph`: no query returns the
  index, `query="<handle>.<chapter>"` returns one chapter verbatim, an unknown
  name is refused naming what is available, and nothing about it can write.
- [x] 6. Test the handbook contract: index completeness, verbatim chapter, refusal
  on an unknown name, read-only, and that the partition holds (every chapter
  reachable, every chapter named in the index, no chapter text also resident).
- [x] 7. Re-point the 12 `engine.write_graph.__doc__` assertion sites across the 8
  test modules one at a time — resident guidance keeps reading `__doc__`, moved
  guidance reads `served_tool_guidance` — and record which choice each site got.
- [x] 8. Test that the public connector's `write_graph` description is unchanged
  and uncoupled from the engine's, so chatbot clients cannot be affected.
- [x] 9. Test that the resident block and chapter index do not vary by account,
  universe, source or provider.
- [x] 10. Measure AFTER: per-handle definition bytes and the total block, and put
  the before/after table in the PR body.
- [x] 11. Lower the ratchet in `tests/test_converse_turn_cost.py` from 58,000 to
  the measured new total, with the latency rationale in the message.
- [x] 12. Sync the delta specs into `openspec/specs/` and archive the change in
  this same lane.
