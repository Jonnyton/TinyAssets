---
title: SPLITROOT N1 multiplayer replication audit contract
type: plan
status: working-draft
source_issue: 1057
request_id: WIKI-DESIGN
wiki_source_path: pages/plans/splitroot-n1-multiplayer-replication-audit-contract-2026-05-24.md
wiki_source_updated: 2026-05-24
---

# N1 contract - multiplayer replication audit

[[index]] [[splitroot-multiplayer-slice-plan-2026-05-24]] [[splitroot-rung-1-local-playable-prototype-earned-2026-05-23]] [[splitroot-c5-command-while-you-wait-contract-2026-05-24]]

Goal: `9171b100de33`. Rung: **3**. **First multiplayer sub-slice.**

This page preserves the community-filed SPLITROOT N1 contract in the
Workflow brain namespace. The implementation target named by the contract is
an Unreal project (`Source/ArchonFactoryCanary/...`) that is not present in
this Workflow checkout. This repository-side handling is therefore
design-preservation only; code and test implementation must happen in the
Archon/Hex Unreal repository or in a worktree that contains that source tree.

## Goal

The multiplayer slice plan claims the rung-1 substrate is MP-ready because
all order payloads track `IssuingPlayerId` and the order pipeline is
state-machine-free. N1 proves that claim by auditing every replicated
component and adding tests that the replication invariants hold under a
client-server round trip.

This slice is structural rather than additive: most of the work is verifying
replication, adding tests, and making small `UPROPERTY` or relevancy
adjustments. New gameplay code should be minimal.

## Contract files

- `Source/ArchonFactoryCanary/Public/ArchonTeamRtsStateComponent.h`
- `Source/ArchonFactoryCanary/Public/ArchonTeamVisibilityStateComponent.h`
- `Source/ArchonFactoryCanary/Public/ArchonCombatHealthComponent.h`
- `Source/ArchonFactoryCanary/Public/ArchonRespawnStateComponent.h`
- `Source/ArchonFactoryCanary/Public/ArchonRangedWeaponComponent.h`
- `Source/ArchonFactoryCanary/Public/ArchonMapTableActor.h`
- `Source/ArchonFactoryCanary/Private/Tests/ArchonReplicationAuditTests.cpp`
- `Proof/local-proof-checks.ps1`

## Audit matrix

| Component | Current claim | Required N1 invariant |
|---|---|---|
| `UArchonTeamRtsStateComponent` | Team id, command sequence, accepted/rejected reasons, and last accepted intent replicate. | Per-team relevancy: players only receive their team's state and intent payloads; command sequence remains monotonic for observers. |
| `UArchonTeamVisibilityStateComponent` | Team id, visibility cells, friendly sources, and building snapshots exist in the visibility state. | Team fog/lit grids and snapshots are isolated by team; `FriendlySources` is server-only or empty on clients. |
| `UArchonCombatHealthComponent` | C1 contract says health, max health, armor, and death behavior replicate. | Damage is visible to all observers; health-change and death notifications reach clients through replication/notify flow. |
| `UArchonRespawnStateComponent` | C4 contract owns player/team id, life state, timer, and spawn points. | Respawn timer details are owner-only; team spawn availability can be team-wide. |
| `UArchonRangedWeaponComponent` | C2 contract owns ammo, fire state, stats, and fire notifications. | Ammo/fire state is observer-consistent; server fire produces multicast effects/projectile visibility for relevant observers. |
| `UArchonAiCombatBehaviorComponent` | AI behavior is server-driven and observed through replicated results. | Clients do not simulate AI; any HUD-visible target/stance fields are read-only replicated state. |
| `UArchonFactionMovementComponent` | Movement impulses rely on standard character movement replication. | Other clients see jump/impulse outcomes through character movement; local cooldown prediction remains local unless telemetry is explicitly added. |
| `AArchonMapTableActor` | Default actor relevancy. | Actor is always relevant so all clients can see strategic visibility regardless of pawn location. |
| `AArchonCanaryRtsSquadActor` | Team/squad ids, order state, command sequence, and destination replicate. | Enemy squads replicate only when visible under the team visibility predicate; paths are visible to observers who pass relevancy. |

## Named tests

The N1 proof expects fourteen named Unreal automation tests in
`ArchonReplicationAuditTests.cpp`:

1. `ArchonFactory.Replication.TeamRtsState_PerTeamRelevancy`
2. `ArchonFactory.Replication.TeamRtsState_CommandSequenceMonotonic`
3. `ArchonFactory.Replication.TeamVisibility_GridPerTeam`
4. `ArchonFactory.Replication.TeamVisibility_FriendlySourcesServerOnly`
5. `ArchonFactory.Replication.RespawnState_OwnerOnlyRelevancy`
6. `ArchonFactory.Replication.CombatHealth_DeathBroadcasts`
7. `ArchonFactory.Replication.RangedWeapon_FireMulticastReachesObservers`
8. `ArchonFactory.Replication.RangedWeapon_AmmoStateConsistent`
9. `ArchonFactory.Replication.MapTable_AlwaysRelevant`
10. `ArchonFactory.Replication.Squad_VisibilityGated`
11. `ArchonFactory.Replication.OrderFromPlayerA_VisibleToPlayerB`
12. `ArchonFactory.Replication.OrderFromPlayerB_AlsoVisibleToPlayerA`
13. `ArchonFactory.Replication.OrderFromDifferentTeamsAreIsolated`
14. `ArchonFactory.Replication.RuntimeSquadPath_VisibleToObservers`

Each test should set up a two-controller test world, manipulate server-side
state, tick/await replication, and assert the client-visible invariant. If
headless Unreal automation is too heavy for a unit-style test, the acceptable
fallback is a runtime smoke path using a `-SimulateMultiplayerWithBots` flag,
provided the same invariants are asserted.

## Proof integration

`Proof/local-proof-checks.ps1` should gain a
`ClaimsMultiplayerReplicationAudit` flag that maps to the fourteen tests above.
N1 does not require a new end-to-end smoke script; N8 owns the full
two-player integration smoke.

## Out of scope

- Per-player input bridge isolation tests; that is N2.
- Per-player map table selection sets; that is N3.
- Order pipeline conflict resolution under simultaneous orders; that is N4.
- Session route and listen-server hosting; that is N6.
- End-to-end two-player smoke; that is N8.

## Repository handling notes

- The Workflow checkout does not contain `Source/ArchonFactoryCanary` or
  `Proof/local-proof-checks.ps1`, so this issue cannot safely produce the
  requested Unreal patch here.
- `python scripts/check_primitive_exists.py sha 9171b100de33` reports that the
  goal id does not resolve as a commit in this checkout. Treat the value as an
  external SPLITROOT goal identifier unless the Archon repository proves
  otherwise.
- The smallest safe Workflow-side change is this plan page, which makes the
  contract discoverable to future brain/wiki sweeps without pretending the
  Unreal implementation was completed.

## Gate

N1 is done only when an opposite-family checker verifies:

1. The Unreal source tree contains the relevancy/property changes required by
   the audit matrix.
2. All fourteen named replication tests exist and pass.
3. The proof script exposes `ClaimsMultiplayerReplicationAudit` and fails if
   any named test fails.
4. No out-of-scope multiplayer slices are silently pulled into N1.
