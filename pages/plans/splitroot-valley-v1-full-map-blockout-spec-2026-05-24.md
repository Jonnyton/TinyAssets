---
title: Splitroot Valley v1 full map blockout
type: plan
status: working-draft
source_issue: 1062
wiki_source_path: pages/plans/splitroot-valley-v1-full-map-blockout-spec-2026-05-24.md
wiki_source_updated: 2026-05-25T02:14:58Z
wiki_source_sha256: 4388a77f14ba87b3f4c219c7a8c3a2281e393b527a3d7a51985836a3c9e6b62b
---

# Splitroot Valley v1 — full map blockout

[[index]] [[archon-fantasy-rts-fps-v0-map-blockout-2026-05-20]] [[splitroot-s5-blockout-spec-2026-05-23]] [[splitroot-polish-art-direction-2026-05-24]] [[splitroot-kinwild-bound-leap-contract-2026-05-24]]

Goal: `9171b100de33`. Targets: rung-2 manual playtest viability + rung-3 prep.

## Why this is needed

The first-60-seconds blockout (S5) covered a small Verdant-vs-Lenswright
corner. The full-valley v0 spec (May-20) was conceptual: lanes, bases,
resource sites described in prose. Neither gives Hex a concrete map
to build, and neither shows Kinwild Covenant geometry.

**Manual playtest is not informative until the player can walk through
a real Splitroot Valley with all three faction footholds and three
movement-verb geometries.** This spec makes that concrete.

## Scale + coordinate system

World origin: the **Central Splitroot Tree cluster** sits at world (0, 0, 0).
The three faction homelands radiate out from center. Total valley
playable extent: **~120,000 × 80,000 uu** (1200m × 800m), matching the
upper end of the v0 conceptual scale.

| Direction | Faction homeland | Approximate base location |
|---|---|---|
| West (−X) | Verdant Choir | (−40000, 0, 0) |
| East (+X) | Lenswright Compact | (+40000, 0, 0) |
| North (+Y) | Kinwild Covenant | (0, +30000, 0) |

Three bases form a triangle around the center, NOT a mirrored
two-base layout. Three-team valley fits Archon's "factions matter"
identity better than 1v1 mirror — and it sets up future 3-team /
2v2 / 1v1v1 modes.

(NOTE: at v0 the canary plays Verdant vs Lenswright only; Kinwild
foothold is geometry + spawn point only, no live AI from that base
until Kinwild AI ships. Two-team default match: Verdant West vs
Lenswright East; Kinwild base is a third-party or neutral fortification
visible from both.)

## Actor inventory + world coordinates

### Verdant Choir homeland (west)

| Actor | Location (uu) | Notes |
|---|---|---|
| `BP_VerdantOutpost` (base spire) | (−40000, 0, 0) | Tall central spire, 1500×1500×4000 placeholder. |
| `BP_VerdantCommandHall` | (−39500, 0, 200) | Houses the map table. Player spawns 8s walk from here. |
| `BP_VerdantSpawnChamber` | (−40500, 0, 100) | Behind the command hall. Safe respawn area. |
| `BP_VerdantProductionYard` | (−40000, 1500, 0) | Future production structure spawns squads here. |
| `BP_VerdantCore` | (−41000, 0, 200) | Base core objective. Deeper than outer choke. |
| `BP_VerdantOuterChoke` | (−36000, 0, 100) | Main defensive entry. Cover geometry. |
| `PlayerStart` (team 0) | (−40000, −500, 250) | Verdant team default spawn point. |

### Lenswright Compact homeland (east)

| Actor | Location (uu) | Notes |
|---|---|---|
| `BP_LenswrightOutpost` (base) | (+40000, 0, 0) | Wide low building, 2000×1500×1500 placeholder. |
| `BP_LenswrightCommandHall` | (+39500, 0, 200) | Map table here. |
| `BP_LenswrightSpawnChamber` | (+40500, 0, 100) | |
| `BP_LenswrightProductionYard` | (+40000, −1500, 0) | |
| `BP_LenswrightCore` | (+41000, 0, 200) | |
| `BP_LenswrightOuterChoke` | (+36000, 0, 100) | Two corner turrets per art-direction silhouette spec. |
| `PlayerStart` (team 1) | (+40000, 500, 250) | Lenswright team default spawn. |

### Kinwild Covenant homeland (north)

