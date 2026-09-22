# Tasks — cloud-only runtime admission

No runtime guard lands until this change clears cross-family review. Task 1 is
the bounded hosted preflight (`scripts/cloud_only_preflight.py`, committed here,
**not yet run** — lead reviews placement before any execution); it resolves the
facts that could change the design. Task 6's refusal flip is gated on task 5
resolving CLOUD on the real droplet. Record-only stages (tasks 1, 5) are
observation and are reported as **incomplete**, never as a closed boundary.

- [ ] 1. Add `.github/workflows/cloud-only-preflight.yml` as designed
  (`ubuntu-latest`, `permissions: contents: read`, `workflow_dispatch` +
  schedule, never `pull_request`), run `scripts/cloud_only_preflight.py` once,
  and record its sanitized verdicts here: container metadata reachability,
  expected droplet id digest, connector in-set/out-of-set counts, public DNS
  target class. A typed `unknown` stops the lane; it is not a pass. If metadata
  is unreachable, revise `design.md` § Evidence primitive before task 4.
- [ ] 2. Re-read each provider URL in `design.md` § Source citations and their
  limits, correct any that moved, and record the read date — none of them was
  fetched when this change was written.
- [ ] 3. **Prevention (review finding 2):** delete the off-cloud ingress
  capability — `_start_tunnel` (`fantasy_daemon/__main__.py:3294`), its three
  call sites (`:3542,3755,3844`), the `tinyassets/__main__.py:48,63`
  re-exports, the plugin-runtime mirror, and the env gate that armed it. Update
  `tests/test_integration.py:2213` to assert the capability is absent. Rebuild
  the plugin (`python packaging/claude-plugin/build_plugin.py`). State tunnel-
  token custody as the Layer C invariant it is — code cannot enforce it.
- [ ] 4. Record the expected droplet id into the release state
  `deploy-prod.yml` already writes, then implement
  `resolve_platform_runtime_provenance()` — fail-closed, dedicated internal
  metadata client (literal address, no redirects, sub-second timeout, no user
  input, not reachable as a user capability, SSRF link-local classification
  unchanged), recorded-instance match, refusal ledger. Resolver is **injected**
  in tests, never satisfied by an environment variable.
- [ ] 5. Land the resolver in record-only mode; confirm on the droplet that it
  resolves CLOUD and the recorded id matches. Do not flip a resolver that cannot
  resolve CLOUD in production. Report this stage as observation, not enforcement.
- [ ] 6. Flip claim admission into the claim CAS transaction
  (`_transaction_allows_assigned_consumer` / `authority_claim`), keeping
  `_consumer_skip_reason` as the diagnostic.
- [ ] 7. Flip runtime registration (resolved provenance, instance id + boot epoch
  bound, re-validated on read) and the origin-ingress backstop refusal.
- [ ] 8. Flip startup, foreground and served execution (boot assertion, no
  degraded mode, the three `executor_class="cloud"` literals), and the recovery
  paths: watchdog, release-reconcile and stale-runtime retirement leave work
  pending when no admitted successor exists.
- [ ] 9. Write the test matrix from `design.md`. Negatives 1–7 **must be run
  against the unfixed tree and fail there**; positives 8–9 assert preserved
  behaviour and may pass at baseline. Add focused unit tests for the preflight
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
