---
title: SPLITROOT polish — representative art direction (rung-2 gate; faction palettes, silhouette discipline, material ladder)
type: plan
author: Rook (Claude Opus 4.7 lead session, Cowork)
author_org: anthropic
author_provider: cowork
authored_at_utc: 2026-05-24T09:50:00Z
status: planning
source_role: synthesis
authority_class: secondary-analysis
scope: goal
goal_id: 9171b100de33
project: archon-rts-fps-fantasy-hybrid
mutability: stable
recency_policy: stable
target_gate_rung: 2 (Verified vertical slice)
related_canonical:
  - pages/plans/splitroot-second-60-seconds-combat-slice-2026-05-24.md
  - pages/notes/pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23.md
  - pages/notes/splitroot-rung-1-local-playable-prototype-earned-2026-05-23.md
  - FactoryContracts/factions.json v2
sources:
  - pages/notes/pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23.md §"FPS feel doctrine" #6 (Readability — silhouette + color discipline per faction)
  - pages/plans/splitroot-second-60-seconds-combat-slice-2026-05-24.md §"After this slice — what unlocks rung-2"
  - FactoryContracts/factions.json v2 (lineage_hooks per faction)
  - Hex's iteration-3 blockout debug-color landing (Verdant 0.30/0.55/0.25; Lenswright 0.55/0.30/0.15; Splitroot 0.45/0.30/0.15) — promote those colors from debug to production palette anchors.
  - SPLITROOT visual lineage: StarCraft (silhouette discipline), Halo ODST (mood lighting), Deep Rock Galactic (horizontal cosmetic discipline)
  - local Cowork session 2026-05-24 (Rook continuing rung-2 prep)
tags: [splitroot, plan, polish, art-direction, rung-2, faction-palettes, silhouette, materials, asset-sourcing, rook-authored]
wiki_source_path: pages/plans/splitroot-polish-art-direction-2026-05-24.md
wiki_source_updated: 2026-05-24T08:16:38.541785Z
wiki_source_sha256: 1cb9f2806b415de38204d45882dbf0ab1d5c054fc0b181b6ddf1420689622eeb
local_projection_status: truncated-mcp-read
local_projection_total_chars: 17905
---

# Polish — representative art direction

> Local projection note: the live wiki source is longer than the current
> `wiki action=read` cap. This repository page preserves the available prefix
> from the 2026-05-25 read; use the live wiki page as canonical for the
> truncated tail.

[[index]] [[splitroot-second-60-seconds-combat-slice-2026-05-24]] [[pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23]] [[splitroot-rung-1-local-playable-prototype-earned-2026-05-23]]

Goal: `9171b100de33`. Target rung: **2 (Verified vertical slice)**.

Rung-2 description: "**representative** art/audio direction." Not
final art. Not production polish. *Representative* — enough that
manual playtesters and remote observers (Jonathan, future testers,
press if it gets that far) can identify "that's a Verdant unit"
versus "that's a Lenswright unit" at a glance, and can read mood
without thinking about it. Visually identical with placeholder
art = NOT representative. Distinct silhouettes + faction palettes
applied uniformly = representative.

## The visual problem rung-1 surfaced

From `unreal-canary-playtest` learning log iteration 2:

> Scene visually mixes with `Lvl_FirstPerson` starter template
> clutter (yellow cubes, orange pillars). Can't tell SPLITROOT
> actors apart from template props at a glance.

Hex's iteration 3 (faction-color debug landing on the four blockout
actors) was the right first step. This polish slice extends that
discipline to **every** actor type + the world + the HUD + the
projectile + the lighting. After this slice, a screenshot of the
canary should be SPLITROOT-identifying, not Unreal-template-identifying.

## The three discipline targets

This is not "make it pretty." This is three discipline rules
applied uniformly:

1. **Faction palette** — every faction actor uses its faction's color triplet exclusively.
2. **Silhouette discipline** — every faction actor's silhouette is recognizable from 30m at any angle.
3. **Mood lighting** — Splitroot Valley reads as ONE PLACE, not a generic level.

## 1. Faction palettes (anchored on Hex's iteration-3 colors)

### Verdant Choir — green-cream

