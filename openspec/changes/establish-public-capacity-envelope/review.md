# Independent planning review — 2026-07-24

Environment: Windows, branch
`codex/establish-public-capacity-envelope`, based on `origin/main`
`412a876add4a1df914dea7017cd94f924e4aa30d`.

This is an independent same-provider review of a planning-only OpenSpec
change. It does not satisfy the required fresh Claude opposite-provider gate
and grants no implementation, baseline-run, production-access, activation, or
threshold authority.

## Initial verdict: ADAPT

The first review identified seven blocking issues:

1. A mutable current-topology fact was hard-coded into a timeless capability.
2. Host acceptance was required for every adaptation rather than only the
   decisions that actually belong to the host/product owner.
3. The future test files collided with an active broad `tests/` claim.
4. Tasks directed edits inside the separately owned PostgreSQL #1670 lane and
   blurred the line between harness plug-ins and domain-owned drivers.
5. Complete-system coverage omitted MCP/session, collaboration/discovery,
   ingress, export, storage growth, and moderation/abuse cells.
6. Deny-by-default safety blocked production mutation but not production
   target/network/store/read access.
7. An isolated clone could have been mislabeled as the public deployment's
   current capacity envelope.

## Adaptations

- The first baseline is now the dated `412a876a` fixture. Run-time probes must
  match it exactly or refuse the baseline and require a new dated fixture.
- Isolated-clone evidence retains its own topology/environment identity.
  Public-deployment cells stay `unknown` without matching capacity-relevant
  deployment fingerprints.
- Normal factual/spec corrections close through accepted re-review. Named
  host/product-owner decisions remain required for PLAN/product boundaries,
  budgets, production access/effects, first-write/activation, and numerical
  public-launch SLOs.
- Implementation waits for release or narrowing of the broad `tests/` claim.
- #1670 and domain owners publish their own adapters/drivers under separate
  claims; this lane owns only shared contracts, orchestration, validation, and
  conservative envelope projection.
- The catalog now represents every complete-system surface named by the
  research. Missing owner suites remain explicit `unknown` cells.
- Safety now refuses production endpoint, network, store, and read access by
  default, in addition to writes, effects, providers, markets, payments, and
  privileged resources.

## Final verification and verdict

The final independent review returned `APPROVE`:

- `openspec validate establish-public-capacity-envelope --strict`: valid.
- `openspec validate --all --strict`: 42/42 passed.
- `git diff --check`: passed.
- All 36 implementation tasks remain unchecked.
- No runtime, test, workflow, deployment, production, or PLAN files are
  changed.

The required next gate remains a fresh Claude source/deployment/ownership
review. Any `ADAPT` findings must be incorporated and re-reviewed before an
implementation claim or baseline run begins.

## Current-main refresh — 2026-07-24

Environment: Windows, branch `codex/establish-public-capacity-envelope`,
rebased onto `origin/main`
`0a82dbecdf11eb6f4a8a41060e5f26faf5d06662`.

This refresh appends to, and does not rewrite, the historical review above.
The dated `412a876a` single-origin fixture remains intentional: a run-time
source, deployment, or topology mismatch must refuse that fixture and require
a separately reviewed dated fixture. Rebasing the planning branch does not
silently relabel current main as the topology that `412a876a` observed.

Current main advances the operator-request owner through three later stages:

- #1693 reauthorizes committed replay against current ordinary scope and the
  exact current ACL before lookup.
- #1694 commits canonical request admission, its admission receipt, public
  result/event, and a pending protocol-v2 task transactionally.
- #1696 adds the bounded internal epoch-2 queue lifecycle, claim lease, and
  pure cross-epoch selection.

These are stage-typed operator-request facts, not generic capacity evidence.
The #1694 admission receipt is not a provider-attempt receipt, and the #1696
internal queue lease is not an external B2/provider/market execution lease.
None of the three authorizes credentials, compute, provider access, market
purchase, spending, settlement, or external execution. A harness plug-in may
consume the owning capability's accepted stage assertions, but passing
admission, replay, or queue cases must leave unsupported public execution and
provider capacity `unknown`.

### Refresh verdict: ADAPT

Before accepted re-review, the planning contract must:

1. consume operator-request evidence through stage-typed owner plug-ins without
   converting admission or internal scheduling success into execution capacity;
2. replace the stale assertion that an active broad `tests/` owner blocks all
   work with a fresh exact-Files `claim_check` immediately before a separately
   claimed implementation lane; and
3. preserve the dated-fixture mismatch refusal and the distinction between
   internal queue claims and external execution authority.

The opposite-provider source/deployment/ownership review and accepted re-review
remain pending. This ADAPT verdict grants no implementation, baseline run,
production access, activation, threshold, provider, market, or execution
authority.

### Same-provider re-review after current-main adaptations: APPROVE

The combined planning diff now:

- keys envelope cells by lifecycle stage, actor/scope boundary, and
  supply-provenance class so admission and internal scheduling evidence cannot
  promote B2, provider, market, execution, delivery, or settlement capacity;
- separates path-level evidence from complete-platform readiness and keeps
  every required failed or unknown Forever Rule surface non-green;
- pins the owner plug-in ABI, independent observer/oracle, load-validity and
  concurrent-user metrics, isolation matrix, BYOC provenance, and
  price-conditioned market supply evidence; and
- replaces the stale broad-`tests/` blocker with an exact prospective-Files
  collision check immediately before a separately claimed implementation.

Fresh evidence on 2026-07-24:

- targeted strict OpenSpec validation: pass;
- full strict OpenSpec validation: 42/42;
- `git diff --check` and conflict-marker scan: pass;
- exact eight-file planning/coordination scope, with no runtime, tests,
  workflows, deployment, canonical specs, or PLAN changes;
- `STATUS.md`: 56 lines with no landed operator rows; and
- tasks: 47 unchecked, zero checked or partial.

This same-provider `APPROVE` does not satisfy task 1.1. Fresh Claude
opposite-provider review and accepted re-review remain mandatory before
implementation or baseline execution.
