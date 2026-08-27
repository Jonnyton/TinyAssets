# Preserved worktree content — harness reset P1

> **The files themselves were removed from the working tree on 2026-08-26**, once
> the reset merged to `main` as `e4180697`. They are permanently in git history
> and this manifest is the index. Recover any one with:
> `git show e4180697:docs/audits/harness-reset-preserved/<worktree>/<path>`
>
> Keeping 47,000 lines of recovered duplicates checked out served no purpose the
> history does not already serve. The manifest stays because *knowing what was
> rescued* is the part a reader needs; the bytes are one command away.

Captured 2026-08-25 before any worktree reap. Base `origin/main` @ `8cbf9769`.

## Why this exists

The v1 plan said "reap the worktrees." Codex's review flagged that as the one irreversible step,
and it was right. A scan of all 61 sibling `wf-*` directories found **31 with no `.git` at all**
(detached remnants — `git worktree remove` never ran, or the `.git` file was deleted) and
**3 registered worktrees with uncommitted changes**.
Hashing every source file in the orphaned directories against the object database found **49 files
whose content git has never seen**. They are copied here verbatim, and the dirty worktrees' diffs
are saved as patches. Only after this landed were the directories safe to remove.

## Orphaned-directory files (content unknown to git)

| Worktree | Path | Bytes | sha256[:16] | Modified |
|---|---|---|---|---|
| `wf-anon-identity` | `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/api/engine_helpers.py` | 15601 | `9a5d2a9a19f5dcaf` | 2026-07-21 16:23 |
| `wf-anon-identity` | `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/api/helpers.py` | 8404 | `e16ddbc52b3d3fec` | 2026-07-21 16:23 |
| `wf-anon-identity` | `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/api/permissions.py` | 5580 | `e55cf5bc041250f0` | 2026-07-21 16:23 |
| `wf-anon-identity` | `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/api/status.py` | 56129 | `2acffb0b8687de7a` | 2026-07-21 16:24 |
| `wf-anon-identity` | `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/api/universe.py` | 198155 | `a920315ab01c486f` | 2026-07-21 16:25 |
| `wf-anon-identity` | `tests/test_anonymous_identity_fail_closed.py` | 5693 | `c03d98bce82a0a5f` | 2026-07-21 16:25 |
| `wf-anon-identity` | `tests/test_current_actor_auth_context.py` | 4519 | `fe1a5cc86f888fc3` | 2026-07-21 16:27 |
| `wf-anon-identity` | `tinyassets/api/engine_helpers.py` | 15601 | `9a5d2a9a19f5dcaf` | 2026-07-21 16:23 |
| `wf-anon-identity` | `tinyassets/api/helpers.py` | 8404 | `e16ddbc52b3d3fec` | 2026-07-21 16:23 |
| `wf-anon-identity` | `tinyassets/api/permissions.py` | 5580 | `e55cf5bc041250f0` | 2026-07-21 16:23 |
| `wf-anon-identity` | `tinyassets/api/status.py` | 56129 | `2acffb0b8687de7a` | 2026-07-21 16:24 |
| `wf-anon-identity` | `tinyassets/api/universe.py` | 198155 | `a920315ab01c486f` | 2026-07-21 16:25 |
| `wf-blob-locks2` | `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/runtime/lease_store.py` | 96351 | `f20e2bb80c9a8021` | 2026-07-21 15:05 |
| `wf-blob-locks2` | `tests/test_lease_store.py` | 185790 | `8de4c65d89eaffa8` | 2026-07-21 15:19 |
| `wf-blob-locks2` | `tinyassets/runtime/lease_store.py` | 96351 | `f20e2bb80c9a8021` | 2026-07-21 15:05 |
| `wf-drain-20260728-233434-74ed1e-complete-test-identity-and-reset` | `docs/ops/test-identities.md` | 4356 | `2eb31488780cdba8` | 2026-07-29 00:45 |
| `wf-drain-20260728-233434-74ed1e-complete-test-identity-and-reset` | `openspec/changes/test-identity-and-reset/tasks.md` | 8797 | `0d62e7bc89ba0350` | 2026-07-29 00:45 |
| `wf-drain-20260728-233434-74ed1e-transport-workflow-chain-buildin` | `openspec/changes/paid-market-track-e-wave-2-transport/tasks.md` | 23326 | `2ddaadc15296d24a` | 2026-07-29 11:08 |
| `wf-drain-20260728-233434-74ed1e-transport-workflow-chain-buildin` | `tests/test_paid_market_workflow_routing.py` | 4040 | `7eb840edb9f3cfc3` | 2026-07-29 11:07 |
| `wf-drain-20260728-233434-74ed1e-transport-workflow-chain-buildin` | `tinyassets/api/market_workflow.py` | 3626 | `a2c6df04ccdd0563` | 2026-07-29 11:07 |
| `wf-drain-20260728-233434-74ed1e-universe-personification-relay-s` | `openspec/changes/reconcile-universe-personification-relay/design.md` | 16976 | `75e1c84a7b4fc5f3` | 2026-07-28 23:51 |
| `wf-drain-20260728-233434-74ed1e-universe-personification-relay-s` | `openspec/changes/reconcile-universe-personification-relay/implementation-notes.md` | 13973 | `f8528e4ba01db2b4` | 2026-07-28 23:53 |
| `wf-drain-20260728-233434-74ed1e-universe-personification-relay-s` | `openspec/changes/reconcile-universe-personification-relay/specs/universe-personification-and-relay/spec.md` | 13368 | `6acb241136871738` | 2026-07-28 23:51 |
| `wf-drain-20260728-233434-74ed1e-universe-personification-relay-s` | `openspec/changes/reconcile-universe-personification-relay/tasks.md` | 13197 | `33e89d0c3e6b9cac` | 2026-07-28 23:59 |
| `wf-drain-20260728-233434-74ed1e-universe-personification-relay-s` | `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/universe_server.py` | 90100 | `a7673362b65f84c5` | 2026-07-28 23:59 |
| `wf-drain-20260728-233434-74ed1e-universe-personification-relay-s` | `tests/test_universe_write_boundary.py` | 16694 | `3bf5f695c5b19a95` | 2026-07-28 23:58 |
| `wf-drain-20260728-233434-74ed1e-universe-personification-relay-s` | `tinyassets/universe_server.py` | 90100 | `a7673362b65f84c5` | 2026-07-28 23:59 |
| `wf-effect-route` | `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/runtime/lease_store.py` | 87649 | `ec86d13c677d221f` | 2026-07-21 15:25 |
| `wf-effect-route` | `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/runtime/signed_record_contracts.py` | 10134 | `70b142d55af4b66f` | 2026-07-21 15:22 |
| `wf-effect-route` | `tests/test_lease_store.py` | 167779 | `f8e9509e1d96d6f7` | 2026-07-21 15:31 |
| `wf-effect-route` | `tests/test_signed_records.py` | 11394 | `8a6ec961088623f4` | 2026-07-21 15:30 |
| `wf-effect-route` | `tinyassets/runtime/lease_store.py` | 87649 | `ec86d13c677d221f` | 2026-07-21 15:25 |
| `wf-effect-route` | `tinyassets/runtime/signed_record_contracts.py` | 10134 | `70b142d55af4b66f` | 2026-07-21 15:22 |
| `wf-test-identity` | `openspec/changes/test-identity-and-reset/tasks.md` | 1508 | `75a40cf3cb21fdf9` | 2026-07-21 17:20 |
| `wf-test-identity` | `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/api/identity.py` | 1769 | `3de4cb3ebc830bfa` | 2026-07-21 17:08 |
| `wf-test-identity` | `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/api/status.py` | 55526 | `c8700babf06621f1` | 2026-07-21 17:05 |
| `wf-test-identity` | `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/auth/middleware.py` | 18310 | `4976f510d92adad6` | 2026-07-21 17:03 |
| `wf-test-identity` | `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/providers/base.py` | 28087 | `a90dc06634cdd0d3` | 2026-07-21 17:05 |
| `wf-test-identity` | `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/reset.py` | 11438 | `880cc47300a23c41` | 2026-07-21 17:09 |
| `wf-test-identity` | `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/universe_server.py` | 97774 | `8ce6221b2e473677` | 2026-07-21 17:08 |
| `wf-test-identity` | `tests/test_identity_observability.py` | 2980 | `34a848370e962a47` | 2026-07-21 17:06 |
| `wf-test-identity` | `tests/test_provider_auth_evidence.py` | 2912 | `e24e8e9d757ac001` | 2026-07-21 17:04 |
| `wf-test-identity` | `tests/test_scoped_identity_reset.py` | 9873 | `ae0fc5b93983a4ee` | 2026-07-21 17:10 |
| `wf-test-identity` | `tinyassets/api/identity.py` | 1769 | `3de4cb3ebc830bfa` | 2026-07-21 17:08 |
| `wf-test-identity` | `tinyassets/api/status.py` | 55526 | `c8700babf06621f1` | 2026-07-21 17:05 |
| `wf-test-identity` | `tinyassets/auth/middleware.py` | 18310 | `4976f510d92adad6` | 2026-07-21 17:03 |
| `wf-test-identity` | `tinyassets/providers/base.py` | 28087 | `a90dc06634cdd0d3` | 2026-07-21 17:05 |
| `wf-test-identity` | `tinyassets/reset.py` | 11438 | `880cc47300a23c41` | 2026-07-21 17:09 |
| `wf-test-identity` | `tinyassets/universe_server.py` | 97774 | `8ce6221b2e473677` | 2026-07-21 17:08 |

