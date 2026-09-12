# Independent HTTP agent implementation review

Claude reviewed exact ffbc918fbfc54f1c6343c9ede66d689a0ef2e8c9 against73f49e35,
read-only, September10 2026. Dispatch26138 completed exit0 in567s, VERDICT: ADAPT.
The wrapper captured the stop-hook recap rather than the full original verdict.
Full findings were recovered from this exact dispatch's local transcript
c03988c8-7bc2-48cd-9104-c0a1df328b4d; no replacement review was launched.
The reviewer reports27 new tests passed6.19s. Its cited runner line offsets were
incorrect; the code paths below were independently located by symbol before edits.

## AGREE

Per-inference fresh admission; intent after successful consume and before POST;
finite accepted-binding allowance without refill; no unknown/known tool replay;
cancellation drain before settlement; transactional current-home plus fresh
custody/grant/route checks; full encoded input/output accounting and exact decimal
cost handling; unchanged native CLI path; conservative statusless proxy handling.
All seven prior shape adaptations were found applied.

## DISAGREE_EVIDENCE: required correction

InteractiveHttpAgentTurn only finalized failures after an inference intent.
A later failure before that intent left a ready turn with completed tool rounds.
close_unused and AgentTurnJournal.abandon accepted only zero-round roots, while
reset_blockers treated ready as active. Thus a context/slot/claim failure after a
known result could permanently block owner reset despite no uncertain effect.

Required fix: allow a non-executing close of a fully settled ready frontier,
preserving all history; call it on runner failure and final cleanup. Keep started
inference, pending tools and ambiguous results blocked. Test a second-inference
pre-intent failure, preserved results, no replay and an empty reset-blocker set.

Applied locally after the review: abandon now accepts only validated ready state
(including completed rounds), the reader accepts abandoned only over a ready
frontier, and close_quiescent closes failures without making any turn resumable.
Zero-round roots remain ready through the writer's existing one all-skipped retry.
Three composition regressions cover later claim, intent and history failures;
journal cases cover retained history/idempotence/no-resume and rejection of five
incomplete/ambiguous frontiers including tampered terminal labels.

## DISAGREE_CONCERN: non-gating, still open

- Held truncated/refusal/filter/unknown stops currently surface an error rather
  than their partial text; settle the user-facing display before live activation.
- A post-response storage/home failure preserves inference_started as ambiguous;
  do not broaden this close to erase that evidence.
- Final writer receipt covers only the last inference; turn-cost UI must use all
  journal/reservation rows.
- executor_tools is local executor capability, not a claim by remote discovery.
- Future failed-inference fallback must count prior launches/reservations.
- Cancellation drains an outstanding HTTP request, so transport cleanup can
  outlast the nominal absolute deadline.

Explicitly unfinished feature scope: public current/saved policy consumption,
typed candidate fallback and clickable controls. No new deployment or live proof.
