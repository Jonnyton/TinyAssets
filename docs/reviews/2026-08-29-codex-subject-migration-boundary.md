# Codex review — subject-migration boundary (2026-08-29)

Dispatched via `scripts/peer_agent.py codex` with the brief below; verdict verbatim after it.
**Applied on the droplet the same night.** Ownership columns the code compares as
CURRENT authority were re-pointed (104 rows): `branch_definitions.author` 78,
`agent_bindings.created_by` 8, `llm_credential_deposit_owners.owner_user_id` 6, `goals.author` 5,
non-Pipes `outbound_connections` 3 + `outbound_connection_grants` 3, `branch_schedules.owner_actor` 1.
The digest-covered serving chain (`llm_credential_custody`, `provider_assignments`,
`provider_work_bindings`) was REBUILT through `bind_serving_provider` + `set_serving`, the same
state-transition functions the app's Connect gesture calls; the superseded old-owner rows were then
deleted. Left as history, deliberately: `contribution_events.actor_id` 131, `branch_versions`
(31 immutable snapshots; author only feeds cross-author fork attribution), `effector_consents.granted_by`
(never compared at check time), `agent_bindings.updated_by`, `action_approvals.decided_by`,
`operation_scopes.defined_by`, `app_channel_bindings.bound_by`, `agent_definitions.author_id` (list filter
+ idempotency only), node-level `author`/`approved_by` inside `node_defs_json`, admissions and receipts.
Left for the product: the two WorkOS-Pipes GitHub connections (environment-bound credential; reconnect in
production), and the 16 `background_branch_bindings` + 9 `cloud_automation_controls` (a continuing delegation
under the old principal — re-issue through `prepare_cloud_automation` when that lane is live; the consumer was
already refusing on executor audience before tonight). `scheduled_work` and `app_principal_mappings` have no
reader in the current tree. Sweep after all of this: 1,457 references to the old subject remain, every one of
them in one of the categories above. Backups: `_backup_subject_migration_20260829T055340Z` under the
`tinyassets-data` volume.

**Live proof (2026-08-29 06:07–06:13Z, tinyassets.io/mcp/app, signed in as the founder):** home
resolves to `u-01kxm1vszd8hwp7em418asq8h9`; the 400-turn thread renders; the universe answers on the
founder's own subscription, recalls the last piece of work, reads its status with its tools, and counts
its 78 branches.

**Lesson recorded:** my first inventory was a compacted summary of the sweep, which had truncated the
list — `branch_definitions.author` (78 rows) was in the real output and not in the summary, and the
universe came back with 0 branches. Re-run the sweep; never work from a summary of one.

## Brief

    Judgement call on a live identity migration. I want you to REFUTE my classification.
    
    CONTEXT: TinyAssets moved from WorkOS staging to production tonight. Every user got a NEW
    `user_…` subject id. Two accounts, both the founder's:
      user_01KWGB2NV5PV4PWHT5RYKJPB8X -> user_01M160DTZ9AQS64FNR224RMEV7  (primary)
      user_01KY3ZGR4VY0DYQ6BVJS4ZM5Y5 -> user_01M160RTA1DFSJEK5QAK3KQY4S
    Already migrated and verified: founder_home, universe_acl, conversation_turns
    session_id (400 turns). Founder is signed in to the right universe with memory back.
    
    A sweep of every sqlite db under /data finds the OLD subject still referenced here
    (db / table / column / rows):
      .tinyassets.db  llm_credential_custody        owner_user_id   3
      .tinyassets.db  llm_credential_deposit_owners owner_user_id   6
      .tinyassets.db  provider_assignments          owner_user_id   2
      .tinyassets.db  agent_bindings                created_by/updated_by 8/8
      .tinyassets.db  scheduled_work                owner_id        12
      .tinyassets.db  operation_scopes              defined_by      3
      .tinyassets.db  action_approvals              decided_by      2
      .tinyassets.db  app_principal_mappings        subject_id + record_json 1
      .tinyassets.db  app_channel_bindings          bound_by        1
      .tinyassets.db  cloud_automation_continuations record_json    9
      .tinyassets.db  assigned_queue_refusals       branch_task_id  1
      outbound.db     outbound_connections          owner_user_id 5, credential_ref 2
      outbound.db     outbound_connection_grants    owner_user_id   5
      .runs.db        branch_schedules              owner_actor     1
      .runs.db        branch_versions               publisher 31, snapshot_json 31
      .runs.db        contribution_events           actor_id        131
      u-*/.effector_consents.db  effector_consents  granted_by      4+3
    SYMPTOM RIGHT NOW: the app tells the founder "Connect a model" — the LLM credential
    custody is owned by the old subject so `resolve_serving_agent_binding` fails the
    `grant.owner_user_id != owner_user_id` check and the universe cannot speak.
    
    MY PROPOSED CLASSIFICATION:
      A. OWNERSHIP / AUTHORITY columns — must be rewritten or the feature is dead for the
         new id: llm_credential_custody, llm_credential_deposit_owners, provider_assignments,
         outbound_connections.owner_user_id, outbound_connection_grants.owner_user_id,
         effector_consents.granted_by, scheduled_work.owner_id, app_principal_mappings,
         app_channel_bindings.bound_by, agent_bindings (both), branch_schedules.owner_actor.
      B. AUDIT / PROVENANCE — record who DID something at the time; rewriting would be
         falsifying history. Leave alone: contribution_events.actor_id,
         branch_versions.publisher, action_approvals.decided_by, operation_scopes.defined_by.
      C. SERIALIZED BLOBS containing the id — record_json, snapshot_json, credential_ref,
         branch_task_id, conversation content. Need per-case reading; some are (A) inside
         JSON, some are (B).
    
    QUESTIONS:
    1. Is the A/B split right? Name any I have on the wrong side, with the consequence.
    2. `effector_consents.granted_by` — a consent given by the OLD subject: does migrating
       it silently extend a consent the NEW subject never gave? Both ids are the same human,
       but the system cannot know that. Is rewriting it correct, or should consents be
       re-granted?
    3. `llm_credential_custody.owner_user_id` — this gates access to a deposited API
       credential. Rewriting it transfers custody of a secret to a different subject id.
       Same-human, but state the risk plainly. Is there a safer path (re-deposit?) and is it
       worth it for one user tonight?
    4. Is there a fourth category I'm missing?
    5. The deeper point: this migration touched 24 columns in 5 dbs because subject ids are
       scattered everywhere. Should the fix be a `subject_aliases` table the resolvers consult
       (old->new, one place), instead of rewriting every store? Trade-offs?
    
    Be brief and concrete. VERDICT then findings.

