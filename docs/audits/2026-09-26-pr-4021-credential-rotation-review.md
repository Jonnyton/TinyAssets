# PR 4021 independent review

**Filed:** 2026-09-26
**Verified:** Windows development worktree, head bf880354de49271a72f327c4f01e90de87ff0861; source inspection of `git diff origin/main...HEAD` and callers.
**Severity:** P1

Source: independent Codex review requested by the author. No subagents, peer subprocesses, worktrees, production operations or implementation edits.

## Findings (reviewer's original text)

P1 DISAGREE_EVIDENCE: The 403 search window crosses rows. `tinyassets/runs.py:7333` takes 220 characters after the status regardless of the actual body length. This summary becomes credential_rejected even though neither response establishes a dead key:

```
external write failed - a/authenticated_external_call: far side answered HTTP 403: Forbidden [far_side_error]; b/authenticated_external_call: far side answered HTTP 404: invalid_token [far_side_error]
```

The persisted delivered-body preview is at most 160 characters (`runs.py:5220`); its suffix after the status is at most 179 characters including `: ` and ` [far_side_error]`. The exception route uses 200 body characters (`effectors/__init__.py:853`), giving 219. These are maxima, not fixed row lengths. A 220-character slice cannot enforce row isolation. The producer functions themselves accept arbitrary error strings and node/sink lengths. The existing regression (`tests/test_replacing_a_rejected_credential.py:161`) pads the first body, avoiding the short-row failure. Classify structured rows before summarizing. A marker after the 160/200-character preview is also already lost before this matcher runs.

P1 DISAGREE_EVIDENCE: `_rotate_answer` ignores the result of `resolve_request` (`tinyassets/api/pending_requests.py:2181`) and unconditionally returns answered. `tinyassets/storage/pending_requests.py:355` catches storage exceptions and returns False. A successful vault write followed by a failed pending-request DB update therefore reports success while leaving the card pending. Retrying can overwrite a subsequently rotated key because rotation preserves the incarnation. Concurrent answers can both read pending before either writes; the gesture lock covers the vault operation, not the request-status check and settlement. Check settlement and serialize/revalidate the whole answer transaction, with an explicit recovery/idempotency strategy for the separate stores.

P1 DISAGREE_EVIDENCE: A real dead-key 403 is missed. Amazon Neptune documents the response-body message verbatim: "The security token included in the request is invalid." (HTTP 403, Unknown/Missing Access Key or Session Token). Source: https://docs.aws.amazon.com/neptune/latest/userguide/errors-engine-codes.html . `_CREDENTIAL_GAP` (`tinyassets/runs.py:7302`) allows only one intervening word; this message has five between token and invalid. It matches neither regex direction and is classified external_write_failed, leaving the agent on the retry/repair path. This finding is source-derived, not a live API invocation.

P2 DISAGREE_EVIDENCE: Preview admits an impossible legacy rotation. With a live owner-matching connection/grant but an existing http vault record lacking its owner row, `_rotation_target` (`tinyassets/api/http_connection.py:960`) succeeds and the rail raises a card. The write reaches `credential_vault.py:746`, refuses the legacy slot, and rotation returns credential_ownership_transfer_unsupported (`http_connection.py:1178`). The old key remains safe, but the owner was asked to paste a replacement that cannot land. Keep the vault fail-closed rule; either perform ownership preflight before raising the card or provide a deliberate ledger-backed legacy adoption path.

P2 DISAGREE_EVIDENCE: A stored auth_scheme=none is accepted by rotation (`tinyassets/api/http_connection.py:1148`), although connect_http deliberately excludes it (`http_connection.py:80`). `_secret_shape_error` falls through, a secret is stored, and the broker then ignores it (`tinyassets/storage/outbound_connections.py:3329`). A legacy/lower-level no-auth connection can therefore get a false repair receipt. Restrict rotation to supported pasteable schemes at preview and write time. Current connect_http cannot create this input, so this is a legacy/lower-level case.

