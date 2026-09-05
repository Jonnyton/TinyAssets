# The "connect a model" ask appears only when nothing is bound, not when the credential dies

**Filed:** 2026-09-01, from the founder's instruction after his universe stopped
answering:

> "i cant do as you ask and reconnect cause a naevie user wouldnt know that. if
> that is the case then the request for that should pop up."

**Severity:** P2 — it strands an owner in a state they cannot diagnose or exit
without being told where to look.

**Raised to P1 by a live recurrence, 2026-09-05.** A third unserved state hit
production and it is the most ordinary one of the three: the credential is
perfectly valid and the **subscription is out of usage**. The founder's home
universe was bound to codex, codex was locked out until Sep 7, and the rail
offered nothing — exactly the dead end described below, reached without anything
expiring or being revoked. This is not a rare end-of-life event; it is what a
metered subscription does on a busy day. See
`2026-09-05-the-restored-claude-credential-expires-in-hours.md`.

## The gap

`list_requests` prepends the synthesized connect ask when
`not _serving_llm_bound(...)` (`api/pending_requests.py:765`). That helper
resolves the serving **binding row**
(`api/pending_requests.py:699-709`) and returns True whenever one exists.

So there are two different unserved states and only one of them asks:

| state | binding row | ask appears |
|---|---|---|
| never connected | absent | **yes** |
| connected, credential expired or revoked | present | **no** |
| connected, credential VALID, subscription out of usage | present | **no** |

In the second and third, the owner is bound, unserved, and un-asked. Every turn
fails, the rail shows nothing to do, and the only route out is knowing to go and
reconnect a provider that still *looks* connected — and in the third it really
is connected, so "reconnect" is not even the right advice. The exit there is
*serve on something else, or wait for the reset*, which is what the
`quota_or_cooldown` notice now says (#3074) and what the rail still does not
offer.

## Why the notice cannot paper over it

The honest-failure change in this same PR adds an `auth_invalid` notice. The
first draft said *"there is a request waiting for you to do exactly that"* —
which would be **false in precisely this case**, and would have been the same
confident-wrong shape that change exists to remove. The notice now describes the
action without asserting a rail row exists. That is a workaround, not the fix.

## The fix

Broaden the condition from "is a binding row present" to "is this universe
actually servable": a binding whose credential is unusable should raise the ask
the same way no binding does.

`credential_vault._usable_subscription_record(universe, service)`
(reached from `snapshot_llm_subscription_credential`,
`credential_vault.py:1601-1612`) is the per-universe signal — the right one,
because it reads the universe's OWN vault rather than host auth.

**Do not use `api/status.py::_provider_auth_snapshot` for this.** It reads the
shared-volume host auth paths, which is why it reported codex `"ok"` on
2026-09-01 while the founder's universe could not run at all. Gating a
per-universe ask on host credentials would reproduce the original confusion in a
new place.

Cost: `list_requests` is a hot read on every rail poll, so the check needs to be
cheap or cached; a filesystem stat of the vault record is probably acceptable,
a live provider probe is not.

### The vault check alone does not cover the third state (2026-09-05)

`_usable_subscription_record` answers "is there a usable credential here", and
in the quota case the answer is **yes** — the credential is valid, the meter is
empty. So the fix above, implemented as written, would still have left the
founder bound, unserved and un-asked on 2026-09-05.

The servable signal therefore has two halves, and the second one cannot come
from the vault:

1. **a usable credential** — the vault stat above, cheap, correct as described.
2. **a provider that is not currently refusing** — which is only ever learned
   from a failed attempt. The router already records it: the last failed
   attempt's `skip_class` / `failure_class`, now including `quota_or_cooldown`
   (#3074, `providers/diagnostics.py::classify_unavailable`).

That makes the cheap implementation a **read of the last recorded failure for
the universe**, not a probe: if the most recent served attempt failed
`quota_or_cooldown` and nothing has succeeded since, raise the ask — and word it
as *serve on something else or wait for the reset*, never as *reconnect*, which
is wrong advice for a credential that is fine. It also satisfies the cost
constraint the same way the vault stat does, and it keeps the rule this whole
strand is built on: the ask is raised from evidence the system actually has,
never from a guess.
