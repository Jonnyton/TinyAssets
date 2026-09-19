# Next slice: trusted in-node structured delivery

Architecture-only proposal, September 19, 2026. Not implementation approval,
runtime proof, or closure of artifact delivery. Root owns release and live tests.
This extends the existing change; it creates no new change, PR, or top-level tool.

## Current boundary and source evidence

The structured delivery MVP is deployed according to the root's release proof;
current `origin/main` tasks record the protected deployment gate. This review
did not independently probe production. A fresh `git fetch origin main` and
`git diff origin/main -- <files below>` found no changes to the inspected runtime
files versus this isolated delivery worktree. Main's newer task/spec updates
remain authoritative; do not overwrite them from this older branch.

| Requirement | Existing implementation / remaining gap |
|---|---|
| Owner-authorized explicit JSON send | `tinyassets/api/deliveries.py:50` checks the sender's owned source/link and current receiver grant, accepts once and dispatches after commit. It accepts caller-supplied JSON; it does not attest that a node produced it. |
| Durable occurrence + provenance storage | `tinyassets/storage/deliveries.py:139` already accepts an internal `source_run_id`, includes it in the request digest, and stores source branch/node from the link. The public API does not supply it. Existing uniqueness is sender/universe/link/occurrence, not run-scoped. |
| Trusted in-node send | Missing. `tinyassets/graph_compiler.py:1573` has no delivery alias; `:1877` admits only declared `tools_allowed` aliases. `:2016` builds its parent invoker without run/placement provenance. |
| Correct placement identity | `tinyassets/graph_compiler.py:3311` already receives `parent_run_id` and `graph_node_id`; `:2588` carries immutable actor/universe/authorship context. These must reach the invoker. A reusable node-definition ID is not the scheduled placement ID. |
| Exact binary transfer | Explicitly refused in `tinyassets/api/deliveries.py:33` and `tinyassets/delivery_runtime.py:29`, including worker revalidation at `:57`. No accepted runtime artifact binding exists. |
| Existing file helpers | `tinyassets/authoring/io.py:389` requires owner **and session**, then returns all bytes. `tinyassets/workspace_fs.py:517`/`:602` provide held-descriptor regular-file reads/copies; POSIX semantics are not Windows proof. `tinyassets/execution_authority/blob_proof.py:892` takes whole `bytes`, not a streaming writer. None grants cross-owner runtime read authority. |
| Byte accounting | `tinyassets/workspace_pool.py:521` couples byte admission with checkout lease/job locks. It is not a generic retained-artifact reservation. `usage_policy.py:216` reserves effect count, not retained bytes. Do not call either a ready-made file-retention contract. |

Primitive inventory: `check_primitive_exists.py action deliver_output` reported
CLEAN, but direct source inspection finds the existing dynamically routed action
in `api/deliveries.py:14,130`, canonical graph routing and served wrappers. Treat
that inventory result as a scanner false negative, **not** permission to add a
second delivery API. `read_artifact` also reported CLEAN; no reader is proposed
in this slice. PLAN's Scoping Rules and State & Artifacts require composable
hard boundaries, thin handles, durable bytes, and no platform-authored workflow.

## Smallest independently usable implementation

Enable an owner-authored code node to call the **existing delivery action** over
the existing parent-mediated sandbox RPC with `(link_id, occurrence_id, outputs)`.
It can send repeated, intentionally distinct JSON occurrences from a user loop.
It does not expose arbitrary graph writes, run control, credentials or foreign
file handles. This closes the in-node portion of task 2.5, not tasks 2.4/3.3.

1. Thread an immutable parent-only provenance value from the authenticated run
   through compilation to the code-node invoker: actor, universe, source branch,
   actual source run, scheduled placement, and admitted execution context. Use
   existing `BranchExecutionContext` and run/compiler inputs; do not infer identity
   from child kwargs, mutable state, `NodeEnqueueContext.actor`, or a reusable
   definition. Missing authenticated context or unavailable run must refuse.
   Normalize the admitted principal through the existing identity/run-owner path;
   `actor="universe:<id>"` is not itself the human principal used by link ACLs.
   Do not add a delivery-specific `caller_provenance == "own"` gate.
