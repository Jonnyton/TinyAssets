## 0. Evidence And Contract

- [x] 0.1 Record the production-reproduced container-name collision, safe
  recovery, bounded handoff design, and executable delta requirements.

## 1. Test-Driven Repair

- [x] 1.1 Add failing tests for exact finalized-recovery handoff, ordinary
  canonical predecessor preservation, and foreign/partial/running refusal.
- [x] 1.2 Carry exact recovery provenance through preflight and retire only the
  recorded stopped recovery generation during target preparation.
- [x] 1.3 Add and pass interruption/replay tests proving removal intent is
  durable, exact-empty replay is idempotent, and partial substitution fails.
- [x] 1.4 Add a production-shaped failing test for a stopped strict-subset
  canonical target left by failed health convergence, plus foreign/running/
  restart-enabled/same-name refusal.
- [x] 1.5 Write-ahead and replay removal of only the exact proved partial target
  IDs, without `-v`, before unsafe recovery starts.
- [x] 1.6 Bind fixed-name sidecars by exact ID, Compose project/service labels,
  non-writer mounts, and `restart=no`; replay exact removal, recreate them in
  unsafe recovery, and re-fence a partial recovery-sidecar start.
- [x] 1.7 Retry one transient partial recovery-sidecar Compose start within the
  same recovery invocation only after durable exact-ID capture and removal;
  bound the retry and re-fence a repeated failure.
- [x] 1.8 Treat zero-exit incomplete inventory as a partial start, and make the
  writer refence independent of post-capture sidecar name/identity drift while
  stopping a still-present captured sidecar only by exact ID; record but do not
  let a sidecar stop failure preempt the volume-writer fence.
- [x] 1.9 Reduce a restored sidecar ownership refusal to a fixed predicate
  class plus fixed name, with raw IDs, labels, mounts, and host values excluded.
- [x] 1.10 Reduce an invalid restored-sidecar Compose project to a fixed
  non-secret category (`current-canonical`, `legacy-workflow`, `legacy-deploy`,
  `recorded-recovery`, `unrecorded-recovery`, `missing`, or `other`) without
  publishing the observed label.

## 2. Verification And Release

- [x] 2.1 Pass the focused fence suite, Ruff, strict OpenSpec validation, and
  independent exact-head fail-closed/security review.
- [x] 2.1a Close the rejected failed-candidate diagnostic findings and obtain
  independent exact-head re-review: actual public source-file paths only, no
  traceback function/line values, exact container image/revision binding,
  deploy/intervening-failure and cancellation coverage, mismatch suppression,
  hard capture deadlines, pinned upload, and publication gated on explicit
  restored-or-safely-fenced cleanup plus terminal-receipt proof.
- [x] 2.1b Replace literal `\t` Docker-template framing with a fixed separator;
  regression-lock all seven boundaries through the real candidate-state
  validator and obtain independent exact-head approval.
- [x] 2.1c Classify the identity-bound candidate's Docker pre-start error without
  publishing raw daemon or host text; reproduce and independently review the
  exact capture contract before another controlled deploy.
- [x] 2.1d Diagnose the preserved systemd/Compose failure window through a
  read-only bounded remote classifier; publish fixed signals only, independently
  review the workflow, then run it without another production mutation.
- [x] 2.1e Reduce a classified name conflict to only matching allowlisted
  canonical container names, independently review the additive fixed schema,
  and rerun the same preserved window without production mutation.
- [x] 2.1f Hand the two proved recovery sidecar names to canonical Compose with
  write-ahead exact-ID ownership, interruption replay, and failure-path route
  restoration; independently review before controlled production mutation.
- [x] 2.1g Independently review the fixed project-category diagnostic and run
  it only through the normal preflight before choosing a provenance migration.
- [x] 2.1h Admit only the audited finite set of recovery project identities
  whose public workflow revisions predate writer-only recovery; retain exact
  ID/service/non-writer capture and refuse every other recovery-shaped project.
- [x] 2.1i Independently review the finite migration authority and rerun the
  immutable image through only the normal deployment path.
- [x] 2.1j Normalize a preflight `activating` daemon state to its healthy
  terminal `active` restore expectation, while retaining exact enabled-state
  comparison and refusing inactive, failed, or otherwise drifted units.
- [x] 2.1k Make cleanup-triggered refencing publish a non-contradictory
  terminal receipt, with focused tests for forward-success/cleanup-failure.
- [x] 2.1l Independently review the exact terminal-state repair before another
  production mutation.
- [ ] 2.2 Land the repair, deploy one immutable image through the normal fence,
  and record exact-five canonical fleet plus public MCP canary evidence.
- [ ] 2.3 Resume the OAuth diagnostic deployment only after the repaired normal
  deploy completes from a finalized recovery generation.
- [ ] 2.4 Sync the delta into `daemon-runtime-and-dispatch`, archive this
  change, and retire its STATUS row after live acceptance evidence is durable.