| Actor | Location (uu) | Notes |
|---|---|---|
| `BP_KinwildEncampment` (base) | (0, +30000, 0) | Low tent cluster, central fire-pit. |
| `BP_KinwildCommandHall` | (0, +29500, 200) | |
| `BP_KinwildSpawnChamber` | (0, +30500, 100) | |
| `BP_KinwildProductionYard` | (−1500, +30000, 0) | |
| `BP_KinwildCore` | (0, +31000, 200) | |
| `BP_KinwildOuterChoke` | (0, +26000, 100) | |
| `PlayerStart` (team 2) | (500, +30000, 250) | Kinwild team default spawn (rung-3+ enables this). |

### Central Splitroot Tree cluster (map centerpiece)

| Actor | Location (uu) | Notes |
|---|---|---|
| `BP_SplitrootTreeCentral` (main trunk) | (0, 0, 0) | Tall central trunk, 1500×1500×6000 placeholder. The map landmark. Visible from every base outer choke. |
| `BP_SplitrootRoot_West` (above-ground root knee-wall) | (−4000, 0, 0) | Splits toward Verdant. ~3000×600×800 ramp. |
| `BP_SplitrootRoot_East` | (+4000, 0, 0) | Splits toward Lenswright. |
| `BP_SplitrootRoot_North` | (0, +4000, 0) | Splits toward Kinwild. |
| `BP_CentralResourceSite` (capture zone) | (0, 0, 100) | 1500uu capture radius centered on the trunk. The most contested point. |

### Side resource sites (one per inter-faction border)

| Actor | Location (uu) | Border | Notes |
|---|---|---|---|
| `BP_SideResource_VerdantLenswright` | (0, −15000, 0) | West-East seam (south of center) | Each side's faster-access resource. Capture zone 1200uu. |
| `BP_SideResource_VerdantKinwild` | (−20000, +15000, 0) | West-North seam | Capture zone 1200uu. |
| `BP_SideResource_LenswrightKinwild` | (+20000, +15000, 0) | East-North seam | Capture zone 1200uu. |

Each side-resource is on a SEAM between two factions — encourages
those two factions to contest it specifically.

## Cover-stone geometry per movement verb

The first-60-seconds slice spaced cover stones at root-vault distance
(1700uu / 17m). The full valley needs cover patterns inviting all
three movement verbs.

### Verdant root-vault corridor (west lane to center)

12 cover stones along the West-Central axis at 1700uu spacing:

| Stone # | Location (uu) |
|---|---|
| 1 | (−35500, 0, 0) |
| 2 | (−33800, 0, 0) |
| ... | (each 1700uu east of previous) |
| 12 | (−16800, 0, 0) |

Verdant players root-vault stone-to-stone toward center.

### Kinwild bound-leap corridor (north lane to center)

The bound-leap is flat-glide 18-22m. Cover spacing 2000uu (20m) with
slight elevation variation (±400uu Z) to invite bound-leap chains
that descend the gentle slope toward center.

| Hop # | Location (uu) | Z elevation |
|---|---|---|
| 1 | (0, +27000, +400) |
| 2 | (0, +25000, +200) |
| 3 | (0, +23000, 0) |
| ... | (each 2000uu south of previous) |
| 12 | (0, +5000, 0) |

Bound-leap players descend from Kinwild base toward center.

### Lenswright pressure-thrust corridor (east lane to center)

The pressure-thrust (Lenswright movement, contract not yet authored)
is sprint+crouch+jump → vertical pressure cylinder. Cover should be
TALLER and SPACED FARTHER APART (24-30m) because pressure-thrust
lifts high enough to clear obstacles, and the deployable Pressure
Gate doubles boost. Cover layout: 8 tall pillars + 4 low cover slabs.

| Element # | Location (uu) | Height (uu) |
|---|---|---|
| Tall pillar 1 | (+35000, 0, 0) | 1200 |
| Tall pillar 2 | (+32500, 0, 0) | 1200 |
| ... | (each ~2500uu west) | |
| Pressure-Gate pad 1 (visual hint geometry) | (+33500, 0, 0) | flat decal — future deployable spawns here |
| ... | | |

(Detailed pressure-thrust geometry deferred until Lenswright movement
contract lands; this is a sketch.)

### Underpass / low ravine (cross-lane connector, south)

Per v0 spec: optional low path. v1: confirmed include.

A trench cut through the valley at Y = −18000, running west-east. ~600uu
deep, ~1500uu wide. Connects all three side-resources via an
ambush-friendly low route. Two ramps per lane (West, Central, East)
give attackers options to drop into / climb out of the underpass.

## Lighting + atmosphere (per art direction polish plan)

Apply `splitroot-polish-art-direction-2026-05-24` §"Mood lighting":

- One `ADirectionalLight` — sun pitch -25°, yaw 30°, color (1.0, 0.85, 0.7), intensity 6 lux at noon scale.
- One `ASkyLight` — intensity 0.3.
- One `AExponentialHeightFog` — density 0.05, color (0.42, 0.50, 0.55).
- One `APostProcessVolume` (unbounded) — bloom 0.4, default tone mapping.

