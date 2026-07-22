## Context

`tinyassets/api/first_contact.py` owns first-contact home reservation, materialization, and binding.
After that step, the `converse` entry path invokes universe intelligence. The canonical identity and
live MCP requirements currently collapse these stages by asserting that birth returns a first-person
reply, although downstream execution can fail and the MCP surface is required to report that failure
honestly.

The broader question of which requester-owned or accepted-market compute and model authority may
execute the turn is not implemented. Canonical specs describe as-built behavior, so that future
contract stays in an active change.

## Goals / Non-Goals

**Goals:**

- Make the canonical first-contact requirement match the two-stage implementation.
- Preserve the existing atomicity, scope-gate, and pure-read guarantees.
- State the existing structured insufficient-scope failure instead of the stale awaiting-card claim.
- Keep unbuilt execution-authority requirements visible without syncing them as current behavior.

**Non-Goals:**

- Change runtime behavior or public tool descriptions.
- Implement requester/BYOC or market routing.
- Claim that maintainer-resource exclusion is fully enforced today.

## Decisions

### Modify the existing requirement rather than add a second birth requirement

The requirement name and all birth mechanics remain accurate. Replacing only the overclaimed outcome
keeps one canonical owner for first-contact birth and avoids contradictory requirements.

### Describe the handoff, not a guaranteed provider outcome

After successful birth, the call returns to the conversation entry path. A reply or an honest
downstream error is governed by the separate personification-and-relay capability. This states the
observable stage boundary without inventing execution-authority enforcement.

### Keep future authority rules in the active implementation change

Requester/BYOC and accepted-market authority, fail-closed missing-authority results, and receipts are
future behavior. Syncing any of those statements here would turn design intent into false as-built
truth.

### Correct the stale insufficient-scope presentation

The scope gate correctly prevents reservation, but the current MCP entry path returns a structured
creation/load error with `auth_scope_required=true`; it does not render an awaiting card. Canonical
truth records that actual outcome without changing the authorization boundary.

## Risks / Trade-offs

- **Risk: the correction could be read as weakening first-person relay.** The relay capability still
  owns successful reply behavior; this change only removes the claim that birth guarantees success.
- **Risk: future work could forget the missing authority boundary.** The active `universe-creation`
  change retains that residual with explicit dependencies and scenarios.

## Migration Plan

Sync this one modified requirement into the canonical identity spec, archive the correction, and
strictly validate all OpenSpec artifacts. No runtime migration or rollback is needed; reverting the
spec commit restores the prior wording.

## Open Questions

None for this as-built correction. The active residual change owns the unresolved execution design.
