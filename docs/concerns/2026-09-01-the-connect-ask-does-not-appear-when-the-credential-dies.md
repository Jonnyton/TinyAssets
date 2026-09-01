# The "connect a model" ask appears only when nothing is bound, not when the credential dies

**Filed:** 2026-09-01, from the founder's instruction after his universe stopped
answering:

> "i cant do as you ask and reconnect cause a naevie user wouldnt know that. if
> that is the case then the request for that should pop up."

**Severity:** P2 — it strands an owner in a state they cannot diagnose or exit
without being told where to look.

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

In the second, the owner is bound, unserved, and un-asked. Every turn fails, the
rail shows nothing to do, and the only route out is knowing to go and reconnect
a provider that still *looks* connected.

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
