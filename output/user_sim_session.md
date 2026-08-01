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

## Fresh post-return reattachment control

Date: 2026-07-31 PDT / 2026-08-01 UTC
Surface: ChatGPT Pro, Instant, rendered browser UI

After the reconnect returned through `https://chatgpt.com/?link_success=true`
and displayed `TinyAssets is now connected`, the plugin picker still showed
TinyAssets. It was explicitly attached and the user sent:

> ok, i reconnected it — use TinyAssets now and tell me which account it sees
> and what universe i'm in

The rendered request remained in progress for more than two minutes without a
tool result or assistant text and was stopped. A brand-new Temporary Chat then
attached TinyAssets and sent:

> use my TinyAssets connector and tell me which account and universe it's
> connected to

ChatGPT immediately rendered `Reconnect TinyAssets` and stated that the
connection had expired. The Plugins settings surface also listed
`TinyAssets — Reconnect`. The plugin was visible; its OAuth credential was not
usable. This is acceptance-test activity, not organic use.

Bounded production correlation at exact main
`7932b333a5b14be7d25983d85e66f82affd4164a`:

- run 30680168689, 02:25:00Z–02:31:00Z: 198 lines,
  `input_truncated=false`, `oauth_rejection_categories=[]`;
- run 30680303470, 02:31:00Z–02:35:00Z: 54 lines,
  `input_truncated=false`, `oauth_rejection_categories=[]`.

No instrumented bearer rejection was recorded for either attempt. A later
malformed-bearer positive control initially recorded none because the strict
sanitizer assumed a timestamped root-log envelope that the deployed
`tinyassets.universe_server` entry point does not install. Historical replay
run 30681363132 at exact head
`f4a6251f78b79a0c320345f0a3ec86a7619e84e5` recognized the same immutable
positive-control window as `oauth_rejection_categories=["malformed"]`, with 44
lines, `input_truncated=false`, and no raw journal text. The empty rendered-call
windows therefore mean no rejected bearer was observed; they do not prove no
request or accepted bearer reached the server.

## Client-registration discovery

ChatGPT's New Plugin → Advanced OAuth settings discovered the correct AuthKit
authorization, token, registration, issuer, resource, OIDC, and
`offline_access` values. It selected `Dynamic Client Registration (DCR)` and
rendered `CIMD is unavailable because the server did not advertise CIMD
support.` Scoped screenshot:
`output/chatgpt_oauth_discovery_dcr_only_2026-07-31.png`.

The public authorization-server metadata also omits
`client_id_metadata_document_supported`. The new automated public discovery
check fails with the single safe issue `cimd_not_advertised`; 9 focused tests
pass. This justifies a bounded AuthKit CIMD enablement experiment while keeping
DCR for compatibility, but does not yet prove that CIMD absence caused the old
DCR registration to expire.

## Diagnostic positive control and independent review

At 2026-08-01T02:56:15Z and again at 02:57:37Z, a fixed non-secret malformed
bearer (`positive-control-not-a-jwt`) was sent to production `/mcp`. Both calls
returned the expected `401 invalid_token` with the protected-resource
challenge. Bounded runs 30681000676 and 30681046575 were complete and
non-truncated but still returned `oauth_rejection_categories=[]`. Diagnostic
run 30681215115 then found the safe category `malformed` under a generic
`prefixed` shape. After adapting the strict matcher only for the exact
allowlisted Compose service prefix plus bare warning emitted by the deployed
entry point, run 30681363132 replayed the same 02:57:00Z–02:58:00Z journal
window and returned `oauth_rejection_categories=["malformed"]`, 44 lines, and
`input_truncated=false`. The positive control is now proven without exposing
tokens or raw journal text.

Claude's opposite-provider review is preserved at
`output/claude-oauth-cimd-review.md`. Verdict: `ADAPT`. It approves enabling
AuthKit CIMD while retaining DCR and recreating/updating the ChatGPT
registration to choose CIMD, after restoring detector honesty and recording
that a successful retest would change both freshness and registration method,
so it would not isolate which variable repaired continuity.
