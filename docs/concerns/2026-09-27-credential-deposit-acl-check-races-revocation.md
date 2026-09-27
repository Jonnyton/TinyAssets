---
severity: P2
title: A credential deposit's admin-ACL check is not serialized with revocation
filed: '2026-09-27'
summary: >-
  connect_llm reads the admin ACL, releases the connection, then writes the vault, so an
  admin revoked inside that window still lands a credential in the universe.
---

**Filed:** 2026-09-27
**Verified:** 2026-09-27, gpt-6-astra review of `565cbc64` (PR #4052). It was reproduced
with the real routes and vault writes, with the revocation inserted after the final ACL read.
**Severity:** P2. The race is narrow, and it needs an actor the owner had explicitly
granted `admin`. The outcome is an unwanted credential in the owner's vault, which the
owner can remove. Nothing is read out of the vault.

## What happens

`tinyassets/api/llm_deposit.py` `connect_llm` checks for an explicit `admin` row with
`list_universe_acl`, then calls `write_credential_vault` after the connection has been
released. The vault does not recheck the ACL, and nothing orders the write against
`revoke_universe_access`. Sequence: the owner grants actor B `admin`; B starts a deposit;
the owner revokes B after the ACL read and before the write; the deposit returns
`connected`, and the vault holds B's credential.

This predates #4052. The chatbot deposit path on main already takes a
`universe_id` and has the same check-then-write shape. #4052 adds the app's device
sign-in as a second caller of the same function. Revoking before the poll correctly refuses.

## Fix shape

Recheck the admin row inside the vault's write transaction, on the same connection
that commits the record, so that revocation and deposit serialize on one lock.
