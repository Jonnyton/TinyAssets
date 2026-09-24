# Platform LLM call audit — Hard Rule 15 enforcement

**Date:** 2026-09-24. **Branch:** `claude/platform-has-no-llm-enforce`. **Rule:**
AGENTS.md Hard Rule 15, "The platform has no LLM" (PR #3957). **Risk tier:** Tier 2
(the floor: credential exposure / a shared credential serving a user). **Review:**
the cross-family (Codex) review is **owed**. It has not been run.

"Before" citations are at base `4096b6b0`. "Now" citations are at the PR head.

## The rule

A model call is allowed only when it comes from one universe, carries that universe
owner's authority, and runs on credentials the owner connected. Nothing else may
call a model: no platform feature, no host login, no environment key, no maintainer
credential, and no fallback.

## Where the rule is enforced: one module, wired into every provider launch

`tinyassets/providers/owner_binding.py` holds both checks. `ProviderRouter` is the
only code that calls `BaseProvider.complete`. A search on 2026-09-24 found exactly
three call sites, all in `router.py`. Two of them are now gone.

- **Entry check.** `require_owner_bound_context` (`owner_binding.py:74`) runs first
  in `ProviderRouter.call` (`router.py:505`), `call_with_policy` (`:1455`) and
  `call_judge_ensemble` (`:1664`), before any provider is looked up, probed or
  configured. It refuses a call in any of these cases:
  - there is no `UniverseContext`;
  - the context has no `universe_dir`;
  - the call has neither a server-minted `ProviderInvocationCarrier` for that
    universe nor a live `provider_request`, which the router then authorizes
    against the owner's serving binding.
- **Launch check.** `require_owner_bound_dispatch` (`owner_binding.py:109`) runs at
  the top of the provider loop in `_call_routed`, before budget reservation and
  `provider.complete` (`router.py:880`). The same check also replaces the old
  fallback-chain branch as a hard stop (`router.py:792`). The provider being
  launched must be the one the owner's authority names. It must also not be a
  host-credential built-in:
  - `gemini-free`, `groq-free` and `grok-free` read the host's `*_API_KEY`;
  - `ollama-local` is the host's own `localhost:11434`.

  If the launch is refused, the carrier is settled as `CANCELLED_BEFORE_LAUNCH`.
- **How a refusal fails.** It raises `PlatformLLMCallRefusedError`, which is a
  `ProviderAuthorityHeldError`, so every existing caller passes it on instead of
  swallowing it. `call_provider` therefore never quietly returns its
  `fallback_response` (Hard Rule 8). A universe that has no owner authority gets the
  existing "Connect your provider…" message, so the run-failure taxonomy still
  classifies it correctly (`tinyassets/api/runs.py:838`).

## Audit table

Classes:
- **LIVE** — could run in production (`python -m tinyassets.universe_server`,
  `deploy/compose.yml`), or on a shipped desktop host.
- **LATENT** — possible in code, but no production caller reaches it.
- **DEAD** — no caller, or only tests call it.
- **OK** — already bound to the owner's authority.

### Live violations (fixed in this PR)

| # | Site (before) | What happened | Reach | Now |
|---|---|---|---|---|
| 1 | `providers/router.py:870` (`else: chain = FALLBACK_CHAINS…`), `providers/call.py:280` (`_real_router = _build_fallback_router()`), `providers/base.py:626-636` (no-universe env = host `os.environ`) | A call with no universe was served by a platform fallback chain. The chain went `claude-code` → `codex` → `gemini`/`groq`/`grok` → `ollama-local` and used the host's own CLI logins: `CLAUDE_CONFIG_DIR=/data/.claude` and `CODEX_HOME=/data/.codex` (`deploy/compose.yml:104,106`). | LIVE. `universe_server` builds this router at import time. Any caller without a universe reached the platform's subscription. | Refused at entry. The fallback-chain branch is replaced by a hard stop. |
| 2 | `api/selector_dispatch.py:731-747` → `quality_leaderboard.py:216` | The leaderboard's selector branch ran on the raw `call_provider`, with no universe (hence #1): a platform model call for ranking. | LIVE. Public `run_graph goal_id=…` → `run_canonical` (`universe_server.py:1788`) → `market.py:2445` → `canonical_dispatch.py:455`, whenever a Goal sets `auto_canonical_via_leaderboard`. Also the `quality_leaderboard` and `recommended_parent_for_fork` extension actions (`extensions_leaderboard_actions.py:97,114`). | **Fails closed.** `dispatch_selector` returns `selector_retired` and runs, publishes and resolves nothing. It is not rewired to any universe (founder, 2026-09-24). |
| 3 | `api/market.py:2391` `_action_goal_run_canonical` | The market's canonical auto-refresh reached #2. | LIVE (same path as #2). | No model is called. The stored canonical stands, with source `leaderboard_no_entries`. No market behaviour was built. |
| 4 | `router.py:536` `_apply_auth_health_policy` → `base.py:1127` `subscription_auth_health` → `base.py:942` `_codex_live_auth_probe_uncached` | To prune the unbound chain, the router probed host logins. The codex probe is a **real `codex exec` prompt on the host `CODEX_HOME`**: a monitoring model call on the platform's credential. | LIVE whenever #1 was (the fallback router is built with `auth_health=subscription_auth_health`). | Unreachable: the unbound chain is gone. The router accepts `auth_health` and never calls it. The probe function itself remains (follow-up 6). |
| 5 | `fantasy_daemon/__main__.py:106-141,1879`, `domains/fantasy_daemon/phases/*` (`_provider_stub.py`, `worldbuild.py`, `reflect.py`, `commit.py`, `consolidate.py`, `writer_tools.py`), `fantasy_daemon/__main__.py:3003`, and the helpers they use: `knowledge/raptor.py:341`, `memory/reflexion.py:246,285`, `ingestion/extractors.py:261-276`, `ingestion/indexer.py:172`, `evaluation/editorial.py:119`, `retrieval/agentic_search.py:387` | The legacy host daemon installed a router on the host's CLI logins and called `call_provider` with no universe. | LIVE on any desktop host running the packaged `daemon` role (`desktop/packaged_entrypoint.py:165`). Not the cloud container. | Refused loudly (`PlatformLLMCallRefusedError`). **This feature lost its LLM** (see below). |

### Latent or dead (closed or deleted in this PR)

| # | Site (before) | Class | Now |
|---|---|---|---|
| 6 | `router.py:889` `TINYASSETS_PIN_WRITER`, plus `:988` pinned auth probe | LATENT. Read on every call. On an unbound call it chose the host provider; on a bound call it could refuse the owner's provider or run the host `codex exec` probe (#4). It is not set in `deploy/compose.yml` or `deploy/tinyassets-env.template`. I could not check `/etc/tinyassets/env`. | **Retired.** The router never reads it. |
| 7 | Carrier with `universe_dir=None` → `provider.complete(universe_dir=None)` → host env (`base.py:626-636`) | LATENT. Every production carrier site sets `universe_dir`: `agent_runtime_provider_execution.py:689`, `background_served_provider.py:886`, `cloud_automation_continuation.py:2428`, `foreground_run_provider.py:1167`, `workflow_agent.py:126`. Tests relied on it. | Refused at entry. The carrier's universe must also match `universe_dir`. |
| 8 | An owner binding that names `gemini-free`, `groq-free`, `grok-free` or `ollama-local` | LATENT. The API-key ones were off in production (`TINYASSETS_ALLOW_API_KEY_PROVIDERS: "0"`, `compose.yml:113,300`). `ollama-local` had no gate at all (`ollama_provider.py:21`, host `localhost:11434`). | Refused at launch whatever that flag says. An owner connects these as their own open provider (`api_key_http:<definition>`) instead. |
| 9 | `router.py:1640` `call_with_policy` running its policy provider loop with no universe | DEAD in production. The only policy router it could reach was `graph_compiler`'s empty `_get_shared_router()`, which has no providers. | Collapsed into `call` behind the entry check. The loop is deleted (about 280 lines). |
| 10 | `router.py:2099` `call_judge_ensemble` fanning out across host judges | DEAD. It has no production caller. | Returns the owner's one judge through `call`. The fan-out is deleted. |
| 11 | `graph_compiler.py:1505` `else _get_shared_router()` (the brief cited `:1543`) | DEAD. The fallback was unmarked, but the router it used was always empty, so policy nodes already went through the bound bridge. | Deleted. A policy node is served only by the run's injected, universe-bound caller; otherwise it uses the bound bridge. |
| 12 | `bug_investigation.py:204,274,331` (`enqueue_investigation_request`, `_maybe_enqueue_investigation`, `_resolve_investigation_handler`) | DEAD in production. `wiki file_bug` never calls it (guarded by `tests/test_bug_investigation_wiring.py`), and its env vars are not in the deploy template. Its design was a platform model call: it chose the canonical through #2, then queued a run on a universe's model because a bug was filed. | **Deleted**, per the founder: superseded by user workflows and cross-owner delivery. |
| 13 | Router chain-drain (BUG-029 Part B) and the degraded-judge tail | DEAD once #1 was gone: they only served a chain that fell back to `ollama-local`. | Deleted. |
| 14 | `compose.yml:293` `slack-agent` (`python -m tinyassets.slack_agent_worker`) | DEAD. The profile is opt-in, and the module was deleted in #2451. | Unchanged. Listed as follow-up 7. |

### Compliant or not a model call (no change)

| Site | Why it passes |
|---|---|
| `cloud_automation_continuation.py:2428-2431` | A requester-owned `ProviderInvocationCarrier`, and `universe_dir = base / continuation.universe_id`. |
| `universe_intelligence.py:624,875`, `interactive_http_agent.py:41` | Served turn. `authorize_served_provider_call` binds the owner's serving binding and credential snapshot. |
| `api/connection_inference.py:586` | Served request carrier minted from the owner's serving binding. |
| `api/runs.py:1231,1939,2368` (`_bind_run_provider_call`), `foreground_run_provider.py:1167` | Foreground run carrier. |
| `background_served_provider.py:886,1629`, `runtime/assigned_queue_consumer.py:1315` | Background carrier authorized for the queued task's owner. |
| `agent_runtime_provider_execution.py:680`, `workflow_agent.py:126` | Carrier plus `universe_dir`. |
| `automations.py:1079`, `consumer_runtime.py:107`, `run_input_direct.py:126`, `runs.py:728`, `delivery_runtime.py:171` | `bind_universe_provider_call`: a universe context is required, and the router needs its carrier or request. |
| `providers/native_discovery.py:122`, `api/model_options.py:88`, `providers/served_model_plan.py:153` | Model-catalogue discovery with owner custody. No generation. |
| `onboarding/hosted_model_auth.py:255` | PKCE key exchange. No model call. |
| `api/status.py:298,300` (`OLLAMA_HOST`, `ANTHROPIC_BASE_URL`) | A read-only status hint. Neither variable routes a call. A universe provider child starts from an allowlisted, empty environment. |
| `api/universe.py:6458` (`engine_source=host_daemon`) | Config only. No call. |
| `scripts/peer_agent.py:411-414` | Developer tooling on a developer's machine. Not the platform. |

## Platform features that lost an LLM dependency, and what they do now

- **Quality leaderboard and selector (`quality_leaderboard`,
  `recommended_parent_for_fork`).** They return `ok: false`,
  `error_kind: "selector_retired"`, with a message pointing the user to their own
  workflow. Nothing is ranked. What still uses it live: `run_graph goal_id=…` on a
  Goal that sets `auto_canonical_via_leaderboard`, and the leaderboard extension
  actions.
- **Market `run_canonical` auto-refresh.** It no longer refreshes. It uses the
  stored canonical. If none is stored it returns the existing `no_canonical_handler`
  rejection.
- **Bug-investigation auto-trigger.** Deleted. Filing a bug writes the wiki page
  and nothing else, as it already did in production.
- **Legacy desktop daemon (`packaged_entrypoint` `daemon` role → `fantasy_daemon`)
  and the fantasy-domain phases, RAPTOR, reflexion, extraction and editorial
  helpers.** Every model call they make now fails with `PlatformLLMCallRefusedError`.
  Re-plumbing them to run as the owner's universe with a carrier is not done here.
  The shape the founder named is user-built workflows.

## Left for a follow-up deletion

1. The rest of the selector machinery:
   - `resolve_selector_branch_version_id`, `ensure_default_selector_published`
     and the published "Platform Default Selector v1" LLM branch
     (`api/selector_dispatch.py`);
   - the `goals.selector_branch_version_id` column and backfill;
   - `scripts/migrate_design_008_selector_backfill.py`;
   - selector rollback handling in `rollback.py`;
   - `set_selector` surfaces and `tests/test_goals_set_selector.py`.
2. The leaderboard itself: `api/quality_leaderboard.py`,
   `extensions_leaderboard_actions.py`, and the `auto_canonical_via_leaderboard`
   and `min_completed_runs_for_canonical` Goal fields plus the refresh branch in
   `api/canonical_dispatch.py`.
3. The rest of bug investigation:
   - `build_run_payload`, `attach_patch_packet_comment` and
     `REQUEST_TYPE_BUG_INVESTIGATION` (`bug_investigation.py`);
   - the `bug_investigation` branches in
     `runtime/claimed_branch_execution.py:84,121`;
   - `filing_effort_dispatch_route` (`api/market.py`);
   - the `bug_investigation` queue checks in
     `scripts/retire_cheat_loop_deploy_fence.py`;
   - the `retired_wiki_forwarding` root in
     `scripts/check_background_authority_inventory.py`;
   - the helper tests.
4. The legacy fantasy daemon's provider plumbing:
   - `fantasy_daemon/__main__.py` router build;
   - `domains/fantasy_daemon/phases/_provider_stub.py`;
   - the unbound helpers in row 5;
   - the host-credential executors (`gemini`, `groq`, `grok` and `ollama`
     providers) and their registration in `providers/call.py`.
5. Dead router surface:
   - `FALLBACK_CHAINS`, now only a catalogue of names for `api/status.py`;
   - `_apply_api_key_provider_policy`;
   - the `auth_health` and `chain_drain_empty_threshold` constructor parameters;
   - `graph_compiler._get_shared_router` (used only by `api/status.py:1554`).
6. `providers/base.py` `_codex_live_auth_probe` (a real `codex exec`) and the
   host-environment branch of `subprocess_env_for_provider`. The branch is kept only
   for `scripts/peer_agent.py`, which is developer tooling.
7. **Host action (production).** The daemon container still holds platform CLI
   logins: `CODEX_HOME=/data/.codex` and `CLAUDE_CONFIG_DIR=/data/.claude`
   (`compose.yml:104,106`), seeded by `docker-entrypoint.sh`. No code path reaches
   them now, but the credentials still exist. Removing them is a production change
   and was out of scope. So is the dead `slack-agent` compose profile.

## Adjacent finding (not this rule)

`graph_compiler.py` returns `"[Mock response for <node>]"` when `provider_call is
None`. That is a mock that looks like real output (Hard Rule 8). It is not a model
call, so it stays out of this PR.

## Verification

All runs were on 2026-09-24, on a Windows 11 host, using
`C:/Users/Jonathan/Projects/TinyAssets/.venv` with
`--basetemp=C:/Users/Jonathan/AppData/Local/Temp/ta-pt-nollm/<x>`.

- **New tests** (`tests/test_platform_has_no_llm.py`). Red first: against the base
  source files (the new exception class kept, so the module imports) they gave
  **14 failed, 1 passed**. The pass is `test_refusal_is_held_authority…`, a type
  check. Of the 14 failures:
  - 12 are behavioural: the call was served, the host spy provider
    (`claude-code`) was reached through the leaderboard, the selector or the
    market refresh, a host-credential provider launched, or the host pin
    interfered.
  - 1 is structural: the bug-investigation trigger still existed.
  - 1 is type-only: the base already refused a context-without-authority, but
    with the parent class.

  Green: against the PR head, **15 passed**.
- **Provider, router, selector, leaderboard, canonical, bug-investigation, policy,
  compiler and wiki suites** (77 files):
  `pytest <files> -n 8` → **1574 passed, 18 skipped**.
- **Full suite** (`pytest tests -n 8 --continue-on-collection-errors`): 22572
  passed, 148 failed. I set-compared the failing files against the base source.
  - 139 failures are identical at base: the deploy-workflow, host-uptime,
    backup, cheat-loop-fence, workspace-resolver and MCP-instruction suites.
  - 8 were regressions from this PR, all retired-design router tests. They are
    now deleted or rebound, and those files pass: 140 passed.
  - The remaining failure is the timer flake below.
- **Existing failures and flakes that are not from this PR:**
  - `tests/test_background_authority_inventory.py` fails the same way at base:
    unreviewed `onboarding` and `scheduler` call sites, which this PR does not
    touch.
  - `tests/test_provider_sync_queue_deadline.py` has a Windows timer flake
    ("node budget had not actually elapsed", missing by under 1 ms). It also flaked
    at base (1 of 4 runs).
- **Retired-design tests.** Tests that only asserted the retired design were
  deleted, not marked xfail:
  - platform fallback order;
  - host-login quarantine;
  - host writer pin;
  - judge fan-out;
  - chain drain to `ollama-local`;
  - policy cross-provider fallback;
  - selector run and parse;
  - the investigation enqueue.

  Every test that still describes live behaviour was rebound to an owner carrier
  instead:
  - cooldown classification;
  - diagnostics;
  - admission slot;
  - sync-queue deadline;
  - tool-wait evidence;
  - allowlist.
