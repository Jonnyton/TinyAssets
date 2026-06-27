---
title: MCP tool description clarity audit — chatbot cold-read pass
date: 2026-04-25
author: dev-2
status: active
scope: tinyassets/universe_server.py — all 6 public @mcp.tool decorators + server instructions
---

# MCP tool description clarity audit

A cold-read pass from a chatbot's perspective: given only the MCP tool
listing, can the model pick the right tool, pick the right action, and
form correct calls on the first attempt?

Tested against: `tinyassets/universe_server.py` as of 2026-04-25.

---

## Summary scorecard

| Tool | Cold-pick clarity | Action list completeness | Arg discoverability | Top gap |
|------|---|---|---|---|
| `universe` | Good | Good — one-liner per action | Good | `queue_list/cancel` + new subscription actions not in docstring action list |
| `extensions` | Good | Action groups well-structured | Mixed | `force` param semantics not linked to the conflict it bypasses |
| `goals` | Excellent | Clear action table | Excellent | `set_canonical` missing (if planned) |
| `gates` | Good | Clear but Phase 6 stub gap | Mixed | Chatbot can't tell which actions are live vs stub without calling |
| `wiki` | Excellent | Best in class | Excellent | `cosign_bug` semantics terse |
| `get_status` | Good | N/A (single action) | Good | Caveats contract could state explicitly that chatbot MUST read before making privacy claims |

---

## Per-tool findings

### `universe` — "Inspect and steer a workflow's universe"

**Strengths**
- First sentence ("Inspect and steer") matches the user-visible action perfectly.
- `action` arg lists reads vs writes clearly.
- `path` dual-semantic explanation (read_output vs add_canon_from_path) is
  exactly the kind of footgun that needs documentation — and it has it.

**Gaps**

1. **Dispatch table includes actions not in the docstring action list.**
   The `action` arg docstring lists reads and writes but omits:
   `queue_list`, `queue_cancel`, `subscribe_goal`, `unsubscribe_goal`,
   `list_subscriptions`, `post_to_goal_pool`, `submit_node_bid`,
   `daemon_overview`, `set_tier_config`.
   A chatbot trying to list queued requests won't find `queue_list` in the
   docs and may hallucinate a different action name or use the wrong tool.

2. **`control_daemon` commands not enumerated inline.**
   The docstring says `text` can be "daemon command: pause | resume | status"
   but a chatbot scanning the action list can't tell `control_daemon` needs
   `text` — it looks like it just takes `universe_id`.

3. **`tag` param for `get_recent_events` is documented correctly** but the
   example prefix-match note (one of the most non-obvious behaviors) could
   be made more prominent since it changes the cardinality of results
   significantly.

**Recommended fix (scope: docstring only)**
- Add the missing actions to the `action` arg enum list.
- Add one example call per action group (reads / writes / queue / bids).

---

### `extensions` — "Workflow-builder surface: design, edit, run, judge custom AI graphs"

**Strengths**
- Action groups are the clearest structure of any tool. Five named groups
  with their member verbs is scannable.
- `build_branch` / `patch_branch` preference callout is load-bearing and
  present.
- `run_branch` async note + `get_run` mermaid hint prevents a common
  "why is run_branch not returning output" confusion.

**Gaps**

1. **`force` param described as overriding `local_edit_conflict` but
   the chatbot doesn't know what a `local_edit_conflict` looks like.**
   A user chatting casually will never pass `force=True` because it
   sounds dangerous. The docstring should explain: "The server will
   return a structured `local_edit_conflict` response (not an error)
   when this happens — you can then pass `force=True` to override if
   the user confirms."

2. **`spec_json` shape is documented but `changes_json` shape is buried.**
   `changes_json` is the most common arg for iterative editing but its
   schema (op enumeration) is harder to find than `spec_json`. Both are
   long — both need a link or example.

3. **Run action group missing `get_routing_evidence`** if it's now live.
   Check whether the new action from Task #14 is in the dispatch table
   and add it to the action group list.

