# Existing exact HTTP connection cannot always redeposit as full access

**Filed / reproduced:** 2026-09-19 UTC, Windows Python3.14, isolated temporary
test universes only. **Severity:** P2. No production or real account mutation.

While replacing a source-inspection assertion with an end-to-end behavior test,
an existing exact connection (GET/PUT endpoint) returned `connection_conflict`
when the same owner rotated its key with `access=full`. This is not a success
receipt and must not be normalized or retried automatically.

## Base proof and reproduction

Independently reproduced on untouched runtime at base
`bcac8d1a250350ff48da2cfda3bd428831d361ea`, in isolated detached worktree
`wf-http-full-base-proof/TinyAssets`. Only an untracked diagnostic test was
added; `git diff --name-only` was empty. Command:

```
python -m pytest -q tests/test_full_deposit_base_probe.py --tb=short
```

One failed in1.06s, actual result
`{'error': 'connection_conflict', 'resource': 'connection'}`. The same sequence
failed in the connection-removal branch; therefore this predates that patch.

Reproduce with the existing `tests.test_workspace_authority` base/auth/universe
helpers and `tests.test_full_channel_access.GITHUB_ENDPOINT`:

1. Create u-1, owner/admin alice; sign in as alice.
2. `connect_http(universe_id="u-1", payload={"destination":"github",
   "secret":"test-original-key", "allowed_endpoints":[GITHUB_ENDPOINT]})`
   returns provisioned with exact access.
3. Same payload with secret=`test-rotated-key`, access=`full` returns conflict.

Likely cause to verify in the fix: `_connect_http` widens stored HTTP scopes
before its later `set_access_mode` compare-and-swap uses the earlier raw policy
snapshot (`tinyassets/api/http_connection.py`, re-provision path and7a block).
The old test only checks the ledger CAS plus source placement, so did not cover
this whole API sequence. Keep its assertions intact while adding a real behavior
regression when fixing this finding. Rotation can have occurred before the
conflict; preserve truthful partial-outcome reporting and fresh owner authority.

Separate follow-up after the current removal release, not an unreviewed authority
change folded into that patch. Owner queue: full-channel-access behavior repair.
