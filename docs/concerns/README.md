# Concerns

One file per unresolved concern. **This directory replaced the `STATUS.md` Concerns section on
2026-08-25**, when the board was retired in the harness reset.

## Why files, not GitHub issues

Codex's review of the reset plan (`docs/audits/2026-08-25-harness-reset-codex-review.md`) argued
this and was right: GitHub issues are externally mutable, network-dependent, and **absent from a
clone**. A security finding that only exists in a web UI is not evidence a fresh checkout can act
on. A tracked file is. Link an issue from a concern file when one exists — but the file is canonical.

## Conventions

- **Filename:** `YYYY-MM-DD-short-slug.md`, dated by when the concern was **filed**.
- **Header:** `**Filed:**` / `**Verified:**` / `**Re-verified:**` / `**Severity:**` (P0/P1/P2, or
  omitted when severity is not the point).
- **Source (verbatim)** — the original text, unedited. Never paraphrase a security finding forward;
  paraphrase drifts, and the drift is what let `#1489` end up pointing at an unrelated merged PR.
- **Re-verification** — when a premise is re-checked, record the date and what changed. Line numbers
  and paths rot; the premise usually doesn't. Correct the citation, keep the finding.
- Resolve a concern by **deleting the file**. Git holds the history.

## Open concerns

