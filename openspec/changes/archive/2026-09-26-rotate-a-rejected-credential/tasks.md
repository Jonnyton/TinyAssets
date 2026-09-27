# Tasks: rotate a rejected credential

Owner: claude-code (credential-rotate lane). One branch, one PR. Shape per
design.md.

- [x] 1. `runs.py`: `credential_rejected` — the delivered-status matcher, the
  per-row 403 body test (compact + copular rules), insertion into
  `_classify_external_write` between the refusal KINDS and the refusal WORDS.
- [x] 2. `runs.py`: `ACTIONABLE_BY["credential_rejected"] = "user"` and
  `CREDENTIAL_REJECTED_ACTION` returned by `external_write_suggested_action`.
- [x] 3. `authenticated_external_call.py` + `_collect_external_write_errors`:
  a delivered result and its error row carry the connection's `destination`, so
  the card names the right one.
- [x] 4. `credential_vault.py`: `http_credential_record()` — the one builder,
  stamping `deposited_at`; the deposit and both oauth2 refresh writers use it.
  Plus `http_deposit_refusal()`, the read-only predicate the preview shares with
  the writer.
- [x] 5. `http_connection.py`: `rotate_http` / `_rotate_http` under the gesture
  lock — vault-only write, every refusal before it, redacted projection; and
  `preview_rotate_http`, which applies the same refusals with no write.
- [x] 6. `pending_requests.py`: the `rotate_http` action type, `_rotate_ask_verdict`
  (scheme + incarnation capture, refusals at raise time), `_SECRET_FIELD_TYPES`,
  the card sentence, `_assembled_secret` shared with the deposit, and the answer
  branch that calls `rotate_http` and reports an unsettled card honestly.
- [x] 7. Served guidance: the rotation paragraph in
  `_WRITE_GRAPH_CONNECTIONS_CHAPTER` points at `rotate_http` and says why
  remove+connect is not the repair path.
- [x] 8. Tests: 50 in `tests/test_replacing_a_rejected_credential.py`, including a
  real 401 through the real broker and vault resolver. Each behaviour
  mutation-checked (19 rounds across both passes).
- [x] 9. `python packaging/claude-plugin/build_plugin.py` (engine_mcp_server.py
  is canonical) and `ruff check` on every touched file.
- [x] 10. Codex refute-review dispatched and folded: 8 of 9 findings fixed, 1
  accepted. The verdict and the lead's receipt are on PR #4021 (comment
  5850412279) and the resolution table is in its body; the reviewer's full text
  was filed as a `docs/audits/` file during the PR and removed on landing, since
  every finding it holds is either fixed or filed. The two not fixed there are in
  `docs/concerns/`.
- [x] 11. Sync the two spec deltas into `openspec/specs/` and archive, same lane.
  Done in the follow-up PR the lead asked for, after #4021 landed as 2e7ace67.
  Two corrections were needed on the way in, both found by diffing requirement
  TITLES against the stored specs rather than assuming the delta applied:
  * the connection delta MODIFIED "Guided reconnect preserves the universe",
    whose subject is reconnect-after-disconnect — replacing it would have
    deleted a requirement about something else. The removal-is-not-the-repair
    content is its own ADDED requirement, and the stored one is untouched;
  * the substrate delta ADDED two requirements and left "Run failures map to a
    terminal status taxonomy" claiming only `external_write_failed` /
    `external_write_refused` for effect failures. That requirement is where the
    taxonomy lives, so it gains the "additionally classify" paragraph this spec
    already uses for each new class, pointing at the two new requirements
    instead of restating them.
