# Subscribing buys a flag and nothing else

**Severity:** P1 · **Filed:** 2026-08-28, while preparing Stripe for live activation
**Surface:** the product, not a module

## The finding

Nothing in the codebase reads the subscription tier except the billing module that
writes it and the status route that displays it:

```
$ grep -rn "get_tier\|get_plan" tinyassets/ --include=*.py \
    | grep -v storage/subscription_state.py | grep -v ^tinyassets/billing/ \
    | grep -v ^tinyassets/onboarding/
(no matches)

$ grep -rn "usage_limit_reached\|usage_policy\|usage_ledger" tinyassets/ --include=*.py
(no matches)
```

There is no metering, no quota, and no capability that a paid universe has and a free
one does not. **A user who pays $20/month today receives a flag in a SQLite table.**

## Why this is the live-activation blocker, not the code

Everything else standing between us and taking real money is mechanical: activate the
account, provision a live price and webhook (`scripts/stripe_go_live.py --provision`),
swap two secrets. Those are steps. This is not a step — charging for a tier that confers
nothing is not a thing to be careful about, it is a thing not to do.

It is also not a bug. The plan the founder approved on 2026-08-28 was *metering **and**
tiers **and** billing*. Billing shipped; metering did not. The gap is a half-delivered
plan, and the half that shipped is the half that takes the money.

## Where the other half is

PR **#2598** (`claude/metering-tiers-billing`), still open, 23 commits ahead of and 15
behind `main`. It carries `usage_ledger.py`, `usage_policy.py`, the effect quota at the
outbound boundary, the engine compute guard, and compute metering in `runs.py`.

It also carries an **older copy of the billing code that has since landed in a much
corrected form** — `stripe_adapter.py`, the billing routes, `app.html`. Rebasing it whole
would conflict on precisely the files that were fixed today, and would risk reverting
those fixes. The metering half should be extracted; the billing half should be dropped.

## Smallest thing that makes $20 mean something

One dimension, not three. The founder named effects first, and effects are the dimension
whose cost is real (they reach the outside world):

- free tier: a generous monthly effect allowance
- paid tier: a much larger one

Storage and compute-minute metering can follow. Landing this **dark** (flag off, default)
matches the founder's own standing guidance — land dark, flip on for one universe, live
test, harden after — and makes the flip a config change rather than a build.

## The founder's call, not mine

Two decisions are genuinely not mine to make:

1. **What the free allowance is.** The plan said "materially more than 50 effects/month"
   and left the number open. Marginal cost is ~$0.12/user/month, so cost is not the
   constraint; anchoring and abuse are.
2. **Whether to launch without it** — selling the paid tier as support-the-project rather
   than as capacity. That is a legitimate choice, but it must be a chosen one, and the
   pricing page has to say what is actually being sold.

Recorded in `docs/host-actions.md`.
