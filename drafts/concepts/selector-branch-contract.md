# Selector Branch Contract (DESIGN-008)

**Status:** shipped in DESIGN-008.

A **selector branch** is a published Workflow branch that ranks the
candidate branches competing on a Goal's leaderboard. The substrate
dispatches it whenever `quality_leaderboard goal_id=<g>` or
`recommend_parent_for_fork goal_id=<g>` is called.

Goal owners bind a selector via:

```
goals action=set_selector goal_id=<g> branch_version_id=<v>
```

Pass `branch_version_id=""` to fall back to the platform default
selector (`platform_default_selector_v1_20260521`).

Anyone publishing a selector implements this contract.

---

## Inputs

The selector run is invoked with the following `inputs` dict (passed
as the `inputs_json` payload to `execute_branch_version_async`):

```json
{
  "goal_id": "<goal-id>",
  "candidate_branches": [
    {
      "branch_def_id": "...",
      "branch_version_id": "<latest active version, or empty string>",
      "name": "...",
      "author": "...",
      "description": "...",
      "signals": {
        "completed_run_count":      <int>,
        "failed_run_count":         <int>,
        "total_run_count":          <int>,
        "judgment_score_avg":       <float | null>,
        "judgment_count":           <int>,
        "judgment_score_samples":   <int>,
        "other_numeric_tags":       {"<key>": <count>, ...},
        "fork_count":               <int>,
        "last_successful_run_at":   <epoch float, 0.0 if never>,
        "age_days_since_success":   <float | null>,
        "has_gate_rung":            <bool>,
        "gate_rung_top":            <str | null>,
        "safe_to_publish":          <bool>
      }
    },
    ...
  ]
}
```

**Signal semantics:**

| Field | Meaning |
|-------|---------|
| `completed_run_count` | Runs that finished with `status='completed'`. |
| `failed_run_count` | Runs that finished with `status='failed'`. |
| `total_run_count` | All runs against the branch (including queued / running). |
| `judgment_score_avg` | Mean of numeric judgment tags matching `quality:N` / `novelty:N` / `score:N`. `null` when no numeric judgments exist. |
| `judgment_count` | Total judgment rows on this branch (numeric + free-text). |
| `judgment_score_samples` | Number of judgments that contributed to `judgment_score_avg`. |
| `other_numeric_tags` | Other tag-name counts (e.g. `risk:N`, `cost:N`) — exposed in case the selector wants to weight them; the default selector does not. |
| `fork_count` | Count of branches whose `parent_def_id` or `fork_from` points at this branch (visibility-respecting). |
| `last_successful_run_at` | Max `finished_at` of completed runs, in Unix epoch seconds (float). `0.0` when no completed run exists. |
| `age_days_since_success` | Days between `last_successful_run_at` and `now`. `null` when no completed run exists. |
| `has_gate_rung` | True iff at least one non-retracted `gate_claims` row exists for this `(branch, goal)`. |
| `gate_rung_top` | The lexicographically-greatest active `rung_key` for this `(branch, goal)`, or `null`. |
| `safe_to_publish` | Best-effort read of `branch.stats.next_action_packet.safe_to_publish` (Loop-2 packet shape). `false` when not set. |

---

## Outputs

The selector run must populate its final state with a `ranked_entries`
key:

```json
{
  "ranked_entries": [
    {
      "branch_def_id":     "<must match an entry in candidate_branches>",
      "branch_version_id": "<published version_id, or empty string>",
      "score":             <float>,
      "rationale":         "<one-sentence human-readable explanation>"
    },
    ...
  ]
}
```

**Rules:**

* Entries are ordered best-first (rank 1 = entries[0]).
* `branch_def_id` is **required** and must be a non-empty string. The
  substrate filters out entries that don't match a `branch_def_id`
  from the input `candidate_branches` (defensive: a misbehaving
  selector cannot conjure phantom branches into the leaderboard).