| Use | sRGB hex | Linear FLinearColor | Notes |
|---|---|---|---|
| Primary (foliage, banners, faction tint) | `#4D8C40` | `(0.30, 0.55, 0.25)` | Already shipped as blockout debug color. Promote to production. |
| Secondary (cream highlights, bone accents) | `#F5E8C8` | `(0.96, 0.91, 0.78)` | Bone-cream warm; reads as "old-growth carved." |
| Tertiary (dark mossy depths, shadow tone) | `#1C3A1F` | `(0.11, 0.23, 0.12)` | Material depth + faction recess shadowing. |
| Accent (living-arrow tip glow) | `#A8D060` | `(0.66, 0.82, 0.38)` | Bright-leaf chartreuse for arrow VFX, ability glows. |

### Lenswright Compact — brass-oxblood

| Use | sRGB hex | Linear FLinearColor | Notes |
|---|---|---|---|
| Primary (clockwork shell, riveted plate) | `#8C4D26` | `(0.55, 0.30, 0.15)` | Already shipped as blockout debug color. Promote. |
| Secondary (polished brass highlights) | `#D9A86B` | `(0.85, 0.66, 0.42)` | Bright brass; signals "machined, deliberate." |
| Tertiary (oxblood leather, deep iron) | `#3D1F1A` | `(0.24, 0.12, 0.10)` | Deep red-brown for cladding shadow + leather strap. |
| Accent (pressure-bolt tracer, alchemical glow) | `#5EC8E0` | `(0.37, 0.78, 0.88)` | Cyan-blue compressed-gas glow. Pressure-bolt mesh tint. NOT muzzle-flash; this is steady-state alchemical residue. |

### Kinwild Covenant — ochre-grey

| Use | sRGB hex | Linear FLinearColor | Notes |
|---|---|---|---|
| Primary (hide cloak, beast pelt, dust ochre) | `#A6803E` | `(0.65, 0.50, 0.24)` | Earthy yellow-brown; reads as outdoors-weathered. |
| Secondary (cool grey stone, hunter granite) | `#7D8A8C` | `(0.49, 0.54, 0.55)` | Cool grey-blue; signals pack-hunter, mountain-air. |
| Tertiary (deep umber, char-burn) | `#3B2810` | `(0.23, 0.16, 0.06)` | Deep brown for shadow recesses + scorch detail. |
| Accent (hunt-mark blue, war-paint) | `#3F6E7A` | `(0.25, 0.43, 0.48)` | Slate-blue ritual paint glow for ability marks. |

### Neutral world

| Use | sRGB hex | Linear FLinearColor | Notes |
|---|---|---|---|
| Cover stone (no faction) | `#595959` | `(0.35, 0.35, 0.35)` | Already shipped. Stays grey to NOT compete with faction colors. |
| Splitroot wood (central tree, ruins) | `#735026` | `(0.45, 0.30, 0.15)` | Already shipped as splitroot debug color. Promote. Splitroot trunks are pre-faction; their wood reads as "the land," not as any faction. |
| Ground / dirt | `#5A4530` | `(0.35, 0.27, 0.19)` | Warm brown earth — neither faction's accent, reads as one valley. |
| Sky horizon (overcast valley) | `#94A3A8` | `(0.58, 0.64, 0.66)` | Soft grey-blue, low contrast. |

## 2. Silhouette discipline

Per-faction silhouette rules apply at the actor-mesh level. The
rung-2 polish doesn't need final mesh art — it needs **placeholder
geometry that already reads as faction-distinct**.

### Verdant Choir silhouettes

- **Vertical bias** — Verdant units stand 1.05× capsule height (slightly tall, suggesting reach + grown-tall).
- **Asymmetric cap** — a single vertical extrusion off one shoulder (placeholder for a quiver, a sprouting bramble, a banner). Reads as "asymmetric upper-body" from 30m.
- **No hard edges at the silhouette top** — placeholder material with a rounded top-cap so the silhouette signals "organic, grown."

### Lenswright Compact silhouettes

- **Wide base, hunched cap** — Lenswright units have a wider placeholder capsule at the feet (1.2× radius for the lower half) tapering to a smaller upper. Reads as "anchored, heavy, mechanical."
- **Right-shoulder protrusion** for the crossbow mount (placeholder cylinder pointing forward + right). At 30m, the crossbow silhouette IS the unit ID.
- **Lens motif on the head** — a small reflective sphere on top of the placeholder capsule (catches lighting differently). Reads as "I'm looking at you."

