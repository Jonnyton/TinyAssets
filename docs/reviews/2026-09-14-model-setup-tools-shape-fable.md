# Fable5.1 missing model-setup tools shape review

Recovered verbatim from the assigned reviewer session's assistant text at
2026-09-14T22:25:15Z; reviewed candidate cdc41498e9bcf6db428fcfa8569d8220d3ab3255.
Reviewer subprocess28078 exited0 after301seconds. Its final stdout was only a
recap after a continuation hook, so it was not sufficient as the review artifact.
Only this task's review text is preserved here, not unrelated session contents.
This approves a proposed shape, not unwritten implementation or live acceptance.

Review complete. Findings below, organized by the four requested return items.

## 1. Minimum coherent served surface

Six operations, of which two already exist. Nothing new is added to the tool catalog. New work is three read targets, two write operations, and one typed consent action on the person-driven rail.

| Need | Operation | Status at cdc41498 |
|---|---|---|
| Inspect choices, catalogue, saved policy, binding state | `read_graph target=model_options` | missing from pin, `tinyassets/engine_mcp_server.py:250` |
| Inspect own bindings | `read_graph target=agent_bindings` / `agent_binding` | missing from pin |
| Select and save default plus fallbacks within accepted authority | `write_graph target=model_preferences operation=save` | no served or universe-server path exists |
| Register the held OpenRouter grant as compute | `connect_compute` | already served, `tinyassets/engine_mcp_server.py:2405` |
| Declare the discovery contract on that registered source | `write_graph target=connection operation=configure_provider_capability` restricted to `capability_kind=model_discovery` | missing from served surface |
| Widen accepted model access or enable serving | `write_graph target=pending_request operation=ask` with a new typed action `bind_model_access` | ask is served, `tinyassets/engine_mcp_server.py:1527`; the action type does not exist |

AGREE with the assignment's framing that named binding choice, catalogue metadata, saved preferences and owner consent are four different operations. The repo's own design already draws that line. Selecting or reordering an accepted model changes only preference generation, while changing accepted connections or model scope changes assignment generation (`openspec/changes/select-agent-models/connection-model-authority.md:64`). So "select among existing authority" is the preference save alone. It never needs a rebind.

## 2. Each missing operation: existing implementation and boundary

**model_options read.** Implementation is `read_model_options` at `tinyassets/api/model_options.py:306`. It refuses an unauthenticated principal, resolves the founder's home, and returns uniform not_found when the requested universe is not that home (line 322). The inner scope requires a complete home plus an admin ACL row (line 51) and refuses an assignment owned by someone else (line 111). Every selector is owner or home derived, so it satisfies the pin rule at `tinyassets/engine_mcp_server.py:239`. Expose as a pinned read target. Two adaptations: it performs live discovery fetches through the owner's grant on every call (line 158) with single-flight but no result cache (`tinyassets/providers/discovery_snapshot.py:253`), so gate it with the same served admission ticket write_graph uses (`tinyassets/engine_mcp_server.py:1588`). And its model names and warnings originate from a third party (line 265), so return it through the existing untrusted envelope.

**agent_bindings and agent_binding reads.** DISAGREE_EVIDENCE with the 2026-08-13 pin comment that lists agent_binding among unsafe targets. Today both queries are universe-scoped: `WHERE universe_id = ? AND agent_binding_id = ?` at `tinyassets/custom_agents.py:999` and `WHERE universe_id = ?` at line 1118. The adapter additionally requires an ACL row for the actor on that universe and returns not_found otherwise (`tinyassets/api/custom_agents.py:49`). With the pinned graph id the binding id only selects inside the universe. Pin-safe. The public `agents` and `agent` targets are global (`list_definitions(base, ...)` has no universe argument) and must stay on browse_commons, which already serves them with the envelope.

**Preference save.** Storage is `ModelPreferenceStore.save` at `tinyassets/storage/model_preferences.py:106`, with BEGIN IMMEDIATE, generation compare-and-swap, and an optional current-home fence. Its only ingress is the app HTTP route at `tinyassets/onboarding/model_preferences.py:23`. The universe-server write_graph has no such target (`tinyassets/universe_server.py:1334`). This therefore needs a distinct served handler, not forwarding. Shape it like the served conversation read (`tinyassets/engine_mcp_server.py:368`): parse with `parse_preference_write`, require the pinned graph to equal the founder home, call the store with `require_current_home=True`, and return the conflict snapshot on a stale generation. Saving grants nothing (`openspec/specs/agent-model-selection/spec.md:103`).

**Model discovery capability.** Implementation is `_configure_model_discovery` at `tinyassets/api/provider_capability.py:137`. It requires an admin ACL row, an owned api_key_http definition, a valid grant bound to this owner and universe, and ledger SSRF validation. Its receipt states `grants_inference: False` (line 219). Metadata never grants an endpoint; the models GET must already be in the owner-approved allowlist (`connection-model-authority.md:94`). Expose as a pinned write operation under the same vetted-founder allowlist as connect_compute, refusing every other capability kind. The voice kind needs live serving authority (line 86) and is out of scope.

