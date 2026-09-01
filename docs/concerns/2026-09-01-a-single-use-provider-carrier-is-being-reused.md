# A single-use provider carrier is being reused, and it reads as a quota outage

**Filed:** 2026-09-01, from the founder's live universe
`u-01kxm1vszd8hwp7em418asq8h9`.
**Severity:** P1 — it is the actual cause of the universe not answering, and
every layer above it reports something else.

## The failure

Three consecutive automation runs (`30c41bd729c74169`, `c0fc403b25544b96`,
`763ec685d40442f6`, ~5 minutes apart) failed with:

```
CompilerError: Provider call failed in node 'heartbeat':
provider invocation carrier is already consumed
```

`ProviderInvocationCarrier.validate_for_call`
(`tinyassets/provider_work_authority.py:1244-1259`) is **single-use by
design** — it removes the carrier id from `_ACTIVE_PROVIDER_INVOCATION_CARRIERS`
and every later call raises. That is a deliberate authority property: one
carrier, one provider call.

The router consumes it once per entry, at
`providers/router.py:551` via `_provider_invocation_carrier(...)`. The carrier
itself lives on `universe_context.provider_invocation`. **So a universe context
reused for a second provider call — a retry, a second node, a re-run — carries
an already-spent carrier and fails closed.**

Not yet established, and the next step: whether the reuse is per-retry,
per-node, or per-scheduled-run. The three failures were an automation firing on
a schedule, which points at the context being minted once and reused per fire.

## Why it is worse than an ordinary bug

It fails **closed**, which is right, but the refusal then travels upward and is
relabelled twice:

1. `router.py:1205` raises `AllProvidersExhaustedError("Armed provider 'codex'
   exhausted; provider authority forbids fallback widening")`. The exception's
   name and text say **quota** regardless of why the attempts failed.
2. `api/runs.py` matched the bare substring `"provider"` and reported
   `provider_unavailable` with *"check ANTHROPIC/GROQ/GEMINI keys"* — on a
   universe with `api_key_providers_enabled: false`, where those variables are
   ignored by configuration.

The founder read the app's version, went and checked his codex usage, and found
it fine. He was right; the platform was wrong three different ways about one
event.

The reporting half is fixed in this change
(`tests/test_a_failed_turn_says_what_actually_happened.py`). **This concern is
the remaining half: the carrier reuse itself.**

## Why it is not fixed here

`provider_work_authority.py` is an authority path, and the correct fix depends
on which of the three reuse shapes is real — a wrong guess either re-mints a
carrier that should be single-use (destroying the property) or leaves the
outage. It wants its own change with the reuse reproduced first.

## What to check first

* Does a served turn take the same path? The founder's chat failure said
  *"**Served** provider 'codex' exhausted"* (`router.py:1119`, the
  `served_authority` branch) rather than *"**Armed** provider..."*
  (`router.py:1205`, the carrier branch). Those are different branches, so the
  chat outage and the automation outage may have different causes and only
  share a misleading label.
* `_reset_provider_invocation_carrier_state_after_fork`
  (`provider_work_authority.py:1266`) clears the active set on fork. A
  subprocess provider that forks between mint and validate would see an empty
  set and report exactly this error.
