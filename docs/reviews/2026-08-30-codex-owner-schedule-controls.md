# Codex exact-head review — owner controls on schedule rows (PR #2702)

Branch `claude/owner-schedule-controls`. Round 1 pinned to c257bda8 (ADAPT: spec delta only); round 2 pinned to 231d0be073bc4a6691156f8e23c585ca6b3d1bf5 (APPROVE). Receipt on the PR body cites the PR comment holding the same text; this file is the in-repo copy.

Dispatched 2026-08-30 via `python scripts/peer_agent.py codex --prompt-file <brief>` on Codex's own budget; verdicts verbatim below.

## Codex exact-head review — round 1 (c257bda8): ADAPT (spec delta only)

1. **AGREE — handler check is the authority.**

The public path is:

`extensions()` → `_extensions_impl()` → `require_action_scope()` → `_SCHEDULER_ACTIONS` → `_schedule_control_context()` → mutation.

- Public delegation: [universe_server.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tinyassets/universe_server.py:2367)
- Scope gate before dispatch: [extensions.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tinyassets/api/extensions.py:480)
- Scheduler routing: [extensions.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tinyassets/api/extensions.py:745), [runtime_ops.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tinyassets/api/runtime_ops.py:858)
- All three handlers call `_schedule_control_context`: [runtime_ops.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tinyassets/api/runtime_ops.py:618), [runtime_ops.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tinyassets/api/runtime_ops.py:807), [runtime_ops.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tinyassets/api/runtime_ops.py:828)
- The context requires authentication, derives `actor` from request-local identity, loads the row, and requires a current admin ACL on the row’s universe: [runtime_ops.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tinyassets/api/runtime_ops.py:570)
- `permissions.current_actor_id()` explicitly has no environment fallback: [permissions.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tinyassets/api/permissions.py:235)

Nuance: this is technically a current row-universe-admin check, not a stored `owner_principal_id OR admin` comparison. The creator initially has that admin ACL; a revoked owner is intentionally refused.

The low-level scheduler functions accept `requesting_actor`/`admin=True`, but static search found no production callers except these checked handlers: [scheduler.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tinyassets/scheduler.py:460), [scheduler.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tinyassets/scheduler.py:575), [scheduler.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tinyassets/scheduler.py:610). Internal engine-MCP `_extensions_impl` calls are limited to branch build/patch/list actions and do not expose schedule control.

Verification: 2026-08-29, Windows NT 10.0.26200, `rg -n` searches for all handler and low-level function calls.

2. **AGREE — legacy handling remains fail-closed.**

For rows with empty `owner_principal_id` and `universe_id`:

- If `owner_actor` is `universe:<uid>` or a bare principal recoverable as the founder of the request universe, a costly-scoped authenticated caller must still be a current admin of that recovered universe: [runtime_ops.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tinyassets/api/runtime_ops.py:516), [runtime_ops.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tinyassets/api/runtime_ops.py:546), [runtime_ops.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tinyassets/api/runtime_ops.py:598)
- Delegated current admins may also control recoverable rows.
- If `owner_actor` cannot establish a universe, `row_universe` remains empty and everyone is refused with `owner_not_admin`, including universe admins.

Thus the exact status of `1508d5dc…` depends on its stored `owner_actor`, which was not included in the prompt. Empty new columns alone do not make it controllable by arbitrary costly principals.

Before this diff, callers needed the outer admin scope and then passed the same handler ACL check. Afterward, costly reaches the handler, but the handler authority is unchanged. This is acceptable: recoverable legacy rows can be cleaned up by their universe’s current admins; ambiguous rows remain orphaned.

Verification: 2026-08-29, same environment, inspected the legacy tests and ran `python -m pytest tests/test_scheduler_owner.py -q` → `71 passed`.

3. **DISAGREE_CONCERN — the code semantics are sound, but the permission delta is not specified.**

Moving the actions changes:

- `effect`: `admin` → `costly`
- OAuth metadata: `tinyassets.extensions.admin` → `tinyassets.extensions.costly`
- `cost_tier`: `admin` → `costly`

Those values derive at [provider.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tinyassets/auth/provider.py:442), with the changed membership at [provider.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tinyassets/auth/provider.py:395).

It does not:

- Perform a budget/billing deduction.
- Add or alter rate limiting.
- Change the mutation `extension_writes` set; all three were already writes at [provider.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tinyassets/auth/provider.py:592).
- Change connector-advertised OAuth scopes. Protected Resource Metadata intentionally advertises only OIDC scopes: [identity-auth-and-access-control/spec.md](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/openspec/specs/identity-auth-and-access-control/spec.md:91).

