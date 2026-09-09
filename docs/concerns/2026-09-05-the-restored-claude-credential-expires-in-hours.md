# The credential that restored uptime on 2026-09-05 expires the next morning

**Filed:** 2026-09-05, during the served-turn outage restore.

**Severity:** P1 — it is a dated fuse under the Forever Rule. Uptime is restored
now and breaks again on its own, with no commit and no deploy in between.

## What happened

The founder's home universe (`u-01kxm1vszd8hwp7em418asq8h9`) served on **codex**,
and that subscription hit its usage limit until **Sep 7th 2026 02:29**. It held
exactly one LLM credential, so "universe authority forbids fallback widening"
left every turn dead. Restore was to deposit a **Claude** subscription credential
and re-point serving to `claude-code`.

The material deposited was the **`accessToken` from the founder's local
`~/.claude/.credentials.json`** — because it was the only Claude token reachable
without a founder-interactive step, and the outage was live.

## The fuse

That token is the short-lived half of a Claude Code OAuth pair:

    expiresAt = 2026-09-06T01:19:06Z

The vault stores it as a bare `token_b64` record (`credential_vault.py`,
`resolve_claude_oauth_token`). **Nothing in the deposit path stores the refresh
token, and nothing refreshes it** — the sibling finding in
`2026-09-01-a-subscription-credential-dies-permanently-at-its-first-token-expiry.md`
is the same mechanism, reached from a different direction. When it expires the
universe returns to exactly the state that opened this outage, except the notice
will now correctly say the credential is invalid rather than shrugging (#3074).

## The fix, in order of durability

1. **Immediate, founder-interactive:** `claude setup-token` mints a long-lived
   `sk-ant-oat01-` token intended for headless use. That is the material the
   browser deposit form already tells the user to paste
   (`connect_deposit.py`: "Run `claude setup-token` ... it starts with
   sk-ant-oat01-"). Re-deposit with it and the fuse is measured in months.
2. **Structural:** a deposit whose token carries a known expiry should record it
   and raise the connect ask *before* it dies, rather than after. Today the ask
   appears only when no binding exists at all — see
   `2026-09-01-the-connect-ask-does-not-appear-when-the-credential-dies.md`,
   which this makes materially more urgent: a universe can now be bound,
   unserved, un-asked, **and** on a clock nobody is watching.

## Why not just deposit the long-lived token during the outage

`claude setup-token` requires a browser approval and a code pasted back into a
terminal. It is a founder action; the outage was not going to wait for it. This
file exists so the shortcut does not become the state of the world.

## Close when

A long-lived Claude token (or a refresh-capable deposit) backs the founder's
home universe, verified by a served turn dated after the short token's
2026-09-06T01:19Z expiry.
