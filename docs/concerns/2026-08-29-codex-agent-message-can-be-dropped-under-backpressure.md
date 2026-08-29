# A codex `agent_message` can be dropped under backpressure, and then a finished turn fails

**Filed:** 2026-08-29 (Codex round 2 on the turn-wait change, P1 evidence)
**Verified:** in the pinned codex-cli 0.146.0 source, not yet reproduced live.
**Severity:** P2 — the failure is loud (Hard Rule 8 holds) and needs a
saturated event queue, which a served converse turn has not been seen to
produce; but when it happens the user loses a reply the model did generate.

## The claim

The codex in-process app-server queue guarantees delivery of exactly one
notification, `TurnCompleted` (`codex-rs/app-server/src/in_process.rs`).
`ItemStarted` and `ItemCompleted` are best-effort and are dropped when the
bounded queue fills; the terminal backfill in
`exec/src/event_processor_with_jsonl_output.rs` emits an `item.completed` only
for item ids it previously saw start. So a healthy turn can reach the daemon as
a `--json` stream that carries `turn.completed` with `usage` but **no
`agent_message` item** — the reply text itself was dropped.

`CodexProvider.complete()` then raises
`ProviderError("codex accounting output omitted result or usage")`
(`tinyassets/providers/codex_provider.py`, the `machine_accounting` parse):
loud, correct, and a lost reply.

## The fix

`codex exec` has `-o / --output-last-message <file>`: it writes the final
assistant message to a file at the end of the turn, from the turn state rather
than from the event queue, so it does not share the drop path. Pass it on the
served `--json` path (a writable path inside the bwrap jail — `/tmp` is the
sandboxed `HOME`), and when the stream carries `turn.completed` but no
`agent_message`, read the reply from that file before raising. Keep the raise
for the case where the file is absent or empty.

Spec home when built: `openspec/specs/provider-routing/spec.md`, the
"Silence inside a codex turn" / "A completed codex turn is never failed by its
own shutdown" scenarios.

## How to resolve this file

Delete it when the `-o` fallback is in `complete()` with a test that feeds a
`turn.completed`-only stream plus a last-message file and gets the reply back,
and the spec scenario records it.
