## Why

A founder talking to their own agent in Slack cannot teach it. The Slack path
pins every sender to `T1` (`tinyassets/effectors/slack_agent_turn.py`
`SLACK_SENDER_TIER`), and `converse` gates `commit_learning` on
`bound_tier == FOUNDER`, so the agent answers fluently and persists nothing.
Proven live 2026-08-05: Tiny was told its origin story through Slack, replied
"now there's a thread running all the way through it", and `origin.md` still
reads `status: not-learned`. The failure is silent — no error anywhere.

Host requirement (2026-08-05): the agent must know **for a fact** whether it is
talking to the verified founder, and when it is not it must be
**programmatically unable** to do founder-only things. Roles beyond that
(org chart, customers, community, moderators) are explicitly out of scope until
a real issue forces them — users custom-make their own agents, so the mechanism
must stay generic across agent shapes (Hermes, OpenClaw, coding,
customer-service, remixes) and must not be special-cased to any one.

A cross-family (Codex) review of the obvious design returned **adapt** with
three CRITICALs; this proposal is that design corrected.

## What Changes

- **BREAKING — tier stops being the authorization boundary.** `converse`
  currently accepts `tier="T2"` as a string, which makes founder capability a
  convention, not a guarantee. External-surface callers lose the ability to
  pass a tier at all and must supply a typed, unforgeable founder grant or get
  the floor tier. The in-process MCP handle, which derives tier from
  authenticated request state, keeps its existing path.
- Add a sealed `FounderGrant` mintable only by the recognition resolver, in the
  module that owns the seal, so no caller can construct one.
- Recognise founders on `(provider, actor_team_id, sender_id)` — the sender's
  OWN workspace, never the delivering one. Landed already (`eac5bbb9`).
- **Do not overload `AuthenticatedAppEvent`.** Its seal today means "this exact
  HTTP body carried a valid HMAC at this timestamp", and existing consumers
  (`app_conversation_authority`) issue thread grants on it. Socket Mode cannot
  make that claim, so it gets a distinct evidence type rather than minting the
  same seal.
- Admit `event_id` through a **durable** replay ledger before minting founder
  authority. Socket dedupe is bounded and memory-only, so after a restart Slack
  can redeliver an old founder message and re-run a learning commit.
- Re-derive authority per call from current server state (founder home, exactly
  one admin ACL row, binding `configured`, matching revision) and additionally
  require the universe directory to exist. Never trust a stored mapping alone.

## Honest invariant

This recognises **the founder's Slack account principal**, not human presence.
A user-token app can post as the account owner, so the guarantee is "Slack
authenticated control of that account", not "the person typed this". Anything
needing the stronger claim requires step-up challenge, which is out of scope.

## Capabilities

### New Capabilities

- `verified-founder-recognition`: transport-neutral recognition of an agent's
  founder from an authenticated external identity, with fail-closed default.

### Modified Capabilities

- `universe-personification-and-relay`: founder capability becomes reachable
  only via a typed grant; external surfaces cannot request it by string.

## Impact

Slack today, and any later surface — Discord, Teams — inherits recognition
without reimplementing it, because the resolver keys on
`(provider, workspace, sender)` and the transports only supply an authenticated
identity. Authority policy leaves the transport entirely.
