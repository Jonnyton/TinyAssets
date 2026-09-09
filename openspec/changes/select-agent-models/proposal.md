## Why

The owner wants each universe's interactive agent to choose suitable user-owned
compute automatically while exposing the actual answering model and letting the
user switch, save a default, and order fallbacks. Today's fixed serving binding,
compiled CLI identities and model-as-definition identity do not provide that
capability; a successful OpenRouter workflow call does not establish it.

## What Changes

- One intent: owner-controlled, truthful model selection for the interactive agent.
- Discover eligible models from authorized connections; prefer available
  subscriptions/local compute over OpenRouter unless the user chooses otherwise.
- Rank suitable OpenRouter models with fresh evidence, not embedded release names;
  free onboarding remains free unless the user explicitly permits spending.
- Persist universe-local default and ordered accepted fallback choices separately
  from connection identity, with per-turn choices and actual response receipts.
- Distinguish model capacity from shared account limits; retry only safely and
  preserve completed tool results. A model switch grants no additional tools.
- Add a clickable model/provider status control in typed chat, distinct from the
  existing speech-voice menu. Display preferred, attempting, answered and waiting
  states honestly, including missing model metadata.

This does not modify private workflows, take over the paused background-self PR,
create provider accounts or authorize hosted custody beyond existing rules.
Two unpowered connection requests remain tracked in their existing concern.
The shared HTTP tool loop is a prerequisite for calling an HTTP connection a
full agent; this change must not enable misleading text-only fallbacks.

## Capabilities

### New Capabilities

- `agent-model-selection`: account-scoped model discovery, saved/current choices
  and visible actual interactive-agent execution identity.

### Modified Capabilities

- `provider-routing`: explicit interactive-agent selection and safe ordered
  fallback within current owner authority and capabilities.

## Impact

Extend existing provider definition/resolution, serving authority, request-local
configuration and router seams; reuse credential-blind outbound discovery and
existing authenticated app ingress. No additional top-level MCP handle. Storage
and authority changes require reviewed design before implementation. Existing
explicit pins remain fixed; previously ignored CLI model strings must not become
active preferences accidentally. Main specs describe only what actually ships.

Owner: Codex (current Patches task). Proposed delivery branch:
`codex/select-agent-models`; no PR or runtime activation yet. Connection recovery
PR #3676 remains the active release priority while this design is prepared.
