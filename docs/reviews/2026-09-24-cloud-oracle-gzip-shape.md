# Bounded compressed transport for cloud-only candidate tests

2026-09-24 UTC; follow-up to merged PR3934, not a change to that reviewed PR.
Claude Opus independent shape review43962 exited0 after215s. Its first review
was recovered from its own task transcript because the old root dispatcher
allowed an unrelated Stop-hook continuation to replace the final message.
Future dispatches use the corrected peer helper already landed with PR3932.

Verdict ADAPT: shape accepted subject to five requirements, all implemented:
explicit byte-exact prepare round-trip; no raw fallback on inflate failure;
bounded output with eof/unused_data/unconsumed_tail/length checks; no cross-zlib
golden compressed fixture; docs and input descriptions updated together.
SHA256 remains over exact uncompressed bytes. The existing path and secret
checks still run after decoding and before writing the candidate. No credentials,
permissions, checkout source, runner, dispatch input count, or test gate changed.

Root measured the actual working ownership candidate at03:26UTC via git diff
against099fe185 plus git diff --no-index for its three new source/test files:
132968 raw bytes,177292 raw base64 chars,48056 gzip base64 chars. Compression
fits the unchanged60000-char cap. This is a transport measurement, not Linux
proof; the candidate still requires integration of newly landed compaction code
before its final source/hash is frozen. All required source/tests must remain.

The reviewer inferred legitimate patches cannot compress beyond23x from three
historical samples. Root does not adopt that universal claim.256KiB is a bounded
engineering choice that covers this measured candidate, not a validity test for
all possible source patches. Oversized candidates fail loudly and require a
nearer already-pushed base or another reviewed transport; never omit proof.

Rollback: remove compression support or this manual-only workflow; no production
runtime is changed. Exact-head implementation review remains required before
landing. Final targeted test and review evidence will be recorded with the PR.
