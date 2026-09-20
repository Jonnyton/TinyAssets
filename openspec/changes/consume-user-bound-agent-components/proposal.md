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

This is **proposal-only**, not implementation approval or a claim of deployed
whole-harness portability. It does not edit, execute or finish the user's
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
Branch: `codex/governed-experience-consumer-shape`. One proposal/shape intent;
no runtime implementation, commit, push or peer dispatch authorized by this file.
The release lead owns the independent review queue and subsequent implementation
decision. PR #3882 is frozen in its separate release worktree.

Potential implementation seams after review: `tinyassets/universe_intelligence.py`,
existing custom-agent API/binding validation, existing Branch snapshot/execution
and provider-authority helpers, and trusted app installation/recovery controls.
No new top-level MCP handle, catalog, credential store, conversation store,
runtime fleet, provider or parallel grant system is proposed. Exact selection
field names and the adapter wire envelope are specified for lead decision in
[turn-contract.md](turn-contract.md), incorporating the independent ADAPT review
and its evidence-qualified disposition. The common admitted-run dispatch guard
belongs to the file lane, not a second consumer execution queue. No runtime
authorization follows from the proposal or its strict validation.