* `score` is **required**, must coerce to float. Suggested 0.0-10.0
  scale; the substrate doesn't enforce a range.
* `branch_version_id` is optional — when empty, the substrate falls
  back to the latest active version for the `branch_def_id`.
* `rationale` is optional — when empty, the substrate synthesizes a
  generic "ranked first of N with score X" string.
* Ties are tolerated. Two entries may have the same `score`.
* Duplicate `branch_def_id`s are filtered out by the substrate (only
  the first occurrence is kept).

**`ranked_entries` can be the empty list** when `candidate_branches`
was empty. The substrate short-circuits dispatch entirely in that
case and never invokes the selector.

**Output may be a JSON string.** Prompt-template nodes typically
emit their output as a string. The substrate parses
`output["ranked_entries"]` as either a list (direct) or a JSON-string
that decodes to a list. Both shapes are accepted.

---

## Failure modes

The substrate translates selector misbehavior into structured error
responses on the caller's `quality_leaderboard` / `recommend_parent_for_fork`
result. The leaderboard never raises a Python exception to the chatbot;
it returns `{ok: False, error_kind: "...", error: "..."}`.

| `error_kind` | Cause |
|---|---|
| `goal_not_found` | The `goal_id` passed to `quality_leaderboard` has no row in `goals`. |
| `selector_not_published` | `goal.selector_branch_version_id` references a `branch_version_id` that doesn't exist in `branch_versions`. |
| `selector_snapshot_drift` | The selector's snapshot was published against a Workflow schema version the runtime can no longer reconstruct. Re-publish at current schema. |
| `selector_dispatch_failed` | `execute_branch_version_async` raised before producing a `run_id` (rare; typically a malformed snapshot). |
| `selector_timeout` | The selector's background run did not finish within `WORKFLOW_SELECTOR_TIMEOUT_S` seconds (default 60s). |
| `selector_run_failed` | The selector run finished with `status != 'completed'`. The run row's `error` field is surfaced. |
| `selector_invalid_output` | `ranked_entries` is missing, not a list, contains malformed entries, or any required key is missing. |

When a selector fails, the leaderboard returns an empty `entries` list
plus the `error_kind` so the chatbot can render a clear "selector
misbehaved" surface. The recovery path is operator action: rebind a
known-good selector via `set_selector`, fork the failing one + fix the
prompt, or unbind to fall back to the platform default.

---

## Default selector

The platform ships a default selector branch published under the
deterministic id `platform_default_selector_v1_20260521`. It is a
single prompt-template node whose prompt encodes the ranking heuristic
the round-1 platform formula used to apply in Python: weight judgment
score highest, then completed runs, then forks, then recency, with a
penalty for failed runs.

**The weights are now a prompt the chatbot can fork and edit, not
Python constants.** A Goal owner who wants different selection logic
for their domain forks the default selector via
`extensions action=create_branch fork_from=platform_default_selector_v1_20260521`,
edits the prompt, publishes, and binds via `set_selector`.

---

## Authority

`set_selector` requires Goal-author or host actor authority (same
surface as `set_canonical`). A selector binding is a per-Goal write;
the platform default is a system-wide fallback.

---

## Cost

Each leaderboard build now triggers one LLM call (the selector run).
The round-1 formula was free. Acceptable trade for the architectural
win: selection logic is now community-evolvable instead of
platform-opinionated.

A future caching slice may memoize selector output keyed by
`(goal_id, candidate fingerprint)` for N minutes. Until then,
leaderboard calls are uncached.

---

## Reference

* `workflow/api/selector_dispatch.py` — selector resolution +
  dispatch + output parsing.
* `workflow/api/quality_leaderboard.py` — leaderboard caller that
  consumes the selector's output.
* `workflow/api/market.py::_action_goal_set_selector` — MCP action
  for binding a selector.
* `workflow/daemon_server.py::set_selector_branch` — storage helper
  with active-version validation.
