# Candidate authority integration: verified constraints and decision gate

September9, source checkout939931a9ff0516e28b7d64ad340cafd023f57401.
This is pre-build design work, not a new authorization path or a shipped claim.

## Reverified constraints

- `provider_serving_binding.py::bind_serving_provider` creates a provider-specific
  serving binding, publishes a deny-all pending assignment, adopts current custody,
  and updates one agent binding's provider_ref and one ready ProviderAssignment.
  Rebinding per fallback would mutate durable serving intent and its generation.
- `provider_assignment.py::authorize_served_provider_call` validates a minted
  authenticated request carrier, exact owner/agent revision, ready assignment,
  provider_ref, binding digest and live custody under admission lock. Its current
  result is exactly one provider. A list of names cannot bypass these checks.
- `resolve_current_serving_provider_authority` is the canonical source for the
  unpowered request predicate too. A separate UI-only definition of readiness
  would recreate contradictory powered/unpowered behavior.
- `RequesterProviderEnrollmentResolver` reads explicit deployment enrollment from
  environment. It is not the self-service owner-selection seam; do not require
  operators to edit enrollment configuration for each model or future provider.
- HTTP ProviderDefinition identity includes its requested model. Subscription
  definition resolution ignores that field and constructs the native provider.
  Dynamic choices must not accidentally activate legacy ignored CLI pins, or
  mutate the shared process-global provider objects.

## Proposed direction to review, not implemented

Keep versioned owner/universe preference separate from authority. Extend the
existing serving-assignment chain to an accepted candidate set, with child
candidate records referencing the existing provider-work bindings and exact
custody identities. Reuse request-carrier validation, role/operation checks,
admission locking and per-candidate binding/custody validation. Do not introduce
a bypass through arbitrary dataclasses or treat a preference as a grant.

The manifest must bind owner, universe, agent anchor, accepted candidate
identities and allowed cost/capability constraints. Preference order and its
generation are captured separately; a reorder is not authority revocation. Legacy
single-provider assignments remain explicit, with no new fallback. New API
models may share a connection but never inherit a broader endpoint grant.

Open exact decisions: canonical manifest placement and digest, relationship to
the existing primary ProviderAssignment and provider_ref, publication transaction,
per-attempt resolution when the primary is revoked, and generation capture versus
in-flight calls. A revoked primary must not disable independently authorized
accepted alternatives; stale candidate metadata must not resurrect authority.
These are engineering decisions for independent shape review before schema/API
or serving-authority implementation, not questions for the user to solve.

## Independent review result

Claude returned ADAPT (exit0,284s); full proposal, source citations and remaining
five pre-build blockers are in
`docs/reviews/2026-09-09-model-candidate-authority-review.md`. Reuse the existing
provider-work and custody stores, add candidate membership to the serving
assignment, and factor one shared validator rather than copy the chain again.
The existing per-request invocation limit is2 and must be resolved for a longer
accepted sequence without creating an arbitrary two-model restriction. This is
not yet schema/authority approval; no such implementation has been started.
