# Purpose

Subscribe and cancel a $20/month plan from the webapp, and nothing else.

Split out of `claude/metering-tiers-billing` after three cross-family REJECTs, all
of which targeted the METERING half (settlement is not exactly-once, wiki_write_back
unmetered, quota wiring). None of that is here. This branch carries only:

- `tinyassets/billing/` — Stripe adapter, stdlib-only, behind a boundary test
- `tinyassets/storage/subscription_state.py` — tier + checkout claim, the only state
- four `/mcp/app/billing/*` routes + the webhook auth exemption
- the plan control in the chat header

No quota, no metering, no enforcement. A universe is `paid` while it has an
entitling subscription and `free` otherwise.

- Metering continues on `claude/metering-tiers-billing`, blocked on a settlement outbox.
