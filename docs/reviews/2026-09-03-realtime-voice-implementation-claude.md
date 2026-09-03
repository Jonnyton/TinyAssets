# Realtime voice implementation review — Claude

Date: 2026-09-03

> Superseded in part by the founder's later 2026-09-03 authority correction. This review does not
> approve the revised subscription-compatibility finding, capability-status route, or locked-
> resource UI. See `docs/reviews/2026-09-03-realtime-voice-authority-correction-review.md`.

Provider/model: Claude Sonnet, invoked through `scripts/peer_agent.py`
Scope: uncommitted `add-realtime-voice-conversation` implementation and tests
Mode: read-only; no network, paid API call, file edits, subagents, or full suite

The wrapper's repository stop hook replaced its final stdout with an unrelated stale-dispatch
status. The actual review was recovered verbatim from the corresponding local Claude session
transcript (`30be7ed7-372e-4162-9f78-cbbc14de2c68.jsonl`). That transcript is local harness state,
not a project artifact; this file preserves the review outcome and dispositions durably.

## Verdict

`VERDICT: AGREE`

The reviewer found no cross-owner breach, ambient-credential fallback, secret leak, or blocking
reason to land the slice dark. It confirmed the authenticated home resolution, caller-universe
rejection, owner-vault lookup, two independent flags, no-store response, secret-free errors,
narrow `converse` tool, CSP gating, call-id duplicate guard, and teardown paths.

## Findings and dispositions

1. `DISAGREE_EVIDENCE`: unsolicited or mismatched Realtime audio was detected only after playback,
   while the delta spec requires refusal and visible failure. **Resolved:** remote audio starts
   muted; only a completed canonical `converse` result opens the playback gate; any audio delta
   without that gate fails closed; transcript mismatch traces counts only and visibly stops voice.
2. `DISAGREE_EVIDENCE`: the design promised rate-limited secret minting but the route lacked it.
   **Resolved:** the authenticated broker now permits ten mints per identity per fixed one-minute
   window and returns a typed, no-store `429` before home or provider access.
3. Cosmetic: microphone denial detail was overwritten by the generic failure message.
   **Resolved:** permission rejection now maps to a stable dedicated user-facing error.
4. `DISAGREE_CONCERN`: the modal lacked Escape handling and a focus trap. **Resolved:** Escape
   cancels, Tab/Shift-Tab remain inside the two modal actions, and dismissal restores prior focus.
5. `DISAGREE_CONCERN`: the checked cross-owner test proved caller-universe rejection but not two
   identities resolving to two credentials. **Resolved:** a deterministic route test now drives
   two identities and proves two distinct home-universe paths and user IDs reach the broker.

The final corrected tree is covered by the focused test and lint evidence in
`openspec/changes/add-realtime-voice-conversation/verification.md`. A targeted same-provider
follow-up is allowed only to verify these exact dispositions; it is review round 2, not a new
wide audit.

## Round 2

The targeted follow-up returned `VERDICT: DISAGREE` on one composite race: a legitimate barge-in
truncates the output transcript, so unconditional mismatch failure would have torn down the whole
session. The other four dispositions were confirmed. The fix now tracks whether the active
canonical response was interrupted. Barge-in mutes immediately and records content-free mismatch
telemetry without failing; an uninterrupted mismatch still fails closed. The Node harness now
executes that full sequence rather than isolated events. The review's concern file was deleted
after resolution, as required by the repository concern lifecycle.

Round 3 was restricted to this one correction and returned `VERDICT: AGREE`. It confirmed with
exact code and test citations that interruption mutes immediately, remains in listening without
teardown, tolerates the expected truncated transcript, and still fails closed on unsolicited audio
or an uninterrupted mismatch. Per the three-round cap, no further review round will be opened.
