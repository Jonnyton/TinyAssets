---
title: Factory Branch Remix Proof - STELLAR FRONT
type: concept
status: proposed
created: 2026-05-24
source_issue: 1049
goal: 9171b100de33
tags: [factory-branch, remixability, splitroot, stellar-front, substrate]
---

# Factory Branch Remix Proof - STELLAR FRONT

[[index]] [[splitroot-second-60-seconds-combat-slice-2026-05-24]] [[splitroot-hero-plan-briar-saint-master-artificer-2026-05-24]] [[splitroot-multiplayer-slice-plan-2026-05-24]]

## Purpose

This page is a falsifiability test for the factory-branch thesis: the factory
branch is the product only if it can spawn more than one product-shaped canary.
SPLITROOT proves that the substrate can ship a game. It does not, by itself,
prove that the substrate is remixable.

The second imagined canary is **STELLAR FRONT**, a sci-fi corporate-war
Archon RTS/FPS hybrid. The test is intentionally concrete: walk every
load-bearing SPLITROOT primitive and classify whether STELLAR FRONT can reuse
it unchanged, reuse it by swapping data, or exposes a substrate failure.

If a load-bearing primitive fails, the bug belongs in the factory substrate,
not in SPLITROOT-specific product code.

## STELLAR FRONT Seed

**Genre:** sci-fi Archon RTS/FPS hybrid. Three corporate factions contest a
moon mining frontier. It keeps the same shared-control table heart, first-person
combat layer, proof ladder, and gate-rung discipline as SPLITROOT.

**Factions:**

- **Aurelian Combine:** corporate-yellow precision faction; jetpack burst;
  plasma carbine and ion-shock pistol.
- **Black-Star Syndicate:** deep-purple smuggler-mercenary faction; grav-slide;
  railgun and shotgun.
- **Hollow Order:** cyan-cold ascetic techmystic faction; phase-step;
  psionic blade-pistol and suppression rifle.

**Map:** Khar-12 Mining Prospect. Same three-base triangle as Splitroot Valley
v1: Aurelian east, Black-Star west, Hollow Order north, central ore vein at
origin, and side-resource sites on inter-faction seams.

**Heroes:** one per faction. Same locked-stats schema: 350 HP, 1.15x speed,
1.3x weapon multiplier, one 12s ability, and one 60s ability. The tactical
identities differ; the horizontal-only paid discipline does not.

## Primitive Audit

| Category | Reuse | Swap data | Extend substrate | Fail |
|---|---:|---:|---:|---:|
| Movement | 2 | 1 | 1 | 0 |
| Combat | 4 | 2 | 0 | 0 |
| AI | 2 | 1 | 0 | 0 |
| Map-table / shared control | 6 | 0 | 0 | 0 |
| Visibility / fog of war | 4 | 0 | 0 | 0 |
| Death / respawn / command while waiting | 5 | 0 | 0 | 0 |
| Hero | 4 | 0 | 0 | 0 |
| Faction | 0 | 0 | 4 | 0 |
| Smoke / proof | 3 | 0 | 0 | 0 |
| Monetization | 3 | 0 | 0 | 0 |
| **Total** | **33** | **4** | **5** | **0** |

The important result is zero fails. STELLAR FRONT is plausible as a second
factory canary because the exercise finds extension points, not genre-locked
dead ends.

## Findings By Substrate

### Movement

`UArchonFactionMovementPolicyLibrary`, `UArchonFactionMovementComponent`, and
`FArchonFactionMovementTuning` mostly carry over. Jetpack burst and grav-slide
fit the existing impulse-shaped movement substrate with different tuning.

The phase-step exposes a real but narrow substrate extension: teleport is not
cleanly represented by a launch impulse. The substrate should support a
teleport movement verb, for example by adding an
`EArchonFactionMovementVerb::Teleport` result and a tuning flag that routes the
runtime component through `SetActorLocation` instead of `LaunchCharacter`.

### Combat

The combat substrate is fantasy-agnostic. `UArchonCombatPolicyLibrary`,
`UArchonCombatHealthComponent`, `UArchonRangedWeaponComponent`, projectile
behavior, damage tags, and weapon class tags all work for plasma, railgun,
shotgun, ion-shock, and psionic profiles as data or subclass swaps.

No factory-level combat change is required by this canary.

### AI

`UArchonAiCombatPolicyLibrary` and `UArchonAiCombatBehaviorComponent` reuse the
same target-selection and role-behavior predicates. Sci-fi roles such as
shielded defender or long-range sniper are enum/data extensions, not a new AI
substrate.

### Map Table And Shared Control

The map-table layer is the strongest proof point. Drag-box selection, server
order ingestion, UMG selection UI, shared-control conflict resolution, per-slot
selection colors, and `FArchonRtsCommandIntent` all survive the genre swap.

This is the Archon-pattern engine rather than SPLITROOT-only product code.

### Visibility

Fog-of-war, lit/fog/black policy, per-team visibility grids, replication
predicates, and last-seen building snapshots carry over unchanged. A mining
station frozen in fog is the same system behavior as a SPLITROOT building
snapshot frozen in fog.

### Death And Respawn

Respawn timer policy, spawn-point selection, respawn state replication,
observer pawn behavior, life-state tags, and the permission to issue map-table
commands while dead are all genre-agnostic.

The command-while-waiting predicate is an Archon heartbeat: death interrupts
first-person control without removing the player from shared strategic play.

### Hero

The hero substrate carries over as a locked-stat and presentation surface.
STELLAR FRONT can use the same server-validated stat schema and swap
mesh/material/audio/VFX presentation data. The paid-content rule remains
horizontal and genre-agnostic.

### Faction

Faction identity is the highest-friction remix point. A C++ enum works for one
game, but a factory substrate wants runtime faction IDs and JSON-keyed lookup
tables.

The strongest follow-up action from this exercise is to make faction identity
configuration-driven:

- faction ID as a runtime `FName` or equivalent stable key;
- `FactoryContracts/factions.json` as the faction registry;
- palette triplets configured from the faction registry;
- faction audio and presentation asset references configured from the registry;
- movement verb and default weapon profile lookups keyed by faction ID.

That change is moderate, but it removes the biggest barrier to shipping the
same binary as multiple game canaries with different seed packets.

### Smoke, Proof, And Gates

The proof-runner pattern, PowerShell smoke scripts, and gate-rung claim
semantics are reusable. STELLAR FRONT would write its own canary subsystem and
smoke scripts following the SPLITROOT proof convention, then bind claims to its
own goal and branch.

### Monetization

Entitlement policy JSON, session-route JSON, and the horizontal-only hero-pack
discipline all carry over with namespace changes. Nothing in the monetization
substrate is fantasy-specific.

## Scoped Substrate Follow-Ups

The canary identifies five extension surfaces:

1. Add teleport as a first-class movement verb in the faction movement
   substrate.
2. Replace compile-time faction enum dependence with runtime faction IDs.
3. Load faction palette data from `FactoryContracts/factions.json`.
4. Load faction audio/presentation references from the same registry.
5. Key movement verb and default weapon profile lookup by runtime faction ID.

These are substrate improvements because they increase remixability for future
canaries. They should not be implemented as STELLAR FRONT-specific product
branches.

## Scoping Verdict

STELLAR FRONT passes the thought experiment: the SPLITROOT substrate appears
remixable, with no load-bearing primitive failures. The exercise does not prove
the factory branch by itself; it narrows the remaining proof obligation to
small runtime-configurability work plus a real second canary smoke.

The project-design change for now is this brain concept page. Runtime work
should be filed separately with exact files, tests, and an opposite-family
checker before touching core substrate code.
