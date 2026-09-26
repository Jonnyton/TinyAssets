# Every universe's outbound traffic shares one IP, with attribution but no per-tenant rate or quota

**Filed:** 2026-09-26, on closing PR #2751 unmerged. That PR argued the network
question correctly and then proposed writing the answer into a spec; the founder's
direction is that platform work carries findings, not design rows, so the finding is
here and the design rationale stays in the closed PR.
**Verified:** 2026-09-26 against `origin/main` `31a1776c`.
**Severity:** P2 — it touches the one platform floor (a user must not affect other
users), but no incident has happened and today's shape bounds it. Not P1 because
outbound currently rides a connection the user holds.

## The finding

Outbound requests from any universe leave through the in-daemon outbound proxy on a
single droplet, so **every universe shares one public source IP**. Services judge by
IP. One universe that gets the address rate-limited or blocklisted degrades every
other universe on the host, and that is a user-to-user effect rather than a
self-inflicted one.

**Attribution exists. Arbitration does not.** The proxy records every request:
`<data_dir>/.outbound-proxy/<grant_runtime_id>/audit.jsonl` and `network.jsonl`
(`tinyassets/storage/outbound_connections.py:1187`, `:3440`, `:4497-4503`). So the
platform can always say *who* did it. It cannot stop it, and attribution does not
un-blocklist anyone.

Checked for the missing half rather than assumed: no `rate_limit`, `quota` or
`per_tenant` anywhere in `storage/outbound_connections.py`. The two things that look
like caps are not egress caps — `node_sandbox.MAX_RPC_CALLS` is a per-node allowance
(`effectors/__init__.py:314`), and the `charge()` accounting in
`effectors/authenticated_external_call.py:341` bounds transform *work bytes* against
`_MAX_TRANSFORM_WORK_BYTES`, which is a memory guard, not a request rate.

## What bounds it today, and why that is not a fix

Two accidents of the current shape keep the exposure small:

1. Outbound goes through `authenticated_external_call` on a connection the **user
   holds**, so provider-side reputation attaches to that user's own account rather
   than to the droplet. The case where a blocklist does lasting damage — email —
   travels via the user's own email provider.
2. The universe harness tools have no network at all: `universe_tools.py:305` passes
   `share_net=False`, so the jail gets its own empty network namespace and cannot
   open a raw socket.

Neither is arbitration. (1) is a property of what happens to be built, not a limit,
and (2) disappears the moment a use case needs network inside the jail — which is
the checklist's "cloud dependencies and previews" row, since installing a dependency
needs egress.

## The shape of the fix, and the trap to avoid

**Limit, never forbid.** The instruments are ordinary because every action already
has an owner — only users create universes and only universes act, so nothing here
is unattributable:

- per-tenant egress **rate and quota**, which is the missing piece;
- per-tenant egress **identity** when a use case needs it, which removes shared fate
  outright.

The trap is reading `share_net=False` as a safety rule and hard-coding a prohibition
into the surface. It is scoping — "not needed yet", not "not allowed". A prohibition
denies the owner a capability that arbitration solves, and the owner is god inside
their own universe; the floor is only what reaches other users.

Delete this file when per-tenant egress rate and quota exist, or when per-tenant
egress identity makes shared fate impossible.
