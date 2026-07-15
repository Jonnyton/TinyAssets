# Demand Side: Standing Goals & Goal Bounties

## Purpose

Define TinyAssets' native demand engine. Chatbots own conversational demand
("answer me now"); TinyAssets owns standing-goal demand — goals that run while
the user is absent (monitor, maintain, accumulate, curate, optimize) on the
proactivity heartbeat — plus goal bounties, the primitive that makes demand
transferable. This capability composes existing primitives only (design law:
primitives + commons, never features) and addresses the cold-start/retention risk.

Historical source of record (untouched): `docs/exec-plans/active/2026-07-09-demand-side-design.md`.

## Requirements

### Requirement: The standing goal is the native demand unit

Standing goals SHALL be the native demand unit — decoupled from attention (a
universe with three standing goals consumes compute at 3 a.m.), the forecastable-
demand moat (declared branches are tomorrow's demand visible today, feeding Track
E §5), and the retention answer (the user returns because something LANDED while
they were gone).

#### Scenario: demand scales with goals held, not sessions opened
- **WHEN** a universe holds multiple standing goals
- **THEN** it consumes compute while the user is absent
- **AND** that demand fills the batch market independent of session activity

### Requirement: Product rules (binding)

The system SHALL enforce these three binding product rules verbatim:

1. Every commons archetype ships with 2–3 standing goals pre-attached, chosen so the FIRST produces a felt, gate-claimed win inside week one ("your first brief arrives Sunday" — never "explore the platform").
2. Onboarding's terminal state is a standing goal running, not an empty universe.
3. Leading demand metric: **standing goals per active universe** (leads the north-star weekly-gate-claims metric).

#### Scenario: onboarding terminates in a running standing goal
- **WHEN** a user finishes onboarding
- **THEN** the terminal state is a standing goal running, not an empty universe
- **AND** its first gate-claimed win is designed to land inside week one

### Requirement: Goal bounties make demand transferable

A goal bounty SHALL be a goal with escrowed money that ANYONE may claim by
passing its gates, so money summons other people's universes and compute. It SHALL
create demand without owning compute, speculative fulfillment of idle capacity,
and a funding mechanism for the commons' own gaps.

#### Scenario: money summons another universe's work
- **WHEN** a poster escrows money on a goal with machine-checkable gates
- **THEN** anyone may claim the bounty by passing its gates
- **AND** the poster converts money directly into platform work without owning compute

### Requirement: Composition rules (pinned — Opus must not improvise these)

The system SHALL enforce these six bounty composition rules verbatim:

1. **Machine-checkable gates only.** Bounties may only attach to gates with automated verification. No human-acceptance step exists → no poster-side griefing surface. If a goal's gates aren't machine-checkable, it cannot carry a bounty (fail closed).
2. **Escrow at post** via `escrow_lock_entries` into `escrow:bounty:<id>`. Gate-ladder bounties escrow **per-tranche**, tranche weights apportioned exactly via `apportion_exact` over declared gate weights.
3. **First verified claim wins the tranche.** Ordering: (gate-verification timestamp, claim id) — deterministic ties. Settlement per tranche = existing fee split (99/1, `FEE_PPM`), ledger postings via the standard adapters, `assert_drained` on the tranche escrow.
4. **Expiry:** unclaimed tranches past the bounty's declared deadline refund to the poster in full (no fee — no settlement occurred).
5. **Disputes:** standard dispute window on claim evidence; reuses existing machinery unchanged.
6. **Provenance:** a bounty-claimed artifact enters the commons under the claimant's authorship with standard attribution; the bounty poster receives usage rights per the bounty's declared license terms (composed fail-closed at post time, Track G machinery).

#### Scenario: a non-machine-checkable goal cannot carry a bounty
- **WHEN** a goal's gates require a human-acceptance step
- **THEN** it cannot carry a bounty (fail closed)
- **AND** no poster-side griefing surface exists

#### Scenario: first verified claim wins the tranche and drains the escrow
- **WHEN** multiple sellers race an open bounty tranche
- **THEN** the first verified claim (by gate-verification timestamp, claim id) wins
- **AND** the tranche settles 99/1 and `assert_drained` holds on the tranche escrow

### Requirement: Universe-to-universe services are deferred behind bounties

Minted workflows callable as paid service endpoints (universes hiring universes) SHALL be deferred behind bounties: bounties prove transferable demand with zero new trust surface; services add availability/SLA questions revisited after bounty volume exists.

#### Scenario: services wait for bounty volume
- **WHEN** universe-to-universe paid services are proposed
- **THEN** they remain deferred until bounty volume exists
- **AND** bounties carry transferable demand in the meantime with no new trust surface

## Open founder decisions

None currently open. This is a binding design note composing existing primitives;
its product rules and bounty composition rules are pinned. (The six exact launch
archetypes and their week-one-win standing goals are a seeding checklist for
founder selection during rehearsal-build week, not an open design decision.)
