# Codex review — sealed refresh-token store, three rounds (2026-08-29)

For `docs/concerns/2026-08-23-byo-llm-refresh-token-store.md` (deleted with this record). Landed as #2673,
deployed `74eafd60`, proven live 2026-08-29: legacy plaintext store discarded on first use, sealed
store at 0700, configured key armed (no ephemeral warning), a refresh from the founder's web session
rotated the handle. Three rounds is the cap; what round 3 still flagged is listed at the end, unfixed
by decision, not by omission.

## Round 1 — REJECT

VERDICT: REJECT

1. **DISAGREE_EVIDENCE** — The store publishes the live successor bearer handle in plaintext. `superseded_by` is outside AES-GCM ([session_store.py](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/session_store.py:280)), and rotation writes `new_handle` there ([session_store.py](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/session_store.py:397)). A data-dir reader can collect those values and submit the newest handle to the token endpoint. Tombstones remain until the seven-day `exp`, not merely the 120-second grace. This preserves the original cross-user disclosure, now as directly usable session handles rather than raw refresh tokens.

2. **DISAGREE_EVIDENCE** — Key isolation does not hold. Cloud workers receive both `/etc/tinyassets/env` and the shared `/data` volume ([compose.yml](C:/Users/Jonathan/Projects/wf-refresh-session-seal/deploy/compose.yml:254)); they then copy their environment into universe daemon children ([cloud_worker.py](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/cloud_worker.py:487), [cloud_worker.py](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/cloud_worker.py:1273)). The seal key is popped only on first store use ([session_store.py](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/session_store.py:113)). Approved source code executes with full builtins in-process ([graph_compiler.py](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/graph_compiler.py:1840)). It can therefore read the key before first token use—or import `session_store` and access the loaded key afterward.  
   `_safe_provider_child_base_env()` itself is allowlisted ([base.py](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/providers/base.py:395)), but other paths still copy `os.environ` wholesale ([base.py](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/providers/base.py:374), [base.py](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/providers/base.py:570)).

3. **AGREE** — The primitive AES-GCM use is sound: random 96-bit nonce, 256-bit key, and handle-bound AAD ([session_store.py](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/session_store.py:275)). Hex versus 32-byte base64url is unambiguous.

4. **DISAGREE_CONCERN** — Base64 parsing is permissive, not “exactly base64url.” `urlsafe_b64decode()` is used without strict validation ([session_store.py](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/session_store.py:104)); I confirmed a key containing `$` still decodes and is accepted. Use strict alphabet/padding validation.

5. **AGREE** — Refresh-token session fixation by storage adoption is closed: authorization-code exchanges mint, and refresh rotation starts from the store-returned `current_handle` ([__init__.py](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/__init__.py:338), [__init__.py](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/__init__.py:442)).  
   **DISAGREE_CONCERN** — “Ignores incoming `session_ref`” is inaccurate: successful cookie/code paths delete the caller-supplied handle ([__init__.py](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/__init__.py:451)). That is caller-directed mutation, although not fixation.

6. **DISAGREE_EVIDENCE** — Grace does not recover all refresh races. If two requests read the same handle before either rotates, both send the same single-use AuthKit token; the loser receives `refresh_failed` with no store reread/retry ([__init__.py](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/__init__.py:405)). After two rotations, an older handle fails the one-hop check ([session_store.py](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/session_store.py:371)); a WebView without the cookie receives `no_refresh_token` and must log in again. The optional browser lock mitigates but does not guarantee native/multi-process serialization ([app.html](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/app.html:530)). It is not necessarily a permanent loop, but repeated concurrent refreshes can repeat the failure.

7. **DISAGREE_CONCERN** — Ephemeral fallback is not fail-loud enough for production. A malformed configured key logs and silently continues with ephemeral storage ([session_store.py](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/session_store.py:120)); clients see ordinary successful sign-in followed by unexplained logout after restart. When onboarding is enabled, malformed configuration should fail startup or return a distinct unavailable error. A verified production key reduces immediate likelihood, not the defect.

8. **DISAGREE_EVIDENCE** — Legacy deletion is memoized before success ([session_store.py](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/session_store.py:170)), while deletion errors are swallowed ([session_store.py](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/session_store.py:196)). A transient failure leaves plaintext records present and prevents retry for the process lifetime. Destroying already-disclosed tokens instead of migrating them is correct; proceeding when destruction fails is not.

9. **DISAGREE_EVIDENCE** — Test decoration/gaps:

   - `test_a_signin_never_stores_under_the_handle_the_caller_sent` assertions at [test_refresh_session_seal.py](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tests/test_refresh_session_seal.py:106) already pass the post-#2627 plaintext implementation; fixation was previously closed.
   - Wrong AAD is covered by the copied-record test.
   - Missing: plaintext successor-handle detection, pre-first-token worker inheritance, overlapping refreshes, tampered ciphertext, truncated records, strict malformed-base64 rejection, clock boundaries/skew, and legacy-deletion failure/retry.

10. **AGREE** — No direct weakening of the same-origin or cookie controls: the gate still precedes body processing ([__init__.py](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/__init__.py:283)), and `Secure; HttpOnly; SameSite=Strict` remains ([__init__.py](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/__init__.py:464)). The refresh race above is an availability regression, not a same-origin bypass.

Focused verification: **44 passed, 2 platform-skipped**. The green suite does not cover the two ship blockers: plaintext successor bearers and key exposure to worker/user-code processes.

## Round 2 — REJECT (round-1 blockers confirmed fixed)

## VERDICT: REJECT

The round-1 blockers are fixed, but two remaining implementation defects invalidate the expiry/sweep guarantees.

