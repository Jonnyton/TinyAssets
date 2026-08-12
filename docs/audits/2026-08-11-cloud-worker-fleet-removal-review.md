# Review: `retire-cloud-worker-fleet` — uncommitted diff vs `04eb0f60`

Scope reviewed: 160 files, +4,026 / −23,788. No files edited. My own scratch artifact was moved out of the worktree to `/tmp/codex-fleet-review.md`.

Method: read the diff directly; ran `docker compose config` against both the new and base compose; ran `python -m pytest` over 9 relevant test files (**440 passed, 1 skipped**) and `ruff check` over all changed non-deleted Python (**clean**); verified canonical↔plugin mirror parity byte-for-byte (**matches**); confirmed no live import of `cloud_worker` / `host_pool` / `idle_cycle` / `subscription_auth_health` survives. A background Codex cross-family review returned `VERDICT: adapt` and independently reached findings 1, 2, 4, 6 and 7 below.

The direction is right and much of it is well built: `call.py`'s ambient `_build_fallback_router()` is gone, `_provider_child_runtime_env` is a real deny-by-default allowlist, `fallback_chain` now raises loudly in two places, and the entrypoint strips 13 ambient credential vars. The findings below are where the implementation does not yet hold the line the change claims.

---

## BLOCKING

### 1. `deploy/compose.yml:252` — invalid Compose schema; every production deploy fails
A `volumes:` key is nested under `networks.default`:

```
networks:
  default:
    name: tinyassets-net
    volumes:
      - tinyassets-data:/data:ro
```

Verified: `docker compose -f deploy/compose.yml config` → `validating deploy/compose.yml: networks.default additional properties 'volumes' not allowed`. The base commit passes the same schema check. It also looks like a botched attempt to mount the data volume into `slack-agent`, which the comment 60 lines above explicitly forbids ("since 2026-08-06, no `tinyassets-data` mount either") and which `retire_cheat_loop_deploy_fence.py` actively deletes containers for.

Per your own deploy-fence design, a failed deploy stops the writer *before* proving the new one — this lands as an outage with zero containers, not a no-op.

**Remediation:** delete lines 251–252. Add a real schema test — every existing compose test uses `yaml.safe_load` (well-formed YAML passes), which is why 440 tests went green over a file Docker rejects.

### 2. `.github/workflows/deploy-prod.yml:1794` — hardcoded `5` fences every healthy worker-free deploy
```python
if len(containers) != 5 or len(images) != 1 or len(revisions) != 1:
    raise SystemExit("active fleet identity is not exact")
```
`containers` comes from `observe_fleet()` → `_exact_inspections()` (`scripts/retire_cheat_loop_deploy_fence.py:847`), which iterates `EXPECTED_CONTAINERS` — reduced by this diff from 5 names to 1 (`retire_cheat_loop_deploy_fence.py:35-36`). So `len(containers)` is now always 1, the check always trips, and `fence_unsafe_and_fail` runs. This is inside the `if: always()` cleanup step (line 1541), so it fires on successful deploys too.

**Remediation:** derive the expected count from the fence's `EXPECTED_CONTAINERS` contract instead of a literal, and add a regression test over that workflow script block.

### 3. `scripts/retire_cheat_loop_deploy_fence.py:1734` — every deploy mass-cancels the entire queue
`hold_queue_work_without_requester_executor(volume_dir)` is called unconditionally in `preflight()` after quiescence. It walks every `branch_tasks.json` and every `.tinyassets.db` under `/data` and sets **all** pending/running/cancel_requested rows to `cancelled` with `error_code=no_requester_owned_executor` (lines 417–460). It takes only `volume_dir` — it never checks whether the universe actually has an assigned credential.

The docstring says "This one-time transition", but nothing makes it one-time. After this lands, a routine deploy silently destroys every user's in-flight and queued work, stamped with a reason that is false for any universe whose credential is healthy.

