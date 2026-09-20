# Late spoken-turn failure can offer another account's text

Found by independent Fable metadata review57196 on7733074d, September20,2026.
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