2. Add one explicit delivery alias to the existing in-node allowlist, checked by
   `tools_allowed`. Pass only the three data parameters above. Reject attempts
   to pass actor/universe/run/node/branch, nested authority selectors, arbitrary
   action names or source-context objects. Preserve legitimate control-looking
   fields **inside** ordinary output data.
3. Factor the current acceptance service so public direct sends and trusted node
   sends share current ACL/link/generation/preflight, admission, digest, atomic
   acceptance and dispatch. Keep the existing author-store then runs-store lock
   order. Node calls additionally require that the link source exactly matches
   trusted branch **and placement**, that the run belongs to this actor/universe,
   and that its compiled output contract matches the mapped fields. Revalidate
   current source ownership; do not turn a stale running definition into authority
   over a replaced link. Persist `source_run_id` using the existing internal seam.
4. Reuse `tinyassets.idempotency.derive_effect_key` (`:43`) to derive the stored
   node occurrence, following the domain-separated mapping precedent in
   `tinyassets/handoffs/models.py:229`, **not** that handoff's payload-hash identity.
   Map `goal_id` to a canonical domain-tagged source principal/universe/link tuple,
   `schedule_period` to the trusted source run, and `item_fingerprint` to the hash
   of a canonical `{placement_id, user_occurrence_id}` object. Validate exact
   strings before derivation. Exclude outputs/content so changed replay conflicts
   in the existing request digest rather than silently becoming another send.
   Keep the existing delivery transaction as the only acceptance/replay ledger;
   do not add the handoff/outbound receipt tables or their migration-mode flag.
   Direct sends retain **all** existing key semantics, including values resembling
   generated keys. No reserved-prefix ban, rewrite, new table or backfill. If a
   direct legacy row occupies a derived key, node admission detects the absent
   `source_run_id` and refuses `occurrence_conflict`; never adopt or relabel it.
   Conversely, direct sends cannot replay a node row as a direct occurrence.
   Existing source-run/node/link provenance must agree on node replay. Identical
   local occurrence names in different source runs remain independent. Current
   `_receipt` (`storage/deliveries.py:113`) exposes no occurrence field at all:
   preserve it unchanged, return its stable delivery ID, and do not fabricate a
   new original-occurrence field by decoding a hash.
5. Preserve the sandbox's existing RPC accounting and cancellation checks, and
   the receiver's existing run admission. Ensure a successful node delivery is
   counted as a write by the source run's settlement rather than being refunded
   as read-only (`effectors/__init__.py:1037`). Do not mark a declared node effect
   as fired or change once-per-node effect semantics. Source failure after an
   accepted transfer cannot undo it; no automatic resend of ambiguous work.

No new provider dispatch path, callback URL, daemon worker, generic public
`start_node`, automatic effect declaration, receiver retry, or file support.
Public explicit owner sends remain valid but are not relabelled node-produced.
Child output is untrusted data even when its execution provenance is genuine.

### Exact reuse rule (authority is not attribution)

`BranchExecutionContext` documents actor/universe/delegation trust, not a blanket
ban on designs with another contributor. `runs.py:4297` classifies the current
branch as own when its author is the run actor **or an admin of the run universe**.
`api/branches.py:2528` creates a remixed branch with the authenticated ledger actor
as author and retains `fork_from`; node references/approval provenance are not a
separate execution grant (`api/branches.py:202`). Thus an admitted owned/remixed
branch containing copied, referenced or shared node definitions may deliver from
its own authorized placement/link, regardless of original contributor metadata.
The new path must test that case and must not require approval flags or original
author equality. Retain existing source-code admission unchanged: direct foreign
source code is currently rejected upstream at `graph_compiler.py:2024`, and the
current link-management gate requires an owned source branch. Public readability
or `approved=True` alone therefore does not grant a foreign branch access to the
runner's private link. This is an existing platform limitation, not a new RPC
restriction or a claim that every possible future delegated-reuse form is solved.

