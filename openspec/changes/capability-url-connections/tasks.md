# Tasks: capability-URL connections

Owner: claude-code. One PR (#4115), one branch (`claude/capability-url-auth`).
Shape per design.md.

- [x] 1. Storage grammar: `_URL_SECRET_SCHEME`, the reserved `{secret}` /
  `{secret+}` placeholder in `_validate_param_patterns` (injected escaped
  pattern, caller-declared pattern refused), `_URL_SECRET_SEGMENT_RE`, and
  `url_secret` in `_SUPPORTED_HTTP_AUTH_SCHEMES`. `as_dict()` omits the derived
  pattern so a stored endpoint round-trips.
- [x] 2. Binding (D6): `validate_url_secret_binding(scheme, endpoints,
  access_mode=)` from `create_connection`, the deposit door, dispatch, and as
  SQL predicates on `extend_http_connection_endpoints` / `set_access_mode`.
- [x] 3. Bundle + header: the segment (and each segment long enough to be one)
  in the bundle; `_ssrf_auth_headers` emits **no** header.
- [x] 4. Driver: `_substitute_url_secret` after `_enforce_endpoint_allowlist`,
  positioned by the MATCHED endpoint's template (astra round 1 F3), with
  `_reject_stray_reserved_tokens` over path and query, raw and decoded
  (astra round 2 F2).
- [x] 5. Dispatch fail-closed: `_dispatch_http` re-checks scheme AND access mode
  on the current row before a bundle is built.
- [x] 6. Deposit door: `url_secret` in `_DEPOSITABLE_AUTH_SCHEMES`,
  `extract_url_secret` (the pasted-link parser, D4), and the same extraction on
  `rotate_http`.
- [x] 7. `looks_like_embedded_secret` + `embedded_secret_refusal` at the three
  authoring doors: the ask, `connect_http`, `extend_http` (D5).
- [x] 8. Ask surface: the scheme sets, the fixed `capability_url` field name,
  the `full` refusal, and the grant sentence that says where the code goes.
- [x] 9. Guidance: the webhook example in the `write_graph.connections`
  chapter, plus two tests that the chapter's OWN example validates and
  deposits.
- [x] 10. Tests: `tests/test_capability_url_connections.py`, 117 cases, with
  mutation checks named in the docstrings of the substitution, the positioning,
  the stray-token invariant and the segment-echo cases.
- [x] 11. `python packaging/claude-plugin/build_plugin.py` (mirror parity green
  on every commit).
- [ ] 12. Land, then, in order: `python scripts/deployed_sha.py
  --assert-contains <sha>`; run
  `scripts/probes/capability_url_live_proof.py --universe <founder uid>` inside
  the daemon container (the invocation is deliberately not written out — see
  the probe's own docstring and `drop-first-exec`); then sync + archive this
  change.

  The probe is committed, self-cleaning, and refuses to run without an explicit
  `--universe` the named principal administers. Rehearsed 2026-09-30 against a
  throwaway data dir (`PROOF_BASE=...`): 10 of its 12 checks pass there, and
  the two that do not are exactly the two that need the token to exist in
  **production's** hook DB — check 6 (the receiver's 202) and check 11 (the run
  it enqueued).

## Review

Two `gpt-6-astra` rounds, both folded; verdicts and dispositions in design.md
§D9. Stopped at two per `AGENTS.md` (a third reviews repairs to repairs).

## Filed, not fixed — both pre-existing and scheme-independent

- `docs/concerns/2026-09-29-redeposit-race-sends-new-secret-to-old-endpoint.md`
  (P2) — astra reproduced it with `bearer` on the pre-feature commit
  `7743112e`, which is why it is not in this PR.
- `docs/concerns/2026-09-30-no-user-agent-blocks-cdn-fronted-webhooks.md`
  (P1) — found by the live-proof rehearsal: the driver sends no `User-Agent`,
  so Cloudflare answers `error code: 1010` before any CDN-fronted receiver sees
  the request. Affects every scheme, on a shared hot path.
