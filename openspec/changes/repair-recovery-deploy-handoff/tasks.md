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

## 2. Verification And Release

- [x] 2.1 Pass the focused fence suite, Ruff, strict OpenSpec validation, and
  independent exact-head fail-closed/security review.
- [ ] 2.2 Land the repair, deploy one immutable image through the normal fence,
  and record exact-five canonical fleet plus public MCP canary evidence.
- [ ] 2.3 Resume the OAuth diagnostic deployment only after the repaired normal
  deploy completes from a finalized recovery generation.
- [ ] 2.4 Sync the delta into `daemon-runtime-and-dispatch`, archive this
  change, and retire its STATUS row after live acceptance evidence is durable.
