# Shape review disposition — lead decision pending

2026-09-19. Independent Fable 5.1 reviewed exact
`3ce73a2a399be74944a28ff2325b546f7f48c6ed`, session 29752, terminal exit 0 after
470 seconds. Full assistant output is retained verbatim in `shape-review.md`.
**ADAPT**, not approval to implement. No runtime, account, user design or live
workflow was changed. This receipt commit does not relabel review as exact-head
approval of later edits.

## Supported direction and concrete decisions for lead

- Reuse public composition/private binding plus governed published graph, not
  another runtime/catalog. Self-contained multi-step graph first; reject both
  invoke variants and unresolved executable references. Engine-tool strategy
  currently has exactly one prompt node (`shared_self.py:14-28`), unlike ordinary
  multi-prompt graphs; document that limit. Explicit separately authorized tools
  remain effects, not invented immutable dependencies.
- Use the existing runs database reservation and `_insert_run_in_transaction`
  (`runs.py:1468-1492`) atomically, not conversation best-effort persistence or
  the epoch-2 RequestAdmissionStore queue. Owner/universe/session-scoped key,
  digest, captured selection, one reserved run and terminal/projection status
  need a reviewed table/API contract before implementation.
- Capture validated preference DATA/generation, derive fresh run authority per
  use. Do not substitute a converse carrier or model-plan capability. Preserve
  user ordering and budget checks; graph preferences cannot add authority.
  Actual result attribution must name its producer, not first response/default.
- Preserve trusted explicit install/disable/rollback and engine-channel refusal.
  A current owner principal alone cannot distinguish human consent from agent
  activity. Public source definitions never inherit creator grants.

## Evidence-based qualifications (do not adopt stale premises)

1. Reviewer cites `storage/request_admissions.py:105` for in-process code nodes.
   That is a stale explanatory docstring, contradicted by actual
   `graph_compiler._build_source_code_node:1993-2040`: OS child sandbox, fail
   loudly without bwrap, and foreign-code provenance refusal. Receiver-authored
   code via remix is already required there. A receiver-authored active v1
   restriction may reuse that provenance boundary; missing code confinement is
   not a verified reason to impose it. Source ownership alone is not code safety.
2. Reviewer infers agent install writes from the presence of `write_graph`.
   Actual `engine_mcp_server.py:1671-1678` already rejects `agent_binding`;
   `served_tools.py:34-36` explicitly says broad binding mutation unavailable.
   Preserve/test this existing refusal when adding selection. No current bypass
   was established by that citation; arbitrary public connector callers remain
   subject to their ordinary authenticated authority.
3. Reviewer says top-level version runner has no local authorization check.
   `_action_run_branch_version:2171-2246` does call the runner without a visible
   version-owner check in that helper. The proposed new consumer must explicitly
   authorize before loading, regardless of outer canonical routing checks. This
   bounded inspection is not a declaration of an exploitable existing route.
4. Recursion is structurally excluded by the current served tool set lacking
   `converse`; preserve that boundary. Never reinterpret comparison lineage as
   causal ancestry. Cloud lane owns causal execution-family root/epoch if needed.

## Remaining transaction details to settle, not optional hardening

- The suggested terminal path writes conversation rows then marks the runs row
  committed. A crash between those writes will duplicate history unless the
  conversation pair has a durable unique canonical-turn projection key. This
  dedupe is REQUIRED for exactly-one projection, not the review's optional
  follow-up. Observation/reconciliation must never rerun effects.
- The suggested digest includes history-tail hash. Reconnect must compare stable
  client request content and reuse the captured history hash, not recompute a
  new history digest and reject the original request after unrelated turns.
  Keep immutable admission context separate from replay-supplied fields.
- Define empty node fallback policy versus explicit exclusions before adopting
  literal fallback-chain intersection; absence must not silently discard the
  user's authorized fallback order. Confirm actual producer attribution for
  derived/combined output without inventing a single producing model.
- Canonical reservation must name the SAME admitted run identity as the file
  lane's `run_input_admissions`/manifest and cloud lane's family root/epoch.
  Coordinate column/table ownership before builds; no parallel authority queue.
- Review mentions two `converse` parameters and a pending envelope but does not
  name their schema. Lead must approve an explicit minimal public contract and
  migration/retention/cancellation behavior before implementation.

No PLAN conflict was found. Arbitrary UI, nested/foreign harness loading, full
setup migration and two-owner live consumption remain unproven/unsupported.
Layout-only proof is separate. Root assesses these material storage/API choices.
