# Remaining model execution — September14 reviewed decisions

Owner approved one remaining-design Fable5.1 review and one final release review.
The first completed against f8299c49 in576s, VERDICT ADAPT, source reasoning only.
Full artifact: `docs/reviews/2026-09-14-model-selector-shape-fable.md`.
This document is the lead disposition before implementation. It does not approve
the full PR or describe deployed behavior.

## Native selection (R1/R2)

AGREE: separate executor default, requested opaque ID, and reported answering ID.
Introduce a typed native selection, not a fabricated HTTP pricing/wire contract.
The router overwrites request-local native configuration from current authority;
ordinary caller configuration cannot confer selection permission. A selected
default omits the CLI model argument and ignores process-global model overrides.
Codex uses `-m`, Claude uses `--model`; no native implicit fallback flag is added.

Explicit IDs already accepted in ModelAccess may execute as owner-declared IDs.
They are not verified available and the picker must label their basis. This is
incremental propagation, not completion of the owner's all-available-model list.
Discovered IDs require fresh owner-bound enumeration, matching current custody.
Provider-default execution remains valid when enumeration is unavailable.

Register discovery/selection behavior on installed executor objects, not vendor
names or release lists in the policy kernel. Enumeration gets an exact owned
credential snapshot, runs outside admission locks and database transactions,
and cleans it up in finally. Do not use the maintainer home or issue inference
to enumerate. Codex model/list is a documented metadata-only seam; its current
official documentation was fetched September14. Claude's documented initialize
control response contains models, but its direct CLI transport and completeness
still require validation. No SDK primary writer or fabricated enumeration claim.

Native workflow evidence is an explicitly versioned alternative inside the
existing strict selection evidence field; HTTP evidence remains byte-compatible.
Owner-declared evidence contains no observation timestamp: declaration is not
discovery. The router carries native selection separately from HTTP selected-model
facts, avoiding accidental HTTP cost/context calculations for native executors.
Native admission checks exact member, model scope, current custody and lifecycle.
Inspection distinguishes owner declaration from enumeration and actual receipts.

## Workflow tool coordinator (R3/R4/R6/R7)

AGREE: keep the existing served-request tool fence chat-only. A shared progress
loop receives separate chat/workflow authority adapters. Each workflow inference
reserves under the same receipt/claim; each tool rechecks current owner, immutable
work/branch, member and applicable cancellation/lease/activation. Configured tool
identity comes from receipt facts, never caller actor/graph strings. No fake chat
request, parallel grant store, or journal-as-authority path.

Before relaxing existing router/tool refusals, pin them with negative tests.
Add read-only sealed carrier accessors for round provenance; observe each actual
admitted workflow inference. Add versioned journal lineage for work-owned rounds,
retaining legacy chat record decoding and excluding work records from chat-only
projection. A completed tool result is preserved; uncertain external effects
hold and suppress whole-node retry, rather than beginning a fresh replayable turn.

Carrier provenance accessors are now built: reservation ID, work receipt ID and
selected member binding ID/generation/digest. Legacy provider-scoped receipts
retain their binding tuple. Reads do not consume/rearm a carrier or grant fresh
authority. Windows/Linux real-store groups each pass 115 tests, zero skips;
HTTP compiler/router cases verify the selected member rather than the aggregate
manifest root. This is not yet the dispatch observer or workflow adapter.

## Round allowance (R5 — adaptation pending before workflow integration)

### R4 format correction before implementation

DISAGREE_EVIDENCE with reusing round version2 for work: current
storage/agent_turn_journal.py dispatches that version to NativeInput, whose
existing native payload is version2/kind=native_agent. Preserve HTTP version1
and native version2 byte-for-byte. New work payloads use version3 with explicit
kind (engine_inference/native_agent), authority_kind=work_invocation and a
nonempty work_receipt_id. Root input headers use version3 with the same lineage;
chat headers remain version2 (and legacy version1 still reads). SQL containers
remain unchanged. Every inserted/read round must match its root lineage, so work
cannot masquerade as chat or move between work receipts. TurnSnapshot exposes
lineage without converting it into execution authority. Reset continues to
preserve/block uncertain effects for either kind; it must not hide work holds.
No existing row is migrated or rewritten. The workflow adapter will supply the
actual admitted receipt, never a caller's synthetic chat request.

The lineage format is now implemented and tested on Windows and Linux (258
passes in each, zero skips). Evidence:
`docs/reviews/2026-09-14-work-agent-journal-proof.md`. Current-home checks and
all execution guards remain unchanged; this checkpoint grants no work authority.

Shared progress extraction now built locally: AgentTurnCoordinator plus the
served-chat adapter retain existing chat behavior, including original input
records and typed fallback refusal. Ten executable differential cases compare
the old coordinator with the new composition through real stores and router.
Evidence: docs/reviews/2026-09-14-shared-agent-coordinator-proof.md. This neither
implements the workflow adapter nor relaxes the pinned authorization refusals.

AGREE with the finding: current admission counts one inference per node attempt;
multi-round tools need an explicitly finite allowance under the same work cap.
DISAGREE_CONCERN with automatically adding a new workflow `max_agent_rounds=0`
knob as the only repair: this would keep existing workflows unable to use the
capability unless their authors changed them. Reuse existing declared work/member
invocation allowances where possible. Resolve the exact derivation against the
immutable compiler and budget code before implementing this arithmetic. No gate
is relaxed meanwhile. No user workflow is edited for the proof.

R6 refinement from the actual compiler: `_call_policy_router_with_retry` catches
AllProvidersExhaustedError and starts the entire node again. Even a *known*
completed tool followed by later capacity exhaustion would be replayed by a new
turn. Therefore a work adapter must suppress whole-node retry after any dispatched
tool, not just an unknown effect. Safe no-effect capacity traversal remains inside
the same coordinator/history. A pre-intent failure can retain existing retry only
when no earlier action was dispatched. Cancellation must keep its original signal.

## Order and completion

Implement native propagation with basis labels and tests; then owner-bound
enumeration. Implement shared progress with unchanged chat behavior and the
workflow adapter only after round allowance is resolved. Final approved review
is reserved for the complete tested candidate. Windows/Linux tests, CI, actual
deploy containment/canary, and ordinary rendered app/workflow proof remain open.
