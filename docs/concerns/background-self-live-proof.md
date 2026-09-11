# Background self still needs deployed execution proof

Founder request, 2026-09-09: build and test the actual proactive background system. Prior staged prompt exercises did not prove useful work or automatic continuity.

Source inspection found `run_due_automation` passes the persisted static inputs to `_execute`; graph prompt nodes do not receive founder engine tools. Change `automation-live-context` adds a read-only input resolver. It is a prerequisite, not completion of the founder's request.

Remaining acceptance: independent review, scheduler integration tests, deployed activation, a newly recorded real founder signal recovered without a manually supplied handoff, useful authorized work with a verifiable artifact, a second tick recovering that artifact, and shared foreground/background ownership. Do not call local fixtures live founder work. No autonomous posting, merging or deployment is authorized by historical approval text in a snapshot.

Regression follow-up: a scheduler error can erase last_run_id. A non-initial context tick with no retained run now refuses instead of forgetting work. Seventeen standalone tests pass. Two scheduler integration tests are added but unrun locally because pytest is absent. Ruff, independent Claude review, durable recovery across failed ticks, shared ownership, and deployed useful-work proof remain pending.


Verified 2026-09-11 in the Linux Python 3.13 workspace: 27 context tests and 7 checkpoint tests passed; compilation and plugin staging passed. The live private workflow produced a real selector generator-consumption fix and passed 8 new tests with manually supplied context (run ddbb617dc9e449f1). Separate execution checks passed 9 selector fixtures, then 17 selector/discovery fixtures, preserved earlier completion, and rejected replay before workspace creation. This is execution evidence, not automatic context-recovery proof.

The new 20-minute automation is staged and paused, preserving four historical drafts and the verified results; the original fixed-snapshot schedule remains active. The current runtime does not include the resolver. Independent Claude review is blocked: the workspace executable is absent (exit 127), and an explicit live Claude review is refused because that provider is not connected to this universe. A review request is pending in the founder app. Shared foreground/background task ownership is still open; artifact deduplication does not implement it.

CI on 90db00fb98df287168798d6f1b586711a0570a45 ran 15,065 tests and identified this concern's missing index link as its sole new failure. The current change adds that link without modifying the gate decision or quarantine.