### Claims

**R1**

- **AGREE** — Rotation replaces the old session with a tombstone whose successor is encrypted; AAD binds kind and handle. No retired token or successor handle appears in the record ([session_store.py:350](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/session_store.py:350), [session_store.py:491](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/session_store.py:491)).
- **DISAGREE_EVIDENCE** — Tombstones are not swept “at end of grace.” `_sweep_expired()` runs only during first directory initialization, before `_initialised.add()` ([session_store.py:218](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/session_store.py:218)). Tombstones created afterward remain indefinitely unless presented or the process restarts. I reproduced `expired_tombstone_still_exists_after_store_dir=True`.
- **DISAGREE_EVIDENCE** — `exp` is unauthenticated and directly controls acceptance ([session_store.py:358](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/session_store.py:358), [session_store.py:450](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/session_store.py:450)). Editing only `exp` replayed the old handle after its original grace deadline.

**R2**

- **AGREE** — `arm()` is the last module-level action ([session_store.py:531](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/session_store.py:531)); `main()` imports/arms before its logger, app construction, and consumer thread ([universe_server.py:3263](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/universe_server.py:3263)).
- **DISAGREE_EVIDENCE** — The claimed subprocess proof does not spawn a subprocess; it inspects two generated environment dictionaries in-process ([test_refresh_session_seal.py:281](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tests/test_refresh_session_seal.py:281)). My fresh-process import audit found zero pre-arm subprocess events, so the current production path is clean, but the stated test evidence is overstated.

**R3**

- **AGREE** — Parsing is restricted to the stated base64url/hex forms ([session_store.py:90](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/session_store.py:90), [session_store.py:127](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/session_store.py:127)).

**R4**

- **AGREE** — A configured malformed key is popped and raises `RuntimeError`; absence produces one process-lifetime warning and an ephemeral key ([session_store.py:141](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/session_store.py:141)).

**R5**

- **AGREE** — Initialization is memoized only after deletion and sweep succeed; `FileNotFoundError` is success, other deletion failures raise, and the endpoint returns the constant 503 body ([session_store.py:218](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/session_store.py:218), [session_store.py:251](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/session_store.py:251), [__init__.py:315](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/__init__.py:315)).
- **DISAGREE_CONCERN** — Malformed typed metadata is not fail-closed: `exp: "not-an-int"` raises `ValueError` from `read()`, producing repeated 500s until the file is repaired or removed. The new malformed-record tests miss this.

**R6**

- **AGREE** — Upstream refresh failure performs no store mutation and does not clear cookies ([__init__.py:421](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/__init__.py:421)).
- **DISAGREE_CONCERN** — The test is a sequential approximation, not an actual synchronized two-request race. It does establish the claimed loser-does-not-damage-winner result.

**R7**

- **AGREE** — All listed test categories exist; 41 focused tests pass.
- **DISAGREE_EVIDENCE** — No durable mutation evidence supports “14 mutations each shown RED.” Missing negatives include edited `exp`, actual post-grace file removal, and malformed `exp`/`v`.
- Tests that would pass round 1 include the explicitly labelled `test_regression_guard_a_signin_still_never_adopts_a_caller_handle` ([test_refresh_session_seal.py:107](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tests/test_refresh_session_seal.py:107)), plus tampered ciphertext, truncated/non-object JSON, expiry boundary, two rotations, and the loser/winner test.

### Direct answers

1. No plaintext credential in the new server-side JSON or `.tmp` records, logs, errors, or 503 body. Globally, plaintext remains by design: `session_ref` is returned and stored in `localStorage`, while the refresh token is emitted as a Secure/HttpOnly `Set-Cookie` value ([app.html:327](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/app.html:327), [__init__.py:479](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/__init__.py:479), [__init__.py:482](C:/Users/Jonathan/Projects/wf-refresh-session-seal/tinyassets/onboarding/__init__.py:482)).

2. No current pre-arm subprocess path found. Importing `universe_server` alone leaves the key present until `main()`, but its import chain emitted zero subprocess audit events.

3. Kind-bound AAD prevents relabelling but does not protect expiry. Extending `exp` is a real combined-risk scenario: someone with a captured old handle plus writable data-dir access can mass-extend tombstones; the server decrypts the sealed successor for them. Preserve outer `exp` as a sweep hint, but enforce an authenticated inner deadline.

4. The legacy-deletion failure is not memoized and retries correctly. Malformed metadata can instead cause a persistent 500 outage.

5. Decoration tests are named under R7 above.

6. I would block on authenticated expiry enforcement and malformed-metadata fail-closed handling. The claimed end-of-grace sweep must also be implemented or the claim removed.

Verification on 2026-08-29, Windows: affected suites `67 passed, 2 skipped`; focused Ruff clean; canonical/plugin runtime copies match.

## What round 3 fixed

- Authenticated deadline sealed inside the ciphertext; plaintext `exp` is a sweep hint only.
- Malformed metadata fails closed (record deleted), never a raised ValueError.
- Expired records swept on any store use at most once a minute.
- A real child process is spawned in the test and shown not to see the key.

## Reported as-is (not fixed)

- In-process user code (approved source nodes) could read the key: `docs/concerns/2026-08-28-user-code-runs-in-process.md`, separate boundary.
- Two-tab refresh race: pre-existing single-use-token behaviour shared with the cookie path; the loser gets a 401, the winner is unharmed.
- The compose `worker*` fleet mounts /data and copies env: removed under `openspec/changes/user-owned-automations`.
- The `session_ref` bearer still lives in localStorage on the native path by design (the WebView drops cookies).
