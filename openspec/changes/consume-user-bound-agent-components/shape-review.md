I'll perform this bounded shape review myself, read-only, starting with the change directory and then the cited runtime seams.

One last check: whether the version-run entry point itself authorizes the pinned version's branch for the requester, since the adapter's "access checks precede snapshot load" claim depends on it.

Review complete. I inspected the change's six artifacts and the cited runtime seams read-only, altered no files, and dispatched no peers (the brief forbids recursion). Answer follows.

## Shape answer

One receiver-selected immutable Branch as the canonical turn handler is the right smallest consumer beyond the layout MVP. It reuses the existing executor, binding store, and snapshot store with no parallel runtime or catalog. It is not implementable as drafted: two primitives the design leans on do not exist, and two safety narrowings are needed. Details per question, then the three concrete choices.

**Q1. Reuse and scope: AGREE, with one DISAGREE_CONCERN on strategy breadth.**

- **No duplicate consumer exists.** Every current caller of a pinned version is a different trigger with a different sink: the advertised version run at `tinyassets/api/runs.py:2171`, scheduler ticks passing the schedule-row principal at `tinyassets/api/runs.py:65-73`, Goal route-back at `tinyassets/api/canonical_dispatch.py:170-179`, and child nodes at `tinyassets/graph_compiler.py:2860`. None is admitted by the canonical turn or writes the canonical reply. The served writer can already call `run_graph` (`tinyassets/served_tools.py:113-124`), but the persona writer still authors the reply and learning still runs at `tinyassets/universe_intelligence.py:1102-1131`. The adapter replaces the author of the turn, which nothing does today.
- **It permits user-authored strategy, not a renamed writer.** A snapshot carries multiple prompt nodes with per-node model policy and fallback chains (`tinyassets/foreground_run_provider.py:469-479`), code nodes, and an engine-tool agent node.
- **DISAGREE_CONCERN on breadth.** A graph that requests the universe's engine tools must have exactly one prompt node (`tinyassets/shared_self.py:14-28`). So "multi-step control plus ordinary tools" is narrower than the design states: tool-using harnesses are single-prompt-node graphs. Document this as a v1 limit, not a blocker.
- **Unsupported cases are correctly excluded.** Executable UI, foreign harness loaders, and setup migration stay inert. The layout reader rejects any extra field (`tinyassets/onboarding/app_layout.js:36-42`); the turn contract's "field names only" mirrors it.

**Q2. One-user and second-owner safety: AGREE on the identity model, DISAGREE_EVIDENCE on install consent, DISAGREE_CONCERN on provenance.**

- **Receiver-owned and latest-updater checks work on existing columns.** Bindings record `created_by` and `updated_by` and CAS on revision (`tinyassets/custom_agents.py:1042-1046,1194-1228`). A write collaborator may update the owner's binding (`tinyassets/api/custom_agents.py:49-79`), which flips `updated_by` and correctly holds the selection. Resolve "one eligible binding" server-side with a bounded exact query like `serving_binding_candidates` (`tinyassets/custom_agents.py:1084-1102`), never the 100-row list the layout controller already refuses on saturation.
- **Current authority holds per attempt.** Founder home, serving binding, run status, immutable subject, and cancel flag are rechecked on every provider attempt (`tinyassets/foreground_run_provider.py:159-190,703-727`). Revocation after install refuses the next use.
- **DISAGREE_EVIDENCE: binding CAS alone is not install consent.** The served agent's tool list includes `write_graph` (`tinyassets/served_tools.py:117`), and its engine identity is the founder principal (`tinyassets/universe_intelligence.py:307-309`). An agent-initiated binding update therefore records `updated_by` as the founder, indistinguishable from a click in the trusted UI. Browsed commons content can steer that agent. The existing precedent is the reviewed allowlist for served automation writes (`tinyassets/served_tools.py:126-128`). Obligation: consumer-selection writes from the engine-tool channel are refused in v1, detected from request state, not principal. Do not invent a grant; the pending-request path is the later home if agent-initiated installs are ever wanted.
- **DISAGREE_CONCERN: foreign-authored execution of the private conversation.** The design feeds founder message plus receiver history into the pinned graph. Code nodes run user-supplied source in-process (`tinyassets/storage/request_admissions.py:105-106`), and the OS sandbox concern is still open. The version-run entry point performs no visibility or ownership check on the pinned version (`tinyassets/api/runs.py:2237-2246`; only universe-bound run reads check visibility). The design's claim that "public graph access checks precede loading the snapshot" has no code behind it for a top-level version run. Narrowing below.
- **Disable and rollback** as CAS updates surfacing `agent_conflict` (`tinyassets/api/custom_agents.py:384-385`): AGREE.

**Q3. Canonical turn feasibility: AGREE on history, actor, closure, cancellation, recursion. DISAGREE_EVIDENCE on model policy and on exactly-one terminal reply.**

