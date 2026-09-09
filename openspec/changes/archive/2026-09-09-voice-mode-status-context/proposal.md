## Why

Voice currently overwrites the only visible conversation status, so a founder cannot tell whether the universe is still working after Voice is stopped. The universe also receives only message text and therefore cannot reliably know whether Voice was active when the turn began.

## What Changes

- Give conversation progress and Voice transport separate, independently updated status regions.
- Make stopping Voice state explicitly whether a pending text reply continues, arrives, or fails; stopping speech transport does not cancel the canonical conversation turn.
- Add an optional `voice_active` boolean to the founder-only `converse` input and pass it to the universe as bounded informational context for that turn.
- Have the shared web app derive `voice_active` from the actual Voice state at invocation time for both typed and spoken turns; never infer it from message wording.
- Keep the context ephemeral: it does not change authority, learning extraction, or the persisted founder/universe message text.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `realtime-voice-conversation`: Voice and conversation progress remain independently legible, stop behavior is explicit, and the app reports its actual Voice state with each canonical turn.
- `live-mcp-connector-surface`: the founder-only `converse` handle accepts bounded optional interaction-state context without expanding authority or changing the canonical message.

## Impact

- Public MCP `converse` input schema and universe relay prompt context.
- Shared onboarding web app status markup, Voice state rendering, and turn invocation.
- Conversation and voice state-machine tests, public surface tests, runtime mirror, and specifications.
