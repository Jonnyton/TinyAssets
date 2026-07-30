## Why

The unattended OpenSpec drain entered a terminal failure budget after a worker
returned an otherwise valid `BLOCKED` result using the human task label
`main-red round 2` instead of the controller slug `main-red-round-2`. A result
format mismatch must not strand an admitted worktree or turn recoverable work
into a red, stopped drain.

## What Changes

- Make the admitted worker brief name the exact canonical target token required
  in its terminal result.
- Canonicalize a literal human-label result target to the same bounded slug used
  at admission while retaining strict rejection of templates, multiple markers,
  invalid statuses, and invalid PR URLs.
- On resume, replay the last result artifact when a parser improvement makes a
  previously `INVALID_RESULT` marker valid, undoing only that parser failure
  strike and applying the ordinary result transition.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `development-coordination-runtime`: Require admitted result identity to be
  explicit and require recoverable replay of a newly valid terminal result.

## Impact

The change affects the OpenSpec drain supervisor, its focused unit tests, the
development-coordination runtime specification, and the Windows drain run
currently preserved under `output/openspec-drain-auto-20260728-211331`.
