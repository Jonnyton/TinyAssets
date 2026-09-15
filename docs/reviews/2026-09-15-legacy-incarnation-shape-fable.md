The Stop hook lists dispatches from other lanes and another worktree. This session is a bounded read-only review with an explicit instruction not to take ownership of unrelated work, so I am not acting on them. The running entry named `legacy-incarnation-shape-fable.md` is this review's own output slot. Full deliverable and verdict repeated below.

**Review: legacy connection identity repair (empty-only incarnation initialization)**

Scope reviewed: the repair note, the two-case regression in `tests/test_http_redirect_approval.py:60-86`, and the three ledger tests Codex added to `tests/test_outbound_http_connection.py:128-164` while this review ran. Runtime confirmed unchanged: `git diff HEAD --stat` touches only the two test files and the design note. The two new redirect tests are red on the unchanged tree with the exact app refusal string:

```
{'detail': "Could not capture this connection's redirect approval policy.", 'error': 'request_invalid'}
2 failed, 36 deselected in 0.65s   (Windows, 2026-09-14, python -m pytest -q tests/test_http_redirect_approval.py -k legacy_connection_can_request)
```

**AGREE: the shape is correct and grants nothing.**

- **The defect is real and the fence is right.** The column migration at `tinyassets/storage/outbound_connections.py:3312` adds `incarnation` with default empty and never backfills. Only `create_connection` mints a token at `outbound_connections.py:3435`. The ask path refuses an empty snapshot at `tinyassets/api/pending_requests.py:696`. Relaxing that check would reopen the replacement-key ABA documented at `outbound_connections.py:3157-3163`. Initializing the row is the only correct fix.
- **No policy change.** The resource model built by `_resource_from_row` at `outbound_connections.py:3216-3240` has no incarnation field. Every owner, grant, mode, scope, endpoint, credential reference and revocation read is byte-identical after the repair. The test's before/after resource equality is a valid check for this.
- **No stale approval is admitted.** A pending redirect ask on a blank row cannot exist, because `pending_requests.py:696` refused it. A pending full ask on a blank row stored no snapshot, because `pending_requests.py:778` requires a non-empty incarnation. Answering it uses the fresh-read fallback at `tinyassets/api/http_connection.py:1023-1028` exactly as today. A snapshot carrying the old token of a deleted and recreated row mismatches the new token and is refused at `http_connection.py:1004-1011`.
- **Empty-only guard is the right narrowness.** Deletion is a hard delete at `outbound_connections.py:4014` and recreation mints a fresh uuid4, so `WHERE incarnation = ''` never touches an initialized row. Revoked rows also get a token. That is harmless, since every CAS path requires `revoked_at IS NULL`.
- **Concurrent initialization is safe.** `_connect` sets no journal mode and a 30-second busy timeout at `outbound_connections.py:3319-3324`. A guarded UPDATE as the first statement of a deferred transaction re-evaluates its WHERE after acquiring the write lock in both rollback-journal and WAL modes, so a loser matches zero rows and never overwrites a winner.
- **Per-row randomness is real.** `randomblob` is non-deterministic, so SQLite evaluates it per row. The 32-character lowercase hex output has the same shape as `uuid4().hex`, and only equality is ever compared.
- **The new ledger tests pin the contention property.** The trace-callback test at `tests/test_outbound_http_connection.py:152-164` fails if any UPDATE runs on a reopen with no blank rows. That is the right executable form of the "no avoidable write contention" requirement.

**DISAGREE_CONCERN, required before code (precision, not shape):**

1. **There is no "existing connection transaction" in `__init__`.** `executescript` at `outbound_connections.py:3284` commits and runs in autocommit, and the following ALTERs are DDL, which Python's legacy transaction control does not wrap. Keep the EXISTS SELECT outside any explicit transaction, issue the UPDATE only when EXISTS returned true, and let the `with` block commit. Do not use `BEGIN IMMEDIATE` as `configure_capability` does at `outbound_connections.py:3744`. That would take a write lock on every ledger construction, and the ledger is constructed fresh at roughly twenty call sites per request path, including effectors.
2. **Order the repair after the ALTER loop** at `outbound_connections.py:3305-3317`, so the pre-column database test at `tests/test_outbound_http_connection.py:128-135` initializes rows in the same open that added the column.
3. **Rebuild the plugin mirror** after the edit. The mirrored copy under `packaging/claude-plugin/.../storage/outbound_connections.py` is gated by `mirror-parity`.

**DISAGREE_CONCERN, deferred (do not block this lane):**

- **A read-only opener on a blank-row database now fails loudly.** Today an initialized database makes `__init__` effectively read-only. After the change, the first open that finds blank rows writes. If any sandboxed effector opens the ledger from a read-only mount before the daemon's own request path has run once post-deploy, construction raises. The window is tiny and the failure is loud, which matches Hard Rule 8, but confirm no jailed child constructs the ledger against a read-only bind before relying on this in production.
- **Snapshot-less old asks keep the weaker comparison.** `http_connection.py:1038` passes `None` when a stored snapshot has no incarnation. The repair neither fixes nor worsens that documented pre-existing gap. Leave it out of this lane.

**Required test additions beyond what is drafted:** none. The drafted set covers pre-column, blank-insert-after-upgrade, per-row distinctness, stable reopen without writes, and the real exact/full ask-and-answer path. The note's acceptance list already names concurrent initialization and stale pre-replacement refusal as the remaining two to write.

**VERDICT: APPROVE**, conditioned on the three required precisions above being reflected in the implementation. No shape change, no authority change, no migration rollback needed.
