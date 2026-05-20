# external_write_packet shape (draft — PR-122 Phase 1)

**Status:** draft authored alongside PR-122 Phase 1 implementation
(branch `claude/pr-122-phase-1-effects-attribute-github-pr-effector`).
Promotion path: this draft is the seed for a canonical wiki page once
the first real Loop 2 PR emission lands. Not yet a stable contract —
fields may add, not remove, until a v1 cut is declared.

## What this is

A documented **shape** that user-built workflow branches emit from a
node's output. NOT a new substrate primitive. The platform reads the
shape out of `run_state` at completion time via the
`workflow.effectors` module.

A node opts in by declaring `effects=["github_pull_request"]` (or
another sink name) on its `NodeDefinition`. After a successful run the
effector scans the node's `output_keys` for the first value that parses
as a packet whose `sink` matches the declared effect.

## Canonical shape

```json
{
  "sink": "github_pull_request",
  "payload": {
    "title": "PR title — required.",
    "body":  "PR body — required, may be empty string.",
    "base_branch": "main",
    "head_branch": "auto/loop-2/cycle-NNN",
    "labels": ["writer:loop-2", "ready_for_checker"],
    "draft": true
  },
  "idempotency_hint": "<optional caller-suggested key>",
  "expected_evidence_keys": ["pr_number", "pr_url"]
}
```

### Fields

- **`sink`** (string, required) — names the external destination. The
  effector dispatches on this value. Today: `"github_pull_request"`.
  Future: `"twitter_post"`, `"discord_message"`, `"webhook"`, etc.
  Unknown sinks return `error_kind="unknown_sink"` instead of writing.
- **`payload`** (object, required) — sink-specific instructions. For
  GitHub PR: see the `payload` keys above. The effector validates
  required sub-keys (`title`) and rejects with `error_kind=
  "invalid_payload"` when missing.
- **`idempotency_hint`** (string, optional) — caller's suggested
  collision key. In Phase 1 this is a passthrough; the effector does
  not derive its own key yet. A future slice may sha256 the payload
  plus the head_branch for a canonical key (named PR-122 follow-on).
- **`expected_evidence_keys`** (list of strings, optional) — names the
  evidence fields the caller hopes to see back. Documentary today; a
  future slice may add validation that the effector populated all
  expected keys.

## Sink: `github_pull_request`

`payload`:

| key            | type    | required | notes |
|----------------|---------|----------|-------|
| `title`        | string  | yes      | non-empty after strip |
| `body`         | string  | yes      | may be empty |
| `head_branch`  | string  | no       | defaults to current branch |
| `base_branch`  | string  | no       | defaults to repo default branch |
| `labels`       | list    | no       | strings; passed as repeated `--label` |
| `draft`        | bool    | no       | defaults to `true` |

Evidence (success):

| key                  | type    | source |
|----------------------|---------|--------|
| `pr_url`             | string  | last non-empty stdout line from `gh pr create` |
| `pr_number`          | int     | extracted from the URL by regex |
| `matched_output_key` | string  | which of the node's output_keys held the packet |
| `stdout`             | string  | full stdout of the invocation |

Evidence (failure): `{"error": "...", "error_kind": "..."}` plus
`matched_output_key` when one was found. `error_kind` values:

- `gh_not_installed`
- `invalid_payload`
- `gh_invocation_failed` (OSError/timeout)
- `gh_nonzero_exit`
- `no_matching_packet`
- `unknown_sink`
- `effector_crashed`

## Dry run

When `WORKFLOW_EXTERNAL_WRITE_DRY_RUN` is truthy in the daemon's env,
the effector logs the intended write and returns
`{"dry_run": true, "intent": <packet>, "matched_output_key": "..."}`
instead of invoking `gh`. Useful for safe defaults during early
adoption and for end-to-end tests that should never touch GitHub.

## Where the evidence lands

The run-completion path (`workflow.runs._run_external_write_effectors`)
attaches per-node evidence to the run's output under:

- `output["external_write_results"]`: full evidence map keyed by
  `node_id` then `sink`.
- `output["external_write_errors"]`: flattened list of error rows
  populated only when at least one effector returned an `error`.

## Out of scope (named follow-ons)

- Twitter/X sink (Tiny daemon — separate PR after Phase 1 lands).
- Per-actor / per-sink credential resolver. Today the effector reuses
  the host's `gh` auth state via the CLI.
- Formal `idempotency_key` derivation (hash of payload + branch).
- Billing / replay semantics.
- Source-code-node alternative — option (c) in the PR-122 filing.