## Verdict

## VERDICT

Refuted. Your A/B split is too coarse. Some A fields are provenance, some are continuing grants that should be re-authorized, and several authority records are integrity-bound—plain ID replacement leaves them invalid.

## Findings

1. Wrong-side columns:

   - `effector_consents.granted_by`: **B, not A.** Runtime consent checks only `(sink, destination, revoked_at)`; `granted_by` is metadata. Rewriting gains nothing and falsifies who granted it. [effector_consents.py](/C:/Users/Jonathan/Projects/TinyAssets/tinyassets/storage/effector_consents.py:165)
   - `agent_bindings.created_by`: correctly A; it is explicitly compared to the current owner. `updated_by`: **B**, merely the last updater. Rewriting it falsifies history. [provider_serving_binding.py](/C:/Users/Jonathan/Projects/TinyAssets/tinyassets/provider_serving_binding.py:736)
   - `app_channel_bindings.bound_by`: likely B unless a resolver actually compares it for authority. “Who bound this” is not automatically “who owns this.”
   - `outbound_connection_grants` and active schedules are not ordinary ownership: they are **continuing delegations/automations**. Blind transfer can preserve action caps and unattended execution under a new principal.
   - Leaving `contribution_events.actor_id` unchanged is historically correct, but attribution/bounty aggregation will split across identities unless reporting canonicalizes the alias.

2. `effector_consents`: do **not** rewrite `granted_by`. The consent is already universe-scoped and remains active regardless of that value. If the production identity must make a fresh consent decision, revoke/pause and re-grant through the authenticated surface. For seven rows, I would re-grant tonight.

3. `llm_credential_custody`: the risk is direct transfer of the capability to use/spend a secret-backed credential. A bad mapping becomes credential use by the wrong account.

   Also, a raw rewrite is technically invalid: custody and provider-assignment digests incorporate `owner_user_id`; changing the column without regenerating dependent authority leaves fail-closed state. [credential_vault.py](/C:/Users/Jonathan/Projects/TinyAssets/tinyassets/credential_vault.py:1008), [provider_assignment.py](/C:/Users/Jonathan/Projects/TinyAssets/tinyassets/provider_assignment.py:981)

   Safest path: re-deposit under the new authenticated subject and recreate the serving binding. For one user, yes, it is worth doing. Acceptable emergency alternative: an explicit, logged, one-to-one administrative transfer using application state-transition functions that regenerate every digest—not SQL replacement.

4. Missing categories:

   - **Continuing grants/delegations:** consents, approvals, schedules, connection grants. Transfer requires a policy decision, not merely identity substitution.
   - **Integrity-bound/immutable state:** digests, content-addressed snapshots, executable references, derived IDs. Regenerate or republish; never search-and-replace. `branch_versions.snapshot_json.author`, for example, participates in access authority and its content hash. [branch_versions.py](/C:/Users/Jonathan/Projects/TinyAssets/tinyassets/branch_versions.py:209)

5. Long term: use identity indirection, but not “every resolver consults `subject_aliases`.” That recreates scattered enforcement.

   Resolve `(issuer, subject)` once at authentication ingress to a stable internal `principal_id`, backed by `external_identities`. Persist that internal ID in operational stores. Keep historical subjects unchanged and use aliases for attribution/display.

   Do not let an old staging token canonicalize into production authority: retire the staging issuer/audience. Tonight, explicitly migrate live ownership, reissue sensitive grants, preserve provenance, and record the verified old→new mapping.