## RTS-table readability requirements

From RTS view of this valley, the player must be able to identify:

- Three faction bases (color: Verdant green / Lenswright brass / Kinwild ochre).
- Central Splitroot trunk + the three root knee-walls radiating out.
- Three side-resource sites (capture-zone outline color = currently-controlling faction, neutral grey if uncontested).
- Underpass entry/exit ramps.
- Cover-stone breadcrumbs along each lane (subtle — they're FPS geometry, not table icons).
- Friendly squads + selection arrows (per [[splitroot-s3-map-table-widget-contract-2026-05-23]] widget).

Camera height for the table view: high enough to see all three bases
+ center in one shot. Roughly 50,000 uu above center → bird's-eye.

## Files

This is a blockout SPEC; concrete asset creation is Hex's lane (or
Rook crossing over if Hex is on combat). Files involved:

- `Content/Maps/SplitrootValley_V1.umap` (new — saved level)
- `Content/Maps/SplitrootValley_V1_BuiltData.uasset` (build artifact)
- New `Content/Blueprints/...` BP actor classes for each unique placeholder shape (~30 new BPs at v1).
- Modify `UArchonCanaryWorldSubsystem` to recognize the new map (or load it as the default canary map instead of `Lvl_FirstPerson` when a `-ArchonRunValleyV1` flag is set).

Alternative (less binary-asset-heavy):
- Skip the `.umap` initially. Have `UArchonCanaryWorldSubsystem` spawn ALL actors programmatically from a `FArchonValleyV1Layout` data struct (one struct per actor: class + location + rotation + faction tag). Gated by `-ArchonRunValleyV1Programmatic` flag. Same pattern as the current S5 programmatic blockout. **Recommended for the first cut** — saves binary asset churn while iterating on coordinates.

## Smoke + proof

- New `Proof/valley-v1-blockout-smoke.ps1` — loads valley, asserts presence of all key actors at expected coordinates.
- Smoke flags: `ValleyV1Loaded`, `ValleyV1VerdantBasePresent`, `ValleyV1LenswrightBasePresent`, `ValleyV1KinwildBasePresent`, `ValleyV1CentralSplitrootPresent`, `ValleyV1SideResourceCountEquals3`, `ValleyV1CoverStoneBreadcrumbVerdantCountEquals12`, etc.

After smoke green, run the playtest skill to capture screenshots from
each faction's player-start vantage. THREE screenshots (one per
faction perspective) — `unreal-canary-playtest` learning log captures
whether each faction's homeland reads distinctly via the art-direction
palette.

## What this spec does NOT cover

- **Final art-direction materials applied to all 30+ BPs** — that's the art polish slice's `UArchonFactionMaterialBuilder` work; this spec just sets the geometric stage.
- **Navmesh build configuration** — Hex's call when implementing.
- **Lighting bake settings** — production preset acceptable at rung-2.
- **Scripted events** (e.g., the central tree growing during the match). Polish.
- **Capture-zone visual rings** — UMG world overlay; polish.
- **Audio environments** — separate audio polish plan.

## Hills check

- **Standard Archon**: ✓ Three faction homelands + shared central objective + side resource sites = canonical RTS map structure. No commander-only valley.
- **Standard FPS**: ✓ Sightlines, cover, navigation routes match standard FPS map design.
- **Faction verbs matter**: ✓ Each lane's cover geometry is SHAPED for its faction's movement verb. A Verdant player on the West lane root-vaults; a Kinwild player on the North lane bound-leaps; a Lenswright player on the East lane pressure-thrusts (when the verb ships). Geometry IS the design.
- **Movement before content**: ✓ The cover-stone breadcrumbs prove the map exists FOR the movement verbs. Combat slots in second.
- **Lenswright no gunpowder**: ✓ Lenswright outer choke has "two corner turrets" per the silhouette spec. Turret design defers to later; no firearm-tagged geometry here.
- **Paid heroes horizontal-only**: ✓ Hero placement is "spawns at base spawn like regular bodies" per v0. Same map for paid and free heroes; no hero-only routes.
- **Factory branch is product**: ✓ The three-base-triangle pattern is RUMIXABLE. Future games on the factory swap faction tags + palette + verb-geometry-shape but inherit the three-pole RTS map structure. The `FArchonValleyV1Layout` struct is the remix surface.
- **Proof ladder sacred**: ✓ Smoke flags assert structural presence. Feel of the valley (does it read as one place, do the lanes invite their verbs, does center fight feel

_Source wiki body truncated at 12000 characters._