**49 files preserved.**

## Dirty registered worktrees (saved as patches)

| Worktree | Branch | HEAD | Patch lines |
|---|---|---|---|
| `wf-consumer-activation` | `claude/run-provider-session` | `3eb798eb5b5e` | 578 |
| `wf-fleet-slice1` | `claude/fleet-slice1-reconciler` | `4f8335b718f8` | 42 |

Apply with `git -C <worktree> apply <patch>` against the recorded HEAD.

## Restore

```bash
# a single file
cp docs/audits/harness-reset-preserved/<worktree>/<path> <path>
# a dirty worktree's work
git -C ../<worktree> apply docs/audits/harness-reset-preserved/<worktree>--<branch>--<head>.patch
```

Nothing here is on any branch's history. This directory **is** the only copy — do not delete it
without confirming each file is either superseded on `main` or genuinely unwanted.
## CI run artifacts (also unknown to git)

`wf-p0-30495376702-artifact` and `wf-p0-30504334373-artifact` each hold 5 small JSON diagnostics
(`cleanup-observation`, `fence-status`, `preflight`, `receipt_snapshot_before`, `unsafe-fence`) from
two P0 workflow runs. Preserved because Actions artifacts expire and these are the only local copy.

## Checked and NOT preserved

- `wf-drain-preserved-20260802-132145-5c093f-a003` — a **prior** rescue of 7 flattened files. All 7
  hash to objects already in git; that rescue was folded back successfully. Its flattened names
  (`packaging__claude-plugin__…`) dodged the path-based scan, so it was hash-checked individually.
