---
title: SPLITROOT "First 60 Seconds" slice — Verdant root-vault, table-ordered Thornbound squad, fog-of-war loop
type: plan
author: Rook (Claude Code lead, Cowork session)
author_org: anthropic
author_provider: cowork
authored_at_utc: 2026-05-23T18:30:00Z
status: planning
source_role: synthesis
authority_class: secondary-analysis
scope: goal
goal_id: 9171b100de33
project: archon-rts-fps-fantasy-hybrid
mutability: stable
recency_policy: stable
target_gate_rung: 1 (Local playable prototype)
related_canonical:
  - pages/plans/archon-fantasy-rts-fps-v0-prototype-spec-2026-05-20.md
  - pages/plans/archon-fantasy-rts-fps-v0-unit-sheet-2026-05-20.md
  - pages/plans/archon-fantasy-rts-fps-v0-map-blockout-2026-05-20.md
  - pages/plans/archon-fantasy-rts-fps-v0-technical-plan-2026-05-20.md
  - pages/notes/splitroot-fog-of-war-decision-2026-05-23.md
  - pages/notes/pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23.md
sources:
  - local repo survey 2026-05-23 (Source/ArchonFactoryCanary/, Proof/, FactoryContracts/)
  - local Cowork session 2026-05-23 (Rook lead, Jonathan owner) — direction set
tags: [splitroot, plan, slice, rung-1, verdant-choir, root-vault, map-table, team-vision, ai-squad, blockout]
---

# SPLITROOT "First 60 Seconds" slice

[[index]] [[archon-fantasy-rts-fps-v0-prototype-spec-2026-05-20]] [[splitroot-fog-of-war-decision-2026-05-23]] [[pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23]]

Goal: `9171b100de33`. Target gate rung: **1 (Local playable prototype)**.
This slice's success = first honest claim against the gate ladder.

## The goosebumps moment this slice has to land

A player loads the canary. They are a Verdant Choir Thornbound standing
at a small mossy outpost. A squad of four Thornbound stands at parade
rest nearby. Across the field, ~200m east, a half-collapsed great
splitroot tree rises out of a bramble field — the central resource
node. To the south, a fog-ghost: a Lenswright Compact outpost they
"scouted before the match," shown as a brass-oxblood silhouette frozen
at last-seen state.

The player hits **Tab**. The world goes top-down. Their outpost is
**lit**. The central splitroot tree is **fogged** (explored, no current
vision). The Lenswright ghost is **fogged with a building snapshot**.

They drag-box the four Thornbound. Four mine-colored selection arrows
pop up above the squad (WC3 Archon UX). They right-click the central
splitroot tree. The squad acknowledges audibly. A pulse marker pins
the destination. A faint pathfinding line traces through the fog.

They hit **Tab** to close. Back in FPS. The squad is jogging past them
— footfalls, choir hum, armor creak. HUD bottom-left:
**"Thornbound squad → Central Splitroot (by you, 4s ago)."**

The player wants to arrive first. They hold sprint and jump — bramble
thickens at their feet and **root-vaults** them forward and slightly
up. Camera dips on takeoff, kicks on land. Sprint again. Root-vault.
Sprint. Root-vault. They reach the central splitroot tree. **Fog lifts
around them — lit.** The Lenswright ghost to the south updates: the
outpost they remembered is gone (it was torn down, the new state is
revealed).

The Thornbound squad arrives behind them, takes overwatch positions,
calls out **"in position."**

That sequence — **Tab, order, Tab, root-vault, arrive, lit, squad
arrives, in position** — is the goosebumps. Landing this is rung 1.

## Why this slice is the right slice

- It exercises every load-bearing system in the v0 spec at the
  minimum non-toy fidelity: shared-control table input,
  AI-squad-as-RTS-output, FPS movement signature, team vision,
  fog ghosts for buildings, mode-switch ergonomics.
