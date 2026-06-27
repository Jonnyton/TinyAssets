# Daemon Memory Architecture: Mini OpenBrain + Observable Wiki

## Status

Accepted direction with an additive runtime slice landed on
`codex/daemon-memory-governor` in May 2026. This extends the current daemon
wiki memory governor; it does not copy OB1/Open Brain code and does not add a
new hosted dependency. Formal pytest coverage, plugin mirror sync, and public
tool/API exposure remain blocked behind the current #18 runtime/test lock.

## Decision

Each soul-bearing daemon should own a private, daemon-scoped memory system with
three distinct surfaces:

1. `soul.md`: durable identity contract.
2. Daemon wiki: curated, human-readable self-model, policies, claims, failures,
   and soul-evolution proposals.
3. Mini brain: atomic, searchable, observable memory entries that the daemon
   can capture, search, review, promote, supersede, and forget under cap.

The normal runtime prompt loads a bounded packet, not the full memory store:

- soul capsule;
- bounded wiki packet;
- top-k task-relevant mini-brain hits;
- memory status, pressure, and trace IDs.

This preserves clean context while letting a daemon learn over time.

## Research Basis

Primary references used in the 2026-05-02 research pass:

- Nate B. Jones / Open Brain / OB1:
  - https://github.com/NateBJones-Projects/OB1
  - https://raw.githubusercontent.com/NateBJones-Projects/OB1/main/server/index.ts
  - https://raw.githubusercontent.com/NateBJones-Projects/OB1/main/schemas/enhanced-thoughts/README.md
  - https://github.com/NateBJones-Projects/OB1/blob/main/docs/01-getting-started.md
- MemGPT / Letta:
  - https://arxiv.org/abs/2310.08560
  - https://docs.letta.com/
- LangGraph memory:
  - https://docs.langchain.com/oss/python/langgraph/add-memory
- Mem0:
  - https://docs.mem0.ai/open-source/overview
  - https://arxiv.org/abs/2504.19413
- Zep / Graphiti:
  - https://github.com/getzep/graphiti
  - https://help.getzep.com/v2/understanding-the-graph
- Reflection and agent learning:
  - https://arxiv.org/abs/2303.11366
  - https://arxiv.org/abs/2304.03442
- User-visible/editable memory:
  - https://arxiv.org/abs/2308.01542
- Recent memory-system papers:
  - https://arxiv.org/abs/2603.07670
  - https://arxiv.org/abs/2603.16171
  - https://arxiv.org/abs/2604.04853
- Observable memory and tracing:
  - https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Memory.html
  - https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/
  - https://docs.langchain.com/langsmith/observability-concepts

## What To Borrow

Open Brain's useful pattern is not Supabase or OpenRouter specifically. The
useful pattern is:

- one durable memory backend;
- vector search plus structured metadata;
- small MCP-like tool surface;
- atomic standalone entries rather than giant notes;
- content fingerprints for dedupe;
- import/review/promote workflows;
- wiki or Obsidian-style notes as a frontend/import source, not the backend.

MemGPT/Letta reinforces the hierarchy: current prompt context is scarce, so the
agent needs a mechanism for moving useful information between prompt context,
recall storage, and archival storage.

Graphiti/Zep reinforces provenance and time: derived facts should point back to
episodes, and changing facts should be superseded rather than silently erased.

MemMachine and MemX reinforce two implementation choices that fit TinyAssets:
preserve enough raw ground truth to audit derived memory, and combine vector
retrieval with keyword/structured filters plus low-confidence rejection.

Memory Sandbox and observable-memory products reinforce the user/host control
requirement: memory needs to be inspectable, editable, and replayable. Bad
memory is worse than no memory.

## TinyAssets-Native Architecture

### Layer 0: Run Scratch

Per-run working state. It dies with the run unless a node/gate outcome records
it as a signal. Scratch is not daemon memory.

### Layer 1: Raw Episodes

Immutable source events:

- node/gate pass, fail, block, cancel;
- work considered/chosen/declined;
- verification results;
- claim proof additions;
- host-authored notes;
- borrowed-soul executions.

Raw episodes live as compact wiki records or DB rows with pointers to large
artifacts. They are ground truth for later memory extraction.

### Layer 2: Atomic Mini-Brain Entries

The daemon-controlled searchable store. Entries are small, standalone, and
typed. They are not prompt preload.

Recommended fields:

