# Live connector acceptance session

Date: 2026-07-31 PDT / 2026-08-01 UTC
Environment: production ChatGPT and Claude web clients, `https://tinyassets.io/mcp`
Deployed revision: `ff2eb75404b87e929997e4aa632a461ca4bcc322`
Image: `ff2eb75404b8@sha256:081f8411dff0e2b57b8186e125eb361029057d7ac023327da66f5b5c8f9ef17a`

## Claude route

Claude was signed in and showed the installed TinyAssets connector as enabled.
The test used an incognito conversation, but Claude refused the prompt before a
connector call because the account had reached its monthly spend limit. The
session therefore continued in ChatGPT, which is an allowed rendered connector
surface for this acceptance gate.

## ChatGPT anonymous connector read

ChatGPT Pro was signed in. A Temporary Chat used the Instant model and attached
the visible plugin result `TinyAssets — Browse and collaborate with TinyAssets
universes.` The user sent:

> Use the attached TinyAssets plugin now to identify the current connector
> principal/account fingerprint and list the universes I can access. Do not
> guess or use prior chat memory; summarize only the live plugin result.

The rendered live result reported:

- principal fingerprint:
  `v1:anonymous:61f932589845e4c03de4d72d34469cc0f372c893a49121b3eb1012f888bfd291`
- bearer credential present: no
- prior session context: no
- active universe: `concordance`
- 15 visible public universes: `concordance`, `default-universe`, `earthos`,
  `echoes-of-the-cosmos`, `grandma-bread-recipe`,
  `local-bubble-galactic-survival-model`, `meridian-ashes`, `paper-notes`,
  `patch-loop-live`, `team-standup-action-tracker`, `tiny`,
  `u-01kxm1vszd8hwp7em418asq8h9`, `u-01ky3gkxg9qmz111v5qk7p2qbm`,
  `u-01ky3zh1arr8qth8jee7zx63pq`, and `workflow-voice`

ChatGPT also reported that the required opening `converse` call was blocked by
its safety checks, so no universe-authored reply was available. Main-pane
evidence: `output/chatgpt_tinyassets_status_2026-07-31.png` (captured
2026-08-01 01:56:51Z).

## OAuth reconnect and failed return continuity

The same conversation then sent:

> Now use TinyAssets to list the public custom agent definitions available to
> remix. For each result, show its definition ID, name, and whether lineage
> information is present. Use the live plugin, not memory.

ChatGPT rendered `Reconnect TinyAssets` and said the connection had expired.
The user selected Reconnect, then Connect in ChatGPT's `Add TinyAssets to
ChatGPT` dialog. The OAuth return reached:

`https://chatgpt.com/?link_success=true`

The observed settings return target was the same conversation with
`?oauth_success=true`; navigating to it restored the conversation but no
longer showed Temporary Chat. The original custom-agent request did not retry.
The user then sent:

> The TinyAssets OAuth reconnect just returned successfully. Use TinyAssets
> now to re-check the live connector principal/account fingerprint and whether
> a bearer credential is present. Do not use the earlier anonymous result or
> memory.

No assistant response or tool call appeared. After reopening the attachment
picker and searching for TinyAssets, the installed TinyAssets plugin result was
absent; only unrelated similarly named image files appeared. Main-pane
evidence: `output/chatgpt_tinyassets_reconnect_2026-07-31.png` (captured
2026-08-01 02:01:47Z).

## Acceptance result

Failed closed. OAuth linking reached a success redirect, but the returned
conversation did not retain a usable TinyAssets connector, did not prove a
bearer-authenticated principal, and did not execute the custom-agent read.
Neither OAuth continuity nor custom-agent live acceptance is complete. This
session is acceptance-test activity, not organic post-fix user evidence.

## Bounded production correlation

Manual read-only workflow run
`https://github.com/Jonnyton/TinyAssets/actions/runs/30679614519` inspected the
complete 2026-08-01T01:52:00Z–02:02:00Z journal window. It ran at independently
approved exact head `7a8e1f2fbfc39e38055723e1da23ea34ad9ed612` and returned
`input_truncated=false`, 812 source lines, and
`oauth_rejection_categories=[]`. The workflow emitted no raw journal text.

