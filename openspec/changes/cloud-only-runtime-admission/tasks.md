# Tasks — cloud-only runtime admission

No runtime guard lands until this change clears cross-family review. Task 1 is
the bounded hosted preflight — **PR #3914 merged, observed06:21UTC September22**; it
resolves the facts that could change the design, and task 4 does not start until
it has actually produced one. Task 6's refusal flip is gated on task 5 resolving
CLOUD on the real droplet. Record-only stages (tasks 1, 5) are observation and
are reported as **incomplete** and not risk-free, never as a closed boundary.
No new gate, workflow or proposal is introduced beyond what is listed here.

- [x] 1. Land `.github/workflows/cloud-only-preflight.yml` as designed
  (`ubuntu-latest`, `permissions: contents: read`, default-branch
  `workflow_dispatch` only, never `pull_request`) — **PR #3914 mergedfdb6ff15**.
  Hosted run35694437735 on main completed06:21UTC2026-09-22: container metadata
  reachable, expected droplet resolved, identity_match=true; public Worker paths
  checked3/bound=true. Tunnel connectors and internal DNS unknown because account
  and tunnel IDs are missing; credential custody unknown, SSH trust TOFU-unverified.
  Overall status unknown, boundary_closed=false, enforcement=none. This clears
  only the actual metadata observation prerequisite, not custody or enforcement.
  Ran `scripts/cloud_only_preflight.py` once after it
  merges and record sanitized verdicts here: remote container metadata
  reachability and expected-id match, connector in-set/out-of-set counts,
  internal-origin DNS binding and canonical MCP Worker routing. Do not emit raw
  identities or enumerable id digests, and assert no cloud fact before the run
  exists. A typed `unknown` blocks enforcement acceptance, not unrelated fixes.
  If metadata is unreachable, revise `design.md` § Evidence primitive before
  task 4.
- [x] 2. Re-read each provider URL in `design.md` § Source citations and their
  limits, correct any that moved, and record the read date. Lead read the
  official contracts on 2026-09-22 UTC and corrected metadata/API/OAuth links.
  Public contract reads do not establish deployed facts or approve runtime code.
- [x] 3. **Prevention (review finding 2):** delete the off-cloud ingress
  capability — daemon, tray and plugin-runtime tunnel startup, its call sites,
  the re-exports and the env gate that armed it. **Landed** in PR #3913, sha
  `dfa22598c35aabad7be27aacbff75d300e17b584`; hosted build `35689968798` /
  deploy `35690255704` passed public handles and the protected-SHA gate at
  05:20 UTC 2026-09-22. This closes an accidental-start path only: the
  cloud-side tunnel remains, tunnel-token custody is the separate Layer C
  invariant, application checks cannot establish exclusive custody, and the
  cloud access policy is still unverified.
- [ ] 4. **Gated on task 1 having actually run.** Record the expected droplet id
  into dedicated typed expected-instance state in the canonical data volume
  before candidate startup, separate from the release receipt, then implement
  `resolve_platform_runtime_provenance()` — fail-closed, dedicated internal
  metadata client (literal address, no redirects, sub-second timeout, no user
  input, not reachable as a user capability, SSRF link-local classification
  unchanged), recorded-instance match and sanitized startup record. Resolution happens
  outside any database write transaction. Resolver is **injected** in tests,
  never satisfied by an environment variable. Do not build against a predicted
  metadata result. Prepare the expected-id state before candidate startup;
  preserve it across success-receipt replacement and compatible rollback.
  Resolve once per process; cached refusal never silently upgrades, and each
  explicit restart resolves anew. Operation-level authority checks remain live.
  Add the **non-mutating peek** on the existing process observation (never calls
  the resolver, never initializes the cache, refuses an inherited parent result
  after a PID change, explicit `unknown` for unobserved/failed) and the sanitized
  canary-only `platform_runtime_provenance` field on the existing authenticated
  `/mcp/pulse`, through the existing request-identity API with no auth or
  permission widening. A health GET SHALL NOT trigger a fresh resolve. Nothing
  branches on the field; it is not enforcement.
