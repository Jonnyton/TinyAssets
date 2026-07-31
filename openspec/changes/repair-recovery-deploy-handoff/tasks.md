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
- [ ] 2.1e Reduce a classified name conflict to only matching allowlisted
  canonical container names, independently review the additive fixed schema,
  and rerun the same preserved window without production mutation.
- [ ] 2.2 Land the repair, deploy one immutable image through the normal fence,
  and record exact-five canonical fleet plus public MCP canary evidence.
- [ ] 2.3 Resume the OAuth diagnostic deployment only after the repaired normal
  deploy completes from a finalized recovery generation.
- [ ] 2.4 Sync the delta into `daemon-runtime-and-dispatch`, archive this
  change, and retire its STATUS row after live acceptance evidence is durable.
