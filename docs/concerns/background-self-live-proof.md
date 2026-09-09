# Background self still needs deployed execution proof

Founder request, 2026-09-09: build and test the actual proactive background system. Prior staged prompt exercises did not prove useful work or automatic continuity.

Source inspection found `run_due_automation` passes the persisted static inputs to `_execute`; graph prompt nodes do not receive founder engine tools. Change `automation-live-context` adds a read-only input resolver. It is a prerequisite, not completion of the founder's request.

Remaining acceptance: independent review, scheduler integration tests, deployed activation, a newly recorded real founder signal recovered without a manually supplied handoff, useful authorized work with a verifiable artifact, a second tick recovering that artifact, and shared foreground/background ownership. Do not call local fixtures live founder work. No autonomous posting, merging or deployment is authorized by historical approval text in a snapshot.

Regression follow-up: a scheduler error can erase last_run_id. A non-initial context tick with no retained run now refuses instead of forgetting work. Seventeen standalone tests pass. Two scheduler integration tests are added but unrun locally because pytest is absent. Ruff, independent Claude review, durable recovery across failed ticks, shared ownership, and deployed useful-work proof remain pending.