4. **Phase gating is implicit.** The eval/iterate group says "(Phase 4)"
   and gates say "(Phase 6)" in comments but the docstring doesn't mention
   that some actions are conditionally stubbed based on feature flags.
   A chatbot calling `gates` when `GATES_ENABLED=off` gets a placeholder;
   the current docstring gives no warning.

**Recommended fix (scope: docstring only)**
- Expand `force` explanation to include the expected conflict response shape.
- Add Phase-flag caveats to gated action groups.

---

### `goals` — "Goals — first-class shared primitives above workflow Branches"

**Strengths**
- Best action table format of all tools. Every action is on its own line
  with a 1-sentence description and required args named.
- `leaderboard` Phase 6 stub callout is exactly right — tells the chatbot
  what to expect today vs later.
- `common_nodes scope="all"` use case is spelled out in detail — the
  chatbot can use this without guessing.

**Gaps**

1. **`set_canonical` not in the action list** (if it's a planned or
   already-wired action for the `file_bug` auto-trigger chain). The
   STATUS Concerns row mentions `set_canonical` as a host-decision action;
   if it's wired in the dispatch table but not in the docstring, add it.
   If it's not yet wired, ignore.

2. **`visibility` field values for `propose` are undocumented inline.**
   The docstring says `visibility (public/private)` in the `propose` line
   but the `Args` section doesn't repeat these. Minor inconsistency.

**Recommended fix (scope: minimal — check set_canonical + add visibility values)**

---

### `gates` — "Outcome Gates — real-world impact claims per Branch"

**Strengths**
- Ladder metaphor (draft → peer-reviewed → published → cited → breakthrough)
  is concrete and memorable.
- `evidence_url` constraint (http(s) with host, content not fetched) prevents
  a class of hallucinated local paths.
- `claim` idempotent note on (branch, rung) key is exactly the kind of
  behavior a chatbot needs to know to avoid confusing error responses.

**Gaps**

1. **No way to tell which actions are live vs Phase 6.3 stub from the
   docstring alone.** The docstring mentions "Phase 6.3 lands git-commit
   integration" but reads as if it's already landed. A chatbot calling
   `define_ladder` may get a stub response. Add explicit "(available now)"
   vs "(Phase 6.3, stub today)" labels to each action.

2. **`attachment_scope`, `eval_verdict`, `node_last_claimer`, `outcome_payload_json`,
   `outcome_note` params are in the signature but NOT documented in the
   docstring.** A chatbot scanning args will see them in the MCP schema
   but have no guidance on when to use them. Either document or omit from
   the signature until they're active.

3. **`bonus_stake` semantics unclear.** What is the unit? What happens if
   nonzero when escrow isn't live? Document the "harmless when escrow=off"
   behavior.

**Recommended fix (priority: medium)**
- Add live-vs-stub label per action.
- Document or remove undocumented params.

---

### `wiki` — "Read, write, and manage the cross-project knowledge wiki"

**Strengths**
- Intent routing guidance ("use extensions for X, use wiki for Y") directly
  prevents the most common mis-routing (chatbots writing workflow structure
  to the wiki).
- `file_bug` dedup behavior (server-side similarity check, returns existing
  bug if match) is documented; reduces 100-duplicate-bug failure mode.
- `severity` enum with concrete triage guidance (critical=data loss) is
  exactly right.

**Gaps**

1. **`cosign_bug` semantics are one sentence.** The intended flow
   ("if similar bug exists, use cosign_bug instead of filing a duplicate")
   is in the MEMORY but not in the docstring. A chatbot seeing `cosign_bug`
   in the action list won't know: what args does it take? what does it return?
   Add: needs `bug_id`; adds reporter_context; returns updated bug page.

2. **`promote` and `consolidate` have no guidance on when a chatbot would
   invoke them.** These are maintenance ops — perhaps clarify that they're
   host/admin actions and chatbots should prefer `write` + `lint` for
   quality checks.

