## Why

The dark background-branch authority store can reserve, claim, release, and conclusively reclaim an attempt, but it cannot durably express why unsafe target work is non-runnable or how the same attempt may leave that hold. One bounded record/service prerequisite from the approved umbrella task 2.6 is therefore isolated so missing, stale, revoked, exhausted, unauthorized, source-mismatched, and indeterminate authority cannot become retries, replacement work, or secret-bearing errors; the parent queue/source integration task remains open.

## What Changes

- Add a closed non-secret hold projection that classifies canonical authority failures without exposing principals, target identifiers, digests, credentials, or resolver detail.
- Add one exact-fence service transition that moves the same reserved, claimed, or running attempt into `target_authority_held`, clears its lease, and preserves its immutable identity and budgets.
- Add a recovery-proven exit that advances only claim/lease fencing for the same binding and attempt after a dead/invalidated predecessor plus a conclusively absent/closed boundary.
- Add an authenticated reauthorization exit that consumes a server-resolved newer binding generation only after every attempt-bound target, source, executor, expiry, and attenuation fact is freshly revalidated; otherwise the same attempt remains held.
- Keep the capability dark: no BranchTask status, queue, dispatcher, source store, provider, public API, or live-runtime integration changes.

## Capabilities

### New Capabilities

- `background-target-authority-holds`: The dark authority-record/service seam for typed hold classification, non-secret projection, and exact-fence same-attempt recovery/reauthorization. The parent background-branch capability continues to own queue and source integration.

### Modified Capabilities

None.

## Impact

The change is limited to the canonical background authority model/service, its packaged runtime mirrors, focused model/service/store tests, and a partial-foundation note under the still-open umbrella task. It adds no dependency, credential access, external effect, public handle, queue mutation, or runtime activation.
