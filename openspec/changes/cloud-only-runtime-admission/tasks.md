# Tasks — cloud-only runtime admission

No runtime code lands until this change is reviewed cross-family. Tasks 1–2
resolve the one fact that could change the design; the refusal flip (task 8) is
gated on task 7 attesting on the real droplet.

- [ ] 1. Probe once on the droplet, read-only, whether `169.254.169.254`
  metadata is reachable from inside the daemon container; record the answer in
  this change. If unreachable, stop and revise `design.md` § Evidence primitive
  before writing any resolver.
- [ ] 2. Resolve the Cloudflare account id and public tunnel id read-only from
  hosted CI using the existing `CLOUDFLARE_API_TOKEN`; if the token lacks scope,
  record the exact non-secret repo variable needed instead. No key printed.
- [ ] 3. Add the read-only custody verification workflow on `ubuntu-latest`:
  droplet identity, tunnel connector set ⊆ droplet addresses, public DNS target.
  Emits ids and booleans only; `::add-mask::` derived values; no `set -x`, no
  write scopes.
- [ ] 4. Record the expected droplet id into the deploy release state written by
  `deploy-prod.yml`, so the resolver has a deployment-recorded instance to match.
- [ ] 5. Implement `resolve_platform_runtime_provenance()` — fail-closed,
  dedicated internal metadata client (literal address, no redirects, sub-second
  timeout, no user input, not reachable as a user capability, SSRF link-local
  classification unchanged) plus the recorded-instance match and a refusal ledger.
- [ ] 6. Write the nine tests from `design.md` § Test matrix, and prove each one
  **red against the unfixed tree** before wiring any enforcement.
- [ ] 7. Land the resolver in record-only mode; confirm on the droplet that it
  attests and that the recorded instance matches. Do not proceed on a resolver
  that cannot attest in production.
- [ ] 8. Flip claim admission into the claim transaction
  (`_transaction_allows_assigned_consumer` / `authority_claim`), keeping
  `_consumer_skip_reason` as the diagnostic.
- [ ] 9. Flip runtime registration: write resolved provenance, bind instance id +
  boot epoch, re-validate on read.
- [ ] 10. Flip startup, foreground and served execution: boot assertion with no
  degraded mode; replace the three `executor_class="cloud"` literals; refuse
  origin ingress when unattested.
- [ ] 11. Flip recovery paths: watchdog, release-reconcile and stale-runtime
  retirement leave work pending when no attested successor exists.
- [ ] 12. Run the Linux oracle on the new tests, get the cross-family review
  verdict, then update `PLAN.md` / `AGENTS.md` references and sync this delta
  into `openspec/specs/cloud-only-runtime-admission/`.
