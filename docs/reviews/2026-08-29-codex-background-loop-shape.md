# Codex review — background-loop shape (2026-08-29)

VERDICT: ADAPT. Brief and verdict verbatim. Preceded by a Claude Explore code review whose
"~20-line resolver fix" this verdict refutes; the two together are the evidence for
`docs/concerns/2026-08-29-background-loop-activation-is-fleet-era.md`.

## Brief

    REFUTE this plan. Answer each numbered question with AGREE / DISAGREE_EVIDENCE (file:line) / DISAGREE_CONCERN. Repo: C:\Users\Jonathan\Projects\TinyAssets (read origin/main; the primary checkout may be stale — use `git show origin/main:PATH` when unsure).
    
    CONTEXT. The "background 24/7 self" (assigned-queue consumer, flag TINYASSETS_ASSIGNED_QUEUE_CONSUMER, live since 2026-08-25) has refused every attempt since 2026-08-07 with
      activate_error:CloudContinuationActivationError: trusted cloud worker assignment is absent or mismatched
    Founder rule: the platform NEVER supplies an LLM; every universe runs on its user's own deposited credential; no host-run fleet. The founder asked tonight whether this machinery is "pre-users" and should be pruned.
    
    A read-only code review (Claude Explore agent) concluded:
    (a) The execution path is current-shape: tinyassets/background_served_provider.py:912-1039 mints its own ProviderWorkBindingSeed from provider_assignments + llm_credential_custody and runs on the user's credential; no worker container needed. The single daemon registers its own runtime/audience (tinyassets/runtime/assigned_queue_consumer.py:401-415, 482-487).
    (b) The ONE surviving fleet-era assumption is the preflight audience check: _ExactAudienceResolver (tinyassets/cloud_automation_runtime.py:209-242) -> daemon_registry.runtime_matches_worker_provider (tinyassets/daemon_registry.py:933-960) demands an author_runtime_instances row (status provisioned, daemon_id match, worker_id match) whose provider_name equals the HISTORICALLY PREPARED provider-work binding.provider — not the universe's current provider_assignment.provider — and cloud_automation_runtime.py:511-514 RAISES on the miss, aborting the whole pump for that principal (assigned_queue_consumer.py:570-576 records it as the refusal above).
    (c) Latent wedge: consumer_id is boot-unique (assigned_queue_consumer.py:129-132); after one successful rotation binding.runtime_id pins a prior boot's runtime and _bind_prepared_background_runtime silently `continue`s (cloud_automation_runtime.py:257, 515-522).
    (d) Executor classes: CLOUD/HOST/DISTRIBUTED (background_branch_authority.py:48-51); prepare_cloud_automation hardcodes CLOUD (cloud_automation_setup.py:237); the carrier requires CLOUD + non-empty daemon_id AND runtime_id (background_served_provider.py:130,132,386,389-390,968-971); runtime_id is None at prepare and only stamped by CLOUD activation (cloud_automation_runtime.py:259-296).
    (e) Dead weight, deletable today: tinyassets/cloud_worker.py (2171 lines; served path uses only _worker_model_for_provider and supervisor_heartbeat_filename), tinyassets/cloud_worker_healthcheck.py (131), and deploy/compose.yml services worker / worker-codex-2 / worker-claude-1 / worker-claude-2 (:195-273; production droplet does not run them). PR #2411 "retire-cloud-worker-fleet" never landed.
    (f) Unrelated second death: the branch_schedules heartbeat scheduler thread is only constructed under `if _event_bus_on` = TINYASSETS_INBOUND_ENABLED (universe_server.py:3017-3021, webhook_inbound.py:92-95), which is DARK by default and unset in prod. Registration APIs still accept schedules that can never fire (api/runtime_ops.py:352,416,479).
    
    PROPOSED PLAN
    P1. Resolver fix (~20 lines): _ExactAudienceResolver.resolve compares provider_name against the universe's CURRENT provider_assignment.provider (or _serving_runtime registers one runtime per binding.provider); accept a rotated runtime_id when daemon_id and worker_id still match; turn the raise at cloud_automation_runtime.py:511 into a RECORDED skip (assigned_queue_refusals row) so one bad principal cannot abort the pump.
    P2. Prune: delete cloud_worker.py + cloud_worker_healthcheck.py + the four compose worker services; relocate the two helpers into the consumer/served modules; remove fleet-only env from docs. Then make the deploy pipeline ship deploy/compose.yml (today it never does — docs/concerns/2026-08-27-deploy-drops-compose-sync.md).
    P3. Scheduler: start the branch_schedules tick thread independently of the inbound flag (it is outbound-only work on the user's own credential), OR refuse schedule registration with a named error when it cannot fire. Pick the fail-loud shape.
    P4. Re-issue the 16 background_branch_bindings + 9 cloud_automation_controls that still authorize the OLD WorkOS subject (staging->production migration 2026-08-29) via prepare_cloud_automation under the new principal, from the user surface.
    
    QUESTIONS
    1. P1: does relaxing the provider-name equality to the CURRENT assignment weaken the trusted-executor fence? Concretely: on a single-daemon deployment, what do daemon_id and worker_id equality still protect against, and is there any path where a different daemon/consumer could claim work meant for this universe after the change? Cite the fence.
    2. P1: is "record and continue" at :511 safe, or does the raise protect a transactional invariant (e.g. a fence/lease that must be released)?
    3. P2: list what else references cloud_worker.py / the healthcheck (tests, scripts, workflows, docs) that would break; anything the served carrier still needs from cloud_worker beyond the two helpers?
    4. P3: which option is correct under Hard Rule 8 (fail loudly, never silently) and Hard Rule 4 (autonomous defaults)? Any reason the scheduler was coupled to inbound on purpose?
    5. P4: any digest/ownership trap in re-issuing under a new principal (like the serving chain: bind_serving_provider then set_serving)? Which function(s) exactly, in what order?
    6. Anything in P1-P4 that contradicts "no host writer ever / every universe runs on its user's own credential"?
    
    VERDICT first (APPROVE / ADAPT / REJECT), then findings. Be concrete and brief.

## Verdict

VERDICT: ADAPT

Reviewed `origin/main@2732e85d`; opposite-family review agreed.

1. DISAGREE_EVIDENCE (`tinyassets/cloud_automation_runtime.py:233`, `tinyassets/storage/provider_work_authority.py:2709`). P1’s provider substitution is incomplete. Later transactional fences still require `runtime.provider_name == prepared_binding.provider`; changing only `_ExactAudienceResolver` remains a refusal. Relaxing those later checks would remove a digest-covered provider pin without rotating authority. The proper fix is an atomic provider-binding/continuation transition—but current continuation rebind explicitly forbids changing `provider_binding_id` (`tinyassets/storage/cloud_automation_continuation.py:352`).

   The existing fence protects universe, exact runtime, provisioned status, daemon, worker, provider, binding generation/digest, owner, and expiry (`tinyassets/daemon_registry.py:943`, `tinyassets/storage/provider_work_authority.py:2699`). A different daemon is rejected. A different consumer cannot reuse the old audience unless authority is deliberately rebound.

   The proposed reboot repair is also unsatisfiable: every boot changes `worker_id` and lease (`tinyassets/runtime/assigned_queue_consumer.py:129`), while `_bind_prepared_background_runtime` rejects a different pinned runtime (`tinyassets/cloud_automation_runtime.py:257`). “New runtime with same worker” does not heal a reboot.

2. AGREE (`tinyassets/cloud_automation_runtime.py:490`). Record-and-continue is transactionally safe at line 511: the code has only performed reads. Activation mutation begins later through `PreparedCloudContinuationActivationService.activate` (`tinyassets/cloud_automation_runtime.py:557`), and trigger claiming begins at line 583. No lease or claim needs releasing.

   Make it a per-automation recorded refusal, then continue the control loop. Preserve the transactional provider fence later in activation/claim.

3. DISAGREE_EVIDENCE (`tinyassets/runtime/assigned_queue_consumer.py:380`, `tinyassets/runtime/assigned_queue_consumer.py:423`). The assigned consumer needs only the two stated helpers, and `background_served_provider.py` imports neither. But deletion fallout is much larger:

   - Live daemon code imports `DEFAULT_HOST_USER` (`fantasy_daemon/__main__.py:220`).
   - Direct tests include `test_cloud_worker.py`, `test_loop_telemetry.py`, `test_auth_refresh_viability.py`, `test_provider_auth_quarantine.py`, `test_soul_loop_dispatch.py`, `test_branch_tasks.py`, `test_cloud_automation_api.py`, and `test_assigned_queue_consumer_live_worker.py`.
   - Inventory/deploy scripts name it (`scripts/check_background_authority_inventory.py:390`, `scripts/retire_cheat_loop_deploy_fence.py:180`).
   - Recovery, logging, HMAC-rotation, Docker-shape, and deployment tests name the four containers.
   - The canonical spec still requires the supervisor and healthcheck (`openspec/specs/daemon-runtime-and-dispatch/spec.md:57`, `:77`).
   - Generated plugin-runtime copies must be rebuilt/removed too.

   Also, do not restore compose sync immediately: production’s live compose must first be fetched and reconciled, per `docs/concerns/2026-08-27-deploy-drops-compose-sync.md:52-68`.

4. DISAGREE_EVIDENCE (`tinyassets/scheduler.py:632`, `tinyassets/universe_server.py:1259`). Pick refusal-with-named-error now. Starting the thread cannot fix schedules: the scheduler emits actor `scheduler:<id>`, while its wired run function accepts only `universe:<id>` and rejects everything else. Registration also accepts caller-supplied `owner_actor`, defaulting to `anonymous` (`tinyassets/api/runtime_ops.py:365`), so there is no safe server-derived universe authority.

   The inbound coupling is structural: `Scheduler.start()` launches tick and event threads together (`tinyassets/scheduler.py:545`), and the lifespan treats the singleton as the inbound event bus (`tinyassets/universe_server.py:3137`). Later, split the lifecycles and add authenticated universe-bound schedule authority; until then, fail registration loudly. Hard Rule 4 does not require an unsafe default.

5. DISAGREE_EVIDENCE (`tinyassets/api/cloud_automations.py:645`, `tinyassets/cloud_automation_setup.py:125`). P4 cannot reissue the existing controls under the new subject:

   - New actor cannot access, stop, or rebind old-principal controls.
   - Principal participates in both definition digest and automation ID (`tinyassets/user_owned_cloud_automation.py:80`, `:218`), so create produces new identities.
   - Credential ownership transfer is explicitly unsupported (`tinyassets/api/llm_deposit.py:185`).
   - Existing agent bindings require creator equality for both bind and enable (`tinyassets/provider_serving_binding.py:371`, `:702`).
   - Private branch versions require the new principal to be their author (`tinyassets/cloud_automation_setup.py:167`).
   - GitHub destination grants are actor-owned and must be reauthorized, not copied (`tinyassets/api/cloud_connections.py:150`).

   Required order after a dedicated identity migration or fresh ownership setup:

   `connect_llm` → new-principal agent binding → `bind_serving_provider` → `set_serving` using the returned revision → `cloud_connections(connect/reconcile)` → `cloud_automations(bind_provider)` → `cloud_automations(create)`/`prepare_cloud_automation`.

   The 16 background bindings are generated consequences of preparation; do not migrate them individually. Explicitly retire the old controls and continuing delegations.

6. DISAGREE_EVIDENCE (`tinyassets/background_served_provider.py:912`, `:1019`). P1, P2, and a corrected P3 do not require a host writer: execution resolves the current assignment, custody, user principal, and deposited credential.

   P4, however, is not currently user-surface-only. `cloud_automations(bind_provider)` uses `RequesterProviderEnrollmentResolver.from_environment` (`tinyassets/api/cloud_automations.py:513`), backed by `TINYASSETS_REQUESTER_PROVIDER_ENROLLMENTS_JSON` (`tinyassets/provider_work_enrollment.py:20`). That manifest carries authority rather than an LLM secret, so it is not a host-supplied model—but it is a host prerequisite. Adapt issuance to derive automation authority from the current user-owned assignment/custody before claiming full compliance.