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