- `entry_id`
- `daemon_id`
- `memory_kind`: `semantic`, `episodic`, `procedural`, `policy`, `claim`,
  `preference`, `failure_mode`, `open_loop`, `contradiction`, `soul_proposal`
- `content`
- `content_fingerprint`
- `source_type`, `source_id`, `source_path`
- `source_hash`
- `reliability`
- `temporal_bounds`
- `language_type`
- `confidence`
- `importance`
- `sensitivity_tier`
- `visibility`: `host_private`, `borrowable_role_context`, `published`
- `promotion_state`: `candidate`, `accepted`, `promoted`, `superseded`,
  `rejected`
- `supersedes_entry_id`, `superseded_by_entry_id`
- `created_at`, `updated_at`

These fields intentionally align with the project hard rule that extracted
facts carry source type, reliability, temporal bounds, and language type.

### Layer 3: Derived Indexes

Indexes are acceleration structures, not truth:

- SQLite table is the canonical mini-brain store.
- SQLite FTS/BM25 handles exact and keyword search.
- Existing LanceDB singleton handles semantic vector retrieval.
- A small relationship graph can be added later for entities, contradictions,
  claims, and temporal facts. Do not start with a general graph database.

All indexes must be keyed by `daemon_id`. Cross-daemon search is denied by
default.

### Layer 4: Curated Wiki

The wiki is the maintained face of the daemon's learning:

- `pages/self-model/current-self.md`
- `pages/decisions/decision-policy.md`
- `pages/signals/learning-signals.md`
- `pages/soul-evolution/proposals.md`
- `claim_proofs/`
- `soul_versions/`
- future `pages/brain/review.md`

The wiki gets updated through promotion, not raw capture. A daemon can propose
wiki changes, but those changes should cite memory IDs and source episodes.

### Layer 5: Bounded Runtime Packet

Prompt composition should be a read policy:

1. Load soul capsule.
2. Load bounded wiki packet from `tinyassets/daemon_memory.py`.
3. Generate a task-specific memory query from the node/gate contract, daemon
   role, recent failure state, and current branch context.
4. Retrieve candidate mini-brain entries by structured filters, FTS, and vector
   search.
5. Rerank by relevance, reliability, recency, importance, source quality, and
   contradiction status.
6. Inject only the top-k entries with IDs and source labels.
7. Log what was injected and what was rejected.

Low-confidence retrieval should inject nothing and say so. Silence is better
than context pollution.

### Layer 6: Observable Memory

Memory observability is first-class. For every daemon run, the system should be
able to answer:

- What did the daemon know before the run?
- Which memory query was generated?
- Which entries were retrieved?
- Which entries were injected into the prompt?
- Which entries were rejected and why?
- Did the daemon cite or ignore the injected memories?
- What new memories were proposed after the run?
- Which proposals were accepted, rejected, promoted, superseded, or compacted?
- Did memory help or hurt the outcome?

This belongs in a local/private telemetry stream by default. Public surfaces
can expose aggregate IDs, counts, hashes, and status, not private content.

Recommended event names:

- `daemon.memory.query`
- `daemon.memory.retrieve`
- `daemon.memory.inject`
- `daemon.memory.write_candidate`
- `daemon.memory.accept`
- `daemon.memory.reject`
- `daemon.memory.promote_to_wiki`
- `daemon.memory.supersede`
- `daemon.memory.compact`
- `daemon.memory.low_confidence_skip`
- `daemon.memory.eval`

Recommended metrics:

- packet chars/tokens;
- wiki bytes, cap bytes, pressure level;
- retrieved count, injected count, rejected count;
- average retrieval score;
- low-confidence skip count;
- contradiction count;
- stale-memory count;
- candidate backlog;
- promotion lag;
- memory-hit outcome correlation;
- compaction removals and unresolved over-cap count.

OpenTelemetry GenAI span conventions can be used for provider/model/run spans,
but TinyAssets should add local custom attributes for daemon memory IDs, pressure,
packet size, and redaction status.

## Write Policy

Do not let every trace become memory. Write candidates must pass filters:

1. Is it durable beyond the current run?
2. Is it supported by a source episode or host note?
3. Is it new, or does it supersede an older memory?
4. Does it affect future decisions, retrieval, claims, tactics, or safety?
5. Is it safe to store under the daemon's visibility and sensitivity policy?
6. Is it concise enough to remain atomic?

Do not store hidden chain-of-thought, raw provider prompts, secrets, or user
uploads beyond the existing authoritative upload/artifact policy. Store a
pointer, hash, summary, and source metadata when full content is sensitive or
large.

