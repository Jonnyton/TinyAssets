# Pre-build review disposition

2026-09-15 UTC, Claude Fable5.1, round1, assigned session61246. Repaired
peer wrapper retained complete opening/review/Stop recap; exit0 after281s.
VERDICT: ADAPT, no tests or edits by reviewer. Full retained source:
output/failed-history-shape-fable.md in this implementation worktree.

Required adaptations accepted:

1. Include shared_self and automation_context consumers, not only three readers.
2. Speaker `platform` is type discriminator, optional metadata is detail. A
   writable legacy store may save safe text-only platform pairs.
3. Saved failures clear the local slot but render explicit resend from their
   adjacent founder row; unsaved/unknown keeps local recovery.
4. Pure exception-to-code and code-to-safe-sentence mapping, no filtering or
   persisting `_served_failure_notice` raw fallback.

Lead verified new reader sources: shared_self68 principal reader/fenced memory;
automation_context44-63 all-session query, called207, persisted owner field at
automations265. Added owner filtering to prevent this new sink widening access,
and no partial-text resend when status peek truncates the original. These are
design constraints for implementation/tests, not verified runtime fixes.

Nongating pair-writer recommendation accepted. Do not take a failure code alone
as proof that no effects occurred; phase evidence is necessary. Account deletion
still needs an actual coverage test; reviewer did not trace it end to end.
Rollback retains platform-aware readers/UI and bytes, reverting only writes.
No changes to app-agent workflow definitions or the background-self project.

Implementation checkpoint, September 15, 2026 UTC: the adapted storage, five
readers and UI are implemented locally. The focused Windows cohort passed
320 tests in 46.78s (session 14767); see VERIFICATION.md. Exact-head independent
code review, Linux proof, PR, deployment and live failure-history proof remain.

## Implementation round2, September15 UTC

Fable5.1 session2344 completed353s/exit0 ADAPT at exactdf09debe (draft3856).
Full ordered answer: output/failed-history-implementation-fable.md. Reviewer
ran only tests/test_conversation_failure_history.py:29passed5.95s, Windows,
temporary root outside the repo. Agrees on admission, safe metadata/no receipt,
atomic persistence, owner isolation/deletion and explicit retry/refresh.

Required correction accepted: live UI must retain `note`/`error` recovery copy,
including first-contact setup guidance/Connect CTA. Fixed notice belongs to
restored history; it is not a reason to hide live explanation. Typed and voice
tests reproduced the regression (3failed/11passed before the fix). Live failed
execution keeps an explicit side-effect/retry caution; raw live copy never
enters durable storage. Fixed-notice fallback remains for missing live copy.

Optional notes: mapping consolidation remains later work; legacy text-only
setup rows cannot infer a Connect CTA from missing metadata (normal source
control still exists); non-principal automation-session exclusion is now
explicit in proposal; verification's old uncommitted status corrected.
Final exact-head round3 and hosted Linux CI remain before ready/landing.
