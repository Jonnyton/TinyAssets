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
| **P0** | [Graph/provider false attestation](2026-07-02-graph-provider-false-attestation.md) — router fallback neutralizes isolation refusals | 2026-07-02 |
| **P0** | [Unauthenticated LAN session leak + CSRF writes](2026-07-21-unauth-lan-session-leak-csrf.md) — do not LAN-run | 2026-07-21 |
| **P0** | [Public-site privacy, deps, and CI secret exposure](2026-07-27-public-site-privacy-deps-ci.md) — a same-repo PR can request 19 secrets | 2026-07-27 |
| **P1** | [Power-cycle driver cannot live on the box](2026-08-28-power-cycle-driver-cannot-live-on-the-box.md) — a shutdown-and-resize script run ON the droplet would have left it off with nothing alive to restart it; cancelled ~40s in, no impact. Also: I declared a credential absent after checking two of four places | 2026-08-28 |
| **P1** | [User code runs in the daemon process](2026-08-28-user-code-runs-in-process.md) — an approved source node reads the live Stripe key, every vault, every user's refresh token, and writes the paid-tier DB. #2629 bounds WHO may approve; nothing bounds what the code does | 2026-08-28 |
| **P1** | [No OS engine sandbox](2026-07-02-no-os-engine-sandbox.md) — in-process confinement only; the denylist fails open | 2026-07-02 |
| **P1** | [No live failure proof](2026-07-23-no-live-failure-proof.md) — escalation and caps are CI-only | 2026-07-23 |
| **P1** | [Founder-taught canon defaults public](2026-08-06-founder-canon-defaults-public.md) — Codex reproduced | 2026-08-06 |
| **P1** | [Served-agent BUILD verb parity](2026-08-23-served-surface-build-verb-parity.md) — partial; the rest is authority-sensitive | 2026-08-23 |
| **P1** | [BYO-LLM refresh-token store](2026-08-23-byo-llm-refresh-token-store.md) — fixation + world-readable files + handle-as-filename CLOSED (#2627); plaintext at rest remains, and encryption cannot fix it while user code shares the process | 2026-08-23 |
| **P1** | [`write_brain` persistent prompt-injection](2026-08-24-write-brain-prompt-injection.md) — attacker content re-injected into system role every turn | 2026-08-24 |
| **P1** | [Pending-request mute bypass](2026-08-27-pending-request-mute-bypass.md) — different asks collide, and the asking agent can unmute itself | 2026-08-27 |
| **P1** | [Unsafe-fence recovery path deleted](2026-08-27-unsafe-fence-recovery-path-deleted.md) — #2442 removed the only exit from `phase=unsafe_fenced` (observed live 2026-08-05, all five containers Exited) while three workflows still arm the fence | 2026-08-27 |
| **P1** | [GitHub App token refresh never reaches the daemon](2026-08-27-github-app-token-refresh-never-reaches-daemon.md) — a 45-min timer writes an `env_file` the running process snapshotted at container creation; the unit is also skipped silently without a bootstrap file nothing creates | 2026-08-27 |
| **P1** | [Deploy drops the compose sync](2026-08-27-deploy-drops-compose-sync.md) — `deploy/compose.yml` is never shipped to the droplet, so every compose-level change is inert in production | 2026-08-27 |
| **P1** | [A deploy kills every in-flight turn, silently](2026-08-29-a-deploy-kills-in-flight-turns-silently.md) — the container is recreated under a running served turn: no reply, no log line, the thread reloads without it; killed two live tests in one day | 2026-08-29 |
| **P1** | [A refused outbound effect completes the run silently](2026-08-28-a-403-effect-completes-the-run-silently.md) — GitHub said 403, the run said `completed` with no error and the log said nothing; the reason sat unread in the effect-evidence map | 2026-08-28 |
| **P2** | [Archived a universe that WAS bound](2026-08-28-archived-a-bound-universe.md) — live-data cleanup removed `u-01ky3zh1arr8qth8jee7zx63pq` while its `founder_home` row still pointed at it; recovered because the step archived rather than deleted | 2026-08-28 |
| **P2** | [The assigned-queue consumer error-loops ~41×/min](2026-08-28-assigned-queue-consumer-hot-error-loop.md) — ~2,500 tracebacks an hour on a fresh container, steady state, unrelated to what raised them; every real error now arrives buried in it | 2026-08-28 |
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
| **P2** | [`converse` SSE stream has no keepalive](2026-08-28-converse-sse-stream-has-no-keepalive.md) — a minutes-long turn sends zero bytes until the result | 2026-08-28 |
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
