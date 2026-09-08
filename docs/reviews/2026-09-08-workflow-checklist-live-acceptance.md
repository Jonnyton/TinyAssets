# Workflow checklist: rendered acceptance

Environment: existing authenticated TinyAssets app conversation in Chrome at
https://tinyassets.io/mcp/app, read through supported visible browser controls.
Date: 2026-09-08. Latest full retest reported deploy `4a1877f0044a` at 13:20 PDT.
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

Nine rows pass on the latest accumulated rendered evidence. This does not prove
arbitrary future providers, all model selection, repository writes, all automation
mutations, all possible workflows, cross-client parity or first-contact behavior.
The wider capability audit, request-withdrawal gap and request-panel draft-loss
bug remain follow-ups. Draft-loss has independent shape review, not an implemented
fix. No separate organic post-fix user-use claim is made.
