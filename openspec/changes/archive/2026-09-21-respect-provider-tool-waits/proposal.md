## Why

The Claude stream reader ends identified, still-running native tool calls at the
model-idle deadline. Two real-reader tests reproduce this on the deployed runtime.
Persisted failures also lose tool phase/progress age, preventing attribution of
the recent sequential timeout. This patch addresses bounded waiting and its evidence.

## What Changes

- Track native tool identities through normalized start/result events; pending
  work receives a bounded allowance, not a globally larger idle timeout.
- Preserve safe typed tool phase/progress-age diagnostics through the existing
  failure chain/read path; absent evidence remains unknown.
- Keep absolute deadlines, cancellation, authority and no-blind-replay rules.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `provider-routing`: honor identified pending tools and retain their typed
  failure-phase evidence across adapters/routers and served run diagnostics.

## Impact

Claude protocol normalizer/reader, shared attempt diagnostic projection and
existing run-error sanitization, with focused stream/router/persisted-read tests.
No new handle, grant, migration, provider selection or private workflow edits.
Owner root Codex; Claude Fable shape/exact review and Opus implementation.
Branch codex/provider-tool-wait; one PR. Historical run6ffec5e973734074 remains
unattributed beyond its established idle timeout; a retry is not proof of cause.