| Severity | Concern | Filed |
|---|---|---|
| **P2** | [Run submission accepts missing required branch inputs](2026-09-03-run-submission-accepts-missing-required-inputs.md) — unresolved required inputs are detected only after admission; submission needs an authority-preserving preflight refusal with exact missing-input guidance and no run row | 2026-09-03 |
| **P1** | [The no-anonymous cutover is one of three and still leaves a public read](2026-09-03-no-anonymous-cutover-is-one-of-three.md) — the existing owned branch is an unmerged PR-1 source change; `/mcp/pulse`, residual anonymous fallbacks, a red targeted test, and no exact-head receipt remain | 2026-09-03 |
| **P1** | [Local MCP OAuth session lifecycle is only partly proven](2026-09-03-local-mcp-oauth-session-lifecycle-is-partly-proven.md) — login authenticates the direct `workflow-live` client, but both bundled `codex_apps` connector surfaces stay anonymous in the same fresh task and emit no linking challenge | 2026-09-03 |
| **P2** | [Capacitor CLI still resolves a vulnerable UUID library](2026-09-03-capacitor-cli-uuid-advisory.md) — high/critical mobile build-chain advisories are removed, but current `@capacitor/cli` still reaches `uuid@7.0.3` through `xcode`; build-time only, no compatible upstream update yet | 2026-09-03 |
| **P2** | [App Store privacy policy is still an explicitly unfinished legal draft](2026-09-03-app-store-privacy-policy-is-draft.md) — the public URL is reachable and contains contact/data sections, but it says “Draft v0,” omits iOS until PR #2798 deploys, and cannot truthfully be treated as final without founder/counsel approval | 2026-09-03 |
| **P2** | [iOS shell risks App Review minimum-functionality rejection](2026-09-03-ios-web-wrapper-app-review-risk.md) — the signed binary loads the same remotely served client as the web surface; native OAuth return and packaging may not satisfy Apple's Guideline 4.2 without a meaningful iPhone-native interaction | 2026-09-03 |
| **P2** | ["Connect any LLM" is real for one endpoint shape, not every shape](2026-09-03-connect-any-llm-remaining-shapes.md) — `anthropic_messages` is offered but the deposit always sends `bearer` and `header_name` is not a deposit-time field, so an endpoint following the published spec cannot authenticate; plus `get_status` reports the daemon HOST's CLI as `llm_endpoint_bound` with no per-universe serving field, which sent the founder's own universe chasing a phantom runtime bug | 2026-09-03 |
| **P2** | [What account deletion still does not do, after three review rounds](2026-09-02-account-deletion-residue-after-the-three-round-cap.md) — shipped path deletes the user's data and refuses rather than touching anyone else's; residue is no retry worker for an unreachable Stripe, no global fence over writers, and blocking rather than anonymising foreign rows | 2026-09-02 |
| **P2** | [Auto-merge landed #2773 six minutes after its Codex verdict said REJECT](2026-09-02-auto-merge-landed-2773-before-its-cross-family-verdict-was-read.md) — auto-enroll binds merge to CI, not to the cross-family verdict; measured: enrolled 05:59Z, REJECT written 06:03Z, merged 06:09Z. Drafts are skipped by auto-enroll, so this lane opens review-pending PRs as drafts | 2026-09-02 |
| **P2** | [Migration and scratch records are publicly discoverable universes](2026-09-02-migration-records-are-publicly-discoverable.md) — seven of the twelve `visibility=public` universes are removal buckets and internal scratch, marked public by maintenance rather than by anyone publishing; the commons page shows them because filtering would falsify its own "what is public" claim. Needs a founder decision: the fix changes live universe records | 2026-09-02 |
| **P2** | [The exact-head receipt and the three-round cap have no exit together](2026-08-31-the-exact-head-receipt-loops-against-iterative-review.md) — every fix voids the receipt, the cap forbids the pass that would restore it; findings went 7 -> 5 -> 1 -> 3 on #2755. CI cannot represent the founder decision the cap assumes ends the loop | 2026-08-31 |
| **P2** | [Hard-coded policy the user should be composing instead](2026-08-31-hard-coded-policy-that-should-be-user-composable.md) — five workflow-shape caps and six platform-selected policies constrain the user's own work; the deeper pattern is one hard-coded policy manufacturing the justification for another | 2026-08-31 |
| **P2** | [Credential removal leaves ownership and orphans](2026-08-31-credential-removal-leaves-ownership-and-orphans.md) — `forget_credential` does not clear the deposit-ownership row, so a DIFFERENT principal's re-deposit is refused as a transfer; and an absent connection row skips the owner check entirely | 2026-08-31 |
| **P2** | [Merging took three rail asks because the PR opened as a draft](2026-08-30-merge-needs-three-asks-because-the-pr-was-a-draft.md) — live naive-user test on #2691: merge `405 still a draft`, the `ready_for_review` REST endpoint does not exist (`404`), only GraphQL works | 2026-08-30 |
| **P2** | [Cancel is advisory, and the run timeout is doing its job](2026-08-31-cancel-is-advisory-and-the-timeout-is-doing-its-job.md) — the owner's ability to stop a borrowed workflow is what bounds it; #2752 reached the running child, the rest of the surface still checks between nodes | 2026-08-31 |
| **P1** | [Fixing an authority key orphans every grant written under the old one](2026-08-31-fixing-an-authority-key-orphans-the-grants-written-under-the-old-one.md) — hit live, blocking the founder's universe mid-run with `missing_consent`; a correctness fix to a key is a silent migration | 2026-08-31 |
| **P2** | [23 of 37 declared dependencies can ship a major into CI unannounced](2026-08-31-unbounded-dependencies-can-red-the-gate.md) — fastmcp 4.0.0 arrived through `>=3.0` and red-ed the gate; #2746 pinned one package, not the shape | 2026-08-31 |
| **P2** | [Workspace admission is narrower than the claims made for it](2026-08-31-workspace-admission-claims-are-narrower-than-stated.md) — four findings from a Codex REJECT on #2742, all pre-existing in the workspace primitive but falsifying the claims that justified the widening | 2026-08-31 |
| **note** | [The node import allowlist is theatre — delete it, don't fix it](2026-08-31-ws-globals-defeats-the-import-allowlist.md) — filed as P1, INVERTED the same day: the measurement holds, but under the isolation floor (cross-user only) it is not a vulnerability | 2026-08-31 |
| **P2** | [The outbound broker child failed to start, cause never found](2026-08-27-outbound-proxy-start-failure.md) — was P0; egress verified working 2026-08-31 (the universe opened #2691 through it). The intermittent was never diagnosed. (The `source_code`-nodes-unrunnable claim here was INVERTED 2026-09-01: they run; only the receipt says otherwise) | 2026-08-27 |
| **P2** | [The background loop cannot run on the current shape](2026-08-29-background-loop-activation-is-fleet-era.md) — its activation layer is fleet-era; the "24/7 background self" has been dead since 2026-08-07 | 2026-08-29 |
| **P2** | ["Connect a model" clears on a signal the turn path does not use](2026-08-29-serving-readiness-panel-disagrees-with-turn-path.md) — a user is told the model is connected while every turn is refused | 2026-08-29 |
| **P2** | [IdP subject ids are persisted in 24 columns across 5 databases](2026-08-29-subject-ids-scattered-across-stores.md) — a tenant identity change is a hand migration today, and there will be another | 2026-08-29 |
| **note** | [The acceptance test: a different connection, a different task, zero patches](2026-08-31-the-acceptance-test-is-a-different-connection-and-a-different-task.md) — the founder's bar for calling the credential work done: another service and another task with NO platform patch | 2026-08-31 |
| **P2** | [The forge table is platform knowledge, and deleting it re-broke a live fix](2026-08-31-the-forge-table-is-platform-knowledge-and-removing-it-broke-a-live-fix.md) — I removed #2753 FORGE_GIT_HOSTS and inverted its regression test, reopening the GitHub checkout 403; restored. The agnosticism argument is real and needs a migration, not a deletion | 2026-08-31 |
| **P1** | [A single-use provider carrier is being reused](2026-09-01-a-single-use-provider-carrier-is-being-reused.md) — the actual cause of the founder universe not answering; fails closed, then gets relabelled as quota by the router and as an API-key problem by the run classifier | 2026-09-01 |
| **P2** | [The connect ask does not appear when the credential dies](2026-09-01-the-connect-ask-does-not-appear-when-the-credential-dies.md) — the rail asks only when NO binding exists, so a bound-but-expired universe is unserved and un-asked | 2026-09-01 |
| **P1** | [A run releases its workspace locks against the wrong database](2026-09-01-a-run-releases-its-workspace-locks-against-the-wrong-database.md) — locks live in the universe DB, the terminal enqueue runs at the root, so every workspace run leaves its universe lock and host slot held; the sweep now consults the root as a backstop | 2026-09-01 |
| **P2** | [Event subscriptions fire without the owner's identity](2026-09-02-event-subscriptions-fire-without-the-owners-identity.md) — the scheduler's event thread runs a subscribed graph with no principal, so provider binding falls back to an anonymous identity; automations and schedules carry the owner, subscriptions do not (Codex on status-says-what-is-true) | 2026-09-02 |
| **P2** | [Provider auth failures are classified by substring, not by the provider](2026-09-01-provider-auth-failures-are-classified-by-substring-not-by-the-provider.md) — `classify_unavailable` guesses auth vs network from words like "token"; three review rounds each found a message on the wrong side; the provider should emit a typed class, and the Claude quick-exit path discards stderr | 2026-09-01 |
| **P0** | [A subscription credential dies permanently at its first token expiry](2026-09-01-a-subscription-credential-dies-permanently-at-its-first-token-expiry.md) — the served snapshot is disposable, so an OAuth refresh can never be persisted; the founder universe went dark 2026-09-01T03:23Z and re-depositing only restarts the timer (Codex CONFIRMED) | 2026-09-01 |
| **P2** | [The serving gesture checks admin once, then mutates three times](2026-09-01-the-serving-gesture-checks-admin-once-then-mutates-three-times.md) — `ensure_founder_serving` re-checks the ACL before, not inside, its three mutations; a revocation in between still lands (Codex on #2760); the fix is on an authority path | 2026-09-01 |
| **P0** | [Graph/provider false attestation](2026-07-02-graph-provider-false-attestation.md) — router fallback neutralizes isolation refusals | 2026-07-02 |
| **P0** | [Unauthenticated LAN session leak + CSRF writes](2026-07-21-unauth-lan-session-leak-csrf.md) — do not LAN-run | 2026-07-21 |
| **P0** | [Public-site privacy, deps, and CI secret exposure](2026-07-27-public-site-privacy-deps-ci.md) — a same-repo PR can request 19 secrets | 2026-07-27 |
| **P1** | [Power-cycle driver cannot live on the box](2026-08-28-power-cycle-driver-cannot-live-on-the-box.md) — a shutdown-and-resize script run ON the droplet would have left it off with nothing alive to restart it; cancelled ~40s in, no impact. Also: I declared a credential absent after checking two of four places | 2026-08-28 |
| **P1** | [User code runs in the daemon process](2026-08-28-user-code-runs-in-process.md) — an approved source node reads the live Stripe key, every vault, every user's refresh token, and writes the paid-tier DB. #2629 bounds WHO may approve; nothing bounds what the code does | 2026-08-28 |
| **P1** | [No OS engine sandbox](2026-07-02-no-os-engine-sandbox.md) — in-process confinement only; the denylist fails open | 2026-07-02 |
| **P1** | [No live failure proof](2026-07-23-no-live-failure-proof.md) — escalation and caps are CI-only | 2026-07-23 |
| **P1** | [Founder-taught canon defaults public](2026-08-06-founder-canon-defaults-public.md) — Codex reproduced | 2026-08-06 |
| **P1** | [Served user-owned branch lifecycle](2026-08-23-served-surface-build-verb-parity.md) — create/inspect/edit/run/delete exist at actor scope, but explicit branch-to-universe binding, general served availability, edit CAS, and unified lifecycle spec truth remain | 2026-09-03 |
| **P1** | [Pending-request mute bypass](2026-08-27-pending-request-mute-bypass.md) — different asks collide, and the asking agent can unmute itself | 2026-08-27 |
| **P3** | [The stop-writer fence is armed by nothing and guarded by three workflows](2026-08-27-unsafe-fence-recovery-path-deleted.md) — stale `unsafe_fenced` state archived 2026-08-29, canary watchdog re-enabled; finish `retire-cheat-loop` 2.5a (guard call sites, script, orphans, tests) | 2026-08-27 |
| **P1** | [GitHub App token refresh never reaches the daemon](2026-08-27-github-app-token-refresh-never-reaches-daemon.md) — a 45-min timer writes an `env_file` the running process snapshotted at container creation; the unit is also skipped silently without a bootstrap file nothing creates | 2026-08-27 |
| **P1** | [A deploy kills every in-flight turn, silently](2026-08-29-a-deploy-kills-in-flight-turns-silently.md) — the container is recreated under a running served turn: no reply, no log line, the thread reloads without it; killed two live tests in one day | 2026-08-29 |
| **P1** | [A refused outbound effect completes the run silently](2026-08-28-a-403-effect-completes-the-run-silently.md) — GitHub said 403, the run said `completed` with no error and the log said nothing; the reason sat unread in the effect-evidence map | 2026-08-28 |
| **P2** | [Archived a universe that WAS bound](2026-08-28-archived-a-bound-universe.md) — live-data cleanup removed `u-01ky3zh1arr8qth8jee7zx63pq` while its `founder_home` row still pointed at it; recovered because the step archived rather than deleted | 2026-08-28 |
| **P2** | [Foreground provider authority gaps](2026-08-27-foreground-provider-authority-gaps.md) — 4 unfixed: `max_invocations` counts node definitions, mock bypass keyed on `__module__`, receipt published before claim, denials masked as "connect your provider" | 2026-08-27 |
| **P2** | [Global subscription-auth seed is a dead path](2026-08-27-deploy-drops-subscription-auth-sync.md) — no workflow delivers the two auth bundles, but Codex review found them vestigial: the fix is removing the entrypoint/runbook contract and the stale process-global gates, NOT restoring delivery | 2026-08-27 |
| **P2** | [A Stripe 4xx reads as our billing being down](2026-08-28-stripe-4xx-reads-as-an-outage.md) — every `HTTPError` becomes `BillingUnavailable`, so a config mistake of ours is reported as infrastructure sickness three layers from the truth | 2026-08-28 |
| **P2** | [Sibling sessions have no subtree budget](2026-08-27-sibling-sessions-have-no-subtree-budget.md) — async fan-out mints a fresh per-run receipt each time, so breadth is unbounded | 2026-08-27 |
| **P2** | [Credential deposit refusals are unobservable](2026-08-27-credential-deposit-refusals-are-unobservable.md) — `connect_http` logs no refusal and returns HTTP 200, so a failed deposit is byte-identical to a successful one in the daemon log; the founder's GitHub deposit failed twice and nobody could say why | 2026-08-27 |
| **P2** | [No reachable remove for http connections](2026-08-27-no-reachable-remove-for-http-connections.md) — the ledger has `revoke_connection` but nothing exposes it, so a deposited key cannot be withdrawn; a naive remove would permanently burn the destination name (deterministic ids + the `revoked_at` conflict) | 2026-08-27 |
| **P2** | [Served provider authority is converse-only](2026-08-27-served-provider-authority-is-converse-only.md) — the live paste-inference call is refused every time (`provider request source is not trusted`); widening it is the rejected keystone, and the agent-asks rail needs no widening | 2026-08-27 |
| **P2** | [An agent can lift a mute the user set](2026-08-27-pending-request-mute-bypass.md) — `dont_ask_again` and `unmute_request` are both reachable by the served agent, which authenticates as the user's own principal; lifts are recorded and surfaced, not prevented | 2026-08-27 |
| **P2** | [`_current_actor` env fallback](2026-06-30-current-actor-env-fallback.md) — bypasses `permissions.py` | 2026-06-30 |
| **P2** | [The scheduled tripwire has been red continuously](2026-08-27-full-tests-permanently-red.md) — `full-tests`, now `heavy-tests`: 107 unquarantined failures, since before the reset; a permanent red carries no more signal than a permanent green | 2026-08-27 |
| **P2** | [`deployed_sha` proves the receipt, not the running binary](2026-08-26-deployed-sha-proves-receipt-only.md) — a rollback with an intact receipt reads as shipped | 2026-08-26 |
| **P2** | [The one file built for the universe to ship is mirrored](2026-08-28-the-agent-shippable-file-is-mirrored.md) — `request_theme.json` tells the agent to edit it and open a PR, but it is mirrored, so a one-file edit always fails CI and needs a human commit | 2026-08-28 |
| **P2** | [Grant granularity is per-file, not per-job](2026-08-28-grant-granularity-is-per-file-not-per-job.md) — a job the founder already approved end-to-end stops for a fresh approval on each additional file, which is the friction they have ruled against twice | 2026-08-28 |
| **P2** | [An agent cannot withdraw its own stale ask](2026-08-28-an-agent-cannot-withdraw-its-own-stale-ask.md) — the rail is append-only from the agent side, so asks it knows are obsolete sit in the founder's face until the founder clears them | 2026-08-28 |
| **P2** | [One key serves both dedupe and muting](2026-08-28-one-key-serves-dedupe-and-muting.md) — the agent rewords its prose, dedupe misses, and the rail grows a second tab for a grant already pending | 2026-08-28 |
| **P2** | [Long `converse` responses: the origin pings every 15s; delivery through the tunnel is unproven](2026-08-28-converse-sse-stream-has-no-keepalive.md) — the "silent stream" premise was false (`tests/test_mcp_sse_keepalive.py`); whether long turns are still cut end to end, and by what, is open until a >3-minute live `converse` is captured | 2026-08-28 |
` (`README.md +2/-87`); the effector has no server-side encoding, so every file write a user's agent makes is corruptible | 2026-08-29 |
| **P2** | [The claude reader idle-kills a turn waiting on its own tool](2026-08-29-claude-reader-tool-wait-idle-gap.md) -- `tool_phase` is telemetry only; codex got the in-flight-tool allowance in #2674, claude did not | 2026-08-29 |
| **P2** | [No user Stop for a running turn](2026-08-29-no-user-stop-for-a-running-turn.md) -- turns now run until finished (3600s backstop); the "interrupted by the user" half of the founder's rule is unbuilt | 2026-08-29 |
| **P2** | [A codex `agent_message` can be dropped under backpressure](2026-08-29-codex-agent-message-can-be-dropped-under-backpressure.md) -- only `TurnCompleted` is guaranteed; a finished turn with its reply item dropped fails "omitted result or usage" instead of returning the reply | 2026-08-29 |
| **P2** | [`initialize_runs_db()` is not concurrency-safe](2026-08-29-initialize-runs-db-not-concurrency-safe.md) — `executescript` upgrades a deferred transaction outside `busy_timeout`; racing boots fail with `database is locked` even on a fresh DB | 2026-08-29 |
| — | [Provider fallback-chain privacy](2026-04-17-provider-fallback-chain-privacy.md) — gemini/groq/grok still in the chains | 2026-04-17 |
| — | [Cloud automation rollback refused >24h](2026-08-05-cloud-automation-rollback-refused.md) — tested, not fixed | 2026-08-05 |

Predating the migration: [synthesis skip echoes](2026-04-16-synthesis-skip-echoes.md),
[`test_record_and_get_stats` flake](2026-04-26-test_record_and_get_stats_flake.md),
[cloud-agent command duplication](2026-08-02-cloud-agent-command-duplication.md).

## Not migrated, and why

Triage found three of twelve board rows did not survive contact with the code. Recorded here so
nobody re-derives them.

**Resolved — `EPOCH2_QUEUE_CONSUMER_READY` (P1, filed 2026-08-03).** The row read: *"3 tests still
assert the closed gate — now the ONLY blockers of main's `full-tests` tripwire."* Inverted.
`tinyassets/branch_tasks_v2.py:113` is `EPOCH2_QUEUE_CONSUMER_READY = True`, and the tests now
assert `is True` and pass (`tests/test_cloud_worker.py:601`,
`tests/test_cloud_automation_continuation.py:1814`; 5 passed, 2026-08-25). Nothing to migrate.

**Expired by design — two watches filed 2026-08-25.** Plug-and-play prod verification (waiting on a
founder X deposit; the first organic post is the proof) and prod disk at 78.6% (already guarded by a
`disk_watch` GitHub issue at 80% and hourly `disk_autoprune` at 85%). Both name their own automated
guard or closing event. A watch whose guard already exists does not need a second home.

## A caution the migration earned

The board's row for the LAN/CSRF finding cited **`#1489`**. PR #1489 is *"feat(command-center):
recover the Agent Village"*, merged — unrelated. Two other concerns cited paths that no longer exist
(`engine_helpers.py:192`, `router.py:89-92`); both premises held at their new locations. Verify a
citation against the code before acting on it, and re-stamp it when you do.

## Four concerns the migration dropped (added 2026-08-26)

The rows above marked 2026-07-02 / 2026-07-21 / 2026-08-05 / 2026-08-23 were **not** migrated on
2026-08-25. They were found the next day by diffing the retired board against this directory, and
every premise still held when re-checked against the code.

Three were security findings, one of them the **P0** LAN/CSRF exposure — for which this README
recorded only a caution about its bad citation, never the finding itself. The
`resolve_interlocutor_tier` item sat in the board's *Work* table rather than its Concerns list,
which is likely how it was passed over.

The lesson is the migration's own: a security finding whose only record is a caution about its
citation is not recorded. **Diff the source against the destination before deleting the source** —
the board was still readable in a stale checkout, which is the only reason these were recoverable.
