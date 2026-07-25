> **Partial release, 2026-07-25 (umbrella task 4.1).** Two requirements were
> **physically moved** out of this delta into `openspec/changes/demand-side-signals/`,
> the successor that now owns the non-monetary half: *Standing goals are durable
> demand independent of chat sessions* and *Onboarding terminates in a useful
> running goal* (the latter restated there as *Onboarding terminates in a running
> standing goal built from remixable commons archetypes*). Its leading-metric
> clause — standing goals per active universe, ahead of the weekly gate-claims
> north star — moved with it but now lives in that change's separate metrics
> requirement, where the visibility scoping it needs belongs. They were moved
> rather than copied so each requirement keeps exactly one active owner,
> matching the release pattern of
> umbrella tasks 1.1, 1.2, and 2.1. The three requirements below stay with the
> umbrella pending tasks 4.2 (bounties, escrow, claims, refunds) and 4.3 (the
> measured direct-service gate), so the `demand-side` capability has two active
> owners split disjointly **by requirement** — never two owners of one
> requirement.

## ADDED Requirements

### Requirement: Goal bounties transfer demand through exact escrowed claims
A goal owner SHALL be able to post a machine-verifiable goal bounty that any authenticated principal or universe satisfying the published eligibility rules can discover, claim, satisfy, and settle without an invitation-only list. This preserves the target's open “ANYONE may claim” market while explicitly refusing anonymous money movement. The bounty SHALL bind immutable goal/gate/version identity and SHALL not transfer control of the owner's universe or credentials.

#### Scenario: money summons another universe's work
- **WHEN** an eligible universe claims an open bounty and produces evidence satisfying its frozen gate
- **THEN** the verified claim settles under the bounty terms while ownership and credentials remain with their original principals

### Requirement: Bounty composition rules are enforced at the boundary
Bounty posting and settlement SHALL enforce all six pinned rules: machine-evaluable gates only with no human-acceptance surface; `escrow_lock_entries` into `escrow:bounty:<id>` at post with gate-ladder tranche weights apportioned exactly; first verified claim per tranche ordered by `(gate-verification timestamp, claim id)` under an atomic compare-and-swap; standard 99/1 settlement using `FEE_PPM`, standard ledger adapters, and `assert_drained`; full no-fee refund of unclaimed expired tranches; the standard evidence dispute window; and claimant authorship plus standard attribution while the poster receives usage rights under license terms composed fail-closed at post.

#### Scenario: a subjective-only goal cannot carry money
- **WHEN** a bounty lacks a machine-evaluable frozen gate
- **THEN** posting is rejected before escrow is locked

#### Scenario: one verified winner drains one tranche
- **WHEN** concurrent claims satisfy the same open tranche
- **THEN** exactly one claim wins by `(gate-verification timestamp, claim id)`, settles 99/1 through standard adapters, and leaves `assert_drained` true while later claims receive a closed result

### Requirement: Direct universe services wait for measured bounty demand
The platform SHALL keep direct paid universe-service products disabled until an explicit, executable launch gate observes sustained qualifying bounty volume and successful settlement quality. The gate's window, threshold, and evidence SHALL be versioned; a prose assertion or absence of services is insufficient.

#### Scenario: services remain dark below the volume gate
- **WHEN** measured qualifying bounty activity does not meet the versioned launch threshold
- **THEN** direct service listing and purchase actions remain unavailable while bounties continue to operate
