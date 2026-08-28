# Worktree purpose

Purpose: fix-http-deposit-error-detail
Provider: claude-code
Branch: claude/fix-http-deposit-error-detail
Base ref: origin/main
Issue/PR: PR pending — found in the founder's live app conversation 2026-08-27
PLAN refs: onboarding app / generic HTTP connection deposit (connect_http)
Ship condition: onboarding tests green (incl. the new red-provable regression test),
  ruff clean, plugin mirror rebuilt; live proof = a real deposit rejection now
  renders the actionable detail in the app.
Abandon condition: superseded by a broader deposit-form rework.
Pickup hints: tinyassets/onboarding/app.html btn-connect-http handler; the Claude
  connect path (~line 1003) was already detail-first and is the pattern copied.
Memory refs: desktop-app-is-electron-cdp-testable, live-test-finds-what-tests-cannot
Related implications: the founder's GitHub api.github.com deposit never landed;
  endpoint validation was fine, the destination-name slug rule refused it silently.
Idea feed refs: (none yet)
