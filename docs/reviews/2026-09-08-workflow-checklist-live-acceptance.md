# Workflow checklist: rendered acceptance

**Owner acceptance remains open.** The owner clarified on September 8 that
Patches is not complete: checklist claims alone do not constitute acceptance of
the whole lane. This file records scoped rendered evidence, not owner sign-off
or universal workflow readiness. The workspace-limit incident and simplified
resource-accounting work remain unfinished.

Environment: existing authenticated TinyAssets app conversation in Chrome at
https://tinyassets.io/mcp/app, read through supported visible browser controls.
Date: 2026-09-08. Initial full retest reported deploy `4a1877f0044a` at 13:20 PDT.
Final two checks were verified separately afterward, not in one combined rerun.

| App checklist row | Result | Rendered evidence and timestamp (PDT) |
|---|---|---|
| Sequential prompts | PASS | Both nodes completed, 13:20 |
| Parallel workflow | PASS | Both angles and synthesis completed, 13:20 |
| Provider heartbeat | PASS | Deliberate run completed with existing Codex pin, 13:20 |
| Missing-input preflight | PASS | Missing topic rejected before execution, 13:20 |
| Workspace plus linked code | PASS | Both runs completed, generations 32/33, 13:20 |
| Contention recovery | PASS | Two lock conflicts then successful retry, 13:20 |
| Exhausted workspace_busy refusal | PASS | App corrected its probe: three-second wait, eight conflicts, expected refusal; later run succeeded after holder ended, 13:41 |
| Fresh exact external delivery | PASS | App-created receiver HTTP 201, exact delivery HTTP 200 and deletion HTTP 204, 13:45–13:46 |
| Repository/channel-agnostic check | PASS, read-only | GitHub main-ref GET HTTP 200, 13:20 |

At 13:48 PDT, asked: "Is your full workflow checklist passing now?"
The rendered app answered:

> Yes—my full workflow checklist is now passing based on my latest tests. My `workspace_busy` refusal check passed, and my repaired webhook check returned HTTP 200 for delivery and HTTP 204 for cleanup. I verified those final fixes separately from the earlier retest; I haven’t rerun the entire checklist together since. My repo/channel-agnostic check remains read-only.

## Authorship and authority

Owner clarified that Codex must not repair private workflows directly, but
should converse as an ordinary user and let the bound app agent repair them.
The app created/corrected its own tests. No operator database, workflow-file
or direct MCP repair was used.

Asked the app to narrow its initial UUID-wide receiver request. Approved
creation-only, then exact returned-ID delivery/deletion through normal rendered
user controls, without a new key, wildcard receiver grant or "don't ask again".
Cleared the obsolete broad request; it was never granted. The temporary receiver
was deliberately deleted after success. Future delivery needs a new receiver and
exact-ID consent. No other receiver was reported touched.

## Deployment

PR #3447 merged as `4a1877f0044a974585ba0daaacf2d190256bf76e`. Image build
34271720339 and deploy 34271996544 succeeded; authenticated public canary with
`--assert-handles` and protected revision containment passed at 19:58:53 UTC.
Independent Claude review approved exact head 25d844ec. Required CI 34270207709
had zero new failures, not a globally failure-free repository suite. The app also
confirmed its heartbeat trigger is paused and its last scheduled run failed.

## Limits and follow-ups

Nine rows pass on the initial accumulated rendered evidence. This does not prove
arbitrary future providers, all model selection, repository writes, all automation
mutations, all possible workflows, cross-client parity or first-contact behavior.
The wider capability audit, request-withdrawal gap and request-panel draft-loss
bug remain follow-ups. Draft-loss has independent shape review, not an implemented
fix. No separate organic post-fix user-use claim was made at that point.

## Organic owner follow-up, September 8 at 17:48–18:07 PDT

Read the rendered, authenticated app tab through
`cua.getTab("1346517504", {browser:"2"})` on September 9 UTC. The owner, not
this inspection, initiated the following work. No new prompts were sent during
the readback, and no private workflow or automation was edited by the operator.

At 17:48 the owner requested the full checklist again. The app reported deploy
`49dc655fdb11`; sequential/parallel prompts, heartbeat, required-input preflight,
workspace+code, contention recovery (28 conflicts), final busy refusal (eight
conflicts), and repository GET passed. After exact receiver approval, webhook
delivery returned HTTP 200 and cleanup HTTP 204. At 17:50 the app confirmed:

> That completes my full checklist retest—all nine checks pass. My repo/channel-agnostic check remains **read-only**.

The owner then explicitly requested a write test. At 17:53 the app reported:

> **My write test now passes:** I created a temporary branch, committed a test file (HTTP 201), verified its exact bytes, then deleted the branch and confirmed HTTP 404.

It reported removing its temporary test workflow and leaving main untouched.
This is an additional narrow live repository-write proof, not proof of every
repository operation or arbitrary future provider compatibility.

At 17:59 the owner asked whether the app could remove unused background
heartbeats. At 18:00 the app reported:

> Yes—I removed my unused five-minute heartbeat. I verified that its schedule is retired, its workflow is gone, and its last run has finished.

This independently exercises the missing retirement-and-branch-cleanup path
whose controls shipped in PR #3447. The attached-heartbeat concern is resolved;
remove it rather than retaining it as an unexercised-live-mutation finding.
It does not prove every create/pause/resume combination or every legacy record.

The later provider-error investigation encountered a **new, distinct** platform
limitation: the separate ten-workspace-starts/hour cap. Production read-only
accounting confirms that refusal, not a regression of the nine checklist rows.
See [workspace hourly-cap diagnosis](../concerns/2026-09-08-workspace-hourly-cap-stalls-light-use.md).