3. **`sync_projects` action appears in the reads list but has no
   documentation in the action table.** What does it sync? When would a
   chatbot call it vs `write`?

**Recommended fix (scope: docstring expansion for cosign_bug + sync_projects)**

---

### `get_status` — "Daemon Status + Routing Evidence"

**Strengths**
- Response schema is explicitly documented inline — extremely unusual for
  an MCP tool and exactly what's needed for a contract-stability claim.
- `caveats` field load-bearing note ("MUST read + narrate") is present and
  prominent.
- `session_boundary` purpose is explained: chatbot can cite this instead of
  relying on prompt-level directives.

**Gaps**

1. **"Chatbots call this when..." sentence implies it's for privacy queries
   only.** The tool is also the right call for "is the daemon running?",
   "what's the active universe?", "what provider is bound?". The docstring
   should broaden the trigger list so chatbots don't skip it when the user
   isn't explicitly asking a privacy question.

2. **`evidence.last_n_calls` field note says "mirrors dispatch_evidence
   caveat-augmentation pattern introduced in commit 7d19f34."** Commit
   references belong in git history, not in a tool description the chatbot
   reads as behavioral guidance. Replace with functional description.

**Recommended fix (scope: minor wording pass)**

---

## Server instructions (FastMCP `instructions=` field)

The server-level instructions are read by the chatbot at connection time.

**Strengths**
- Aggressive-assumption rule ("Invoke it rather than presenting a
  disambiguation picker") is exactly right for the Chatbot-Assumes-Workflow
  UX principle.
- Universe-isolation hard rule with concrete remediation step
  (`universe action=inspect` with explicit `universe_id`) is load-bearing
  and present.

**Gaps**

1. **Fantasy bias survives in the tags list.** The `universe` tool tags
   include `"fiction"`. A chatbot indexing by tags for intent routing may
   skip the `universe` tool for non-fiction domains. Remove `"fiction"` from
   the `universe` tool tags (the server instructions already cover general
   domains; the tag set should reflect the tool's scope, not the benchmark
   domain).

2. **The `control_station` prompt load directive ("Load the `control_station`
   prompt early") is in the server instructions but not enforced by tool
   descriptions.** Tools that depend on behavioral rules from `control_station`
   (e.g. the never-simulate-a-run rule) will still work correctly if the
   chatbot loads the prompt, but there's no tool-level reminder for
   first-time callers who skip the prompts. Consider adding one sentence
   to `universe` and `extensions` docstrings: "Load the `control_station`
   prompt before first use."

---

## Prioritized fix list

| Priority | Tool | Fix | Effort |
|---|---|---|---|
| P0 | `universe` | Add `queue_list/cancel/subscribe_goal/unsubscribe_goal/list_subscriptions/post_to_goal_pool/submit_node_bid/daemon_overview/set_tier_config` to the `action` arg docstring | 15 min |
| P1 | `gates` | Label each action live vs Phase-6.3-stub | 20 min |
| P1 | `gates` | Document or remove undocumented params (`attachment_scope`, `eval_verdict`, `node_last_claimer`, `outcome_payload_json`, `outcome_note`, `bonus_stake`) | 30 min |
| P2 | `extensions` | Expand `force` to explain the conflict response shape | 10 min |
| P2 | `wiki` | Expand `cosign_bug` with required args + return shape | 10 min |
| P2 | `universe` tags | Remove `"fiction"` from tags | 2 min |
| P3 | `extensions` | Add Phase-flag caveats to gated action groups | 15 min |
| P3 | `get_status` | Broaden trigger list; remove commit-hash reference | 5 min |
| P3 | `wiki` | Document `sync_projects` action | 5 min |

---

## What does NOT need fixing

- `goals` action table format — best in the codebase, do not change.
- `wiki` intent-routing paragraph — clear and correct.
- `get_status` schema documentation — gold standard, replicate in other tools.
- Server instructions aggressive-assumption rule — correct and strong.
- `universe` `path` dual-semantic explanation — present and complete.