- ~590 files under `WebSite/site-react/out/` across 5 directories — build output.
- `wf-codex-pr-scope-audit-method-20260504`, `wf-docs`, `wf-fence-fix`, `wf-pr1489-verify` — empty.

## Reap result (2026-08-25)

61 sibling `wf-*` directories → **3 kept** (`wf-harness-reset`, plus the two dirty lanes
`wf-consumer-activation` and `wf-fleet-slice1`, left intact so their owners can land the work).
19 clean registered worktrees removed via `git worktree remove`; registered count 26 → 8.
23 directories fully deleted.

**17 residual empty shells.** Every real file in them deleted; what remains is a single
`.pytest_cache` per directory carrying an ACL the interactive user cannot read or delete. This is
the exact case AGENTS.md § *Testing* documents — a sandbox (Codex/Cursor) pointed pytest's
`--basetemp`/`TMPDIR` inside the checkout and created the dir under a restricted token. Non-elevated
`icacls /grant` does not clear it and a reboot does not help.

Host one-liner to finish, from an **elevated** shell:

```powershell
Get-ChildItem C:\Users\Jonathan\Projects\wf-* -Directory |
  Where-Object { $_.Name -notin 'wf-harness-reset','wf-consumer-activation','wf-fleet-slice1' } |
  ForEach-Object { takeown /F $_.FullName /R /D Y | Out-Null
                   icacls $_.FullName /grant "$env:USERNAME:(OI)(CI)F" /T /C | Out-Null
                   Remove-Item $_.FullName -Recurse -Force }
```

Harmless until then — they hold no content.