- It deliberately omits combat. A 60-second arc with no death gives
  us a tight proof loop and forces the *non-combat* feel to land
  first. If Tab → table → order → fight-alongside doesn't feel like
  *playing RTS* with no enemies around, adding enemies won't fix it.
- It targets a single faction (Verdant) and a single squad type
  (Thornbound). Every other faction, unit, hero, and faction power is
  deferred. This is consistent with the v0 spec's "explicit cuts"
  philosophy: cut hard, ship a small thing that's real.
- It earns rung 1 honestly. The current proof scripts verify that
  seams exist (map table actor, input bridge install, FPS pawn
  possession), but no script demonstrates that a player can issue
  an order and have a squad act on it. That gap is exactly what rung
  1 requires.

## Faction choice: Verdant Choir, not Kinwild

The May-23 design extensions catalogued movement verbs for all three
factions. The original instinct was Kinwild bound-leap (Tribes-coded,
familiar). But the v0 prototype spec
([[archon-fantasy-rts-fps-v0-prototype-spec-2026-05-20]] §"Hard locks")
locks first playable to **Verdant Choir vs Lenswright Compact**;
Kinwild Covenant is reserved.

Verdant root-vault is also better for first-canary tutorial flow:
hold-sprint-then-jump is a single continuous gesture a player
accidentally discovers, vs. Lenswright pressure-thrust's
sprint+crouch+jump chord which has to be taught explicitly. Verdant's
identity also gives the blockout level more scenic anchor (bramble,
splitroot saplings, mossy ruins, the central splitroot tree).

Lenswright shows up in this slice only as a **fog-ghost outpost** —
silhouette, frozen state. No live Lenswright actors at v0.

## Sub-slices (six)

Each sub-slice has its own proof so we can land them incrementally
and the build stays green.

### S1 — Team vision primitive (the load-bearing piece)

Per [[splitroot-fog-of-war-decision-2026-05-23]]. Per-team replicated
visibility grid, three states (black / fog / lit). Sight sources are
friendly units and friendly buildings, each with a radius. Building
ghosts in fog (snapshot at moment of vision loss; do not update until
re-sighted).

Native seam shape (matches existing repo conventions):
- `ArchonTeamVisibilityPolicyLibrary` — pure C++ logic, unit-tested.
  Given `{sources: [{pos, radius}], previousGrid, buildingSnapshots}`,
  return `{newGrid, updatedSnapshots, newlyLitCells}`.
- `ArchonTeamVisibilityStateComponent` — runtime: holds per-team
  grid, ticks sources, replicates relevant cells to the right team's
  clients only.
- `ArchonTeamVisibilityTypes` — UENUMs (`EVisibilityState`) + USTRUCTs
  (`FVisibilitySource`, `FBuildingSnapshot`, `FVisibilityGridCell`).

Proof: automation tests on the policy library (no Unreal world
required) covering: initial black state, lit on source-in-range,
fog on source-out-of-range with explored history, ghost-snapshot
freezes building state, multi-source aggregation, server filters
out enemy-unit replication to non-owning team.

### S2 — AI squad + order pipeline

One squad type (Verdant Thornbound), four-unit squad, single behavior
tree with two states: **Move-to-location** and **Overwatch-at-location**.
Server-authoritative order pipeline. Order payload carries
`{issuingPlayer, orderType, target, timestamp}` even though we're
single-player at v0 — sets up the multi-player HUD UX without needing
multiplayer.

Native seam shape:
- `ArchonAiSquadPolicyLibrary` — pure: next-behavior given
  `{squadState, currentOrder, perception}`.
- `ArchonAiSquadActor` — runtime: owns four child pawns +
  AIControllers + behavior tree using the policy. Replicates squad
  state.
- `ArchonAiSquadOrderTypes` — order USTRUCTs + UENUMs.
- `ArchonAiSquadOrderQueueComponent` (on `ArchonTeamRtsStateComponent`)
  — receives orders from any source (table widget, HUD ping, future
  voice command), routes to the right squad. Server-authoritative.