P2 DISAGREE_CONCERN: Global refusal-kind precedence hides a delivered 401 in a mixed summary (`tinyassets/runs.py:7348`). A row with missing_consent plus a separate delivered 401 returns external_write_refused and suggests consent/extension, omitting the independently necessary rotation. Simply reversing global precedence would hide the consent failure instead; preserve classifications/actions per row.

P2 DISAGREE_CONCERN: The claim of no ledger mutations is literally too strong. `_rotation_target` constructs ConnectionLedger (`http_connection.py:973`), whose constructor migrates schema and backfills empty incarnations for all legacy rows (`storage/outbound_connections.py:3611`, `:3657`). Normal current-schema policy rows are not changed, but this is not a read-only constructor. Likewise the handler does not directly read the old secret, but the vault merge does. Narrow the claims.

P2 DISAGREE_EVIDENCE: The cross-universe test (`tests/test_replacing_a_rejected_credential.py:633`) exercises derived IDs, not a mismatched grant.universe_id. Removing that comparison would leave the test green. The no-secret test (`:711`) has no storage-fault injection despite its comment; its failing call supplies whitespace and then checks absence of an entirely different replacement value. It does not prove exception-path secrecy. Root caplog capture is capable of observing normal propagating module logs; no repository logger configuration was found that disables the relevant modules, but the test has no capture sentinel and its log assertion can run over an empty list.

P2 DISAGREE_CONCERN: The eleven-word guidance exemption (`tests/test_served_tool_guidance.py:76`, `:190`) is defensible for removing obsolete instructions, but its global bag-of-words cannot tie the exemption to that sentence. An identical word added elsewhere can make the exemption stale; unrelated deletions can also balance additions. Prefer an exact, anchored old-passage/new-passage migration or stable per-section guidance assertions, preserving the historical fixture.

AGREE: The explicit admin/depositor/active-grant gates reject the other principal, revoked connection, revoked grant, and mismatched grant universe with the same absent result. No new unauthorized destination-existence oracle was found. Rotation is stricter than remove_http's idempotent absent handling.

AGREE: Direct rotation rejects oauth2 before writing; the rail rejects it before asking. `_assembled_secret` does not bypass the final scheme check. Scheme/incarnation are included in the entire action serialized into the dedupe key (`pending_requests.py:953`, `:2089`). Rewriting a normal pre-existing connect row into rotate_http breaks the comparison. The pre-existing empty-dedupe compatibility bypass remains, but a legacy rotation lacking incarnation refuses against a current nonempty incarnation.

AGREE: All remaining `_DEPOSIT_TYPES` reads are appropriate: line 113 constructs the wider set; line 1247 chooses deposit wording/git-host fields in full-access rendering; line 2036 handles deposit sign-in; line 2047 dispatches deposit answers after the separate rotation branch. Secret field validation uses the wider set at lines 685, 717 and 768.

AGREE: Current-schema ledger policy, grant, endpoints and consents are untouched by the ordinary successful rotation. The general vault resolver reloads per call (`storage/outbound_connections.py:1097`), so no stale bearer cache was found. All identified production HTTP record construction sites now use the timestamp builder. This does not retrofit old records or force generic direct vault writers to use it.

## Validation and cleanup

2026-09-26, Windows, reviewed head: `python -m pytest tests/test_replacing_a_rejected_credential.py -q -p no:randomly --basetemp=C:/ta-rev` -> 43 passed in 3.27s. No additional tests were run. Counterexamples above are static source-derived cases, not claimed executed regressions.

`C:/ta-rev` did not exist before the test and resolved afterward to `C:\ta-rev`. The automatic tool policy rejected native PowerShell cleanup with "blocked by policy". The directory remains; no alternate deletion mechanism was attempted.

VERDICT: BLOCK - rotation can report a completed answer while the request remains pending and replayable.

---

## Resolution (author, 2026-09-26, head after fixes)

