## Why

Requester-owned provider assignments are immutable per binding identity. A
corrected server enrollment (for example, a newly chosen cost ceiling) cannot
replace an already-issued active binding, so cloud automation setup can be
permanently wedged without direct storage access.

## What Changes

- Add an authenticated `rebind_provider` automation operation.
- Revoke the single matching active requester binding and issue the current
  server-enrolled seed in one phone-safe flow.
- Fail closed on ambiguous bindings and preserve the existing bind/reconcile
  idempotency behavior.