This result means the rendered attempt did not produce an instrumented bearer
rejection. It does not prove that a token was accepted. The next rendered test
must explicitly reattach TinyAssets after OAuth returns and force an
authenticated tool call before validator repair is authorized.

## [2026-08-01 11:29 PDT] LEAD DIRECTION agent-interchange acceptance

The user's build/deploy request authorizes one isolated live acceptance chain:
import a disposable declarative foreign agent, inspect its loss report, remix it
with public definitions from other creators, publish it, create a private test
binding, and export it again. Do not activate workflows or perform external
effects. Use ordinary user-language prompts through the visible TinyAssets
connector and retain only non-secret IDs/fingerprints in evidence.

Deployment prerequisite passed: image `4c6e020fdb72` was published by run
`30712318544`; production run `30712443230` passed daemon health, canonical MCP
canary, exact-seven assertion, access gate, receipt proof, and release receipt.

## [2026-08-01 11:34 PDT] USER BLOCKER no host-visible chatbot route

Claude and ChatGPT visible-driver preflights both failed because launched Chrome
never exposed CDP on port 9222. The Codex in-app-browser runtime then reported no
available browser backend (`agent.browsers.list() == []`). No prompt was sent and
no direct MCP substitute was used. Rendered connector acceptance therefore
remains unproven; this is a harness/browser blocker, not a connector failure.

## [2026-08-01 11:36 PDT] POST-DEPLOY WATCH

Scheduled production uptime canary run `30712596613` passed after deployment.
GitHub issue searches found no `stage_import` or `convert_export` reports and no
new deploy-failed issue for image `4c6e020fdb72`. No operation-level production
trace or support record showed organic use of agent interchange, so clean user
use remains unproven and the STATUS monitoring row stays open.
## [2026-08-01 12:15] SYSTEM DIALOG _dismiss_inline_permission_card — detected: "refused Always-allow (not TinyAssets Server card: write graph from tinyassets)" auto-dismiss: skipped

## [2026-08-01 12:06 PDT] USER NOTE repaired schema deployed

PR #2063 merged as `83f2c006`; image run `30713923287` and production run
`30714055993` passed build, health, canonical MCP, exact-seven surface, access,
receipt, and release-state gates. An old Claude conversation retained the prior
tool schema, so acceptance moved to a newly created incognito browser target.

## [2026-08-01 12:12 PDT] USER ACTION fresh connector identity

The new incognito conversation rendered bearer-present status and the same
non-secret principal fingerprint
`v1:3bbaa0d62599ff68974cbea0415b40f17b8d53f6dd2bd39dcceb889235fa9898`.
Tab hygiene remained one tab.

## [2026-08-01 12:15 PDT] USER BUG production commitment key absent

Asked the fresh rendered client to privately stage the disposable Evidence
Weaver JSON and inspect its report without publication. Using the repaired live
tool description, Claude constructed a declarative adapter and invoked
`write_graph stage_import`; this proves the prior envelope-discoverability bug
is fixed. The server then failed closed with `agent_validation_error` because
neither `TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY` nor the master idempotency HMAC
key contained at least 32 bytes. Nothing was staged or published. Production
must install a dedicated secret through the protected deploy path before retry.

## [2026-08-01 13:00 PDT] USER ACTION secure prerequisite deployed

PR #2069 merged as `efda5b404681eaeb4d7d0bcdcd949efcd3ca55fd`.
Image run `30715868638` and production run `30715891674` passed. The deploy
validated the dedicated repository secret before remote mutation, installed it
through the protected daemon-only path, started the exact image, passed daemon
health, canonical MCP, exact-seven, access, unchanged-receipt, and forward
canaries, and published a terminal release-state receipt.

## [2026-08-01 13:02 PDT] USER ACTION rendered import and report

In the same fresh identity-checked incognito Claude conversation, the user
retried the disposable Evidence Weaver foreign JSON. Claude constructed the
adapter from the rendered TinyAssets tool description, corrected its first
tags mapping after a bounded validation error, and staged the candidate
privately as `agent_stage_01kyzematb75t59gp29dhkp4ra`. The rendered response
showed an exhaustive report: identity fields were preserved and
`/extra/purpose` was explicitly unsupported and represented as a tag workaround;
the conversion was correctly labeled non-lossless. Nothing was published by
the staging operation.

