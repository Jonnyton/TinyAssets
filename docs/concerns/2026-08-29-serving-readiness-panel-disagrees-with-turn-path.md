# P2 - The app's "Connect a model" card clears on a signal the turn path does not use

**Filed:** 2026-08-29
**Severity:** P2 -- a user can be told the model is connected while every turn is refused

## Observed (live, 2026-08-29 ~06:10Z, tinyassets.io/mcp/app)

After `llm_credential_deposit_owners.owner_user_id` was moved to the founder's new
subject -- and BEFORE `provider_assignments` was rebuilt -- the WAITING ON YOU panel
dropped its "Connect the model your universe runs on" card, yet the next turn returned
*"Your universe couldn't be reached right now: Connect your provider before running this
universe."* The panel read one ledger (deposit ownership); the turn read another
(`provider_assignments.owner_user_id`, `provider_assignment.py:1165`). With the card gone
there was no user-surface way to re-run the Connect gesture either.

## Ask

Readiness shown to the user must be derived from the same check the turn performs (the
resolved serving assignment for the CURRENT subject), and the Connect gesture must stay
reachable whenever that check fails. Reproduce by pointing `deposit_owners` at a subject
that has no assignment.
