# Automatic OpenRouter bootstrap: Fable5.1 shape review

September15,2026 UTC, peer31465 completed386s,exit0. Round2 of unpowered lane;
round1 was the earlier manual-connect research. VERDICT: ADAPT. Runner final
output lost the actual review after a Stop-hook acknowledgment. Recovered from
this dispatch's own assistant text b1ecd869-750b-4047-b5eb-9b006d5a8078. No new
review dispatched to recover it. Runtime citations: reconnect worktree, design:
0a7f/openspec/changes/select-agent-models/automatic-model-bootstrap.md.

## Required build corrections and lead disposition

1. ADAPT/CORRECTION after lead's real HTTP fixture: the claim that a fully bound
   HTTP source is always invisible was overstated. Config projection writes
   engine_source=requester_local (config.py), which the old helper recognizes.
   The helper still mixes stored native/config presence with readiness and
   treats unreadable state as attached. New projection must distinguish current
   serving, empty, recovery and unavailable; enterSignedIn must route on it.
   HTTP-only serving is a preserved passing control, not the reproduced failure.
2. AGREE: a distinct callback path is necessary. Existing completeSignInIfCallback
   consumes any root ?code= as WorkOS and strips it. Handle model callback before
   identity callback; do not assume provider preserves custom query parameters.
   Exempt only that exact public callback shell from middleware, never begin or
   exchange. Browser bearer plus flow/verifier correlation still gates exchange.
3. ADAPT: expose a safe non-serving first-binding helper; never call legacy
   ensure_founder_serving before discovered/free-only consent. Generic
   custom_agents.create_binding already exists (review's "only creator" was too
   broad), but _platform_binding's reset behavior must not overwrite content.
4. CORRECTION TO ROUND1: request_from_user does NOT require the universe agent.
   _owner_gate accepts the app owner/admin; capture_action runs on creation and
   execute_action on owner answer. Reuse it; no new consent raiser/tool/store.
5. AGREE: lookup_flow checks user only. Explicitly re-resolve current home/admin
   before exchange network and writes; stored flow home is not a current check.

Exact source map: onboarding/__init__.py:735; api/universe.py:6084;
api/http_connection.py:644; onboarding/app.html:656-675,2741;
provider_serving_binding.py:1139; model_access_requests.py:59,97;
onboarding/serving.py:105,361-380; api/pending_requests.py:122-153,663,690-697,
1434-1455; onboarding/openai_device.py:296-357.

## Agreed implementation sequence

New setup projection -> tagged, expiring owner/home/preset-bound PKCE begin ->
authenticated fixed-endpoint exchange -> exact HTTP scopes/candidate/discovery ->
non-serving first binding -> existing deduped free-only model-access request ->
owner answer binds/enables -> optional generic additional-LLM request.

Free-only cost_caps=None and fresh discovered access remain enforced at launch.
Catalogue GET must allow output_modalities query. Same-tab navigation avoids
popup blocking. OAuth's own consent cannot replace TinyAssets model authority:
exactly one return-page model confirmation, not a buried rail or auto-answer.
Acquisition data can describe PKCE code-to-user-key (no client id/refresh), without
pretending this is every OAuth2 protocol. Existing stores give partial resume;
short-lived OAuth state can expire on restart with an honest restart action.

Web first: native callback forwarding is separate follow-up; do not advertise a
working native OAuth flow until tested. Reauthorization can leave vendor orphan
keys; explain rather than auto-delete. Provider privacy settings and lack of
eligible free models require honest recovery without reauthorizing. Account-wide
429 limits must not launch an unbounded sibling fallback hunt.

No runtime code, live account, credential or permission change was made by the
reviewer. Lead accepts the corrected shape for implementation; exact-head review
round3, CI, deployment and rendered separate free-user proof remain required.