The test at `tests/test_retire_cheat_loop_deploy_fence.py:271` blesses this: it cancels a `branch_run` task and asserts the terminal receipt. There is no test that a task with an available credential survives.

**Remediation:** gate it behind an explicit one-shot flag (a durable marker on the volume, or an operator-supplied `--retire-legacy-queue` argument recorded in the run state), and scope it to rows that genuinely resolve to `no_requester_owned_executor` rather than all risk-status rows.

### 4. `tinyassets/assigned_credential_execution.py:112-113` — the authority is invented, not derived; the router's exactness check is self-referential
`_assigned_credential_state` validates the binding through `_current_serving_authority`, which calls `store.validate_in_transaction(..., operation="converse", role="writer")` (`tinyassets/provider_serving_binding.py:434-435`). Those are the only values a serving binding can ever carry — `_SERVING_OPERATIONS = ("converse",)` and `_SERVING_ROLES = ("writer",)` (lines 46–47), hardcoded at issue time (line 319).

It then discards the validated binding and returns:
```python
allowed_operations=("run_graph",),
allowed_roles=("writer", "judge", "extract"),
```
`router.py:184-188` then "enforces" `operation in assigned.allowed_operations and role in assigned.allowed_roles` — comparing a hardcoded constant against itself. `validate_in_transaction` does check `operation in binding.allowed_operations` (`storage/provider_work_authority.py:1938-1939`), so the mechanism exists and is simply not used here.

Net: a credential the user authorized for `converse`/`writer` executes queued `run_graph` work under `judge` and `extract` roles the binding does not contain. This contradicts your standing principle that capabilities are user-declared, read off `ProviderWorkBinding.allowed_operations`, not a platform table.

Compounding it, `router.py:57-62` neutralizes the carrier's operation binding whenever an assigned credential is present:
```python
invocation_operation = (
    carrier.operation
    if ... assigned_credential is not None
    else operation
)
carrier.validate_for_call(role=role, operation=invocation_operation)
```
`validate_for_call` exists to reject an operation mismatch (`provider_work_authority.py:1048`). The automation carrier is armed for `_OPERATION = "repository_spec_delivery"` (`cloud_automation_continuation.py:2278`) and spent on a `run_graph` call — without this special case it would correctly raise. The sealed single-use capability's operation binding is turned into a tautology.

**Remediation:** carry the binding's real `allowed_operations`/`allowed_roles`/generation/digest through `AssignedCredentialAuthority`; validate against those in the router. If queued execution genuinely needs `run_graph` + judge/extract, mint a workflow-serving binding class that *declares* them rather than widening a converse binding. Remove the `carrier.operation` substitution and reconcile the operation names instead.

---

## HIGH

### 5. `tinyassets/providers/router.py:181-224` — the assigned path bypasses every spend ceiling
The branches are `if assigned / elif served / elif invocation`. Budget enforcement lives only in the `served` (197–209, 250–292) and `invocation` (210–221) branches, so once `assigned_credential` is set, the ceilings are unreachable. At `04eb0f60` the automation path had no `assigned` branch, so `invocation_carrier.max_tokens` and `max_cost_microunits` *were* enforced (old `router.py:448-461`) — this is a regression.

`_ClaimedCloudProviderSession` still reserves its per-call `token_share`/`cost_share` in SQLite (`cloud_automation_continuation.py:2440-2461`), so invocation *counts* are capped, but the reserved token/cost ceiling is never applied to `cfg.max_tokens` and never reconciled. The serving binding's own `max_invocations`/`max_tokens`/`max_cost_microunits` (`provider_serving_binding.py:323-325`) are not enforced on this path at all. A runaway queue burns the user's subscription without limit.

**Remediation:** apply the ceiling before the `assigned` branch dispatches — clamp `cfg.max_tokens` to `min(binding, carrier)` and route the assigned path through reserve/finalize the way `served` does.