Production WorkOS grants every authenticated founder coarse `costly`, while platform `admin` remains explicit: [workos_provider.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tinyassets/auth/workos_provider.py:30).

The active `user-owned-automations` change says owners may pause/resume/delete, but does not pin the changed two-layer permission contract: coarse costly scope permits handler entry; authenticated current admin ACL on the row universe authorizes mutation. Because this is an AUTHORITY/public-action tier change, the repository rule requires that delta.

Minimal adaptation: add one OpenSpec requirement/scenario to `user-owned-automations`—or a modified `identity-auth-and-access-control` delta—specifying those two layers. No code change is indicated.

Verification: 2026-08-29, same environment, `rg` over `tinyassets/auth`, `docs/reference`, and `openspec`; `python scripts/openspec_flow.py audit`.

4. **AGREE — tests exercise the real boundary and fail on main.**

- `_ext()` invokes the real `tinyassets.universe_server.extensions`: [test_scheduler_owner.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tests/test_scheduler_owner.py:256)
- `_COSTLY_ONLY_CAPS` explicitly omits `tinyassets.extensions.admin`: [test_scheduler_owner.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tests/test_scheduler_owner.py:50)
- The credential fixture binds a real `Identity` through the authentication middleware; it does not monkeypatch `require_action_scope` or the action-scope registry: [conftest.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tests/conftest.py:90)
- The non-owner test asserts exactly `owner_not_admin`: [test_scheduler_owner.py](C:/Users/Jonathan/Projects/wf-owner-schedule-controls/tests/test_scheduler_owner.py:1264)

Verification, 2026-08-29, Windows/Python 3.14.3:

- `python -m pytest tests/test_scheduler_owner.py -k "costly_only" -q` → `9 passed`
- Loaded `git show origin/main:tinyassets/auth/provider.py` into a clean Python process, then ran the same pytest selector → `9 failed`, all at the former `tinyassets.extensions.admin` scope gate
- `python -m pytest tests/test_scheduler_owner.py -q` → `71 passed`
- `python -m pytest tests/test_action_scopes.py -q` → `5 passed`

5. **AGREE — mirror is byte-identical.**

Canonical and packaged mirror both produced SHA-256:

`FED20605FE13872C91E1DBB3B329CA1EC5400A9BBA2EAEAEFCDC00C65A9B7F3F`

Verification: 2026-08-29, same environment:

- `Get-FileHash -Algorithm SHA256` on both files
- `python scripts/invariants_run.py --check mirror-parity` → `[OK] ... all 377 canonical file(s) mirror-matched`
- Final `git status --short` remained empty.

VERDICT: ADAPT c257bda821ad6ab3ec0b3cb393469b223960dc22
## Round 2 (231d0be0): APPROVE

1. **AGREE** — The requirement accurately states both layers. All three actions are `costly`, while `_schedule_control_context` requires request-local authentication and a current `admin` ACL on the resolved row universe. All four scenarios match the code.

2. **AGREE** — The stable patch ID matches `c257bda8` exactly (`75d3288a…`), confirming rebase-only code changes. `python scripts/invariants_run.py --check mirror-parity`: all 377 files matched.

3. **AGREE** — `python -m pytest tests/test_scheduler_owner.py -q`: 71 passed, 4 deprecation warnings.

VERDICT: APPROVE 231d0be073bc4a6691156f8e23c585ca6b3d1bf5
## Live proof after deploy (production ce339de2, 2026-08-30T03:17:08Z)

From the founder's web-app session (capabilities read/write/costly/submit_request/list, no admin): `extensions action=unschedule_branch schedule_id=9a331b73-b28b-41b6-b900-8019e5eef446` → `{"status":"unscheduled"}` — the same call that was refused at 02:26:53Z on 0ac34796 with `Missing OAuth scope: tinyassets.extensions.admin`. The duplicate heartbeat schedule is gone; the automation (`d25a356811d0405c8bc92ebc9601c68f`) keeps the cadence alone, back under the shared 20/hour run cap.

Same session, 03:17:23Z: `unschedule_branch schedule_id=1508d5dc-2a0e-41e9-bbf2-117265123e39` (the fleet-era row with empty universe/principal and a bare founder `owner_actor`) → `{"status":"unscheduled"}` — the legacy-recovery path Codex traced in round 1 item 2 (bare principal recovers to the founder's universe; current admin ACL required) works live. `list_schedules` → 0 rows.
