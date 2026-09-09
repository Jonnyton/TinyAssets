## Context

The web app has one shared live status node. Voice state rendering and conversation lifecycle code both write it, so whichever runs last hides the other. Speech transport teardown increments the Voice epoch and stops recognition/playback, but it deliberately does not cancel the already-authorized `MCP.converse` promise; the text reply may still arrive without any UI explaining that distinction.

The universe currently receives only the founder message. Message wording is not a trustworthy modality signal, and the server has no need to persist browser Voice state.

## Goals / Non-Goals

**Goals:**

- Keep conversation progress visible while Voice changes state.
- State the observed consequence of stopping Voice, including whether a pending reply continues, arrives, or fails.
- Give the universe bounded, explicit Voice-active state for the current turn.
- Preserve the canonical founder message, history, learning extraction, and founder-only authority.

**Non-Goals:**

- Cancel an in-flight canonical conversation turn when speech transport stops.
- Persist a global presence indicator or synchronize Voice state between tabs/devices.
- Treat Voice state as consent, authorization, or evidence that audio was captured successfully.
- Dynamically mutate context inside a provider subprocess after a turn has begun.

## Decisions

### Separate status regions

Keep the existing `status-line` as conversation/session progress and add a dedicated `voice-status-line`. Voice rendering writes only the latter. Both remain polite accessible live regions with distinct labels.

Alternative: compose both strings into one line. Rejected because unrelated asynchronous writers would still need fragile shared ownership and ordering.

### Stop means transport stop, not turn cancellation

At stop/failure, capture whether the shared send control and turn timestamp show a canonical request in flight. If so, say the text reply continues but will not be spoken. When the request settles, update the Voice status to arrived or failed while the conversation status clears independently.

Alternative: abort the request. Rejected because the current MCP request has no cancellation receipt, and pretending cancellation would make delivery ambiguous.

### Optional per-turn `voice_active` context

Extend `converse` with an optional boolean `voice_active`, defaulting to `false`. The shared app computes it from the Voice state at the instant it invokes `MCP.converse`, for typed and spoken turns alike. The server passes a short informational context block to the universe writer while leaving `founder_message` unchanged for storage and learning extraction.

This is client-reported interaction state, not authority. It describes the start of the current turn and cannot claim what happens after the provider process begins.

Alternative: prepend a hidden marker to the founder message. Rejected because it would alter authoritative user text, pollute conversation memory and learning, and invite wording-based inference.

Alternative: persist a global Voice-presence row. Rejected because per-tab/device state can conflict and no current product behavior requires cross-tab presence.

## Risks / Trade-offs

- **Voice may be disabled after a turn starts while the universe is already generating.** → Define `voice_active` as invocation-time state; the UI separately reports post-invocation stop behavior.
- **Non-app MCP clients can self-report `voice_active`.** → Treat it as informational client context only, never authority or consent.
- **Two live regions could be noisy to assistive technology.** → Use concise, independently labeled polite regions and avoid duplicating conversation progress in ordinary Voice labels.
- **Queued typed turns can outlive the first stopped-Voice turn.** → Re-check the actual shared busy state after queue flushing before declaring the pending work settled.

## Migration Plan

1. Add the optional default-false input so existing clients remain valid.
2. Deploy server and app together in one image.
3. Run focused state-machine tests, public handle canary, protected deployed-SHA assertion, and read-only rendered UI inspection.
4. Roll back the image if the public canary or rendered status contract fails; no stored-data migration is required.

## Open Questions

None for this slice. Cross-device live presence would require a separate persisted-state design.
