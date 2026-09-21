# Pending-tool waiting: pre-build review and red evidence

September21,2026 UTC, base ded0fb12 (verified on origin/main), runtime identical
to deployed f5c5e5ec. Independent Claude Fable subscription peer61378 completed
exit0 in215s, read-only, no delegated work. Verdict ADAPT, incorporated in
openspec/changes/archive/2026-09-21-respect-provider-tool-waits/design.md before implementation.

Reviewer agrees with native-ID pairing, bounded tool allowance, unchanged
absolute/cancellation/authority rules, fail-closed missing IDs, and safe persisted
tool-phase/progress-age evidence. It specifically rejects attributing the exact
historical failure from committed side-effect state or retry success alone.
It identifies the existing normalizer's lost IDs and router's lost tool phase.
Root's proposal incorporates those conditions; exact-head review remains owed.

Root red reproduction committed4dca407f: real Claude reader, synthetic protocol
with identified tool start/result. Ordinary model-idle interval0.15s, tool gap
0.35s, absolute cap5s. Single pending and two-tools/one-completed cases both
incorrectly time out; post-tool silence control correctly times out.
Windows command: python -m pytest -q tests/test_provider_stream_and_classify.py
-k "identified_pending_tool or one_completed_tool or completed_identified_tool".
Result2failed/1passed; base whole file98passed/1skipped. These are supporting
controlled tests, not a claimed production trace or final app acceptance.

Read-only exact-run query confirms6ffec5e973734074 failed06:52:05-06:53:05UTC,
provider_idle_timeout/no protocol event30s, committed state, one indeterminate
reservation. No prompt read/replay. Stored tool phase unavailable: historical
cause remains unknown.

Official protocol source checked September21:
https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls
describes matching tool-use/result IDs. CLI-specific nested framing is recorded
in docs/reviews/2026-09-17-native-answer-model-shape.md. No heartbeat cadence
or provider capacity conclusion follows from these sources.
