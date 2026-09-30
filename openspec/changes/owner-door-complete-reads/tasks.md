# Tasks: owner-door-complete-reads

Owner: claude-code. One branch (`claude/owner-door-complete-reads`), one PR.
Supersedes PR #4151.

- [x] 1. PLAN.md: the principle paragraph (owner surfaces are complete; bounding
  is a model-door projection; the only per-account input is account type).
- [x] 2. `tinyassets/api/graph_reads.py`: move the `read_graph` dispatch out of
  `universe_server`; the connector delegates and keeps its signature/docstring.
- [x] 3. Connector projections: `model_options` -> `compact_model_options`
  (synonym `model_options_summary`); drop `model_options` from
  `_connector_ceiling_exempt`, re-justify the remaining three entries.
- [x] 4. Complete domain reads: `list_pending` (no limit, raises on failure),
  `list_requests` (no limit), `withdraw_request.still_on_rail`,
  `llm_deposit` binding lookup, `list_bindings(limit=None)`.
- [x] 5. History cursor: `load_recent_readonly(before=)`, `get_status`
  `conversation_before` / `conversation_limit` with `has_more` / `next_before`.
- [x] 6. `tinyassets/owner_door/`: `POST /app/api/read`, `POST /app/api/status`,
  mounted from `onboarding_routes`; argument validation (4xx); the domain's
  own document returned unchanged; a server failure is a 500, never empty.
- [x] 7. `AccountType` in `usage_policy`; `universe_owner.account_type_of` /
  `account_type_for_universe`; route every `get_tier` reader through it; delete
  `TierLimits.is_paid`.
- [x] 8. App: an `Owner` client; move every `read_graph` / `get_status` read in
  `app.html`, `app_layout.js`, `app_ui.js` to it; the rail stays visible and
  says it couldn't load; "Show earlier messages" on `has_more`.
- [x] 9. Tests: heavy account (40 requests, >60 KB) complete through the owner
  door; non-owner refused; free vs subscription identical apart from tier numbers;
  import-boundary test (owner door, domain, model-door-only importers of the
  ceiling, single `get_tier` reader); app files never read over MCP; loud rail.
- [x] 10. Update existing tests that stub `MCP.*` reads or patch
  `universe_server._*_impl` for reads; mutation-check the boundary and the rail.
- [x] 11. Regenerate the plugin mirror and the brand receipt; cross-family
  refutation (gpt-6-astra, ≤3 rounds).
- [x] 12. Sync the spec deltas into `openspec/specs/` and archive the change on land.