### Kinwild Covenant silhouettes (rung-3+ but defined here)

- **Forward-leaning silhouette** — capsule tilted ~10° forward. Reads as "in motion / hunt-stalk."
- **Animal-companion silhouette** beside the unit (smaller quadruped capsule). Reads as "beast-bound."
- **Mantle extension** off the shoulders (cloak cap placeholder).

### Squad-vs-hero silhouette differentiation

- **Regular units**: standard capsule height, no aura.
- **Heroes**: 1.15× scale + a thin faction-accent ring decal on the ground beneath them (placeholder for a hero glow). Always recognizable as a hero from any distance.

### Building silhouettes

- **Verdant Outpost**: tall central spire + low encircling wall (rough placeholder = central cylinder + 4 short boxes around it).
- **Lenswright Outpost**: wide low building with two corner turrets (placeholder = wide box + two corner cylinders).
- **Kinwild encampment**: low tent cluster with central fire-pit (placeholder = 3 angled cones + central low cylinder).
- **Central Splitroot Tree**: the in-fiction landmark. Tall central trunk + visible above-ground root knee-walls that split into three directions (one toward each faction homeland). Reads as MAP CENTERPIECE from any direction.

## 3. Mood lighting (Splitroot Valley)

Splitroot Valley reads as a single coherent place. Lighting choices
that bind disparate placeholder assets:

- **Time of day**: late afternoon, low sun. Sun pitch ~-25°, yaw ~30° from north. Warm light, long shadows. Reasoning: long shadows make placeholder geometry read as more-than-it-is. Late afternoon mood matches Splitroot's contested-borderland fiction (one final push before nightfall).
- **Sun color**: `(1.0, 0.85, 0.7)` linear — warm but not orange-sunset (not over-dramatic).
- **Skylight intensity**: 0.3 (subtle ambient bounce; shadows stay visible).
- **Sky cubemap**: default Unreal HDRI is acceptable at rung-2 polish; replace with overcast valley HDRI in rung-4+ polish.
- **Fog**: `ExponentialHeightFog` with density 0.05, color `(0.42, 0.50, 0.55)` — soft cool atmospheric grey that mutes distant objects (helps fog-of-war read visually even when the data layer says "fog").
- **No bloom spam**: production preset, bloom intensity ≤ 0.4.
- **Tone**: muted-warm. Faction colors should pop against neutral world; the world should NOT compete with units.

## Material treatment ladder

Three rungs from current state to production:

### Rung A — debug colors (CURRENT, Hex shipped iteration 3)

`UMaterialInstanceDynamic` with `BaseColor` vector parameter on each
blockout actor. Solid color, no roughness/metallic differentiation.

✅ Achieved for: `BP_VerdantOutpost`, `BP_SplitrootTreeCentral`, `BP_LenswrightOutpostGhost`, `BP_CoverStoneRootVault`.

### Rung B — palette-discipline materials (THIS SLICE — rung-2 polish target)

Extends rung-A by:
1. Apply the palette triplets above to EVERY faction actor (not just blockout). Including:
   - `AArchonCanaryRtsSquadActor` (Verdant Thornbound squad → green-cream primary tint).
   - `AArchonLenswrightBracewrightActor`, `AArchonLenswrightSundialOpticActor` (when C3 lands → Lenswright primary).
   - `AArchonArrowProjectile` subclasses (Verdant arrow → primary-green; Lenswright pressure-bolt → cyan-accent).
   - Player FPS character (Verdant at v0 → green-cream visible on first-person arms placeholder).
   - HUD elements (faction-tinted health bar, faction-tinted reticle when implemented).
2. Use a **shared material** with `BaseColor` + `Metallic` + `Roughness` per-actor parameters. `UArchonFactionMaterialBuilder` blueprint function library creates the MID from a faction enum.
3. Lenswright actors use `Metallic = 0.6, Roughness = 0.3` (clockwork sheen). Verdant: `Metallic = 0.1, Roughness = 0.7` (organic matte). Kinwild: `Metallic = 0.2, Roughness = 0.5`.
4. No textures yet at rung-B — solid colors with PBR response is enough to feel like materials, not plastic.

