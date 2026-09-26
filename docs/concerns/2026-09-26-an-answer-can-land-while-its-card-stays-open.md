# A pending-request answer can land while its card stays open

**Filed:** 2026-09-26, from the Codex refute-review of PR #4021
(the Codex refute-review of PR #4021 — verdict and receipt in https://github.com/Jonnyton/TinyAssets/pull/4021#issuecomment-5850412279, full reviewer text in that PR's history (the audit file it was filed in was removed on landing, since the findings are resolved), P1 #2).
**Severity:** P1. **Owner:** unassigned.

## The finding

`tinyassets/storage/pending_requests.resolve_request` catches a storage fault and
returns `False`. Three branches of `answer_request` ignore that return and report
`"answered"` anyway, so the act happened and the card did not close:

- `_deposit_answer` — the credential is in the vault, the tab stays pending;
- the `extend_http` branch — the grant is widened, the tab stays pending;
- the `remove_http` branch — the key is deleted, the tab stays pending.

The owner is told it is done. The card can be answered again later, and for a
deposit that means re-depositing whatever the owner typed then, over whatever is
there now.

`bind_model_access` already handles this correctly
(`request_resolution_unconfirmed` + `request_pending`), and PR #4021's
`_rotate_answer` follows that precedent. The three above predate it and were left
alone deliberately: changing what a deposit returns on a rare failure path is its
own change with its own tests, and folding it into a credential-rotation PR would
have put an untested contract change under an unrelated review.

## The fix

Check the return in all three branches and return the same shape
`bind_model_access` and `_rotate_answer` use. Each needs a test that injects the
fault (patch `storage.pending_requests.resolve_request` to return `False`) and
asserts the returned envelope says the act landed and the card did not.

Worth deciding at the same time: whether the whole answer should be serialised
against a concurrent second answer. Today both callers can read `status ==
"pending"` before either writes, and the gesture lock covers the connection write
but not the request settlement. For a deposit that is idempotent; for a removal
followed by a deposit it is not.

Resolve this file by deleting it.
