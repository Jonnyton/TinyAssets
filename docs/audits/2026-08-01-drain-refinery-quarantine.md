# Drain refinery quarantine

## Verdict

The local drain's red/yellow gap was not backlog exhaustion. After PR #2053
landed a durable blocker for one refinery target, current main still exposed 47
refinable candidates. `has_alternative_candidate()` nevertheless returned false
because it admitted only `OWNED`, `CLAIMABLE`, and `STALE` classifications.

The bounded fix adds `REFINERY` to that already-filtered alternative set. The
exact blocked target remains in `recent_blocked`, consumed targets remain
excluded, and the next loop still fetches current main before dispatch. No
worker parallelism, synthetic work, product authority, or provider utilization
floor was added.

## Runtime evidence before the fix

The active run `drain-20260731-212735-7059e4` recorded:

- attempt 4 snapshot: `refinable=45`, five concrete hints;
- attempt 4 result: verified `BLOCKED` for
  `refine-openspec-connector-tool-selectio-ac7becfd`, PR #2053;
- no immediate `post-block alternative available` transition despite other
  refinery hints; the next attempt began only after cooldown/recovery.

This directly reproduces the policy defect.

## Test-first proof

The focused test was changed to require a distinct `REFINERY` hint to return
true while the same quarantined target returns false. Before the implementation
change it failed at the positive assertion; after the one-set-member change it
passed.

Fresh verification on 2026-08-01 America/Los_Angeles:

- focused red: one expected assertion failure;
- focused green: 1 passed;
- scheduler-level proof: a blocked first refinery dispatched a distinct second
  refinery without invoking the idle wait;
- `py -m pytest -q tests/test_openspec_drain_supervisor.py
  tests/test_openspec_drain_watchdog.py` — 187 passed;
- Ruff lint — clean;
- `git diff --check` — clean;
- strict OpenSpec validation — valid.

`ruff format --check` reports that both large touched files would be reformatted
on current `origin/main`; the hotfix deliberately does not mix that baseline
bulk rewrite into this behavioral slice.

Post-merge live proof passed on 2026-08-01 America/Los_Angeles in controller
run `drain-20260801-113628-6deab6`, rooted at the merged controller:

- `12:50:48` — attempt 7 returned verified `BLOCKED` for
  `refine-openspec-operator-request-trigge-a4db889e` with PR #2068;
- `12:50:50` — the supervisor logged `post-block alternative available`;
- `12:50:52` — attempt 8 dispatched a different refinery worker;
- the configured idle interval was not entered; controller health remained
  `running`, with zero consecutive failures.

This is the exact blocked-to-alternative path required by task 2.3. Earlier
partial-to-next-refinery transitions separately proved ordinary continuous
dispatch across attempts 1–7.

Host-approved same-provider independent review of exact implementation head
`d0746029186f58e2633fe3bf1e14af0e792b731c` returned `APPROVE` with no blocking
findings. Its one nonblocking request for scheduler-level proof was added and
passes at the final pre-foldback head.