Eight of the nine findings are fixed in this branch; one is accepted and filed as
its own concern. The reviewer's text above is unedited — this section is the
reply, not a revision.

| Finding | Outcome |
|---|---|
| P1 — 403 window crosses rows | FIXED. `_credential_body` bounds a row at the start of the NEXT delivered-status phrase, then caps at 220. `test_one_rows_body_cannot_decide_another_rows_class` now uses the reviewer's unpadded counterexample, and asserts the same shape still catches a marker in the 403's OWN body. The "marker past the producer's 160/200-char preview is lost" observation is accepted and stated in the docstring: it is a MISS, which leaves the row in its existing class. |
| P1 — successful rotation can remain pending | FIXED. `_rotate_answer` checks `resolve_request`'s return and, when it is False, returns `request_resolution_unconfirmed` + `request_pending` naming the destination and saying the key WAS replaced and re-answering is idempotent. `test_a_rotation_that_cannot_close_its_card_says_so` injects the storage fault. The identical gap in `_deposit_answer`, `extend_http` and `remove_http` is pre-existing and out of this branch's scope — filed as `docs/concerns/2026-09-26-an-answer-can-land-while-its-card-stays-open.md`. |
| P1 — a real copular 403 is missed | FIXED. `_CREDENTIAL_DEAD_COPULA_RE` matches `<credential noun> … is/was/has been <invalid/expired/revoked/…>`, bounded by characters and stopped at a sentence break. The extra reach is sound where the compact rule's would not be, because a copula binds its predicate to its subject. The reviewer's verbatim string is a test, with `"The repository is invalid"` and `"Invalid target selected for this token"` as decoys. |
| P2 — preview admits an impossible legacy rotation | FIXED. `credential_vault.http_deposit_refusal()` is one read-only predicate over the same rows the writer compares; both `preview_rotate_http` and `_rotate_http` consult it, so the card is refused before the owner is asked to paste. Returned under its own name rather than flattened into `ask_cannot_be_granted`, because there is no ask to fix. |
| P2 — `auth_scheme=none` gets a false receipt | FIXED. `_unpasteable_scheme()` fails closed on `_DEPOSITABLE_AUTH_SCHEMES` rather than on a list of known exceptions, so a scheme the engine learns later is not rotatable by paste until someone decides it is. Applied at preview and at write. |
| P2 — two tests overstate their protection | FIXED both. `test_a_grant_bound_to_another_universe_is_refused` moves the grant so only the explicit comparison can refuse it. The secrecy test is split: the success path keeps a `capture-sentinel` record proving the capture is live, and `test_a_storage_fault_carrying_the_key_leaks_it_nowhere` injects a fault whose own message holds the value and checks the envelope, every log record, and every rendered traceback. |
| P2 — mixed-summary precedence | ACCEPTED, not fixed. The reviewer's own note applies: reversing precedence hides the consent failure instead, so the fix is per-row classification — and a run carries ONE `failure_class` string, which makes that a redesign of the field rather than a change to this matcher. Filed as `docs/concerns/2026-09-26-one-run-error-carries-one-failure-class.md`. |
| P2 — "never touches the ledger" too strong | FIXED. The docstring now says the two narrower true things: constructing `ConnectionLedger` migrates schema and backfills an empty incarnation as it does for every reader, and the vault upsert reads the existing record to merge it though this handler never looks at the old secret. |
| P2 — guidance exemption is brittle | FIXED, and the reviewer's preferred shape adopted. The allowance is now DERIVED from `REMOVED_PASSAGE` (the verbatim deleted text) instead of a hand-typed word list, and the test asserts the passage and its unique marker word are absent — so unrelated additions and deletions cannot balance into a pass. Mutation-checked by restoring the passage into the chapter. |

`C:\ta-rev` has been deleted by the author.

Every fix above was mutation-checked: each was reverted in place, the suite went
red on the test that names it, and the revert was undone with `git diff --stat`
confirming the tree returned.