## Manage Policy

Each soul-bearing daemon gets a periodic review ritual:

1. Cluster recent entries by work type, topic, outcome, and failure mode.
2. Find contradictions and stale claims.
3. Promote repeated stable lessons to wiki pages.
4. Convert repeated failure reflections into procedural memory.
5. Convert verified external evidence into claim proofs.
6. Draft soul-evolution proposals only when wiki/policy changes are
   insufficient.
7. Mark noisy or obsolete entries as superseded or summarized.
8. Run the memory governor.

This is how a daemon self-evolves without bloating context or mutating its soul
after one bad run.

## Read Policy

Memory retrieval should be conservative:

- prefer recent verified failures when doing similar work;
- prefer promoted wiki policy over raw candidate thoughts;
- prefer source-backed entries over self-asserted entries;
- include contradicted entries only when the contradiction is relevant;
- keep borrowed-role memory separate from executor identity;
- include source IDs so the daemon can cite what it used;
- enforce the 8k soul/wiki/brain overhead budget.

The prompt should tell the daemon that retrieved memory is evidence, not
authority. Soul, node contract, source truth, and tests still win.

## Borrowed Role Context

Borrowing a core-team soul or wiki packet is not copying identity.

If a community or house daemon runs a node under borrowed role context:

- executor identity remains the executor's own daemon identity;
- borrowed soul/wiki/brain entries are cited as role context;
- writes about executor behavior go to the executor daemon;
- role-learning signals may also be routed back to the borrowed role daemon
  when the node contract allows it;
- fixed model eligibility remains enforced by the node contract.

This keeps the v1 loop team unique while allowing community capacity.

## Minimal Tool Surface

Future `tinyassets/daemon_brain.py` should expose a small internal/tool surface:

1. `capture_daemon_memory`
2. `search_daemon_memory`
3. `list_daemon_memory`
4. `review_daemon_memory`
5. `promote_daemon_memory_to_wiki`
6. `memory_observability_status`

Avoid one tool per table. Tools should operate at the daemon memory concept
level, not database mechanics.

## Landed Runtime Slice

The first implementation adds:

- `tinyassets/daemon_brain.py` with daemon-scoped SQLite entries, FTS search,
  content fingerprint dedupe, observable memory events, promotion records, and
  optional LanceDB indexing when an embedding is supplied.
- bounded mini-brain hit injection in `tinyassets/daemon_memory.py`, preserving
  the existing packet cap and reserving brain budget when a task-specific query
  is supplied.
- non-destructive daemon wiki scaffolding for `pages/brain/review.md` using
  write-if-missing semantics, so existing daemon wiki files are not rewritten.
- `scripts/proofs/daemon_brain_smoke.py`, an executable proof kept outside
  `tests/` until #18 releases that tree.

## Remaining After #18

1. Focused pytest coverage landed in `tests/test_daemon_brain.py`; the smoke
   script remains as an operator CLI proof.
2. Plugin mirror parity is green; `tinyassets/daemon_brain.py` is present in the
   packaged Claude plugin runtime.
3. Minimal daemon-owned `universe` action surface landed:
   `daemon_memory_capture`, `daemon_memory_search`, `daemon_memory_list`,
   `daemon_memory_review`, `daemon_memory_promote`, and
   `daemon_memory_status`; `control_station` routes chatbots to those
   actions with `inputs_json` / `daemon_id` guidance.
4. Memory quality evals landed as an internal replay harness:
   `evaluate_daemon_memory_quality` runs deterministic without-memory and
   with-memory cases against selected entries, scores the outcome delta, and
   records `daemon.memory.eval`.
5. Add a host review/editor surface for richer memory inspection and
   correction beyond the action-level review primitive.

## Later

- Relationship graph for claim, contradiction, and temporal fact edges.
- Host dashboard/editor for reviewing daemon memories.
- Domain-specific memory quality eval suites that plug real run replayers into
  the internal replay harness.
- Cross-daemon published memories with explicit visibility, attribution, and
  borrow contracts.
- Role-daemon review rituals for the community loop core team.

## Guardrails

- No one flat memory pool.
- No prompt preload of the whole wiki or brain.
- No direct OB1 dependency without license and architecture review.
- No Supabase/OpenRouter requirement for default TinyAssets memory.
- No LanceDB connection churn; use the singleton.
- No automatic soul rewrite from memory.
- No silent soul copying.
- No unobservable memory injection.
- No public exposure of private daemon memory by default.
