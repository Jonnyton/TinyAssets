# Worktree purpose

Purpose: codex-turn-wait
Provider: claude-code
Branch: claude/codex-turn-wait
Base ref: origin/main
Issue/PR: follow-up to #2674 — live on 2026-08-29 the streamed reader idle-killed a healthy turn (codex --json emits nothing while the model generates); the notice said "exhausted"; the app then reloaded and drew the thread upside down
PLAN refs: provider routing / served turns; onboarding app as a primary surface
Ship condition: reader treats an open turn's silence as generation (tests red-first); served idle/deadline notice names the true class; app keeps a served-error message resendable, never auto-reloads mid-turn, orders history by ts; Codex refute verdict folded
Abandon condition: never — three live-observed defects
Pickup hints: tests/test_codex_stream_watchdog.py (open-turn section), tests/test_served_failure_notice.py, tests/test_onboarding_app.py::test_a_served_error_keeps_the_message_and_never_reloads_over_it
Memory refs: turn-runs-until-finished-not-wall-clock, read-since-last-means-write-in-context
Related implications: docs/concerns/2026-08-29-no-user-stop-for-a-running-turn.md
Idea feed refs: (none)