## [2026-08-01 13:04 PDT] USER ACTION commons discovery

Claude searched both the structured public agent registry and broader commons.
The structured registry returned zero definitions, including an unfiltered
browse. Wiki results were design/process pages rather than published agents, so
Claude correctly refused to misrepresent them as other-creators' remix parents.
A truthful cross-user or multi-parent rendered remix remains blocked by an
empty live commons.

## [2026-08-01 13:06 PDT] USER BUG publish provenance gap

The authorized standalone continuation published public definition
`agent_01kyzeqabemcqb0bsnfegfptdr`, created private binding
`agent_binding_01kyzeqyd010hwever0mfyeyf6` in universe
`u-01kxm1vszd8hwp7em418asq8h9`, independently read the binding back with
`configuration.visibility=private`, and exported the package. No workflow was
created or run and no external effect was triggered. The export preserved the
agent components and content fingerprint
`ffd211eacae6d6fafb2a6bf19dd231db9dda5d0339905ce75c2d728780509d21`, but
`external_origins` and portable lineage were empty: safe receipt-bound source
digest and adapter metadata did not propagate into the published definition.
This rendered client finding is now task 3.5 and must be fixed/redeployed before
interchange acceptance can close.

## [2026-08-01 13:38 PDT] USER ACTION provenance repair deployed

PR #2075 merged as `97f797ee369c6e1833ec28076824a22bc0e77960` after
independent exact-head approval. Image run `30717175465` and production run
`30717318784` passed image publication, HMAC validation/install, daemon health,
canonical MCP, exact-seven surface, access, fleet/receipt, forward canary, and
terminal release-state gates.

## [2026-08-01 13:39 PDT] USER ACTION rolling-upgrade cleanup and fresh stage

In the same one-tab, identity-checked incognito Claude conversation, a read of
pre-fix published stage `agent_stage_01kyzematb75t59gp29dhkp4ra` confirmed that
`source_commitment` and `source_commitment_algorithm` were absent after upgrade,
while the safe sanitized-source digest remained. Claude then staged a second
disposable foreign definition as `agent_stage_01kyzgvhdtw52wdgghy63f90qw`.
The rendered candidate already contained its `agent_interchange_import`
external origin, and the exhaustive non-lossless report accounted for every
source path. Nothing was published by staging.

## [2026-08-01 13:40 PDT] USER ACTION post-fix publish, private bind, and export

Claude published definition `agent_01kyzgwbw2gxnhqzdkqmnsg71b`, created binding
`agent_binding_01kyzgwjgnfb98f1c7wht4kpgm`, and independently read the binding
back as `configuration.visibility=private`. It then exported the definition.
The export preserved content fingerprint
`c53bd308aa26be2ba78222f9e09421f3d511fe89179d7bc9796db6b483ce6a90`
and the safe external origin: adapter ref `user:disposable-import-2`, adapter
version `1.0.0`, adapter digest, sanitized-source digest, and both explicit
`sha256` algorithm fields. A separate rendered read of the public definition
confirmed `adapter_digest_algorithm=sha256` and no `source_commitment` key.
No workflow was created or run and no external effect was triggered.

The structured live commons still contained no public definition authored by a
different creator, so a truthful rendered cross-user blend remains unproven.
This acceptance traffic is not independent organic-use evidence.

## [2026-08-02 15:54 PDT] UNIVERSE CUSTOM AGENTS FOLDBACK

The canonical public canary passed with the exact seven advertised handles:
`python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp
--assert-handles --verbose`. A direct supporting status probe reported live
release `7256335820ef2247c4d7880455a67d88f5dc5c3d`, whose history contains the
custom-agent implementation merge `ba87b1dd89986ad2c9e37880fc7a34467569f9b5`.

The rendered one-tab, identity-checked incognito Claude.ai conversation above
is the acceptance proof for this change: it published public definition
`agent_01kyzgwbw2gxnhqzdkqmnsg71b`, created and privately read back binding
`agent_binding_01kyzgwjgnfb98f1c7wht4kpgm`, and exported the definition with
its fingerprint and safe origin metadata intact.

