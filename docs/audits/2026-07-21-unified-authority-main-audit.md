# Unified authority derivation audit — fresh `origin/main`

**Freshness:** 2026-07-21, Windows workspace clone, base
`144eaba7467613c1aab37fe5d485bff02475500f` (`origin/main`).

**Model:** M1 platform signature (`RecordVerifier` / `Verified[T]`), M2
caller-held content address re-derived at the decision point, M3 fresh external
re-confirmation. Mutable storage may narrow, reject, or audit; it may not grant.

## Result

One independent, live-request M2 conversion is safe on this base:
`run_branch_version` now executes only a full SHA-256-addressed snapshot whose
digest is recomputed immediately before reconstruction. Direct DML that changes
both `snapshot_json` and its adjacent `content_hash` is rejected because neither
column supplies the expected digest. Legacy truncated IDs remain browsable and
can be republished into full addresses, but cannot authorize execution.

The remaining positive-authority classes are listed below. They are not safe to
half-convert on this branch: most require the absent M1 custody/composition root,
three overlap active branches, and the money/external-effect paths require their
specified host-gated rollout. This is a blocker report, not a claim that mutable
authority has been eradicated from `origin/main`.

## Main/ledger contradiction

The distributed-execution task ledger on this base says the M1 signed-record and
S2/S3 foundations landed in PRs #1477, #1479, #1481, #1487, and #1491. The files
are absent from `origin/main`: there is no `tinyassets/runtime/`, signed-record
verifier, lease store, or daemon-enrollment module. Reconciliation commits
`203c09c1` and `ce91c359` exist on `origin/claude/ledger-reconcile`, not main.
The divergent foundation branches have hundreds of files of unrelated ancestry;
stacking them here would not be a fresh-main fix.

Consequently, an M1 conversion on this base would have to invent key custody,
rotation, domain contracts, and the composition root. That would violate the
approved order and create a second trust model. This branch adds only the sealed
`Verified[T]` custody wrapper needed by M2; it does not claim to provide M1 or a
`RecordVerifier` before those prerequisites land.

## Remaining authority registry

| Priority | Live surface / decision | Mutable positive authority on main | Required model and disposition |
|---|---|---|---|
| P0 | Universe read/write/admin checks | `daemon_server.universe_access_permission`, visibility and founder-home rows are consumed by `api/permissions.py`, `api/runs.py`, `api/status.py`, `api/universe.py`, `api/wiki.py`, and auto-ship actions | M1 signed universe grant/home binding + M3 authenticated request principal. **Blocked:** M1 trust root absent. |
| P0 | Daemon pause/resume/restart/banish/update | `daemon_registry.py` derives owner/delegated-host scope from mutable metadata and `created_by`; `api/universe.py` exposes the controls | M1 signed ownership/delegation + M3 request actor. **Blocked:** M1 absent. |
| P0 | Schedule/subscription create, pause, remove, and fire | `api/runtime_ops.py` accepts/stores owner actor; `scheduler.py` treats active rows as firing and lifecycle authority | M1 signed schedule grant, M2 exact branch snapshot at fire, M3 actor. **Blocked:** M1 absent; converting only actor resolution leaves the stored grant authoritative. |
| P0 | External writes (GitHub PR, Twitter, wiki write-back, desktop) | `effectors/authority.py` explicitly treats mutable universe-soul data as authority; `storage/effector_consents.py` treats active SQLite grants as authority; consent grant accepts caller `granted_by` and legacy env actor fallback | M1 exact-sink/destination consent + M3 actor/external confirmation. **Active overlap:** `wf-effect-route` / draft PR #1493 owns GitHub effect routing. Non-GitHub sinks remain unconverted. |
| P0 | GitHub merge | `github_merge.py` accepts packet mode/head fields and trusts the merge response; it does not obtain review authority or post-read the final state | M2 exact head + M3 fresh GitHub review/protection/merge state and post-read, returned as `Verified[GitHubMergeAuthority]`. **Blocked:** separate redesign and host-gated cutover; #1493 never-merges and does not solve this path. |
| P0 | Paid-market claim/retract/stake/refund/release | `api/market.py` trusts mutable `claimed_by`, goal author, `bonus_staker_id`, and env-derived host/actor fields. Completed run rows can mint rung claims | M1 signed ownership/outcome, M3 authenticated actor, ledger conservation. **Blocked:** M1 absent and live-money host gate B25; no bulk signing/backfill. |
| P0 | Completed-run consumers | Mutable `runs.status` and output feed gate claims, leaderboard/canonical selection, selector dispatch, child attachment, and resume/control decisions | M1 signed `RunOutcomeAttestation` + M2 exact result and branch digests. **Blocked:** B2 completion attestation/M1 absent. Runtime-only UX counters may remain audit-only once separated from grant decisions. |
| P1 | Branch publication, ownership, visibility, source-code approval | Mutable branch JSON supplies author/visibility; `approved=True` plus adjacent caller-computable `approved_source_hash` is treated as approval | M1 signed publication/ownership/source approval; M2 exact snapshot/source digest; M3 actor for new grants. **Partially fixed:** only version execution M2 is converted here. M1 parts blocked. |
| P1 | Queue claim and cancellation | `branch_tasks.py` stores mutable status/`claimed_by`; `api/universe.py` uses it for self-cancel authority | M1 signed task/lease claim + M3 current actor. **Blocked:** M1/B2 claim prerequisite absent. |
| P1 | Node-edit rollback | `node_edit_audit` snapshots in `runs.py` are restored by `api/evaluation.py` | M1 signed edit/rollback provenance + M2 snapshot digest. **Blocked:** an adjacent hash is forgeable with the row and no external expected digest exists. |
| P1 | Daemon memory review/promotion | Mutable `promotion_state` selects promoted memory as prompt context; MCP memory actions remain reachable through `api/universe.py` | M1 signed reviewer decision + M3 reviewer, and M2 if promoted material becomes executable input. **Blocked:** M1 absent. Scope-gating alone does not authenticate the stored promotion. |
| P1 | Request actor and effector-consent attribution | `api/engine_helpers._current_actor` falls back to mutable `UNIVERSE_SERVER_USER`; consent grant also permits caller-supplied `granted_by` | M3 authenticated request identity for positive grants. **Blocked as a standalone edit:** the consent row itself would still positively authorize; convert with signed consent, not attribution alone. |
| P1 | S3 daemon enrollment/device authority | The target enrollment code is absent on main; active `wf-s3-devkey` and patch-loop device-auth lanes own the conversion | M1 signed enrollment/device credential + bounded re-enrollment/dual verification. **Blocked:** active overlap and host gate B24. |
| P1 | S2 lease/completion and blob publication | Lease store, signed completion, and blob runtime named by the ledger are absent on main; active divergent branches own them | M1 lease/completion, M2 blobs/capsules/results. **Blocked:** prerequisite branches have not landed; there is no fresh-main sink to patch. |

