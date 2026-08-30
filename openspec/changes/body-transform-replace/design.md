## Context

`$ta.replace` is public packet vocabulary: any universe's write node can use
it, and the `write_graph` tool description teaches it. Wrong guesses here are
expensive (a stored branch keeps the shape forever), so the shape is decided
before it ships.

## Decisions

- **Exact-occurrence refusal, not first-occurrence replace.** `old` must occur
  exactly `count` times (default 1) or the whole call is refused and nothing
  is sent. A model that copies a line with one wrong character gets a refusal
  that says so, never an edit in the wrong place. This is the property the
  live failure (#2714) lacked.
- **Closed key set.** Only `in`, `old`, `new`, `count`. A typo'd key refuses
  instead of running with the default (Codex round 1).
- **Every operand is a transform.** `in`, `old`, `new` and `count` all go
  through `_apply_transforms`, so `in` is normally the decoded `$ta.effect`
  of a fetch node and `count` may come from state.
- **Charged in UTF-8 bytes** against the same 32 MiB working set as the other
  ops: the input once plus the growth per replacement.
- **Not a unified-diff op.** A diff's context lines are exactly the whitespace
  a model gets wrong; `old`/`new` with an exact-match refusal is the smallest
  contract that makes a mistake harmless. Multi-hunk edits chain several
  `$ta.replace` calls (each `in` is the previous output) or use `count`.
- **Not line-number addressing.** The model does not reliably see line
  numbers in a truncated evidence preview, and numbers shift under it.

## Alternatives rejected

Regex replace (catastrophic backtracking on user text, and a model-authored
pattern is a second way to be wrong); server-side "patch" endpoint (a new MCP
action for what a body transform already expresses).
