## Why

Live 2026-08-30 05:5xZ, universe `u-01kxm1vszd8hwp7em418asq8h9`: asked to
change one README line (put the date at the end of the sentence, restore the
final newline), the universe — which had just appended a line correctly in one
run with `$ta.concat` — had no way to EDIT inside fetched text without carrying
it through a model. It re-typed the file: PR #2714 removed every blank line
and turned `\Scripts\activate` into `\Scriptsctivate`; closed before its own
merge node landed it. Appending is covered by the shipped transforms; changing
a line is the more common patch and was not.

## What Changes

One more body transform in the reserved `$ta.` namespace:
`{"$ta.replace": {"in": X, "old": A, "new": B, "count": 1}}` — replaces
exactly `count` occurrences (default 1) of `A` inside `X` with `B`, all three
resolved through the same transforms (so `in` is typically the decoded
`$ta.effect` of a fetch node). It refuses the whole call — nothing is sent —
when `old` is empty, absent from the input, or occurs a different number of
times than `count`, so a typo cannot change the wrong place silently. The
model authors only the old and the new line. `write_graph`'s outbound docs
and the truncated-evidence `body_hint` name it.

## Impact

`tinyassets/effectors/authenticated_external_call.py`,
`tinyassets/engine_mcp_server.py` (docs); one test covering the live README
shape, refusal on absent/ambiguous/malformed input, and `count`.