### 6. `tinyassets/assigned_credential_execution.py:82` — TOCTOU on the serving binding
`resolve_serving_agent_binding(...)` runs *before* the transaction opened at line 88, and `_current_serving_authority` consumes that stale dict (it reads `agent["configuration"]["provider_ref"]` at `provider_serving_binding.py:413` rather than re-reading the row). A concurrent disable, revision bump, or rebind between line 82 and line 90 still yields a snapshot and executes. Everything else in that function is carefully fenced inside one transaction, which makes this the one gap.

**Remediation:** resolve and validate the agent binding inside the same transaction, comparing the revision under the fence. Add a race regression test.

### 7. `tinyassets_tray.py:363-369` — the desktop host still hands the daemon host API keys
The tray strips 5 variables:
```
CODEX_HOME, CLAUDE_CONFIG_DIR, CLAUDE_CODE_OAUTH_TOKEN, OPENAI_API_KEY, ANTHROPIC_API_KEY
```
The container entrypoint strips 13 (`deploy/docker-entrypoint.sh:22-31`). Left inherited: `ANTHROPIC_BASE_URL`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `XAI_API_KEY`, `OLLAMA_HOST`, `TINYASSETS_ALLOW_API_KEY_PROVIDERS`, and both `*_B64` seed vars.

That is exploitable end to end: `fantasy_daemon/__main__.py:128-142` still registers Gemini/Groq/Grok; `gemini_provider.py:42` reads `GEMINI_API_KEY` straight from `os.environ` and never touches `subprocess_env_for_provider`, so the snapshot requirement added at `providers/base.py:346-350` does not guard it; its only gate is `require_api_key_provider_opt_in`, keyed on the `TINYASSETS_ALLOW_API_KEY_PROVIDERS` the tray leaves in place; and `router.py:210-222` accepts an invocation-only context with no assigned credential and no snapshot. Prod is mitigated by the entrypoint; the desktop host is not.

The `desktop-host-runtime` spec delta enumerates the same incomplete 5-variable list, so the spec blesses the gap rather than closing it.

**Remediation:** share one canonical strip list between the entrypoint and the tray, and update the spec delta to reference it rather than restating five names.

---

## MEDIUM

**8. `deploy/ship-logs.sh:34` — log shipping breaks on any non-slack deploy.** The new default includes `tinyassets-slack-agent`, which is behind `profiles: ["slack"]`, but the collection loop treats every entry as required and `exit 1`s on a missing container (lines 89–95). The old default listed containers that always existed. Drop `tinyassets-slack-agent` from the default or make profile-gated services optional.

**9. `tinyassets/api/status.py:1017-1018` — the diagnostic surface lies.** `api_key_enabled = False` and `api_key_vars_present = []` are hardcoded, but `api_key_providers_enabled()` is still live and still gates real behavior (`providers/base.py:143`). `get_status` will report API-key providers disabled on a host where they are enabled. Either report the real value or remove the field — a constant `false` is worse than absence.

**10. `.github/known-failing-tests.txt` — three lines removed for tests this diff never touches.** `test_anonymous_write_challenge.py::test_scoped_canary_token_...`, `test_execution_evidence_store.py::test_invalid_parent_path_is_not_created`, and `test_execution_authority_import_boundary.py::test_database_check_use_swap_fails_before_authority_initialization` are all de-quarantined with no stated Linux evidence (local Windows runs are evidence in neither direction). Only the `test_cloud_worker.py` line corresponds to a deleted test. De-quarantining is the right direction, but each removal needs a CI receipt or it turns `required-tests` red on main.

**11. `tinyassets/providers/router.py:95` — `**_retired_options: object` silently swallows retired kwargs.** No current caller passes any, so this is latent, but a caller passing `fallback_chain=`, `pin_writer=`, or `auth_health=` gets silence instead of an error — in the one module whose purpose is to forbid those concepts. Against Hard Rule 8. Raise `TypeError` naming the retired option.