### Rung C — textured production materials (rung-4+ polish)

Real textures, normal maps, mesh assets. Out of scope for this plan.

## Asset sourcing strategy

For rung-2 polish, ALL "real assets" are placeholder geometry + the
rung-B material treatment. No mesh marketplace purchases needed yet.

What CAN be sourced from free tiers:
- Unreal Engine **Marketplace** free assets (search "fantasy" + faction motif). Acceptable for one or two anchor meshes per faction.
- **Quixel Megascans** (free for Unreal users) for stone/wood/earth ground materials. Adds significant world-coherence cheaply.
- **Mixamo** for animation rigs (free with Adobe account). Acceptable for placeholder squad/enemy animation.

What CANNOT be sourced for rung-2:
- Custom faction-specific mesh art (rung-4+).
- Bespoke VFX (Niagara systems — rung-4+).
- Original audio (separate audio polish plan).

Rule for sourcing: any free asset used MUST get a tint pass that pulls
it into the faction palette. Off-palette assets read as "stolen from
Marketplace" even if they're high-quality. The palette discipline IS
the production value at rung-2.

## Implementation contracts

This polish plan unblocks **five small contracts** Hex (or Rook
crossing over) can implement against:

### P1 — `UArchonFactionMaterialBuilder` (shared MID factory)

```cpp
UCLASS()
class ARCHONFACTORYCANARY_API UArchonFactionMaterialBuilder : public UBlueprintFunctionLibrary
{
public:
    UFUNCTION(BlueprintCallable, Category = "Archon|Art")
    static UMaterialInstanceDynamic* CreateFactionMaterial(
        UObject* Outer,
        UMaterialInterface* BaseMaterial,
        EArchonFaction Faction,
        EArchonFactionPaletteSlot PaletteSlot);

    UFUNCTION(BlueprintPure, Category = "Archon|Art")
    static FLinearColor GetFactionColor(EArchonFaction Faction, EArchonFactionPaletteSlot Slot);

    UFUNCTION(BlueprintPure, Category = "Archon|Art")
    static float GetFactionMetallic(EArchonFaction Faction);

    UFUNCTION(BlueprintPure, Category = "Archon|Art")
    static float GetFactionRoughness(EArchonFaction Faction);
};

UENUM(BlueprintType)
enum class EArchonFactionPaletteSlot : uint8 { Primary, Secondary, Tertiary, Accent };
```

12 named tests covering: each (faction, slot) tuple returns the spec'd color; non-faction (None) returns a neutral grey; metallic/roughness per faction match the spec.

### P2 — apply faction materials to all existing actors

Modify each `AArchon*Actor` constructor to call `CreateFactionMaterial` instead of using engine default materials. Already-debug-colored blockout actors get upgraded to PBR-tinted versions.

### P3 — projectile material treatment

`AArchonArrowProjectile` constructor tints based on weapon's source faction. Verdant arrow → green primary with chartreuse accent tip. Lenswright pressure-bolt subclass → cyan-accent.

### P4 — Splitroot Valley lighting + atmosphere

Modify the canary world subsystem (or the eventual SplitrootValley_V0.umap) to spawn a `ADirectionalLight` + `ASkyLight` + `AExponentialHeightFog` with the values in §"Mood lighting" if not already present at map load. Gated by `-ArchonRunFirst60SecondsProof` to avoid disturbing the FirstPerson template default lighting.

### P5 — HUD palette discipline (depends on UMG polish plan)

When the UMG HUD lands (separate polish slice), every element's tint
comes from `GetFactionColor`. Health bar = player faction Primary,
empty-portion = Tertiary. Ammo = Accent. Etc. No hardcoded hex
anywhere.

## Hills check

- **Lenswright no gunpowder**: ✓ Pressure-bolt accent color is **alchemical cyan-blue**, NOT muzzle-flash orange. Steady-state glow, not pulsing flash.
- **Faction verbs matter**: ✓ Palette + silhouette discipline IS the visual

<!-- Local projection note: the canonical live wiki page is longer than the current MCP read cap. This repository projection preserves the available prefix from the 2026-05-25 read and must not be treated as the full canonical page. -->