- **History and actor.** Same session key `principal:<actor>` (`tinyassets/universe_server.py:2451-2455`) passed as a typed input. Run actor is `universe:<uid>` (`tinyassets/api/permissions.py:366-370`) with the founder as principal, as expected.
- **DISAGREE_EVIDENCE: no path carries the current-turn model choice into run admission.** The converse plan requires a converse carrier (`tinyassets/providers/served_model_plan.py:418-446`); the run session refuses any context carrying `agent_model_plan` or `model_selection` (`tinyassets/foreground_run_provider.py:851-856`; `tinyassets/workflow_agent.py:43-53`). Run-side selection reads only node policy `preferred` and a single provider/model snapshot (`tinyassets/foreground_run_provider.py:730-740`; `tinyassets/providers/work_model_selection.py:10`). Neither module reads the preference store. Without the bridge, the "user changes model for the current turn" scenario and the PLAN Providers clause both fail.
- **DISAGREE_EVIDENCE: no durable admission exists.** `converse` takes no request key (`tinyassets/universe_server.py:2312-2317`); the async version run returns `queued` at once (`tinyassets/runs.py:4786-4789`); conversation rows are written after execution and best-effort (`tinyassets/universe_server.py:2508-2516`); the pair writer has no `ext_id` dedupe (`tinyassets/conversation_store.py:417-419`); the receipt normalizer rejects any key beyond provider/model/status (`tinyassets/providers/execution_receipt.py:28`), so a run id cannot ride in `execution_json`. Comparison lineage is confirmed non-causal (`tinyassets/runs.py:2611-2613,2653-2660`).
- **Cancellation** is advertised (`tinyassets/universe_server.py:1574-1593`) and checked per attempt. Child propagation is absent (`tinyassets/runs.py:4968-4977`), moot under the self-contained rule.
- **Recursion** is already structural: `converse` is not on the engine tool list, so descendant work cannot re-enter the canonical handler. Document it; do not build an ancestry check for v1.

## Concrete choices

- **(a) Self-contained graph, and receiver-authored.** Reject both `invoke_branch_spec` and `invoke_branch_version_spec` at install and re-scan at admission. The live-child resolution at `tinyassets/graph_compiler.py:2768` and the selector-purity precedent at `tinyassets/daemon_server.py:3536-3570` give the rationale. Additionally admit only a version whose snapshot `author` equals the receiver principal (hashed, `tinyassets/branch_versions.py:216`) with `status == active` (precedent `tinyassets/daemon_server.py:3513-3528`). Public content is consumed by copy or remix into the receiver's own universe first, which existing branch publish/remix already supports and which matches the founder's "public is a shape, not a service" rule. This does NOT complete direct execution of a foreign-authored snapshot; that waits on code-node confinement.
- **(b) Reservation home is the runs database, same transaction as the run row.** The run insert seam is explicitly built to commit "alongside a durable intent in its caller-owned transaction" (`tinyassets/runs.py:1485-1492`). The dark request-admissions store is an inactive epoch-2 control plane; borrow its typed idempotency-hash pattern, not the store. The per-universe conversation file is best-effort by contract and cannot be the admission home. Minimal row: owner principal, universe id, session id, client request key, request digest (message, input method, model-choice document, history tail hash), binding id and revision, definition id and component key, branch version id and content hash, run id, state (reserved, running, terminal, committed), and the committed conversation turn number. Obligations: reserve and insert the run in one transaction before any provider attempt, unique on owner/universe/session/key; on terminal, write the conversation pair then mark committed, and reconcile an uncommitted terminal from run output without re-running; a reconnect with the same key returns state and never admits a second run; a send without a key is a new request. `converse` needs two parameters and a pending envelope, a public-surface delta already in scope.
- **(c) Preference data bridge, narrow.** Capture the validated model-preferences document and its generation into the reservation row at canonical admission. Where run admission derives `preferred`, take the first candidate from the turn preference that the node policy does not exclude, with fallbacks as the intersection of the turn's ordered fallbacks and the node's chain; conflicts refuse. Recompute the invocation allowance at `tinyassets/foreground_run_provider.py:469-479` from the effective chain. The receipt must come from the node producing the declared output field, not the first completed response (`tinyassets/providers/execution_receipt.py:51-57`).

No PLAN conflict found. Daemon Platform's "executes only kinds backed by installed, governed adapters" and Scoping Rule 1's "parameters under canonical handles" both cover this shape.

## Blockers and follow-ups

Release blockers to this first adapter:

1. Durable canonical admission per choice (b). Irreducible missing storage primitive.
2. Preference data bridge per choice (c). Irreducible missing primitive; also blocks honest model display.
3. Refuse consumer-selection writes from the served-agent channel.
4. Receiver-authored, active, self-contained version only, with the adapter performing its own authorization since the version runner does not.

Optional follow-ups:

- Fix the proposal's stale paths: the binding store, snapshot store, conversation store, and run provider live at the package root, not under `api/` or `storage/`. Line numbers matched the root modules.
- Document the single-prompt-node limit for tool-using graphs.
- Add `ext_id` dedupe to the pair writer and extend the receipt normalizer to link a run id once the reservation exists.
- The dated agent-spec drift concern stands; nothing here regresses current engine tools.

VERDICT: ADAPT

Checked: none of the listed dispatches belong to this worktree (no output files here, tree clean), and this session's brief is explicitly read-only with no file edits, no peer dispatch, and no other lanes, so re-dispatching or dropping another session's jobs is outside what I am authorized to do here. The review verdict above is the complete deliverable for this session; there is honestly nothing else to advance within its constraints.
