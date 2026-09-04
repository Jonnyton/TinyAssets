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

---

## 2026-08-23 — Webapp ui-test: compute-agnostic surface parity (served agent)

**Surface:** live webapp `https://tinyassets.io/mcp/app`, signed in as founder
(universe `u-01kxm1vszd8hwp7em418asq8h9`), deployed sha `bce0f188` (verified via
`get_status` release_state: running_healthy, forward_canary passed).

**Prompt (typed as a user):** "I want to run my automations on a different
compute provider — say OpenRouter or Kimi, using my own API key. Can I add that
compute channel myself, and what do you need from me?"

**Rendered reply (served on codex, verbatim excerpt):**
> Yes, but not as a simple in-chat toggle from where I'm standing right now.
> What I can see in my live status is: my host is currently bound to `codex`;
> `api_key_providers_enabled` is `false`; my daemon is accepting `any` LLM type,
> but that is not the same thing as having BYO-provider channels wired in.
> So if you want OpenRouter or Kimi with your own key, this looks like a
> code/config change in TinyAssets, not something already exposed for self-serve
> use in this universe. [then asks which provider / global-vs-per-automation /
> where the key lives / models / routing policy / fallback, and recommends
> "add a provider adapter, enable API-key-backed providers in config, define a
> named compute channel…"]

**Finding (CONFIRMED):** the compute-agnostic capability shipped in `bce0f188`
and is live on the CONNECTOR surface (`write_graph target=connection
operation=connect_compute`), but the SERVED webapp agent cannot self-serve it —
it treats compute-channel building as an unbuilt code change.

**Root cause:** `tinyassets/engine_mcp_server.py` exposes to the served agent
ONLY: read_graph, get_status, run_graph, browse_commons, read_commons_shape,
remix_shape, read_brain, write_brain. It has NO write_graph (connect_compute /
connect_http / branch create-patch), no consent (grant_effector_consent), and no
serving-control (set_engine / bind_serving_provider / set_serving). Same
root-cause class as the pre-existing served-agent BUILD/RUN parity gap. Also note
the agent conflated the legacy `api_key_providers_enabled` host flag (gates the
fixed gemini/groq/grok providers) with the new grant-authorized `api_key_http`
model (authorized by the connection grant alone, not that flag).

**Status:** recorded as a P1 STATUS concern; fix is the served build-verb parity
work — authority-sensitive (served build+run = RCE-risk) → OpenSpec + Codex
before build. Positive result: deployed converse round-trip works end-to-end on
the webapp; codex serving is healthy (bwrap available).

---

## 2026-08-23 (cont.) — Surface-parity fix VERIFIED live (compute registration)

After #2491 (connect_compute handler) + #2492 (served enabled-tools allowlists),
deployed sha `f2c95f43` (running_healthy, canary passed). Re-ran the webapp ui-test
(`https://tinyassets.io/mcp/app`, founder).

- ui-test #2 (post-#2491, sha 70157f51): served agent reported `tool_search` returned
  "Found 0 tools" for compute registration — handler was DARK (not in the provider
  enabled-tools allowlist). This drove #2492.
- ui-test #3 (post-#2492, sha f2c95f43): prompt "register my codex subscription as a
  compute provider (connect_compute, subscription_cli/cli:codex/ref=codex)".
  - Turn 1 (model omitted): tool returned the REAL validation error
    `{"error":"connection_setup_invalid","detail":"model must be 1..200 printable
    single-line chars"}` — proof the agent actually invoked the deployed tool.
  - Turn 2 (model=gpt-5-codex): **"I registered it successfully. definition_id:
    provdef_5d696592b51813f32673e3daf49c134a"** (status registered, subscription_cli,
    cli:codex, gpt-5-codex, private) + the correct next step (select via
    llm_policy.preferred_provider).

CONCLUSION: the served webapp agent can now self-serve compute-provider registration
— the surface-parity gap for compute building is CLOSED, live-proven. Independent
read-back not available (read_graph target=connections lists outbound connections, not
provider definitions — a follow-up: add a definitions read surface). Post-fix clean-use
evidence = this founder run; no other users exist yet.

---

## [2026-09-03 23:39 PDT] VOICE DARK-DEPLOY RENDERED CHECK

TAB HYGIENE: one task-owned in-app browser tab for the production app check;
no chatbot prompt was sent.

USER ACTION: Opened the signed-in founder app at
`https://tinyassets.io/mcp/app`. The single Voice control rendered beside the
composer as disabled, with visible status `Voice is not enabled on this
TinyAssets host.` No Voice click, disclosure, microphone permission, provider
change, credential action, or live session was attempted.

MISSION SUMMARY:
- Production disabled-state rendering: PASS.
- Ready/live-microphone acceptance: intentionally NOT RUN; explicit founder
  authority and an eligible already-authorized current provider are still
  required.
- This is rendered app evidence, not a rendered Claude.ai/ChatGPT connector
  conversation and not a claim of cross-client Voice acceptance.

## [2026-09-04 00:02 PDT] VOICE CURRENT-PROVIDER READBACK

TAB HYGIENE: one task-owned signed-in TinyAssets app tab for this read-only
check.

USER ACTION: Asked the founder universe which provider currently powers it and
explicitly asked for no changes. The rendered response identified `codex` via
`subscription_cli` as the active binding. It said the visible `openai_chat` HTTP
registration is the inactive old `plug-and-play-test-model` artifact, not the
serving authority.

MISSION SUMMARY:
- Current binding derived by the authenticated app: `codex/subscription_cli`.
- Eligible `api_key_http` Voice bridge currently serving: no.
- No provider, credential, flag, Voice, or microphone state was changed.
