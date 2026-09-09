## Why

The shared app knows whether each founder turn came from the composer or Voice, but the public conversation contract currently reports only whether the Voice session was active. A typed turn sent while Voice is active is therefore mislabeled, and the universe cannot reliably answer the simple factual question, “Did I type this or say it?”

## What Changes

- **BREAKING**: remove the ambiguous `voice_active` field from the public `converse` operation rather than preserving a legacy alias.
- Add one `input_method` field whose values are `typed`, `spoken`, `app_action`, or `unknown`; the shared app reports the actual path that created each turn.
- Give the universe a plainly labeled, current-turn fact about the input method without adding instructions to change tone or behavior.
- Preserve the founder's authoritative message text and keep input-method metadata informational only, never authority or consent.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `realtime-voice-conversation`: identify the origin of each app turn rather than the ambient Voice-session state.
- `live-mcp-connector-surface`: replace `voice_active` with the explicit `input_method` conversation field.

## Impact

The change affects the daemon-served app conversation client, the public MCP `converse` schema and relay, universe prompt context, packaged runtime mirrors, focused tests, and both affected as-built specs. No storage migration or compatibility path is introduced.
