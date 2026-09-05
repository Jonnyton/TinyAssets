# Independent provider-portability exploration

2026-09-05 02:08 UTC, Claude Fable 5.1, read-only subscription subprocess.
Transcript: `72fdf751-5376-4b5d-81fb-c6b2145cc7e6`, final design report at
02:08:06 UTC. The wrapper's output file retained a later closeout hook; the
actual design report was read from transcript line 153 using `docview.py`.
This is NOT a fourth review or approval receipt for PR #2977. No implementation,
live state, workflows, credentials, or provider choices were changed.

## Independent findings

- AGREE: compiled CLI names exist at registration, definition validation, and
  resolution. A saved model must not become mutable state on globally shared
  provider instances registered by name.
- DISAGREE_EVIDENCE, inventory incomplete: `providers/base.py` also has the
  closed `_PROVIDER_AUTH_OVERLAY_ENV_VARS` map and rejects an unknown provider
  at credential-overlay construction. `provider_serving_binding.py` has
  `_PROVIDER_SERVICE`, and `api/llm_deposit.py` has `_SUPPORTED_SERVICES`.
  Widening just registration cannot produce a usable owner-authorized provider.
- DISAGREE_EVIDENCE, model field is not merely a preference: `model` participates
  in `ProviderDefinition`'s content-addressed id, and HTTP executor identities
  include that id. Moving it to a saved mutable default therefore requires
  an identity/storage migration preserving existing bindings, not an in-place
  change to the current integrity calculation.
- DISAGREE_CONCERN: container-bundled CLI binaries and compiled version-specific
  flags cannot satisfy no-platform-patch updates as built. Binary/profile
  lifecycle must be part of the portability design, not just argument parsing.

Lead reverified the three additional maps and definition-id material on the
local tree at 2026-09-05 02:10 UTC using `rg` and `docview.py` source slices.

## Proposed shape, not approved implementation

Connection-local, versioned execution profiles supply launch/framing/discovery
details to a generic executor. Carry model choice per invocation: explicit
selection, owner saved default, provider default. Re-resolve the authorized
connection at invocation; keep provider instances stateless. Discovery uses that
owner's grant and reports freshness or a precise unsupported/unknown capability,
never a guessed catalogue. A profile/version change must be verified before
activation; failure must stay local and preserve authority and truthful errors.

A proposal is required before code for public payload fields, model-independent
identity and migration, profile-controlled credential overlays, discovery grant
scope, and executable installation/update authority. Existing surfaces should
be extended where appropriate; the report did not establish a need for a new
top-level MCP action.

## Lead qualifications before adopting the proposed shape

- A bounded environment-variable grammar alone is not a custody boundary.
  Launch-loader/control variables and filesystem/network privileges need an
  explicit capability contract and isolation checks, not arbitrary name access.
- Keeping only the two compiled HTTP encoders is not the requested open-ended
  provider extension mechanism. Translation must itself be extensible at the
  authorized connection boundary, including unfamiliar protocols.
- A last-known-good profile cannot keep serving if the old binary/upstream is
  gone. Recovery claims require a verified retained compatible execution artifact
  and still-supported upstream, otherwise precise connection-local refusal.
- The report's suggestion that only a user-hosted CLI can avoid platform patches
  is too strong. Connection-scoped executable artifacts are another possible
  design, but require isolation and installation authority. Do not weaken the
  founder's zero-host-online requirement or treat local-only operation as success.
- Some HTTP APIs require an explicit model. Prefer a provider-advertised default
  when its protocol requires that representation; never infer one from list
  order/latest, silently choose a model, or falsely promise omission works for
  every protocol. If the provider exposes no default, surface that exact gap.

## Required acceptance evidence

An unseen CLI/provider works through a connection description without platform
code; actual authorized tool behavior, cancellation and accounting work; changed
metadata/profile versions are validated and incompatible updates isolated; new
models appear without a platform release; explicit selections remain fixed;
withdrawn choices fail without substitution; parallel connections retain their
own defaults and credentials. Test doubles support these claims but do not
replace actual connected-provider and rendered user-surface proof.

Next: a coherent OpenSpec proposal/design, independently reviewed before the
public/storage/authority implementation. This exploration closes no workflow
checklist row and does not claim model selection or provider portability shipped.
