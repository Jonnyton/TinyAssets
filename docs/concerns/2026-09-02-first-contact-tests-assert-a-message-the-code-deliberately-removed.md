# Seven `test_first_contact` tests assert a failure message #2756 deliberately deleted

**Filed:** 2026-09-02, from the Play-launch lane (PR #2774), which is blocked by them.
**Verified:** yes, and the diagnosis is decisive — with **main's own**
`tinyassets/api/first_contact.py` checked out and none of this branch's changes,
the same seven fail:

```
test_credentialed_universe_still_surfaces_transient_exhaustion_honestly
test_unreadable_vault_never_claims_the_credential_is_missing
test_non_vault_engine_choice_is_an_outage_not_missing_setup[self_hosted_endpoint-extra0]
test_non_vault_engine_choice_is_an_outage_not_missing_setup[market_rented-extra1]
test_non_vault_engine_choice_is_an_outage_not_missing_setup[host_daemon-extra2]
test_unreadable_config_never_claims_the_engine_is_missing
test_non_string_engine_source_does_not_crash_the_failing_turn
```

**Severity:** P2 — no user-facing defect either way; it blocks merges that touch
`tinyassets/api/first_contact.py`, and it hides whether a real guard still holds.

## What happened

Each test asserts `"All providers exhausted" in out["error"]`
(`tests/test_first_contact.py:1091,1133,1185,1211,1233`). #2756 and #2758
("failures: tell the owner what actually happened, or admit we do not know")
deliberately stopped surfacing that string: `universe_server.py:2079-2089` treats
the router's "exhausted … forbids fallback widening" as one of
`_MISLEADING_ROUTER_TELLS`, on the stated grounds that the router says it
"whatever the attempts failed for", and replaces it with

> Your universe's turn could not run, and we could not identify why. This is not
> necessarily anything you did, and it is not a usage or billing limit …

So the tests now assert a design the code intentionally moved past. Their
*intent* — an established, credentialed universe hitting exhaustion must read as
an **outage**, never as "go attach a provider you already attached" — is still
satisfied by the new text, which says it is not the user's doing and not a
billing limit. It is the proxy that rotted, not the guarantee.

## Why nobody noticed

`required-tests` is **diff-driven**: it selects the test surface from the changed
files. `test_first_contact.py` is not in main's required surface, so main's
required job is green (its red workflow is `heavy-tests`, which is not required).
The moment a PR touches `tinyassets/api/first_contact.py` the file is pulled in
and the PR inherits seven failures it did not cause. That is the generalisable
finding: **a diff-driven required surface converts a stale test into a tripwire
for whoever next touches the module**, arbitrarily far from the change that
staled it.

## The decision, which is not mine

Rewriting another lane's assertion to go green is the thing `AGENTS.md` and
`docs/concerns/` both warn against, and whether the new message is *right* is a
product judgment belonging to the lane that made it:

1. **The tests are stale — re-point them at the invariant.** Assert what the
   guard is actually for: status is not `held`, no `reply`, and the message does
   not tell a credentialed universe to attach a provider. Small, and it restores
   a guard that is currently just failing.
2. **The new message is a regression for these cases.** A credentialed universe
   whose provider is exhausted *is* identifiable, so "we could not identify why"
   understates what we know. Then the fix is in `universe_server.py`, not in the
   tests, and these tests are correct to be red.

I lean to (1) — the suppression is deliberate, reasoned in a comment, and about a
string the router emits misleadingly. But (2) is a real reading, and the author of
#2756 is the right person to pick.

Until one is chosen, any PR touching `first_contact.py` cannot merge.
