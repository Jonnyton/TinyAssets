## Context

The app has two independent facts: whether the Voice transport is currently active, and how a particular founder message entered the conversation. The shipped `voice_active` boolean exposes the first fact, but the universe and user expected the second. A composer submit can be typed while Voice remains active, so treating session state as turn provenance is incorrect.

The public `converse` handle is shared by the app and MCP clients. The app can always distinguish its composer path from its browser-speech and realtime-Voice paths. Other MCP hosts may not expose input provenance to TinyAssets.

## Goals / Non-Goals

**Goals:**

- Represent the input method of the specific current turn as `typed`, `spoken`, `app_action`, or `unknown`.
- Make the fact plain enough that the universe can reason from it naturally without behavioral instructions.
- Remove the ambiguous `voice_active` contract and all app/backend uses of it.
- Keep founder-authored message text, learning, authorization, and consent boundaries unchanged.

**Non-Goals:**

- Telling the universe to adopt a different tone or response style for Voice.
- Inferring input method from message wording.
- Claiming that an MCP host knows provenance it did not report.
- Preserving `voice_active` as an alias or compatibility path.

## Decisions

### Use a turn-scoped enum, not session state

`converse` accepts `input_method` with the closed values `typed`, `spoken`, `app_action`, and `unknown`. The shared app passes `typed` from composer and typed request-rail replies, `spoken` from browser speech and realtime Voice tool calls, and `app_action` for lines created by a founder-selected request-rail action. Calls from surfaces that cannot observe provenance omit the field and receive the truthful `unknown` default.

Alternatives rejected:

- Keep `voice_active`: it answers a different question and mislabels typed turns sent while Voice is active.
- Add `input_method` beside `voice_active`: two overlapping facts invite conflicting interpretations and retain the broken public path.
- Require every MCP host to choose typed or spoken: a host that does not expose the fact would have to guess.

### State the fact without behavioral policy

The universe system context says `CURRENT TURN INPUT METHOD` and identifies the specific founder message as typed, spoken, created from a selected app action, or not reported by the client. It does not tell the universe how to sound or whether to mention the field. The model can then answer a direct provenance question from an ordinary fact.

### Preserve provenance through app retries and queues

The app carries the input method with queued and retried turns. A composer-originated resend remains `typed`; a Voice turn remains `spoken`. Restored records that predate this field are `unknown` rather than being guessed from the text or current Voice state.

### Replace the boundary outright

`voice_active` is removed from the FastMCP function signature, generated schema, browser client, writer relay, tests, and specs. It is not parsed, translated, deprecated, or accepted as an alias.

## Risks / Trade-offs

- **Breaking callers that still send `voice_active`** → Intentional boundary replacement; deploy the shared app and daemon in the same immutable image and verify the live schema after deployment.
- **A host omits provenance** → Report `unknown`; never convert absence into `typed` or infer from content.
- **Queued or retry paths lose provenance** → Pin the path in browser-harness tests, including a typed turn while Voice is active.
- **The model still phrases the fact awkwardly** → Use a direct current-turn label and verify through a rendered conversation that asks whether the turn was typed or spoken.

## Migration Plan

1. Replace the public schema, app payloads, and writer context in one commit and image.
2. Rebuild the packaged runtime mirror and run focused schema, app, and writer tests.
3. Deploy through the normal exact-SHA release workflow and run the public handle canary.
4. Verify in the live app with one typed provenance question and one spoken provenance question.

Rollback is the prior immutable image. There is no storage migration.

## Open Questions

None.