**Widening accepted access or enabling serving.** `bind_serving_provider` at `tinyassets/provider_serving_binding.py:491` publishes a new assignment generation. Its docstring is explicit that app and MCP callers supply model_access only through explicit model-access confirmation and that preferences never imply it. The served agent runs as the founder principal (`tinyassets/engine_mcp_server.py:214`), so a served write would let the agent confirm its own access change. That is the same self-consent the workspace refusal blocks (`tinyassets/engine_mcp_server.py:2597`). Requires a distinct boundary: a typed action on the rail, like `grant_workspace_consent` (`tinyassets/api/pending_requests.py:169`, dispatched at line 1412). The action allowlist is closed (line 233), so this is code on the person-driven surface. The action carries binding id, expected revision, root provider, and the model_access map. Validate it at ask time against the owner's current catalogue the way extend asks are checked at raise time (line 797), so the owner never sees a tab that cannot be honoured. On answer, run bind then `set_serving(enabled=True)` as the authenticated owner.

**connect_compute.** AGREE, already served and candidate-only (`tinyassets/api/compute_connection.py:126`). The app's "OpenRouter not registered as compute" finding is closable today: read `connections` for the grant id, then register with `ref=<grant_id>`. After registration the catalogue read shows the source with reason `source_not_accepted` (`tinyassets/api/model_options.py:163`), which is exactly the state that justifies the consent ask.

## 3. Safety blockers and acceptance tests

Blockers, all single-user and all build gates rather than shape changes:

- Home fence must be explicit in the served preference handler. Preferences are home-only by spec (`spec.md:142`), and a non-home pinned universe must refuse rather than write.
- Discovery fetches inside a read need the served admission ticket, or a looping agent burns the owner's OpenRouter rate limit.
- Catalogue strings need the untrusted envelope.
- The typed consent action must be validated when raised, not only when answered.
- I did not verify what `answer_request` records when the downstream bind refuses. Test it.

Acceptance tests:

1. Cross-home: engine pinned to a non-home owned universe. `model_options` returns not_found and a preference save refuses with no row written.
2. Foreign binding: `agent_binding` with another universe's binding id returns not_found. A `bind_model_access` ask naming it is refused at raise time and no request row exists.
3. Stale preference generation: save with generation N after a concurrent save. Conflict snapshot returned, stored policy unchanged.
4. Stale binding revision: owner answers a `bind_model_access` ask after the binding revision advanced. Bind refuses, assignment generation unchanged, request row records failure and is not consumed as success.
5. Grants unchanged: after preference save and after `model_discovery` configuration, grant endpoints and scopes are byte-identical and the assignment digest is unchanged.
6. Unresolved consent: pending ask visible via `pending_requests`. Served `pending_request operation=answer` refused. Serving readiness still refuses the widened choice until the owner answers.
7. Self-consent probe: an ask whose fields pre-fill the answer does not bind. Only the rail path publishes.
8. Register then see: `connect_compute` with the held OpenRouter grant, then `model_options` lists the source with `source_not_accepted` and no assignment.
9. Discovery outside grant: a descriptor whose models URL is not in the allowlist configures but discovery reports unavailable. No endpoint added.
10. Read admission: repeated `model_options` calls beyond the ticket are refused structurally, not by exhausting discovery.

## 4. Catalogue and account proof versus discovery adapter gaps

These are separate and neither is closed by the served surface.

**Account proof gap.** A configured contract carries `independently_verified: False` (`tinyassets/api/provider_capability.py:217`). Native enumeration reports installed executor support, not proof this account has a model list (`tinyassets/api/model_options.py:85`). Declared freshness attests custody, not availability (`native-picker-followup.md:19`). Closing this needs the authenticated user-filtered catalogue and the answering-model telemetry on a real turn (`spec.md:183`).

**Discovery adapter gap.** For OpenRouter the chain is three owner-side steps: register the grant as compute, hold the models GET in the grant via `extend_http` if absent, and configure the `model_discovery` descriptor. No default profile is attached at registration, which the authority seam already flags as not the final experience (`authority-seam.md:109`). For native CLIs the `enumerate_models` override is the only extension point (`native-picker-followup.md:22`). Without it the provider default is the only selectable native choice, and the source reports `enumeration: unknown` as advisory metadata.

DISAGREE_CONCERN with reading the app's request as "expose model_options and agent_binding reads and writes." The reads are safe to pin. The binding write is not, and moving it to the rail is what keeps the picker's own setup under the owner's control rather than an operator's.

**VERDICT: APPROVE** for the recommended shape: three pinned reads, two pinned writes with no authority effect, one typed rail action for the genuine consent, reuse of served connect_compute and ask. This is an ADAPT of the app's literal request, not an approval of any implementation.

