# Realtime voice implementation review — Opus round 2

Date: 2026-09-03
Reviewer: Claude Opus via `scripts/peer_agent.py`
Reviewed head: `050f168ae7fdff3196c76bc1402bde965a483ab7`
Verdict: **ADAPT**

The reviewer first confirmed that the round-one receipt contained exactly the two
blockers named in the new brief and that its committed transcription did not
over-claim approval.

## Structured verdict

1. **AGREE** — round-one blocker A (Stop control clickable and keyboard-operable
   in active states) was fixed in `app.html`, with a browser-harness regression
   assertion covering the active Stop control.
2. **AGREE** — round-one blocker B (binding and ledger preflight off the async
   server thread) was fixed in `realtime_voice.py`, with a thread-identity
   regression test.
3. **AGREE** — contracts 1–5 were sound: three-flag gate; bounded,
   symlink-refused, key-closed manifest; exact owner/universe/grant/connection
   match; POST scope; endpoint allowlisting at preflight and egress; redirects
   disabled; bounded secret-free response projection; unchanged CSP; and
   byte-identical canonical/plugin mirrors.
4. **DISAGREE_EVIDENCE (P2)** — a `converse` result crossing Stop→restart or a
   successful reconnect could speak the prior reply into a fresh session,
   pre-authorize its audio, or let a stale failure tear it down. The handler did
   not bind an in-flight result to its originating epoch and data channel.
5. **DISAGREE_EVIDENCE (P3)** — the browser session timer allowed 3600 seconds
   rather than enforcing the configured 1800-second client cap.
6. **DISAGREE_EVIDENCE (P3)** — disclosure acceptance was keyed only by version,
   so rebinding the universe to another service did not require a fresh
   service-specific disclosure.
7. **DISAGREE_EVIDENCE (P3)** — any `speech_started` event permanently suppressed
   mismatch enforcement for that reply, even when the reported output was not a
   truncated prefix of the canonical response.
8. **DISAGREE_CONCERN (P2, evidence-only)** — Linux symlink coverage and a real
   device/microphone pass were still absent. The branch was correctly dark, so
   this was not an enablement approval.

The four implementation findings were accepted for repair. This receipt is not
approval; a third and final exact-head review is required after the fixes and
reconciliation with current `main`.

REVIEWED_HEAD: 050f168ae7fdff3196c76bc1402bde965a483ab7
VERDICT: ADAPT