## Already conforming or non-authoritative

- WorkOS JWT/JWKS validation is M3 external re-confirmation. It should not be
  re-signed by the platform.
- Mutable status, visibility, revocation, denylist, and expiry fields may remain
  when they only narrow or reject an independently verified grant.
- Audit metadata such as publishers, notes, timestamps, and display counters may
  remain mutable only while no downstream consumer upgrades it into permission.

## Evidence and mutation proof

Search/review included every request-reachable use of the main authority helpers
and storage classes above, plus the distributed-execution OpenSpec/exec plan,
active `_PURPOSE.md` lanes, and the prior S2 authority audits. Representative
commands:

```text
python scripts/session_sync_gate.py
python scripts/worktree_status.py
python scripts/claim_check.py --provider codex-gpt5-desktop
python scripts/provider_context_feed.py --provider codex-gpt5-desktop --phase build --limit 200
Select-String over tinyassets/**/*.py for owner, claimed_by, permission,
  consent, approved_source_hash, completed, promotion_state, authorization
```

M2 decision-level mutation:

1. Publish a valid branch version and retain its full content-addressed ID.
2. Raw-DML update both `snapshot_json` and `content_hash` to attacker-controlled,
   mutually consistent values.
3. With the execution-time digest comparison temporarily removed, the regression
   test is RED: `Failed: DID NOT RAISE BranchVersionContentMismatch`.
4. Restore the comparison to the caller-held digest: the same test is GREEN.

Legacy upgrade TDD proof: with the full-ID filter absent, republishing a legacy
eight-character ID returns that unsafe truncated ID and the test is RED; with the
filter present, republish mints the full digest address and the test is GREEN.

Focused verification on 2026-07-21 in the isolated Windows clone:

```text
pytest tests/test_run_branch_version.py tests/test_signed_records.py \
  tests/test_publish_version.py tests/test_branch_versions_rollback_columns.py \
  tests/test_branch_authoring_actions.py tests/test_rollback.py \
  tests/test_canonical_dispatch.py tests/test_goals_run_canonical.py \
  tests/test_selector_dispatch.py -q
# 196 passed, 16 warnings
```

The warnings are pre-existing Python 3.14/Pydantic/LangGraph deprecations. Pytest
also cannot use the sandbox user's default Windows temp directory; verification
used a workspace-local `TEMP`/`TMP` without changing or xfail-ing tests.

The repository-wide suite is not green evidence: a bounded 1,200-second run
reached 57% with numerous failures/errors already appearing from 4% onward, then
timed out before pytest emitted its failure summary. Those failures are not
hidden or attributed to this branch without evidence. The 196-test consumer
slice above is the branch-proportional verification result.

Focused Ruff checks pass. A broader check that includes the pre-existing
`tinyassets/runs.py` and `tinyassets/api/runs.py` files reports 20 existing E501
violations on mojibake section-ruler lines; none are in this branch's changed
lines, and this branch does not rewrite or suppress them.

## Review gate

No independent review verdict is claimed. The Claude write peer was rejected by
its unaccepted isolated-workspace trust dialog before touching files. Read-only
Fable and explicit Sonnet attempts then exited with empty stderr, the subprocess
Codex reviewer could not read its sandboxed configuration, and the collaboration
review backend reported no thread for this turn. The required Fable-5 review
therefore remains a pre-merge gate; this branch may be published only as draft.
