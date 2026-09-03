# Tasks: full channel access

Owner: claude-code. One PR. Shape per design.md (per-connection
`access_mode`, Codex design round 1).

- [x] 1. Storage: `outbound_connections.access_mode` (`exact` | `full`),
  migration, `ConnectionResource` / `ConnectionView` field,
  `ledger.set_access_mode(connection_id, mode, expected_mode)` CAS.
- [x] 2. `_validated_action`: accept `access: "full"` on `extend_http` (no
  endpoints/scopes) and `connect_http` (`hosts`, no endpoints); refuse other
  values and mixed shapes.
- [x] 3. Outbound HTTP enforcement: after canonical URL safety and the host
  pin, `full` admits any path, query and verb; `exact` unchanged.
- [x] 4. `has_git_scope`: any repository when `full`; exact otherwise.
- [x] 5. Workspace: `_require_consent` and `_check_provision_consent` satisfied
  for any repository on the connection's git host when `full`; host and
  connection checks stay exact.
- [x] 6. Raise/answer: `_extend_preview` verdicts (full-on-exact extends via
  `set_access_mode`; full-on-full and exact-on-full are `already_held`);
  `connect_http` with `access: full` provisions `full`.
- [x] 7. Inventory and rail: `access: "full"` projection; the D5 sentence in
  `_grant_sentence`; `_granted_lines` never renders a wildcard.
- [x] 8. `remove_http` revokes every consent keyed on the connection (the
  stale-consent defect); test that a re-deposit starts with none.
- [x] 9. Served guidance: the agent asks for full by default; exact only when
  the owner asked for less.
- [x] 10. Tests per design D8, including the three explicit proofs from
  Codex design round 3 (resolved-address refusal on a full connection, the
  workspace call site, scoped consent cleanup). Design rounds are closed at
  three (ADAPT, ADAPT, ADAPT; each folded). Code rounds (<=3); verdicts in
  the PR.
- [ ] 11. Live: the founder's universe raises ONE full ask for its github
  key, the founder accepts once, and the GitHub job runs checkout -> build ->
  push -> PR -> merge with no further ask.
