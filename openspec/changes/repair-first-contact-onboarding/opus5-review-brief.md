# Claude Opus 5 opposite-provider review brief

Work read-only in `C:\Users\Jonathan\Projects\wf-first-contact-onboarding`.

Review the exact current working-tree artifacts:

- `openspec/changes/repair-first-contact-onboarding/proposal.md`
- `openspec/changes/repair-first-contact-onboarding/design.md`
- `openspec/changes/repair-first-contact-onboarding/tasks.md`
- `openspec/changes/repair-first-contact-onboarding/specs/**`
- `docs/ops/2026-07-25-first-contact-onboarding-gaps.md`
- current `STATUS.md`, relevant `PLAN.md` modules, and canonical specs
- current code seams in `tinyassets/universe_server.py` and `tinyassets/api/branches.py`
- active changes `universe-creation`, `universe-visibility`, and `retire-legacy-live-mcp-tools`

The first Opus 5 review in `opus5-review.md` returned ADAPT against the pre-hardening draft. Re-check every C1-C3, I1-I9, and M1-M3 against the current rebased head; do not assume the claimed fixes are sufficient.

Check:

- domain fit and minimal-primitives alignment;
- exact-seven invariant and first-contact usability;
- closed/versioned DTO consistency and unambiguous parameter ownership;
- verified authority, author/approval spoof resistance, visibility and non-enumeration;
- V1 commons-only alignment with PLAN and clean exclusion of private/fork/Goal/source-code shapes;
- protected-field safety across both create and existing patch modes;
- actor-scoped body-bound idempotency, rolling-key rotation, transaction, outbox, crash, and expiry claims;
- bounded catalog projection, authoritative publication verification, encrypted cursor, mutation, scan-window, and read-only semantics;
- visibility-safe composition across catalog/create and every exact branch alias/helper;
- minimal non-secret results/errors;
- concurrency/load proof;
- registered-guide and live-wiki correction safety;
- active-owner/file collisions and whether tasks can truthfully land;
- OpenSpec sync/archive hazards or requirements that conflict with current canonical specs.

Do not edit any file. Return a self-contained review beginning with exactly one of:

- `VERDICT: APPROVE`
- `VERDICT: ADAPT`
- `VERDICT: REJECT`

List Critical/Important findings with exact file/section references and concrete corrections. Approve only if this spec/review-only packet is safe to publish as a blocked draft. Runtime implementation, canonical sync/archive, deployment, and live wiki writes remain forbidden.