A freshness check of public GitHub issues/PRs and the available production
status evidence found no independent post-fix custom-agent use. The rendered
acceptance traffic is synthetic and is not counted as organic use. Clean
organic use therefore remains unproven and is retained as a STATUS monitoring
item rather than overstated as acceptance evidence.

## [2026-08-02 16:25 PDT] CHATGPT OAUTH CONTINUITY RETRY

TAB HYGIENE: 1 host-visible ChatGPT tab throughout; Temporary Chat was on,
model was Instant, and TinyAssets was visibly attached before each prompt.

Asked: `i added TinyAssets — can you check whether my connector is working and
tell me what it can see?`

ChatGPT rendered `Reconnect TinyAssets` because the connection had expired.
Reconnect and Connect completed successfully in the same tab and returned
through `link_success=true`. The original call did not resume into a rendered
tool result.

## [2026-08-02 16:29 PDT] USER BUG post-OAuth call still has no result

Returned to the exact conversation, visibly reattached TinyAssets, and asked:
`can you try that TinyAssets connector check again now?` The user turn was
preserved, but no assistant or tool result rendered before the 120-second
driver timeout. No principal fingerprint was shown, so the authenticated-call
acceptance did not pass. Full driver trace is local and ignored at
`output/chatgpt_chat_trace.md`.

## [2026-08-02 16:32 PDT] POST-FIX WATCH

Freshness check: `origin/main`
`9f8975ea51b063d868b89f25b080fe03606feb8b`; public repository issues/PRs plus
the available session and audit evidence showed no independent clean ChatGPT
OAuth use. This synthetic failed retry is not organic-use evidence. Keep the
STATUS monitoring watch open and leave both OpenSpec acceptance checkboxes
unchecked.

## [2026-08-02 19:34 PDT] PER-USER CANONICAL FOLDBACK PREFLIGHT

TAB HYGIENE: 1 host-visible ChatGPT tab throughout. A fresh chat preserved the
complete connector-check prompt but rendered no assistant or tool result within
three minutes; no approval dialog or principal fingerprint appeared.

This is not post-fix acceptance evidence: the supporting public `get_status`
receipt still reported production `git_sha=81c01fa721afa6c29177de32d48b8f77c4e09419`
at 19:34 PDT, which does not include #2184 merge
`d8dea1a9a22aae7338aa6e91e71e96aa3929979c`. The exact-seven public canary was
green. Task 5.1 remains unchecked until a receipt containing the merge is live
and both Claude.ai and ChatGPT render the canonical set/run acceptance flow.

## [2026-08-02 20:47 PDT] CHATGPT OAUTH CONTINUITY POST-#2037 LOCALIZATION

TAB HYGIENE: 1 host-visible ChatGPT tab for the TinyAssets retry; Instant was
selected. Reconnect and Connect completed in the same tab and returned through
`link_success=true`, then TinyAssets was explicitly reattached in the composer.
One mistaken Canva menu selection briefly opened a second OAuth tab; it was
closed without authentication and the TinyAssets conversation was healed back
to one tab before the retry.

Asked: `can you try TinyAssets again now and tell me whether I'm signed in and
what it's connected to?`

## [2026-08-02 20:51 PDT] USER NOTE always-allowed TinyAssets

The turn initially waited on ChatGPT's first-use approval card. Selected
`Always allow` before continuing the existing turn.

## [2026-08-02 20:52 PDT] USER BUG TinyAssets converse action not found

ChatGPT rendered `Resource not found: TinyAssets.converse`. It could discover
the installed connector and its actions, but invocation failed before identity
or universe resolution; no principal fingerprint was rendered. Full driver
trace is local and ignored at `output/chatgpt_chat_trace.md`.

Sanitized production run 30782860916 covered 2026-08-03T03:47:00Z through
03:51:45Z: `input_truncated=false`, 142 source lines, and
`oauth_rejection_categories=[]`. Public metadata and successful deploy run
30780952337 both used resource `https://tinyassets.io/mcp`; WorkOS was enabled
and production audience bypass remained forced off. No rejected-bearer category
was observed; the rendered action-resolution failure makes ChatGPT's connector
registration/attachment seam the next repair boundary without establishing
whether an accepted bearer reached validation. It is not
authenticated-continuity acceptance evidence.

