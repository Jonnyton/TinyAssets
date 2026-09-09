# App read/write sweep reports five capability gaps

**Filed:** 2026-09-08
**Verified:** Rendered report read on 2026-09-08 at 21:51 PDT in the authenticated
existing-owner conversation at https://tinyassets.io/mcp/app, Chrome tab
1346517638, using `cua.getTab('1346517638', { browser: '2' })`.
The report is user-surface evidence, not independent reproduction of each cause;
the messages do not identify the deployed SHA or individual run IDs.

## Source (verbatim)

Universe, September 8, 2026, 9:39 PM PDT:

> I finished the nine checklist checks and a broader read/write sweep. **The checklist passed, but I found five gaps:**
>
> - **Editing workflows:** the documented `patch_node` operation is refused—even though failure messages tell me to use it.
> - **Workspace cleanup:** explicit `discard` falsely rejects a workspace as “not an ancestor.” I reproduced this twice.
> - **Reading results:** completed runs expose status but omit ordinary returned values and generated text.
> - **Failure display:** a failed run can still show its failed code node as “running.”
> - **Cancellation:** I have no exposed tool to cancel a queued or running workflow.

The same message reports passing sequential/parallel prompts, provider execution,
missing-input rejection, Unicode/binary file roundtrips, commands, workspace
contention/recovery, and automation create/pause/resume/delete. It also reports
repository branch/file write/read/delete success, webhook delivery HTTP 200 and
deletion HTTP 204, and 12 workspace starts without the old ten-start limit.
The agent says all disposable workflows, schedules, and remote artifacts were
cleaned up and nothing remains running. A second 21:39 message confirms the
webhook test was already complete; it is not evidence of another fresh run.

## Follow-up boundary

September 9, 2026 06:27 UTC: platform fixes deployed as
0082695793278fabf520c9bf2a8fa2694c4a2823, authenticated canary/SHA passed.
Exact retest prompt sent through the same app conversation. At23:30 PDT the app
confirmed editing, output readback, discard and failed-node state fixed; cancel
stops the run but leaves its code node displayed as running. At23:31 PDT it
confirmed fresh webhook200/204 and all nine older checklist rows passing.
Technical evidence: docs/reviews/2026-09-09-workflow-control-gaps-proof.md.
Keep this concern open for the cancelled-node terminal-state follow-up until
the agent confirms all five gaps closed. Source, tests and deployment do not
replace that acceptance. No organic post-fix use beyond this directed retest
has been observed yet.

September 9,07:11 UTC: cancellation terminal-state follow-up deployed as
ece0a8e25058221143b40859b2050cba0b610ad4 with authenticated canary/SHA proof.
Once-sent00:12 PDT exact retest has no rendered final result yet. After browser
transport loss and normal UI recovery, the saved conversation shows a00:16
"never confirmed — the reply did not arrive" notice, while a new exact-receiver
webhook request demonstrates the app did perform work. Root cause and backend
turn termination are not established. Do not duplicate the retest merely because
the reply was not delivered. Request details are open for the owner's approval;
all-five closure remains unproven. See output/user_sim_session.md for recovery.

The owner explicitly added closing all five gaps to the active limits goal on
September 8 PDT and made the webapp agent's message confirming closure the
completion criterion. Durable combined scope:
`openspec/changes/consolidate-platform-resource-policy/goal-completion-contract.md`.

Reproduce and fix the platform capability or discovery/response contract, not
the owner's private workflows. Check existing primitives before proposing new
public actions. Cancellation exposure overlaps the existing
[served-tool parity concern](2026-09-08-served-tool-capability-parity-gaps.md);
actual stopping behavior is separately tracked in the
[cancellation concern](2026-08-31-cancel-is-advisory-and-the-timeout-is-doing-its-job.md).
This read-only inspection sent no message, ran no workflow, and granted no access.