- [ ] 5. Land the resolver in record-only mode; confirm on the droplet that it
  resolves CLOUD and the recorded id matches. Read it back from the **main
  serving process** — a startup log line is not evidence that the main process
  cached anything, and the hosted preflight's separate metadata child is a
  different process. Route: `scripts/deployed_sha.py --report-provenance`
  printing allowlisted typed fields from the pulse response it already fetched
  (no second call, no raw dict dump, unknown stays unknown, existing
  `--assert-contains` exit semantics unchanged), with the flag added to the
  existing hosted post-receipt `Verify protected receipt contains target
  revision` step — no new workflow, secret or desktop credential. Do not flip a
  resolver that cannot resolve CLOUD in production. Report this stage as
  observation, not enforcement and not risk-free — it still adds a read and a
  startup log record on a live path. Useful evidence is exactly "the responding process
  holds a cached CLOUD verdict"; it is **not** binary freshness (`git_sha` is the
  mutable receipt), **not** the current container incarnation (`uptime_seconds`
  starts at app construction), **not** all workers (one responding sample), and
  **not** attestation or custody. Prove expected-id presence/match across a real
  redeploy and restart, plus rollback-state compatibility, before enabling
  refusal.
- [ ] 6. Flip claim admission onto the **non-optional** predicate
  `_transaction_allows_assigned_consumer` / `_assigned_consumer_refusal_reason`
  (`branch_tasks_v2.py:1170`), not the optional `authority_claim` callback —
  `transaction_check` returns `allowed` unchanged when it is `None`
  (`:489`). Evidence is resolved before the write transaction opens and only the
  resulting process-owned value is read inside the CAS; no HTTP I/O under the
  write lock. Keep `_consumer_skip_reason` as the diagnostic.
- [ ] 7. Flip runtime registration to resolved provenance, re-resolved on read so
  an existing row grants nothing, plus the origin-ingress backstop refusal. Do
  **not** derive anti-replay from `boot_id` (`uuid.uuid4().hex`,
  `assigned_queue_consumer.py:209`): it is incarnation/liveness only. Keep the
  existing descriptor expiry and add no storage schema for it.
- [ ] 8. Flip startup and the last provider-authority boundary — boot assertion,
  no degraded mode, the four `executor_class="cloud"` literals
  (`foreground_run_provider.py:484,595`,
  `background_served_provider.py:1336,1547`), which the queue path cannot reach —
  and the recovery paths: watchdog, release-reconcile and stale-runtime
  retirement leave work pending when no admitted successor exists. Per-universe
  user-bound authority stays exactly as it is.
- [ ] 9. Write the test matrix from `design.md`. Negatives 1–7 **must be run
  against the unfixed tree and fail there**; the claim negative passes **no**
  `authority_claim` callback, or it is vacuous. Positives 8–9 assert preserved
  behaviour (restart, concurrent cloud workers, per-universe authority) and may
  pass at baseline. Add focused unit tests for the preflight
  with no real API calls. Run `python scripts/linux_oracle.py` on the new tests
  (they touch process/network syscalls Windows skips) and
  `python scripts/skip_census.py`.
- [ ] 10. Get the cross-family review verdict, merge, then prove deployment:
  `python scripts/deployed_sha.py --assert-contains <sha>` and
  `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp
  --assert-handles` (export `TINYASSETS_WIKI_CANARY_TOKEN` first).
- [ ] 11. Rendered acceptance through the live connector (`ui-test`): a
  brand-new user completes their **own** OpenRouter OAuth PKCE authorization,
  returns via the automatic callback, approves an eligible free model, and gets
  a first actual tool-capable response — no borrowed subscription, no
  account-specific patch, no change to any existing user's workflow.
- [ ] 12. Sync this delta into `openspec/specs/cloud-only-runtime-admission/`,
  resolve the colliding as-built text named in `design.md` § Colliding as-built
  specs (`desktop-host-runtime:8,24,45,59` local MCP/tunnel serving — task 3
  removes the behaviour, so the spec text follows it;
  `daemon-identity-and-host-pool:76,97` host-pool registration — verify live
  before deleting), and archive the change in the same lane.
