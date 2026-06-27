---
status: active
---

# Track N — Vibe-Coding Node Authoring + Sandbox

**Date:** 2026-04-19
**Author:** dev (task #67 pre-draft; navigator drift-audit #64 flagged this as missing spec)
**Status:** Pre-draft spec. No code yet. Executable on dispatch without design re-research.
**Source of truth:**
- `docs/design-notes/2026-04-18-full-platform-architecture.md` — §27 node-authoring surface, §14 scale, §17 privacy.
- `docs/specs/2026-04-18-full-platform-schema-sketch.md` — `nodes` table, `concept` / `instance_ref` split.
- `docs/specs/2026-04-18-mcp-gateway-skeleton.md` — MCP tool-call routing.
- `docs/catalogs/privacy-principles-and-data-leak-taxonomy.md` — §7 daemon-execution system-point inspected by `inspect_leak_risk`.
- `docs/specs/2026-04-18-remix-and-convergence-detail.md` — `parents uuid[]` lineage bridged by `fork_and_remix`.
- Memory `project_abc_followup_onboarding_transparency_privacy.md` (B-follow code-visibility-one-surface).
- Memory `project_node_software_capabilities.md` (host-registered capabilities; §5 required_capabilities).

Track N is the **largest remaining design-surface** (design note §27.8 estimate ~2.5–4d full / ~2d MVP-narrowed). This spec is the executable plan.

---

## 1. Responsibilities boundary

### Owns

- **`/node_authoring.*` MCP tool family** — 9 tools (listed in §2), each a gateway entry point.
- **Draft-session state** — `node_authoring_sessions` table tracking in-flight author sessions with ephemeral lifetime (§7).
- **Sandboxed runtime** for `test_run` — Supabase Edge Function with resource quotas, filesystem jail, network allowlist (§3).
- **Code-view adapter** — serialization of the node's concept/harness/tools as readable code at three granularities (full / diff / summary).
- **Dry-run orchestration** — executes a node without real side-effects; connector pushes stay simulated; returns deltas only.
- **Test-run vs commit boundary** — test-run results never promote a draft to published; commit is explicit.
- **Leak-risk inspection** — reads §31 privacy catalog + the draft's concept/tools/IO manifest; emits per-field risk annotations.

### Delegates

- **Publish/commit** to `nodes` table via `publish_node` RPC (schema spec #25 §1.4). Track N calls it; it does not own the table.
- **Sandboxed execution isolation** to Supabase Edge Functions infrastructure (Deno runtime + platform quotas). Track N does not reinvent process-level isolation.
- **Remix lineage tracking** to §15.3 RPCs (`remix_node`, `converge_nodes`). Track N's `fork_and_remix` is a thin bridge.
- **Tier-2 local REPL** to tray-daemon surface (spec #30). Track N provides the *protocol*; daemon-host tray ships the *terminal adapter*.
- **Tier-3 native-code PR flow** to `TinyAssets-catalog/` export-sync path (spec #32). Track N provides no tooling here — T3 users use git.

### Not-track-concerns (explicit non-goals)

- **No in-browser IDE.** Code-view is chat-rendered text + diff; nothing fancier at MVP.
- **No multi-user collab-edit on a single draft.** Sessions are single-user; fork for parallel exploration.
- **No version-control beyond the session.** Once committed, `nodes.version` + `parents uuid[]` handle history. Within-session history is best-effort (undo-last-N-edits, not full git).
- **No background test-runs.** `test_run` is synchronous + sandboxed; background/long-running work belongs to the real node execution path after publish.

---

## 2. The `/node_authoring.*` MCP tool family

All tools accept `bearer_token` (resolves to `user_id`) and reject unauthenticated calls. All mutate state only inside the authenticated user's own draft sessions.

### 2.1 `start_session`

```
node_authoring.start_session(
  base_node_id: uuid? = null,       # fork existing published node
  concept_sketch: str? = null,      # or: natural-language starting point
  parent_session_id: uuid? = null,  # or: resume from a prior session
) -> { session_id, draft_concept, draft_harness, draft_tools }
```

**Exactly one of `base_node_id` / `concept_sketch` / `parent_session_id` must be set** (validated at gateway). Returns the seeded draft state.

`base_node_id` path: loads the published node's concept + tools (public) but NOT its `instance_ref` (owner-only RLS). Sets `parents[0] = base_node_id` for lineage.

`concept_sketch` path: emits an empty-skeleton draft with the sketch text preserved in `concept_sketch` field. Chatbot populates via `edit` calls.

`parent_session_id` path: resumes a prior session within its TTL (§7). Outside TTL → 410 gone.

### 2.2 `show_code`

```
node_authoring.show_code(
  session_id: uuid,
  view: 'full' | 'diff' | 'summary',
  since: session_event_id? = null,  # for 'diff': anchor point
) -> { code: str, metadata: {...} }
```

**`full`** — renders the entire draft as structured pseudo-code (see §4 rendering format). Chatbot shows verbatim in a code block.

**`summary`** — renders a natural-language summary of the node's shape: "This is a 3-step pipeline: input validates a string, LLM extracts fields, output writes to CSV. Uses OpenAI GPT-4 as the model." Target audience: T1 users who asked a casual question.

**`diff`** — renders unified-diff-style output of changes since `since` (defaults to session start). Anchored to session event log (§7). Target: T2 users mid-iteration inspecting what the chatbot just did.

Rendering is *adapter-driven* — the chatbot passes user-signal hints to `view`, the tool emits the right granularity. Code visibility is **one surface, adaptive exposure** per B-follow memory. No user-visible "simple mode" / "dev mode" toggle.

### 2.3 `edit`

```
node_authoring.edit(
  session_id: uuid,
  edit_ops: list[EditOp],
) -> { applied: [event_id, ...], rejected: [...], draft_after }
```

`EditOp` types (enum):
- `declare_state { name, type, default?, reducer? }`
- `remove_state { name }`
- `attach_tool { name, kind, signature, impl_ref }`
- `remove_tool { name }`
- `declare_graph { nodes, edges, entry_point }`
- `compose_subnode { name, source_node_id, input_mapping, output_mapping }`
- `declare_io { kind: 'input'|'output', manifest }`
- `set_concept_field { path: JSONPath, value }` — generic escape hatch.

Batched — chatbot sends multiple ops in one call; platform applies atomically (all-or-none per call). Each applied op gets an `event_id` recorded in session-event log; `diff` view anchors here.

Rejected ops carry a reason code (`invalid_type`, `cycle_in_graph`, `unknown_subnode`, `signature_mismatch`).

### 2.4 `test_run`

```
node_authoring.test_run(
  session_id: uuid,
  inputs: dict,
  dry: bool = true,                 # default: simulate side-effects
) -> {
  status: 'ok' | 'error' | 'timeout' | 'quota_exceeded',
  outputs: dict,
  simulated_effects: [{kind, target, payload}, ...],
  trace: [{node, phase, duration_ms, ...}, ...],
  resources_used: {cpu_ms, memory_peak_mb, wall_ms, net_bytes},
}
```

**`dry=true`** — connector pushes, file writes, emails, subprocess invocations all captured in `simulated_effects` but not executed. This is the default. Returns *what would have happened*.

**`dry=false`** — real execution. Still sandboxed (§3), but actual external calls fire. Reserved for final validation before commit; requires explicit user confirmation chatbot-side.

**Both modes** — execute inside the sandbox (§3). Resource limits enforced; `quota_exceeded` returned if caps hit.

Test-runs do **not** commit the draft. Commit is explicit (§2.6). Test-run output is for chatbot+user to read; no persistent storage beyond the session event log.

### 2.5 `inspect_leak_risk`

```
node_authoring.inspect_leak_risk(
  session_id: uuid,
) -> {
  concept_level_risks: [{field, risk_tag, severity, category}, ...],
  tool_level_risks: [{tool_name, risk_tag, severity}, ...],
  graph_level_risks: [{edge, risk_tag, severity}, ...],
  summary: str,
  catalog_refs: [url, ...],
}
```

Reads the draft's current shape + the §31 privacy catalog's system-point taxonomy. Returns annotations the chatbot can narrate to the user.

Risk tags come from the §31 catalog's 5 leak categories (§2 of that catalog — credential leak, instance-data leak, cross-user bleed, connector over-scope, training-data drift).

Used by the chatbot during §29.2 transparent-privacy-reasoning behavior ("here's what I'm marking private, here's why").

### 2.6 `commit`

```
node_authoring.commit(
  session_id: uuid,
  message: str,
  visibility: 'public' | 'private' = 'public',
  license: 'CC0-1.0' | 'MIT' = 'CC0-1.0',
) -> { node_id, version, status }
```

Validates the draft:
- All declared state fields reachable in graph.
- All declared tools referenced by at least one node.
- Graph has entry_point + at least one terminal node.
- No cycles unless explicitly declared in eval-loop pattern (see `integration-patterns.md` §2.3).
- `inspect_leak_risk` has no `severity: 'high'` unresolved annotations — if any present, returns `{status: 'blocked', blockers: [...]}` and chatbot must narrate + user-dismiss before re-commit.

On pass: writes to `public.nodes` via `publish_node` RPC. Returns the new `node_id` + starting `version=1`. Session transitions to `committed` and becomes read-only (but still viewable via `show_code` for audit).

`parents uuid[]` is populated from the session's initial base_node_id + any `compose_subnode` source_node_ids encountered in the draft.

### 2.7 `fork_and_remix`

```
node_authoring.fork_and_remix(
  source_ids: list[uuid],
  new_concept_sketch: str,
) -> { session_id, draft_concept, draft_harness, draft_tools, merged_parents }
```

Starts a session that inherits from multiple published nodes at once — the §15.3 remix primitive. The platform merges concepts by:
1. Union of declared state fields; name-collisions → prefix with `<source_node_id>_` and leave for chatbot to rename via `edit`.
2. Union of tools; name-collisions → same prefixing rule.
3. Graphs are **not** auto-merged — chatbot constructs the new graph via `declare_graph` ops. Source graphs are included in the `show_code` output as reference panels.

`merged_parents` is the deduplicated list written as `parents uuid[]` on commit.

### 2.8 `abandon_session`

```
node_authoring.abandon_session(session_id: uuid) -> { ok: true }
```

Soft-deletes the session (tombstone with 30-day retention for audit). After tombstone TTL, session_id is gone. Used when the user says "nevermind, scrap this." Chatbot-initiated.

### 2.9 `list_sessions`

```
node_authoring.list_sessions(
  status_filter: ['active', 'committed', 'expired', 'abandoned']? = ['active'],
  limit: int = 20,
) -> { sessions: [{session_id, created_at, status, concept_summary, parent}, ...] }
```

Scoped to the authenticated user. No cross-user visibility. Chatbot uses this to answer "what was that thing I was working on yesterday?"

---

## 3. Sandbox execution model

### 3.1 Isolation tier

Supabase Edge Functions (Deno runtime) are the primary sandbox. Each `test_run` spawns a fresh Edge Function invocation with:
- **Process-level isolation** — Deno process per invocation; crashed invocations don't affect sibling test_runs.
- **Filesystem jail** — no host filesystem access; only a scratch `/tmp` path inside the Deno VM. Host files are opaque.
- **Network allowlist** — outbound HTTPS restricted to a declared list (per-node `allowed_domains` field in concept, validated at commit). No arbitrary network egress.
- **Resource limits** — CPU 5s, memory 256 MB, wall-clock 30s, net egress 10 MB per invocation. Configurable per-user-tier later (MVP: single tier).

### 3.2 Sandboxed primitives

What the sandboxed node code *can* call:
- **Limited stdlib** — Deno's safe-by-default stdlib (no FS writes outside /tmp, no child_process).
- **Platform primitives** — `workflow.read_concept_field(path)`, `workflow.write_concept_field(path, value)`, `workflow.log(msg)`, `workflow.request_llm(provider, prompt, opts)` — a declared protocol bridging the sandbox to the platform via RPC.
- **HTTP fetch** — `fetch()` gated through the `allowed_domains` allowlist. Any attempt to fetch outside the list returns an error.
- **Time** — `Date.now()` + `setTimeout` OK; real-wall-clock access is expected.

What it *cannot* call:
- **`Deno.open`, `Deno.readFile` outside /tmp** — filesystem access blocked.
- **`Deno.run`, `Deno.Command`** — subprocess spawn blocked.
- **Unrestricted network** — bare `fetch()` without going through allowlist gate is blocked by the Deno `--allow-net=<list>` flag.

### 3.3 Python-IR option (Q18-nav recommendation)

Navigator Q18 recommended a **Python-sandboxed IR** as the primary primitive (matches the rest of the stack; Deno is a departure). Either works; recommendation per design note §27.4 is Deno Edge Functions for MVP because Supabase already ships them, and the engineering cost of building Python-in-gVisor-or-similar is substantial (~2d addition).

**Decision:** MVP uses Deno Edge Functions. Post-MVP re-evaluate whether a Python-sandboxed IR is warranted — decision criteria: if ≥50% of committed nodes end up needing Python-ecosystem libraries (pandas, numpy, scipy) not available in Deno.

**Node-code-language at MVP:** chatbot writes the node logic in TypeScript/JavaScript targeting the Deno runtime. The *platform-facing concept.jsonb* remains language-agnostic — it describes state/tools/graph structurally. Only the harness `impl_ref` (pointer to the actual executable code) is language-specific.

### 3.4 Cost model

Each `test_run` is metered. Edge-Function invocations are cheap (~$0.0001 per invocation at Supabase's current pricing). Per-user quota: 500 test_runs/day at MVP (well above expected authoring usage). Beyond quota returns `quota_exceeded`; chatbot narrates + suggests waiting or upgrading.

Committed nodes execute on **daemon hosts** (§5 required_capabilities), not on the Edge Function sandbox. The sandbox is for authoring-time validation only.

---

## 4. Code-view rendering format

`show_code(view='full')` returns a structured pseudo-code representation:

```python
# Node: fantasy-scene-drafter (draft)
# Session: 7a9e...
# Last edited: 2026-04-19T14:32:00Z
# Parents: [fantasy-scene-refinement@v2]

state:
  prose_so_far: str = ""              # accumulating
  beat_context: dict = {}
  revision_count: int = 0             # reducer: increment

tools:
  llm_draft: call_llm(provider='anthropic', model='claude-sonnet-4-6')
  llm_evaluate: call_llm(provider='anthropic', model='claude-sonnet-4-6', template='scene_eval')

graph:
  entry: draft_step
  draft_step: llm_draft → evaluate_step
  evaluate_step: llm_evaluate →
    - if score >= 0.8: END
    - else: revise_step
  revise_step: increment revision_count → draft_step
    (guard: revision_count < 3)

inputs:
  beat_context: dict  (required)

outputs:
  prose: str
  revision_count: int
```

**Rationale for structured pseudo-code over raw TypeScript:**
- Chatbot can generate/edit structurally without a JS parser in the loop.
- User readability is higher for T1 users — looks like config, not code.
- Commits back to `concept.jsonb` 1:1 (concept IS this structured shape).
- T2/T3 users who want raw TypeScript: `show_code(view='full', format='raw')` — post-MVP addition (~0.25d). Not launched at MVP.

**`summary` view** just narrates the same structure in prose: *"This is a draft→evaluate→revise loop with 3 retries max. It calls Claude Sonnet 4.6 twice per iteration. Input: a beat context dict. Output: prose string."*

**`diff` view** uses unified-diff syntax against the prior session anchor:
```
@@ graph @@
-evaluate_step: llm_evaluate →
-  - if score >= 0.7: END
+evaluate_step: llm_evaluate →
+  - if score >= 0.8: END
```

---

## 5. Test-run vs commit boundary

**Hard rule:** `test_run` never writes to `public.nodes`. No partial-commit, no auto-save-on-success. Commit is *always* explicit via `commit()`.

**Why:** author iteration naturally produces many broken intermediate states. Auto-save would pollute the catalog or require complex "publish only when marked stable" state. Explicit commit matches the user's mental model ("ship it when I'm ready") and avoids the "oops, I published by accident" failure mode.

**Test-run deltas** are captured in the session event log. Chatbot can replay recent test-runs via `show_code(view='diff', since=...)`. Beyond session TTL they're gone.

**Committed nodes** are immutable once published, *except via further authoring sessions that produce new versions* (tracked in `nodes.version`). Rollback is "commit a new version that undoes the change" — there is no in-place edit after commit.

---

## 6. Schema additions

### 6.1 `node_authoring_sessions` table

```sql
CREATE TABLE public.node_authoring_sessions (
  session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id),
  status text NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'committed', 'expired', 'abandoned')),
  base_node_id uuid NULL REFERENCES public.nodes(node_id),
  concept_sketch text NULL,
  draft_concept jsonb NOT NULL DEFAULT '{}'::jsonb,
  draft_tools jsonb NOT NULL DEFAULT '[]'::jsonb,
  draft_graph jsonb NOT NULL DEFAULT '{}'::jsonb,
  merged_parents uuid[] NOT NULL DEFAULT '{}',
  committed_node_id uuid NULL REFERENCES public.nodes(node_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  last_edited_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL DEFAULT (now() + interval '24 hours'),
  abandoned_at timestamptz NULL
);

CREATE INDEX node_authoring_sessions_user_active
  ON public.node_authoring_sessions (user_id, last_edited_at DESC)
  WHERE status = 'active';

CREATE INDEX node_authoring_sessions_expired
  ON public.node_authoring_sessions (expires_at)
  WHERE status = 'active';  -- for reaper job

ALTER TABLE public.node_authoring_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY sessions_owner_only
  ON public.node_authoring_sessions
  FOR ALL
  USING (user_id = auth.uid());
```

### 6.2 `node_authoring_events` table (session event log)

```sql
CREATE TABLE public.node_authoring_events (
  event_id bigserial PRIMARY KEY,
  session_id uuid NOT NULL REFERENCES public.node_authoring_sessions(session_id) ON DELETE CASCADE,
  event_kind text NOT NULL
    CHECK (event_kind IN ('edit', 'test_run', 'inspect_leak', 'show_code')),
  event_data jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX node_authoring_events_session
  ON public.node_authoring_events (session_id, event_id);

ALTER TABLE public.node_authoring_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY events_owner_only
  ON public.node_authoring_events
  FOR SELECT
  USING (session_id IN (SELECT session_id FROM public.node_authoring_sessions WHERE user_id = auth.uid()));
```

Events are append-only; used by `show_code(view='diff')` to reconstruct anchored diffs. Retention tied to session retention (cascade delete on abandon).

### 6.3 No changes to `nodes` table

`nodes.version` + `nodes.parents uuid[]` already exist per schema spec #25. No new columns needed — `commit()` writes through the existing `publish_node` RPC.

### 6.4 Scale concerns (track J reference)

At ~1,000 concurrent authors:
- `node_authoring_sessions` sized at ~10K active rows (10× headroom). Indexed lookups on `user_id` O(log n). Fine.
- `node_authoring_events` append-heavy — ~100 events per session × 10K sessions = 1M rows steady-state. Monthly partition post-MVP if growth warrants.
- Edge Function concurrency — Supabase default is 100 concurrent per region; 1,000 authors test_running simultaneously would queue. MVP acceptance: queued up to 5s; beyond that, chatbot narrates "platform busy, try again." Track J S12 exercises this.

---

## 7. Author-session state lifetime

**Active sessions TTL = 24h from `last_edited_at`.** Each `edit` / `test_run` / `show_code` call touches `last_edited_at`, rolling the window. An author who touches the session daily never expires it.

**Expired sessions** transition to `status='expired'`; draft state retained 7 additional days (read-only via `list_sessions` with status filter) to let users resume or fork abandoned work. After 7 days, soft-delete to tombstone; after 30d, hard delete.

**Committed sessions** transition to `status='committed'`; draft state retained indefinitely for audit (points to the `committed_node_id` for the history trail).

**Abandoned sessions** (explicit `abandon_session` call) transition to `status='abandoned'`; 30-day audit retention, then hard delete.

**Reaper job:** runs every 15 minutes; updates expired sessions; runs daily hard-delete sweep. Simple cron — Supabase scheduled function or Postgres `pg_cron`.

**Design rationale:** ephemeral (not infinite) because drafts accumulate mental overhead for users; stale drafts in `list_sessions` output are clutter. 24h matches "I'll finish this tomorrow" usage but forces a clear abandon/commit decision for anything longer.

---

## 8. Security — sandbox escape + malicious user blast radius

### 8.1 Threat model

- **Malicious user authors a node** with intent to exploit the sandbox (try to read other users' instance data, try to exfiltrate secrets, try to denial-of-service the platform).
- **Malicious user commits a node** with hidden logic that activates on real execution (after publish). This exits track N's concern — belongs to daemon-host sandboxing (§5) and moderation (spec #36).
- **Sandbox escape eventually happens.** Deno is battle-tested but not perfect; assume at some point a zero-day exists.

### 8.2 Defenses

**Authoring-time (pre-commit):**
- Edge Function runs under Supabase's platform-managed isolation. If escape happens, attacker is inside Supabase's platform layer, not the host.
- No access to other users' data even if escaped — the Edge Function invocation only has the authoring user's RLS context.
- Network allowlist enforced at the Deno `--allow-net` flag level, not at application code. Escape past Deno ≠ escape the platform-level firewall rules on Supabase's Edge runtime.
- Resource limits are enforced by the platform, not user code. Infinite-loop or memory-bomb code hits the quota killer.

**Commit-time:**
- `commit()` validation (§2.6) + `inspect_leak_risk` gate catches obvious risks.
- Moderation review (spec #36) — flagged nodes (high-risk tags, reported-by-user) enter admin queue before being searchable in `discover_nodes`. Does NOT block commit itself — Workflow has a published-but-not-searchable tier. See §8.4.

**Runtime (post-commit, not this track's concern but referenced for completeness):**
- Daemon hosts run published nodes in their own sandbox (§5). Each host declares capability acceptance.
- Users opt-in to running 3rd-party nodes on their daemons; default is to only run user's-own-nodes.

### 8.3 What an escape costs us

**Realistic worst case at MVP:** a sophisticated attacker finds a Deno zero-day, escapes the Edge Function, gains arbitrary code execution on Supabase's Edge runtime. They could:
- Read the authoring user's draft_concept (but they already wrote it, so meh).
- Read the `TINYASSETS_V0_DSN` env var (would need to already have platform code-execution to do that — same as a direct Supabase attack, not a Track-N-specific risk).
- Not read other users' data — Edge Function invocations are isolated at the platform layer.

**Mitigations we're explicitly NOT taking at MVP:**
- Running test_run in a *separate VPC* per user. Overkill for pre-commit drafts.
- Requiring 2FA / fresh auth on every `test_run`. Friction too high for the iteration flow.
- Banning certain stdlib primitives. Deno's default posture already bans the dangerous ones.

### 8.4 Published-but-not-searchable tier

New `nodes.search_visibility` column (additive to schema #25):
```sql
ALTER TABLE public.nodes
  ADD COLUMN search_visibility text NOT NULL DEFAULT 'searchable'
    CHECK (search_visibility IN ('searchable', 'queued_for_review', 'removed'));
```

`commit()` writes `'queued_for_review'` if:
- Author is new (account age < 7 days).
- `inspect_leak_risk` had any medium-severity unresolved annotations.
- Node declares high-privilege connector scopes (e.g., `contacts.write`, `admin.*`).

Moderation (#36) promotes to `'searchable'` or demotes to `'removed'`. Author retains full access to their own queued node (can test_run it, invoke it directly by node_id); it just doesn't appear in `discover_nodes` catalog results.

---

## 9. Tier-2 + tier-3 paths (brief)

### Tier-2 (local daemon-host REPL)

Daemon-host tray (spec #30) ships a "node authoring" pane that speaks the same `/node_authoring.*` protocol over a local socket. Differences:
- No Edge Function — test_run runs on the user's own machine with host-declared capabilities.
- Unrestricted stdlib (user's own machine, user's own risk).
- Can `commit()` directly to Supabase via the same RPC — local REPL is just another protocol client.

**Dev-day absorbed by track D (tray).** Track N provides the protocol doc; track D ships the terminal UI.

### Tier-3 (native PR)

Contributor clones `TinyAssets-catalog/` repo, authors a node as a Python module + YAML manifest matching the schema, submits PR. GitHub Actions export-sync (spec #32) publishes to `public.nodes` on merge.

**No track-N code needed.** Pattern is "write the node, make a PR" — git is the authoring surface.

---

## 10. Dev-day estimate

Aligns with §27.8 of design note. MVP-narrowed:

| Component | Dev-days |
|---|---|
| `start_session` + schema (table + RLS + indexes + reaper) | 0.4 |
| `show_code` (full + summary + diff renderers + session event log) | 0.5 |
| `edit` + op dispatcher + validation | 0.3 |
| `test_run` + Deno Edge Function scaffold + platform-primitive bridge | 0.8 |
| `inspect_leak_risk` + §31 catalog integration | 0.3 |
| `commit` + validation gate + `publish_node` integration | 0.3 |
| `fork_and_remix` + merge logic | 0.3 |
| `abandon_session`, `list_sessions` | 0.1 |
| Tests (integration: full author-flow; unit: each tool) | 0.4 |
| **MVP-narrowed subtotal** | **~3.4** |
| Full-scope additions | |
| Tier-2 local REPL protocol adapter (code, not spec) | 0.5 |
| Raw-TypeScript code-view for T2/T3 | 0.25 |
| Python-sandboxed-IR post-MVP option | +2.0 deferred |
| **Full-scope subtotal** | **~4.15** |

**Recommend MVP-narrowed (~3.4d)** per design note §10 conclusion. Deferrals: tier-2 REPL adapter (lives in track D; spec-only for N MVP), raw-TypeScript view (post-MVP), Python-IR (post-MVP re-evaluate).

---

## 11. Acceptance criteria

**Gate 1 (end-to-end author flow):**
- User-sim persona (Maya or similar T1) describes a new node in plain English to the chatbot.
- Chatbot invokes `start_session` + a sequence of `edit` ops.
- User-sim asks "show me the code" — chatbot invokes `show_code(view='full')` — readable pseudo-code appears.
- User-sim asks "will it work?" — chatbot invokes `test_run(dry=true)` — sandbox returns simulated output.
- User-sim says "ship it" — chatbot invokes `commit()` — node appears in `discover_nodes`.
- Total elapsed: ≤5 minutes of user interaction.

**Gate 2 (sandbox isolation):**
- Adversarial test_run that attempts filesystem read outside /tmp — blocked, returns error.
- Adversarial test_run that attempts network fetch to non-allowlisted domain — blocked, returns error.
- Adversarial test_run that spins CPU infinitely — killed at 5s, returns `quota_exceeded`.
- Adversarial test_run that allocates 1 GB memory — killed at 256 MB, returns `quota_exceeded`.

**Gate 3 (scale — track J S12):**
- 100 concurrent authors each running a `test_run` — p99 <10s, no failures.
- 1,000 authors running sequentially — no session state corruption, no cross-user bleed.

**Gate 4 (privacy integration):**
- `inspect_leak_risk` on a node declaring a `contacts.write` tool emits `severity='high'` annotation citing §31 catalog entry.
- `commit()` blocks until chatbot narrates + user dismisses the annotation.

---

## 12. OPEN flags

| # | Question |
|---|---|
| Q1 | **Deno vs Python-sandboxed IR at MVP.** Recommend Deno per §3.3. Host confirm or push to Python (adds ~2d). |
| Q2 | **Node-authoring language at T1.** Recommend structured pseudo-code (§4) as the *visible* representation + JS/TS as the underlying runtime. Host confirm or push to "raw TS/Python visible from day one." |
| Q3 | **Session TTL 24h — too short, too long?** Recommend 24h per §7. Real-user cadence from user-sim will inform — Maya's "I'll finish tomorrow" workflow might want 48h. |
| Q4 | **Moderation queue trigger thresholds.** §8.4 proposes: new-author + medium-risk + high-priv-connector. Host confirm, or tighten/loosen. |
| Q5 | **Test-run real-execution (dry=false) gating.** §2.4 reserves dry=false for "final validation before commit." Should chatbot *always* require explicit user confirmation, or only when outputs include connector pushes / side-effects? Recommend always-confirm at MVP. |
| Q6 | **Code-view raw-format post-MVP priority.** §4 defers raw-TypeScript view. B-follow says "real nerds edit the code" — does pseudo-code suffice for that, or does T2 need raw-TS at launch? Recommend pseudo-code suffices IF it's actually editable via `edit` ops (i.e., the pseudo-code is 1:1 with the underlying concept). Confirm. |
| Q7 | **Forward compatibility across node versions.** If a node's concept schema evolves (we add new primitive types later), do existing authoring sessions break? Recommend: sessions pinned to their creation-time schema; platform-side migration on next edit. Not MVP critical. |
| Q8 | **Quota enforcement granularity.** Per-user 500 test_runs/day. Should also cap per-session (e.g., 100 test_runs per session — detects runaway iteration)? Recommend no per-session cap at MVP; add only if abuse observed. |
| Q9 | **Bot-authored nodes.** If a different LLM (not user's chatbot) programmatically authors 10,000 nodes via the MCP tools, what's our posture? Rate-limiting in gateway (spec #27) handles volume. But also — should `commit()` flag `concept.authored_by: 'llm'` vs `'human'`? Recommend capture at gateway level via bearer-token attribution (who's the user this is for), not by trying to detect human vs machine. |
| Q10 | **Session-resume across device.** Author starts on laptop, wants to resume on phone. Session is already user-scoped, so this works. No explicit flag needed — `list_sessions` surfaces active sessions across any device the user is signed in on. |

---

## 13. Cross-references

- Design note §27 — the source directive.
- Spec #25 full-platform-schema-sketch — `nodes`, `publish_node`, `parents uuid[]`.
- Spec #27 MCP-gateway-skeleton — routes `/node_authoring.*` tool calls to this spec's RPCs.
- Spec #53 remix-and-convergence-detail — `fork_and_remix` uses those RPCs.
- Catalog §31 privacy-principles-and-data-leak-taxonomy — `inspect_leak_risk` reads system-point taxonomy (§7) + category taxonomy (§2).
- Spec #36 moderation-mvp — queued-for-review tier.
- Memory `project_abc_followup_onboarding_transparency_privacy.md` — code-visibility-one-surface.
- Memory `project_node_software_capabilities.md` — required_capabilities for post-commit daemon execution.
- Memory `project_convergent_design_commons.md` — `fork_and_remix` as the cross-domain sharing primitive.

---

**Status on dispatch:** ready to implement. Spec is executable without further research. Estimated MVP-narrowed: **~3.4 dev-days** per §10.
