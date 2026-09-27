# Tasks: a bounded model-facing catalogue read

Owner: claude-code. One branch, one PR. Depends on PR #4037 (the engine-side
ceiling and `tinyassets/engine_read_views.py`), which is the module this reuses
rather than reimplements.

- [ ] 1. Promote the projection: `engine_read_views.compact_model_options` becomes
  the shared implementation both surfaces call. No behaviour change, and
  `model_options_document()` / `read_model_options` stay untouched.
- [ ] 2. `universe_server.read_graph`: accept `target="model_options_summary"`,
  routed through the same owner/admin/current-home gate as `model_options`,
  passing `query` and `output_offset`. Add it to the target enumeration and the
  `_unknown_target` list.
- [ ] 3. Bound `structured_content` in `_structured_return`, reusing
  `engine_result_bounds.bound_tool_text` for the marker, with `model_options` as
  the single named exemption. The exempt set is a module constant, not a literal
  at the call site.
- [ ] 4. Update `read_graph`'s docstring: `model_options` is the complete
  catalogue and is very large; a caller reading into a model's context uses
  `model_options_summary`.
- [ ] 5. Tests: the summary read through `mcp.call_tool` (not the handler) —
  bounded reply, per-source counts, paging that covers every row exactly once,
  a filter that reports a true total, a borrowed row staying distinguishable,
  and a foreign-scope refusal that is not reshaped into data.
- [ ] 6. Tests: `structured_content` over the ceiling gets the marker;
  `model_options` does **not** (the exemption), proved by asserting the complete
  document still arrives; a reply within the ceiling is byte-identical.
- [ ] 7. Mutation-check the exemption: removing `model_options` from the exempt
  set must turn `test_full_catalogue_survives_read_limit_and_adapter` red. If it
  does not, the exemption is not what is keeping the picker working and the
  design is wrong.
- [ ] 8. Confirm the picker is untouched: `tests/test_app_model_picker.py` green
  with no edit to `tinyassets/onboarding/app.html`.
- [ ] 9. `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp
  --assert-handles` after deploy (Hard Rule 11). The canonical handle set is
  unchanged — this adds a `target`, not a handle — so `--assert-handles` must
  still pass with the existing set.
- [ ] 10. Sync the delta into `openspec/specs/live-mcp-connector-surface/spec.md`
  and archive this change in the same lane (a landed change with unsynced deltas
  is spec drift).
- [ ] 11. Delete
  `docs/concerns/2026-09-26-public-connector-structured-content-is-unbounded.md`
  and its README row — resolving a concern is deleting its file.
- [ ] 12. Live proof: a rendered conversation through the connector where a model
  reads its own model options and picks one without the turn dying. Scripts are
  supporting evidence, never the proof.
