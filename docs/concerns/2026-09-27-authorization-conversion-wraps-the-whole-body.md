---
severity: P2
title: The sign-in conversion wraps the authorization body, not just its entry
filed: '2026-09-27'
summary: >-
  _routable_authorization converts a ProviderAuthenticationError from anywhere inside
  the served authorization context, including its body and __aexit__, while its claim
  that nothing launched is only certainly true for a failure during ENTRY.
---

**Filed:** 2026-09-27
**Verified:** 2026-09-27, gpt-6-astra refute-review round 2 of the spent-sign-in lane,
against `81ed2db3`. The reviewer did NOT establish an unsafe replay through the current
production path -- adapter authentication failures are already aggregated in the router,
and a launched native round becomes held before fallback -- so this is a narrowing of a
claim, not a live defect.
**Severity:** P2.

## Source (verbatim)

> I did not establish unsafe replay through the current production path: adapter
> authentication failures are already aggregated at `router.py:1289`, and a launched
> native round becomes held before fallback (`agent_turn_coordinator.py:283`).
> Held-authority, permission, and storage exceptions are not caught by this wrapper.
> Restrict conversion to failed context entry; propagate body/exit failures unchanged.

## Why it matters

`_routable_authorization` re-raises a sign-in refusal as an exhausted-providers
aggregate carrying `side_effect_state="none"`. That is stated as a fact rather than an
attestation, and it is a fact **because authorization did not finish** -- which is only
guaranteed when the refusal came from entering the context. A refusal raised from the
body, or from `__aexit__` after work happened, would carry the same "nothing ran" claim
without the same basis.

Nothing reaches that today: the body is `_call_routed`, which aggregates its own
authentication failures before returning, so a `ProviderAuthenticationError` does not
escape it. This is one refactor away from being wrong, and the comment currently says
"nothing was launched, because authorization did not finish" as though the code enforced
it.

## Closure

Enter the inner context inside its own `try`, convert only that failure, and let a
refusal from the body or the exit propagate unchanged. Then the comment is enforced by
the structure rather than by the surrounding code's current behaviour.
