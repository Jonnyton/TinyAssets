# ChatGPT Connector — Update Node Approval Bug Scoping

**Date:** 2026-04-25
**Filed by:** dev (scoping pass per task #10)
**Symptom:** ChatGPT connector "Update Node approval ended in generic error"; retry saved node v2.

---

## What The User Saw

1. ChatGPT Actions approval modal showed a generic error on first attempt.
2. User retried the approval.
3. Retry succeeded. The saved branch version is now v2, not v1.

---

## Code Flow — `update_node`

`_ext_branch_update_node` in `tinyassets/universe_server.py:5864`:

1. Reads current branch from DB → gets `version=N`.
2. Applies field mutations in memory.
3. Sets `new_version = N + 1`.
4. Calls `save_branch_definition(...)` — atomic `INSERT OR REPLACE` in SQLite. **This is the only point that persists state.**
5. Tries `record_node_edit_audit(...)` in a separate try/except — swallowed on failure.
6. Returns JSON response.

`save_branch_definition` uses `INSERT OR REPLACE` — atomically upserts. There is no partial-write window.

---

## Root Cause Analysis

### Scenario A — First call failed BEFORE `save_branch_definition` (most likely)

If ChatGPT's approval modal errored before the MCP call was dispatched (e.g., network timeout during the ChatGPT→Cloudflare→daemon hop, or a ChatGPT-side rendering failure), then:

- No MCP call reached the server.
- Branch remained at v1.
- Retry ran `update_node` once → DB goes from v1 → v2 (correct).

**This is not a code bug.** The "v2" is the expected first successful write. The ChatGPT UI displayed "generic error" for a client-side failure, not a server-side one.

### Scenario B — First call succeeded server-side, ChatGPT dropped the response

If the MCP call reached the server and `save_branch_definition` completed (branch → v2), but the HTTP response was dropped/timed out before ChatGPT received it, then:

- Branch is at v2 in DB.
- ChatGPT showed "generic error" (timeout on response receipt).
- Retry ran `update_node` again → DB goes v2 → v3.
- User sees "v2" — but actual DB state is v3.

**This would be a problem**: the node was edited twice (once silently), the second edit may have overwritten a clean state with the same content but now at v3 instead of v2. The audit trail correctly captures both edits but the user has no visibility.

### Scenario C — Audit write failed and surfaced as error (unlikely)

The `record_node_edit_audit` call is inside `try/except Exception` and logs but does not re-raise. It cannot cause an error response to the user. **Ruled out.**

---

## Evidence Needed From Host

To distinguish A vs B:

1. **Daemon log around the error time** — was a POST to `/mcp` received? Did it return 200?
2. **Branch version in DB** — is it v2 (Scenario A) or v3 (Scenario B)?
   Check: `extensions(action="get_branch", branch_def_id=<id>)` → look at `version` field.
3. **Node edit audit count** — `record_node_edit_audit` rows for that branch_def_id. One row = Scenario A. Two rows = Scenario B.

---

## Fix Shape (if Scenario B is confirmed)

**Problem:** `update_node` has no idempotency key. Retries always produce a new version.

**Fix options:**

**Option 1 — Idempotency key on `update_node`** (recommended, minimal)
Add optional `idempotency_key: str` param to `extensions()` and `_ext_branch_update_node`. On first call, store `(idempotency_key, branch_def_id, result_json)` in a lightweight SQLite table. On retry with same key, return cached result without re-applying the edit.

- Files: `tinyassets/universe_server.py` (param + dispatch + handler), `tinyassets/runs.py` (new table `update_idempotency`), `tests/test_update_node_idempotency.py`.
- Invariants: key expires after 24h; key scoped to `(actor, idempotency_key)` not global; only `update_node` uses it (other actions are naturally idempotent or have different semantics).

**Option 2 — Expected version check**
Add `expected_version: int` param. If branch version in DB != `expected_version`, reject with `{"status": "conflict", "current_version": N}`. Caller (ChatGPT) passes the version it read; retry with wrong version is safely rejected.

- Files: `tinyassets/universe_server.py` only (small diff — `expected_version` param already exists on `extensions()` for `project_memory_set`).
- Invariants: `expected_version=0` or absent = "don't check" (backward-compat default).
- ChatGPT side: the connector prompt must pass `expected_version` in the `update_node` call.

**Option 2 is lower-risk** — no new table, no TTL logic, easy to test, composable with idempotency if needed later.

---

## Scenario A Fix (ChatGPT UI clarity)

If root cause is Scenario A (client-side failure), no code fix needed. The ChatGPT connector Action definition could add a note in the action description: "If approval errors, check the branch version before retrying to avoid double-edits." This is documentation, not code.

---

## Recommended Next Step

1. Host checks daemon log + branch version + audit row count (see Evidence section above).
2. If Scenario A: close as ChatGPT-side UX issue; document in connector prompt.
3. If Scenario B: dispatch Option 2 (expected_version check) as a dev task.
   Files: `tinyassets/universe_server.py`, `tests/test_update_node_idempotency.py` (new).
   Invariant: `expected_version` absent → no check (backward-compat).

---

## File Boundary For Fix (Option 2)

| File | Change |
|------|--------|
| `tinyassets/universe_server.py` | `_ext_branch_update_node`: check `kwargs.get("expected_version")` before save; return `{"status": "conflict", "current_version": N}` on mismatch. |
| `tests/test_update_node_expected_version.py` | New: match, mismatch, absent (backward-compat). |

No schema changes. No new tables. ~30 lines of code + ~40 lines of tests.
