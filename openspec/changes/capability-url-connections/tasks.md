# Tasks: capability-URL connections

Owner: claude-code. One PR, one branch (`claude/capability-url-auth`).
Shape per design.md.

- [ ] 1. Storage grammar: `_URL_SECRET_SCHEME`, the reserved `{secret}` /
  `{secret+}` placeholder in `_validate_param_patterns` (injected escaped
  pattern, caller-declared pattern refused), `_URL_SECRET_SEGMENT_RE` /
  `_URL_SECRET_TAIL_RE`, and `url_secret` in `_SUPPORTED_HTTP_AUTH_SCHEMES`.
- [ ] 2. Binding (D6): `_validate_url_secret_binding(scheme, endpoints)` called
  from `create_connection`, and the `access: full` refusal.
- [ ] 3. Bundle + header: `_build_http_secret_bundle` returns the segment as
  `token` for `url_secret`; `_ssrf_auth_headers` emits **no** header for it.
- [ ] 4. Driver: substitute the vault segment into `canonical.path_qs` **after**
  `_enforce_endpoint_allowlist`, re-validating the segment grammar first;
  refuse a placeholder-carrying URL under any other scheme.
- [ ] 5. Dispatch fail-closed: `_dispatch_http` re-checks the binding on the
  current row before a bundle is built.
- [ ] 6. Deposit door: `url_secret` in `_DEPOSITABLE_AUTH_SCHEMES`
  (`api/http_connection.py`), `_secret_shape_error`, and
  `_extract_url_secret(secret, endpoints)` — the pasted-link parser (D4).
- [ ] 7. `looks_like_embedded_secret` + the refusal at the three authoring
  doors: `_validated_endpoint_list` (ask), `connect_http`, `extend_http` (D5).
- [ ] 8. Ask surface: `url_secret` in `pending_requests`/`connection_inference`
  scheme sets, the fixed `capability_url` field name, and the grant sentence.
- [ ] 9. Guidance: one short Slack/Discord-style webhook example in the
  `write_graph.connections` chapter.
- [ ] 10. Tests per D8 (`tests/test_capability_url_connections.py`), with the
  mutation check on the substitution and on each binding refusal.
- [ ] 11. `python packaging/claude-plugin/build_plugin.py` (mirror parity).
- [ ] 12. One `gpt-6-astra` refute round; live proof on the founder's own hook;
  `deployed_sha.py --assert-contains`; sync + archive this change.
