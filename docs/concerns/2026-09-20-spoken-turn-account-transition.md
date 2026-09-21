# Late spoken-turn failure can offer another account's text

**Filed: 2026-09-20.** Found by independent Fable metadata review57196 on7733074d.
Source evidence: tinyassets/onboarding/app.html sendVoiceTurn has no equivalent
of sendTurn's stillHere owner/home guard before render/failure handling.
sendConversationRequest checks login epoch and throws on changed account, but
sendVoiceTurn catches that error and calls offerResend with the old spoken text.
The late finally checks composer ownership, not the preceding failure offer.

This predates the active-turn recovery patch and is not fixed by it. Spec now
limits the late reply/failure painting claim to typed turns. No live account
transition was induced; this is source-derived, not a reproduced production leak.
Root must prioritize a bounded actual-JS regression and voice parity correction,
preserving durable recovery and never replaying an old request into a new account.
Acceptance: old spoken replies/failures/settle cannot paint or enable a retry
under a different owner/home; original-owner reload recovery remains available.

## Local implementation state (2026-09-20, branch codex/spoken-turn-owner-fence)

Source fix in `sendVoiceTurn`: the same epoch+owner+home fence `sendTurn`
holds. Past the fence a success throws `voice_turn_retired` instead of
returning text, the catch rethrows without `sessionExpired`/notice/offer,
and `flushSendQueue`/`Voice.conversationSettled` run only for `stillHere()&&mine`.
The awaited callers (`_handleBrowserUtterance`, `handleToolCall`) keep their
existing generation guards; `voiceFriendlyError` gained the retired reason.
Evidence: `tests/test_app_spoken_turn_account_fence.py` executes the page's own
`sendVoiceTurn` and `Voice` under node, 12 cases, red on the parent tree
(retry offered under B, session-expired fired, Voice settled) and green after.
Not yet done: live acceptance through the real app with an induced account
transition. Keep this file until that is seen.