Proof: policy library tests (issue move → behavior switches; reach
destination → transitions to overwatch; new order received in-flight
→ last-order-wins). Plus a `unreal-map-smoke.ps1` extension that
spawns a squad, issues a move via the order queue API, ticks the
world, asserts squad arrived at destination ± tolerance within N
seconds.

### S3 — Map table widget (UMG)

A real RTS widget — not a menu. Tab opens it (existing
`ArchonPlayerInputBridgeComponent` already handles the mode-switch
plumbing). The widget:
- Renders the team vision state from S1: terrain shroud/fog/lit,
  building ghosts in fog, friendly units lit, enemy units only lit.
- Drag-box selection of friendly squads.
- Right-click issues a move order through the S2 order pipeline.
- WC3-style colored selection arrows above selected units (mine-colored
  even in single-player so the per-player UX is built-in).
- Pulse marker at order destination, fade after ~2s.
- Faint pathfinding line from squad to destination (replicated from
  the squad's AIController).
- Esc/Tab closes back to FPS pawn.

Native seam shape:
- `UArchonMapTableWidget` — UUserWidget subclass in C++ owning the
  selection, order, and render logic. UMG layout authored as a
  Blueprint asset that derives from the C++ class (per skill
  guidance: native contract first, BP for presentation).
- `ArchonMapTableSelectionPolicyLibrary` — pure: drag-box
  intersection logic, selection priority rules (e.g., squads over
  individual units), unit-tested.

Proof: policy library tests for selection + box-intersection +
multi-player selection arrows. Manual proof (screenshot) for the
widget rendering. Smoke script asserts the widget can be opened,
exercises one drag-box-select-and-order, asserts the order arrives
at the squad.

### S4 — Verdant root-vault movement signature

Extend `ArchonCanaryFpsCharacter` with a faction-aware locomotion
component. v0 has one faction (Verdant) so the only movement signature
is root-vault.

Mechanic per [[pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23]]:
hold sprint, press jump → bramble thickens under foot, fling forward
+ slightly up. No resource cost; ~3s cooldown. Cooldown shown on HUD
as a small bramble icon (placeholder art OK).

Native seam shape:
- `ArchonFactionMovementPolicyLibrary` — pure: given
  `{faction, inputState, cooldownState}`, return
  `{shouldLaunch, launchImpulse, newCooldownState}`.
- `ArchonFactionMovementComponent` on the FPS character — calls the
  policy each tick, applies impulse via Unreal's `CharacterMovement`.
- `ArchonFactionMovementTypes` — `EFactionMovementVerb`,
  `FFactionMovementCooldown`.

Proof: policy library tests covering cooldown enforcement, impulse
direction, the hold-sprint+jump gesture detection, the no-input case.
Manual proof: video of player root-vaulting across the blockout.

### S5 — Splitroot Valley blockout (v0)

A small flat field, ~300m × 200m. One mossy Verdant outpost at the
west spawn (player start + AI squad start), one great splitroot tree
at center (resource node — geometry only at this slice, no capture
logic yet), one ghost-keep silhouette to the south-east (Lenswright,
shown only via the S1 fog-ghost system as a frozen brass-oxblood
silhouette mesh with no AI). Geometry should invite root-vault paths:
cover stones, low walls, terrain ramps at gestural distances (12-18m
hops fit root-vault range).

Native/asset shape:
- `Content/Maps/SplitrootValley_V0.umap`
- Placeholder meshes from Unreal Starter Content / Quixel free assets
  / authored greybox.
- Lighting: low sun, baked. No dynamic time-of-day at v0.
- One `BP_VerdantOutpost`, one `BP_SplitrootTree_Central`, one
  `BP_LenswrightOutpost_Ghost`.

Proof: smoke script verifies map loads, expected actors spawn,
expected player start, expected AI squad start, expected ghost actor
exists with `bIsGhost=true`.

### S6 — Goosebumps integration test

Extend `Proof/unreal-map-smoke.ps1` (or add a sibling
`Proof/first-60-seconds-smoke.ps1`) that runs the full arc headlessly:

1. Load `SplitrootValley_V0` in PIE/headless.
2. Assert: player pawn spawned, Thornbound squad spawned at parade
   rest, ghost-keep spawned.
3. Programmatically open the map table widget.
4. Programmatically drag-box select the squad.
5. Programmatically right-click on the central splitroot tree.
6. Tick world ~3s — assert order received by squad, behavior
   transitioned to Move-to-location.
7. Close table widget — assert FPS pawn re-possessed.
8. Programmatically apply sprint+jump inputs at ~2s intervals — assert
   root-vault impulse fires, cooldown enforced between launches.
9. Tick world until pawn reaches central splitroot tree (timeout
   ~30s) — assert lit cells around pawn position, ghost-keep snapshot
   updated if visibility extends that far.
10. Assert squad arrives at destination within N seconds — squad
    transitions to Overwatch behavior.

Outputs: smoke log with timestamped assertions, optional video
capture for manual review of feel.

Passing this smoke = rung 1 claim is earnable. (Feel verification
still requires manual playtest with video — Rook's hill: proof
ladder is sacred, automated proof gates structural correctness, not
feel.)

## Existing local code that this slice extends

Inventory from `Source/ArchonFactoryCanary/` (2026-05-23):

| Existing | Slice uses it for |
|---|---|
| `ArchonCanaryFpsCharacter` | S4 extends with `ArchonFactionMovementComponent` |
| `ArchonCanaryWorldSubsystem` | S1 hosts per-team `ArchonTeamVisibilityStateComponent` registry |
| `ArchonFpsInputProfile` | S4 adds root-vault gesture (sprint-held + jump) detection |
| `ArchonMapTableActor` | S3 wires Tab open → widget show |
| `ArchonMapTableInteractorComponent` | S3 reuses interactor for table open/close |
| `ArchonMapTablePolicyLibrary` | S3 extends with selection + order routing decisions |
| `ArchonPlayerInputBridgeComponent` | S3 reuses for FPS ↔ table mode switch |
| `ArchonSessionPolicyLibrary` | unchanged at v0 (offline = full free, already correct) |
| `ArchonTeamRtsPolicyLibrary` | S2 extends with order-routing + last-order-wins logic |
| `ArchonTeamRtsStateComponent` | S2 hosts `ArchonAiSquadOrderQueueComponent` as child |

New native modules to add: `ArchonTeamVisibility*`, `ArchonAiSquad*`,
`ArchonFactionMovement*`, `ArchonMapTableWidget`. New maps:
`SplitrootValley_V0.umap`. New tests: matching `Tests/` for each new
policy library.

## Hard cuts from this slice

- Combat (no shooting, no melee resolution, no death, no respawn).
- All non-Verdant factions as live actors. Lenswright appears only as
  S1 fog-ghost.
- Heroes (`Briar Saint`, `Master Artificer` — deferred).
- Production / Supply economy.
- Resource capture mechanics (central splitroot is geometry, not
  capturable yet).
- Faction powers (Root Wall, Pressure Gate — deferred).
- Multiplayer / network. Single-player canary. Order payload tracks
  `issuingPlayer` so future multiplayer is a small change, not a
  refactor.
- Respawn screen and "command while you wait" pattern (deferred to
  the second slice — that one requires death + body picker).
- Dynamic time-of-day, weather, audio dialog beyond placeholder
  acknowledgments, faction-coherent VFX beyond placeholder.

## Repository projection note

This local projection was created from `wiki action=read` on 2026-05-24.
The live read response was truncated by the wiki API at 15000 of 17412
characters. The local copy is trimmed to the last complete section before
that cutoff; the canonical live page should be treated as authoritative for
the omitted tail.

Source read proof:
- path: `pages/plans/splitroot-first-60-seconds-slice-2026-05-23.md`
- updated: `2026-05-24T05:36:37.830260Z`
- sha256: `7053430084ab65224d5a5b56423d07bb4344f1763ffc0e318b47bbb7cc9d5a9c`