Other identity seams were checked and are not substitutes: `idempotent_by_step`
(`idempotency.py:274`) uses caller inputs and a separate expiring, non-atomic
check-then-call store; `resolve_effector_identity` (`:75`) consumes packet fields
and a rollout mode; the declared effect chain (`effectors/__init__.py:745`) is
once per run/placement, not once per user loop occurrence. Reuse the canonical
key derivation, but only with parent-held provenance and the existing durable
delivery acceptance transaction.

## File follow-through: exact prerequisite, not base64 workaround

After this slice, the prior design's read-only input bundle remains the right
shape: authorize a real source capability, stage/hash exact bytes, atomically bind
an immutable copy to accepted delivery and receiver attempt, and expose bounded
parent-mediated chunk reads to the admitted entry plus its downstream nodes.
No path string, raw foreign handle, naked hash or public URL grants access.

Before implementing files, resolve these concrete seams in the existing design:

- Streaming held-handle ingestion/finalization; current authoring reader and
  blob `put_blob` buffer whole files. Reuse their integrity/ownership contracts,
  not their whole-buffer signatures as a claim of large-file support.
- Atomic staged/committed byte reservations and receiver retention attribution,
  reconciled across delivery acceptance and crash cleanup. Extract/reuse the
  existing real-resource accounting rules without inventing a fake checkout job.
  Establish global lock order if physical-root coordination precedes SQLite;
  do not hold author/runs writer locks during arbitrary file streaming.
- Run/entry/downstream binding and bounded exact-byte read action under existing
  `read_graph`, implemented through the same trusted RPC seam above. Entry is
  permitted even though it is not its own ancestor; unrelated nodes/runs are not.
- Committed blobs outlive sender handle expiry; uncommitted staging is bounded
  and unobservable. Receiver deletion/retention, two-party account deletion and
  orphan recovery need explicit disposition before enabling intake.

These are real remaining work, not an external blocker and not implementation
approval. Keep file envelopes loudly refused until the whole safe transfer path
exists. A small inline-base64 demonstration does not close the file requirement.

## Focused verification and release acceptance

Proposed tests: extend delivery public/reservation/runtime tests plus compiler
RPC fixtures. Cover actual sandbox RPC on Linux; denied undeclared tool;
forged provenance at every boundary; shared definition/two placements; nested
invoke retaining child run identity; wrong link placement; revoked ACL/link;
missing/stale context; same occurrence replay/concurrent replay; changed replay;
two distinct loop occurrences; same local occurrence across two source runs;
direct/node provenance separation including legacy key collision; copied/remixed
shared definitions accepted under an owned placement; upstream foreign-code
admission unchanged; post-acceptance
source cancellation; write settlement; safe sender receipt versus receiver run.
Keep file refusal, existing wiki/enqueue RPC and direct-send regressions green.
Use fixture-owned graphs only. Run focused Windows and Linux oracle, plugin
mirror, lint, exact-head cross-family review, required CI and deployed SHA/public
canary gates; no broad architecture re-review or full local suite is required.

Live acceptance is **dependent on root's authorization of the second account**
after general connection-removal/onboarding/tool-parity fixes and clean free-only
sign-in proof. Do not access that account now. Then two independently authenticated
users, through ordinary rendered conversations, author their own receiver and
sender loop, permit/link, execute two sends, inspect receipts and receiver outcome,
and demonstrate denied unauthorized/revoked sends without operator graph edits.
Keep the devices-off/cloud-execution premise explicit. Same-owner fixtures and
canaries support safety but cannot replace two-owner rendered proof. Even a full
JSON/RPC live pass does not close capability 6 until exact file transfer and the
remaining receiver-retry requirement are implemented and accepted.

## Decision requested from root

Approve this bounded RPC-first shape for a subsequent implementation assignment,
or direct the next builder to the larger file-binding/reservation boundary.
No runtime edits, peer dispatch, tests, push or production changes were performed
for this architecture-only task. Root authorized a proposal-only commit and a
prepared review brief; actual peer dispatch waits for root's single-slot queue.