**12. `tinyassets/providers/claude_provider.py:216` — `complete_json` missed the signature change.** It still calls `subprocess_env_for_provider(self.name, universe_dir=universe_dir)` with no `credential_snapshot_dir`, which now raises unconditionally (`base.py:346-350`). `complete()` at line 121 was updated; this one was not. It has no callers today, so it is latent, not live.

---

## Do the tests meaningfully assert fail-closed exact-authority behavior?

**Partly — the negative cases that matter most are missing, and the central test is vacuous.**

Genuinely load-bearing:
- `test_no_universe_call_cannot_inherit_host_provider_auth` (`tests/test_assigned_credential_execution.py:152`) — real function, ambient `CODEX_HOME`/`OPENAI_API_KEY` set, expects a raise. Good.
- `test_resolver_maps_missing_assignment_to_typed_hold` (:238) — unmocked, real empty directory, typed hold. Good.
- `test_daemon_does_not_claim_queue_when_credential_is_unavailable` (:328) — proves the daemon respects the hold and leaves the task `pending`. Good.
- `test_assigned_credential_failure_never_tries_another_provider` (:85) — proves no widening on exhaustion. Good.

Vacuous:
- `test_resolver_snapshots_exact_serving_credential_and_cleans_it` (:163) monkeypatches out `load_provider_assignment`, `resolve_serving_agent_binding`, `SQLiteProviderWorkAuthorityStore`, `current_serving_authority`, `snapshot_llm_subscription_credential` and `cleanup_llm_credential_snapshot` — i.e. every component that constitutes the authority check. What remains under test is dataclass plumbing and the `try/finally`. Worse, its stub returns a binding carrying `allowed_operations=("run_graph",)`, which production code never reads (finding 4) — the test creates the impression the authority is binding-derived when it is hardcoded.
- The four router tests all construct `AssignedCredentialAuthority(...)` directly, inheriting the hardcoded `allowed_operations` default, so the "exactness" they assert is the constant asserting itself.

Absent entirely — every one of these is a mutation probe the current suite would pass unchanged:
- a binding whose `allowed_operations` lacks `run_graph` → must hold (today: silently allowed)
- role `judge`/`extract` outside `binding.allowed_roles` → must hold
- `current_serving_authority` returning a mismatched provider / `binding_id` / `credential_reference_id` → must hold (the check at `assigned_credential_execution.py:99-104` is real but untested; the stub makes all three compare equal trivially)
- an assigned call exceeding the binding or carrier token/cost ceiling → must refuse (finding 5)
- serving status revoked between resolve and snapshot → must hold (finding 6)
- `docker compose config` schema validity (findings 1 and 2 both survived a 440-test green run)

Also removed without replacement: `test_credential_fail_closed.py` lost the secret-safe exception-chain coverage. `base.py:375` now does `raise ... from exc`, preserving `__cause__`/`__context__` across a path that reads raw credential bytes (`base.py:366`), and the replacement `test_malformed_claude_token_is_sanitized` (:148) only inspects the outer message. Your own review-patterns note lists four channels that leak a credential out of an exception; a `str(exc)` assertion catches none of them. Most of the other 29 deletions were legitimate — they covered the vault-overlay path this change removes — and generic mirror parity is still guarded by `tests/test_pre_commit_mirror_parity.py`.

---

## Verdict

**CHANGES REQUIRED.**

Findings 1–3 mean this cannot be deployed at all: the compose file is rejected by Docker, the cleanup step fences a healthy deploy, and the fence destroys the production queue on every run. Finding 4 means the change does not yet deliver its own headline requirement — the credential is resolved exactly, but the *authority* attached to it is manufactured rather than derived, and the router check that is supposed to enforce exactness compares a constant to itself. 5–7 are the reachable consequences of that same gap.

Suggested order: 1 and 2 (one-line deploy unblocks), then 3 (data loss), then 4 and 5 together (they are the same seam), then 6 and 7. Findings 3 and 4 are the two I would not merge on any timeline without a fix.
