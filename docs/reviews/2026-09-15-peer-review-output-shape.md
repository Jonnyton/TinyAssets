# Retain peer-review output: pre-build shape review

2026-09-15 UTC, Windows host, Claude Fable 5.1, round 1. Assigned process
57131 completed in 197 seconds with exit 0, VERDICT: ADAPT. The brief scoped
only review-output retention, not bootstrap PR3853 or baseline PR3854. No
subdispatch, edits or test run. Source at review matched main89a335578a1576a1b4253375e6d900a770338009.
Full retained review: primary worktree output/peer-review-capture-shape-fable.md.

## Required corrections and implementation disposition

- AGREE: Claude `--output-format stream-json --verbose`, no partial messages,
  no change to subscription auth, model selection, permissions, hooks or Codex.
- DISAGREE_EVIDENCE: reuse `_normalize_stream_obj` in
  `tinyassets/providers/claude_provider.py` instead of a parallel event parser.
  Accepted: wrapper validates capture envelopes and delegates text extraction to
  that normalizer; production provider code stays unchanged.
- DISAGREE_CONCERN: message-id dedupe could discard separate blocks with shared
  ids. Accepted: keep every block, compare only terminal text with the final
  retained block, stripped for echo comparison.
- AGREE with gap: non-JSON nonempty lines must fail with line number/length,
  never silently drop them or print raw stdout. Accepted; malformed assistant
  or result envelopes also fail without exposing payloads.
- AGREE: convert existing plain-text success tests to real protocol shapes;
  preserve timeout/nonzero/Codex checks and test review plus Stop recap.
- Update module/help and canonical/mirrored skill output contracts. Multiple
  verdicts are retained, never selected by the wrapper.

Reviewer verified installed CLI flags and existing normalizer/fixture precedent.
Unverified external premises: current terminal-event fields; continuation event
ordering; shared-id behavior. Synthetic tests cover capture behavior but a real
CLI run is still required. Session-specific Stop-hook injection is a suggested
proof method, not permission to edit host-wide hooks. Unrelated Stop-hook scope
nudges remain a separate issue; capture repair does not resolve that concern.

## Local implementation evidence

Windows, 2026-09-15 UTC, retain-peer-review-output worktree:
`python -m pytest -q tests/test_peer_agent.py`: 39 passed, 1.15 seconds.
`python -m ruff check scripts/peer_agent.py tests/test_peer_agent.py`: passed.
No real-CLI proof, exact-head implementation approval, PR or landing claimed here.
