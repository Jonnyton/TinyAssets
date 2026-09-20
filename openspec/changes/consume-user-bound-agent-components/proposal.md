## Why

Users can already discover, combine and privately bind public agent definitions,
and the app consumes a narrow layout component. The canonical conversation still
has no demonstrated consumer for a user-selected reusable harness: preserving
its component bytes is not running it. Users must be able to change that behavior
without replacing their universe's private data or borrowing a creator's access.

## What Changes

- Propose a receiver-owned consumer selection under the existing AgentBinding,
  with explicit install/disable/rollback and current-authority checks.
- Review one functional first adapter: an immutable user-authored Branch handles
  a canonical foreground conversation turn through existing graph execution;
  the existing app-layout consumer remains independently usable in the same
  public composition. Layout application alone never enables a turn handler.
- Preserve canonical conversation identity, current user model choice and
  provider/effect/admission policy. No second writer or fallback replay runs
  after an uncertain selected-handler outcome.
- Reserve a canonical request and the same admitted run atomically in the existing
  runs database; project terminal history idempotently in the existing conversation
  store. Reconnect compares stable caller intent, not changed history/defaults.
- Add an opt-in keyed `consumer_request` object under `converse` and owner-scoped
  `read_graph target=conversation_turn` status. Preserve legacy default chat and
  require explicit keyed protocol before custom-handler effects.
- Expose supported versus unsupported consumers honestly. Arbitrary executable
  browser renderers, native-device adapters and general setup migration remain
  outside this first adapter; unknown components stay portable and inactive.
- Keep reusable source and lineage public; receiver installation/configuration,
  conversations, memory, connections and credentials remain receiver-private.

This bounded implementation passed independent review at `f9b91ed7`; final
test/spec integration still requires lead verification, CI, deployment and
two-owner live acceptance. It is not a claim of deployed whole-harness portability.
It does not edit, execute or finish the user's
PR #3840, PR #3842, background-self work or any example design.

## Capabilities

### New Capabilities

- `governed-agent-consumers`: explicit receiver-private selection and governed
  consumption of public agent components, first through a Branch-backed turn
  adapter with visible recovery and retained private state.

### Modified Capabilities

- `universe-personification-and-relay`: canonical conversation may use an
  explicitly selected receiver-owned governed turn handler instead of the
  default writer pipeline, while retaining its actor, model, memory/receipt
  boundaries and one canonical reply.

## Impact

Owner: Codex, under the founder's explicit coordinated parallel MVP push.
Release branch: `codex/consumer-release`, assembled separately from the preserved
original `codex/governed-experience-consumer-shape` tree. Implementation was approved
by the lead on September 19; exact-head review and follow-up remain lead-owned.
This change does not authorize editing another release or private user design.

Implemented seams are canonical `universe_server.converse`, private consumer
selection/admission/projection, existing Branch execution/provider authority and
trusted app installation/recovery controls. The built-in writer stays unchanged
when no custom handler is selected.
No new top-level MCP handle, catalog, credential store, conversation store,
runtime fleet, provider or parallel grant system is proposed. Exact selection
field names and the adapter wire envelope are specified for lead decision in
[turn-contract.md](turn-contract.md), incorporating the independent ADAPT review
and its evidence-qualified disposition. The common admitted-run dispatch guard
belongs to the shared file/consumer substrate, not a second consumer execution
queue. Recorded lead authorization and independent review, not proposal validation
alone, govern implementation. Deployment and live acceptance remain outstanding.