## [2026-08-08 ~13:05 PT] SLACK USER-PATH-MAP WALK — Round 1 (B1 progress + C1 template + F1 automation)

Driver: Claude Code, browser (Chrome, founder Slack login), DM D0BMPBUBBSB
(u-tiny / "Demo App"), workspace T0BN5LK57FT. Prod hotfix hash-verified
(5/5 files match claude/slack-socket-mode) before driving.
Map: docs/audits/2026-08-08-agent-user-path-map.md.

Typed as user: "morning! set me up a daily automation: each morning give me 2
bullets on what's new in AI agent platforms, delivered right here. use one of
your starter patterns if that helps. tell me what you're doing as you go - i
want to see the steps, not just the final answer."

Watching for: progress notes DURING the turn (B1), template use (C1),
automation created paused + told so (F1), finish state (B2), consent ask if
anything costly fires (E1).

RESULT Round 1 (sent 20:20 PT, final reply 20:22 PT — ~2 min turn):
- 20:20 instant "on it…" ack; 20:20 mid-turn note: "Chat surface lookup was
  ambiguous — I'll deliver to your DM with me directly…"
- 20:21 finish note: "done — Built branch ai_agent_platform_daily (id:
  648eec466166) using the sequential starter template — gather → draft → END.
  Wrapped it in automation ai_agent_news_daily (id:
  work_01kzfp7tj2t14xr0kwsd8neyby), daily cadence (86400s), delivering to
  Jonathan's Slack DM. Started — state is now active."
- 20:22 final: what's running + HONEST limitation (gather = LLM inference, not
  live web) + offered upgrade (add web search) + "first briefing arrives
  tomorrow morning."
VERDICTS: C1 PROVEN (template instantiated from a plain user ask). F1 PROVEN
(real ids, cadence, deliver_to this DM). B2 PROVEN. B1 OBSERVED for a short
turn (2 mid-turn notes; long-job walk still pending).
FINDING (E1 gap): agent called start_automation in the SAME turn — no consent
ask — despite build_automation's created-PAUSED contract. Run-once asks
(proven 2026-08-07); run-daily-forever did not. Consent model inconsistent for
recurring spend. Candidate primitive fix: costly-gate start_automation +
run_automation_now like run_branch.
NEXT: took the offered upgrade — walks C4 (iterate an existing branch); also
probes whether a branch node can get real web access (possible MISSING
primitive).

## [2026-08-08 20:24-20:27 PT] Round 2 (C4 iterate + B1 long-job progress + consent correction)

Typed as user: "yes - upgrade it to use real web search... also: you started
the daily one without asking me... for anything that spends on a schedule i
want the final start it? question to be mine..."

RESULT (6 replies, ~3 min): live step-notes streamed DURING the work:
"Reading operation scopes to find the web search one" / "Defining web_search
operation scope" / "Building upgraded branch with web_search on the gather
node" / "Building new automation (paused) with the upgraded branch". Then
finish note + final: old ai_agent_news_daily PAUSED (pulled down), new
ai_agent_news_daily_v2 (work_01kzfpfc9216d7r8bwv85wdj6g) built PAUSED, gather
node has web_search in tools_allowed, declared operations
llm_inference/web_search/chat_post, closes with "Want me to start it?"
It restated the corrected rule: "Any automation on a schedule gets built and
left paused; want me to start it? is always the last line."

VERDICTS: C4 PROVEN. B1 PROVEN (4 step-notes mid-turn on a real job).
F2 stop-path PROVEN (paused the old one). F5 OBSERVED (scope defined +
declared ops). A3 accepted in-turn; durable recall needs a LATER conversation.
E1 consent ask now pending MY yes — walks record_approval next turn.
OPEN PROBE: does web_search in tools_allowed actually reach the web at run
time, or is it declared-but-unhonored? Next: yes + run-now, judge freshness.

## [2026-08-08 20:27-20:37 PT] Round 3 (E1 turn-boundary consent seam surfaced)

