# external_write_packet shape (draft — PR-122 Phase 1 + Phase 2 Slice 1)

**Status:** draft authored alongside PR-122 Phase 1 implementation
(branch `claude/pr-122-phase-1-effects-attribute-github-pr-effector`),
extended in PR-122 Phase 2 Slice 1 (branch
`claude/pr-122-phase-2-authority-idempotency-consent`) to add the
``destination`` field. Promotion path: this draft is the seed for a
canonical wiki page once the first real Loop 2 PR emission lands. Not
yet a stable contract — fields may add, not remove, until a v1 cut is
declared.

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
  "destination": "Jonnyton/Workflow",
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

- **`sink`** (string, required) — names the external destination type. The
  effector dispatches on this value. Today: `"github_pull_request"`.
  Future: `"twitter_post"`, `"discord_message"`, `"webhook"`, etc.
  Unknown sinks return `error_kind="unknown_sink"` instead of writing.
- **`destination`** (string, required for real writes in Phase 2) —
  per-sink destination identifier. For ``github_pull_request`` this is
  the ``owner/repo`` slug, e.g. ``"Jonnyton/Workflow"``. The Phase 2
  authority gates (capability env + consent grant) key off this value
  exactly; no wildcard or case-insensitive match. **Backward compat:**
  packets that OMIT `destination` continue to land on the Phase-1
  dry-run-only path. They cannot mint a real write regardless of
  capability/consent state — this is the migration grace path for
  existing Phase-1 packets.
- **`payload`** (object, required) — sink-specific instructions. For
  GitHub PR: see the `payload` keys above. The effector validates
  required sub-keys (`title`) and rejects with `error_kind=
  "invalid_payload"` when missing.
- **`idempotency_hint`** (string, optional) — caller's suggested
  collision key. The Phase 2 effector treats this as the deduplication
  key against ``external_write_receipts``: a hit returns the recorded
  evidence with ``idempotency_dedup_hit=true`` instead of firing again.
  Omitting the field opts out of dedup (every invocation runs). A
  future slice may sha256 the payload plus the head_branch for a
  canonical caller-independent key.
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

Evidence (Phase 2 dry-run from a closed gate):

```json
{
  "dry_run": true,
  "phase": "phase_2",
  "reason": "missing_capability" | "missing_consent" | "concurrent_in_flight" | "operator_kill_switch_active",
  "destination": "Jonnyton/Workflow",
  "capability_env_var": "WORKFLOW_GITHUB_PR_CAPABILITIES",
  "capability_lookup_failed_for": "Jonnyton/Workflow",
  "intent": <packet>,
  "matched_output_key": "..."
}
```

`capability_env_var` + `capability_lookup_failed_for` are present only
when the reason is `missing_capability`. Round-2 (Codex P1.2) replaced
the round-1 per-destination suffix env (which collapsed `octo/my.repo`
and `octo/my_repo` to the same env name) with the JSON-map
`WORKFLOW_GITHUB_PR_CAPABILITIES` env; the dry-run evidence names the
literal destination string the host needs to add to that map.

Evidence (Phase 2 idempotency dedup hit):

```json
{
  "idempotency_dedup_hit": true,
  "phase": "phase_2",
  "destination": "Jonnyton/Workflow",
  "matched_output_key": "...",
  "evidence": <recorded-evidence>,
  "recorded_run_id": "<original run that produced the PR>",
  "recorded_at": <unix-ts>,
  "idempotency_hint": "..."
}
```

## Operator kill switch

`WORKFLOW_EXTERNAL_WRITE_DRY_RUN` is the operator panic-button
override. When truthy on the daemon's env, the effector **always**
returns dry-run evidence — ALL gates (capability + consent +
idempotency reservation) are bypassed; no real write fires for this
sink. The host flips the env on a live daemon to disable all real
writes without revoking consent or rotating capability tokens.

The dry-run evidence shape under this override:

```json
{
  "dry_run": true,
  "phase": "phase_2",
  "reason": "operator_kill_switch_active",
  "kill_switch_env": "WORKFLOW_EXTERNAL_WRITE_DRY_RUN",
  "intent": <packet>,
  "matched_output_key": "..."
}
```

Round-3 contract (Codex round-2 verdict on PR #969): round-2
inadvertently left this env recognized-but-ignored on the gate-
orchestrated path while these docs still claimed it was a working
kill switch. The fix restores it as a hard override at the top of
`run_github_pr_effector`, before any of the three gates run.

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