Typed as user: "yes, start it. and run it once right now so i can see today's
bullets..." (my yes arrived WITH the request).

RESULT (2 replies, honest stop): "Hmm - the approval recorder hit a
permissions snag on my end. Jonathan, could you say yes, run it one more time
so the system can pick it up fresh. That's the only gate between here and
your bullets."

DIAGNOSIS (verified against design, not a crash): the pending approval record
is created ONLY by a refusal inside the turn, and record_approval unlocks only
for pendings that PREDATE the turn (defect-3 fix from 2026-08-07). The prior
turn asked "Want me to start it?" in PROSE without arming the gate, so the
user pays an extra round trip for a yes already given. Agent honest, but
self-misdiagnosed a designed gate as "a permissions snag."

PRIMITIVE CANDIDATE (SDK approval-requested state, audit #7 open question):
a request_approval tool - the agent ARMS the consent gate in the same turn it
asks the prose question; next-turn yes maps to the pre-existing pending.
Keeps the no-self-approval invariant intact; removes the double-ask.

Replied "yes, run it" (turn 4): expect record_approval + start + run-now +
delivery; web_search-honored-at-runtime probe still open.

## [2026-08-08 20:37-20:55 PT] Round 4 (E1 completes; run executes; TWO dead primitives found)

"yes, run it" (armed pending) -> approval recorded, automation triggered, run
25b32388ab12425a queued to background executor. Turn honest and complete.

SERVER-VERIFIED RESULTS (checkpoints DB + Slack API history):
1. tools_allowed NOT honored at run time: gather node LLM ran without
   WebSearch -- its own output: "Web search requires a permission grant I
   don't currently have in this environment." Draft node honestly refused to
   fabricate bullets from the error text. Run "completed" with a meta-question
   as its briefing.
2. NO delivery: deliver_to=slack:T0BN5LK57FT:U0BMXFK83UK is stored and unread;
   0 messages posted to the DM after the run finished. User still sees "It's
   running!" forever.
3. NO scheduler exists: nothing outside store/agent-actions/tool-defs
   references scheduled_work. cadence_seconds is a number nobody reads. The
   agent's "first briefing arrives tomorrow morning" is a false promise.

ENABLING PRIMITIVES TO CODE (Task 3):
A. Map node tools_allowed (web_search/web_fetch vocabulary) -> provider
   allowed_tools at node execution, gated by the automation's
   declared_operations. Capabilities are user-declared; the runner must honor
   the declaration.
B. Scheduled-work executor loop in the daemon: run due active automations AND
   post finished-run output (run-now included) to deliver_to.
C. request_approval tool so a prose "start it?" arms the consent gate.

## [2026-08-08 20:56-21:07 PT] Rounds 5-7: primitives deployed and PROVEN live as a user

Deployed commit 3515d7b5 (7 files, docker cp route, backups kept, daemon
restarted healthy, loopback canary exit 0, 5/5+2 md5 verified).

Within the executor's first sweeps, UNASKED, the DM received:
1. the stranded 25b32388ab12425a backlog ("*ai_agent_news_daily_v2*:
   findings/briefing") - delivery of run-now results works;
2. "*weekly_update* run 383b6bd1652741d6 FAILED: CompilerError: Node draft...
   input_keys [brief] not present" - a SECOND stranded automation fired on
   its elapsed cadence and its failure was delivered AS a failure. Fail-loud
   delivery works.

Round 6 (the decisive walk): "run the news briefing once more so i can check
the web search actually works this time."
- Agent: "Gate is armed. Ready to fire - just say yes..." (request_approval
  arming its prose ask - Primitive C live, no double-ask).
- Typed "yes" -> approval recorded -> run 20:05 -> 20:05:48 the DM received
  *ai_agent_news_daily_v2* findings DATED THIS WEEK: "Cloudflare - Agents
  Week 2026 (Aug 3-7)... Cloudflare Wallets... Browser Run...", "Microsoft -
  Project Perception (public preview Aug 3)". Impossible without live
  WebSearch (model cutoff Jan 2026). Primitive A live. Delivered without
  being asked. Primitive B live.

VERDICTS: tools_allowed honored (A) PROVEN; scheduler+delivery (B) PROVEN
both success and failure shapes; consent armed-at-ask (C) PROVEN, one yes,
no repeat ask. E1 now covers resume (recurring spend gated).

Round 7 in flight: stop_automation as a user (weekly_update) + "what can you
do" discoverability (A4).

## [2026-08-08 21:2x-22:0x PT] X-POSTING GOAL - walk, build, deploy

Round 8 (attempt as user): asked for an X automation - project updates in my
voice, niche watching, learns from engagement. Agent built the RIGHT shapes
with what existed: x_ai_watcher (6h, sequential) + x_ship_post (on-demand,
evaluator_optimizer with a performance_notes input), both PAUSED, notes to
wiki/x-automations.md - and named its blockers precisely: (1) no X API
creds, (2) watcher is LLM-knowledge not live web (it did not know
tools_allowed is honored now), (3) no engagement read for the learning
loop, (4) wants voice examples.

CODE (commit ea762659, deployed 2026-08-08 ~21:55 PT, 5/5 md5, canary
green): effector surface (grant approval-gated -> effector_consents, the
SAME store twitter_post checks; revoke ungated; unknown sinks refused
before the gate; @handle canonicalization + key-safe approval keys) +
x_engagement.py (receipts -> X public_metrics; honest empty/missing-creds/
vanished-post shapes) + node action posts.engagement + agent tools
(authorize_posting / list_posting_authorizations / revoke_posting /
read_post_engagement) + packet contract in build_branch docstring + posting
flow in the agent prompt. 83 tests green, lint clean, mirror rebuilt.

Round 9 in flight (test as user): gave posting permission in words +asked
for live-web watcher + the learning story. Expect: armed consent ask ->
my yes -> authorize_posting recorded; watcher rebuilt with
tools_allowed=[web_search]; engagement explained (honest no-creds state).
Still host-action: TWITTER_* env keys (X developer portal).

## [2026-08-08 22:0x-23:0x PT] X-POSTING GOAL - live proofs, one incident, three more fixes

Round 10 (consent walked end-to-end): armed pending
effector.grant:twitter_post:kwisatzh4derach -> typed yes -> approval
recorded -> authorize_posting succeeded. SERVER-VERIFIED:
(twitter_post, @kwisatzh4derach, user_01KWGB2NV5PV4PWHT5RYKJPB8X, None) in
/data/u-tiny/.effector_consents.db - the exact store the post effector
gates on.

Round 11 (live watcher): x-ai-watcher-live (57c046067cb0,
tools_allowed=[web_search]) ran (547fb4933d204690); executor delivered 5
findings DATED Aug 5-7 WITH SOURCE LINKS (Cloudflare Kitesurf, Cloudflare
OS...). The "niche events we might want to post about" half is proven.

Round 12 INCIDENT: my terse "topic: ... run it." (answering the agent's own
question) was misread by the stateless next turn as a build request ->
agent published+activated "Tiny" and connected it WORKSPACE-WIDE, no
consent ask. Rollback turn was honest and exposed a second gap: NO
disconnect tool existed (unbind_channel had no agent tool).
FIXES (commits eb9f56c7 + 1e68d5ba, deployed, canary green):
(chat_surface, bind_channel) now approval-gated with scope-exact keys
(channel vs workspace_wide); disconnect_agent_from_chat added (ungated -
narrowing); prompt teaches "a terse message after my own armed ask is
almost always the ANSWER - check list_pending_approvals first" and armed
asks must carry every given input.

Round 13 (learned drafter): "checking pending approvals" reflex fired
(new prompt live); run e7027bd01474475c completed - in-node
posts.engagement read returned the honest empty state ("No post history
yet - drafting cold") and produced a clean on-voice draft. Disconnect
attempt refused: pre-existing ambiguous_agent_binding on T0BN5LK57FT -
filed as P2 (needs binding-id-targeted unbind).

STILL HOST-ACTION: TWITTER_* creds (X developer portal, OAuth1.0a user
context) into the daemon env, vault-first. Until then: posting + metrics
refuse honestly; the parked first draft awaits keys + founder ok.
