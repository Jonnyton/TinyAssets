---
title: Hero plan — Briar Saint + Master Artificer
type: plan
status: working-draft
source_issue: 1054
wiki_source_path: pages/plans/splitroot-hero-plan-briar-saint-master-artificer-2026-05-24.md
wiki_source_updated: 2026-05-24T15:37:59Z
---

# Hero plan — Briar Saint + Master Artificer

[[index]] [[pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23]] [[archon-fantasy-rts-fps-v0-unit-sheet-2026-05-20]] [[f2p-expansion-monetization-model-2026-05-21]] [[splitroot-second-60-seconds-combat-slice-2026-05-24]]

Goal: `9171b100de33`. Target: rung-3 (`content_complete_alpha`) + rung-4 F2P validation prep.

## Why this plan exists now (before rung-3 implementation)

Two reasons:

1. **The horizontal-only paid hero discipline is a HILL.** Per Rook persona at `.claude/rook.md` §"Hills I Will Die On": *"Paid heroes are cosmetic and horizontal. Combat math, economy, movement, damage, survivability, command authority — untouchable. The second we sell power we poison every future remix this factory might produce."* This plan locks that discipline in writing **before** implementation pressure arrives.
2. **Heroes are the factory branch's monetization remix surface.** Per the F2P model, future paid hero packs are how the substrate makes money. If the surface that paid heroes implement against is loose (allows stat changes, allows new abilities, allows unique mechanics), the whole horizontal-only discipline fails by drift. Lock the surface narrow at planning time.

## The horizontal-only hero contract

A "paid hero" CAN have, vs a "free hero":

| Field | Free hero ships with | Paid hero pack can vary |
|---|---|---|
| Combat damage values | Locked to spec | NO — paid hero deals identical damage |
| Health pool | Locked to spec | NO |
| Movement speed | Locked to faction default + verb | NO |
| Ability cooldowns | Locked to spec | NO |
| Ability effects (mechanic) | Locked to spec | NO — same mechanic, different presentation |
| Vision radius | Locked | NO |
| Faction power access | Locked | NO |
| Map-table command authority | Locked (= regular player) | NO |
| **Visual mesh / texture / animation** | Default | **YES — entirely** |
| **Voice lines + audio cues** | Default | **YES — entirely** |
| **Ability VFX color / shape** | Default | **YES — color/particles can differ, mechanic identical** |
| **Hero name + lore** | Default | **YES** |
| **Cosmetic recolors of weapons/armor** | Default | **YES** |
| **Death animation / death-line / kill-feed banner** | Default | **YES** |

The pattern: paid hero packs add **presentation variety**, not power.
Two paid heroes from the same faction class do the SAME damage at the
SAME range with the SAME cooldown. They just look + sound different.

This is the **Deep Rock Galactic** discipline applied to a competitive
hybrid game. DRG sells dwarf cosmetics; combat math is locked. Same
discipline here.

## Hero contract — `UArchonHeroComponent`

Future contract for Hex to implement (rung-3 prep; not for now):

```cpp
USTRUCT(BlueprintType)
struct FArchonHeroLockedStats
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, EditAnywhere, Category = "Archon|Hero|Locked")
    float MaxHealth = 350.0f;  // ~2.3× regular unit; survives focused fire ~3s

    UPROPERTY(BlueprintReadOnly, EditAnywhere, Category = "Archon|Hero|Locked")
    float ArmorModifier = 1.0f;  // SAME as regular units — armor is NOT paid

    UPROPERTY(BlueprintReadOnly, EditAnywhere, Category = "Archon|Hero|Locked")
    float MovementSpeedMultiplier = 1.15f;  // Slight; reads as "presence" not "power"

    UPROPERTY(BlueprintReadOnly, EditAnywhere, Category = "Archon|Hero|Locked")
    float WeaponDamageMultiplier = 1.3f;  // Kills regular bodies in 1-2s

    UPROPERTY(BlueprintReadOnly, EditAnywhere, Category = "Archon|Hero|Locked")
    EArchonHeroFaction HeroFaction = EArchonHeroFaction::None;

    UPROPERTY(BlueprintReadOnly, EditAnywhere, Category = "Archon|Hero|Locked")
    EArchonHeroAbilityKind AbilityOneKind = EArchonHeroAbilityKind::None;

    UPROPERTY(BlueprintReadOnly, EditAnywhere, Category = "Archon|Hero|Locked")
    float AbilityOneCooldownSeconds = 12.0f;

    UPROPERTY(BlueprintReadOnly, EditAnywhere, Category = "Archon|Hero|Locked")
    EArchonHeroAbilityKind UltimateKind = EArchonHeroAbilityKind::None;

    UPROPERTY(BlueprintReadOnly, EditAnywhere, Category = "Archon|Hero|Locked")
    float UltimateCooldownSeconds = 60.0f;
};

USTRUCT(BlueprintType)
struct FArchonHeroPresentation
{
    GENERATED_BODY()

    // PAID PACKS VARY THESE — these fields are the entire remix surface for monetization.

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Hero|Presentation")
    FName HeroDisplayId = TEXT("default");  // Pack identifier, e.g. "briar_saint_storm_variant"

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Hero|Presentation")
    FText DisplayName;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Hero|Presentation")
    TSoftObjectPtr<USkeletalMesh> CharacterMesh;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Hero|Presentation")
    TSoftObjectPtr<UMaterialInterface> CharacterMaterialOverride;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Hero|Presentation")
    TArray<TSoftObjectPtr<USoundBase>> VoiceLineBank;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Hero|Presentation")
    TSoftObjectPtr<UNiagaraSystem> AbilityOneVFX;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Hero|Presentation")
    TSoftObjectPtr<UNiagaraSystem> UltimateVFX;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Hero|Presentation")
    FLinearColor AccentColorOverride = FLinearColor::White;
};

UCLASS(ClassGroup=(Archon), Blueprintable, meta=(BlueprintSpawnableComponent))
class ARCHONFACTORYCANARY_API UArchonHeroComponent : public UActorComponent
{
    GENERATED_BODY()

public:
    UArchonHeroComponent();

    // ConfigureHero takes BOTH locked-stats AND presentation. Locked-stats
    // come from EArchonHeroFaction lookup (see GetLockedStatsForFaction).
    // Presentation comes from the entitlement layer — what the player owns.
    UFUNCTION(BlueprintCallable, Category = "Archon|Hero")
    void ConfigureHero(
        const FArchonHeroLockedStats& InLockedStats,
        const FArchonHeroPresentation& InPresentation);

    UFUNCTION(BlueprintPure, Category = "Archon|Hero")
    FArchonHeroLockedStats GetLockedStats() const { return LockedStats; }

    UFUNCTION(BlueprintPure, Category = "Archon|Hero")
    FArchonHeroPresentation GetPresentation() const { return Presentation; }

    UFUNCTION(BlueprintPure, Category = "Archon|Hero")
    FName GetActiveHeroDisplayId() const { return Presentation.HeroDisplayId; }

private:
    UPROPERTY(Replicated)
    FArchonHeroLockedStats LockedStats;

    // Presentation is REPLICATED but the LOCKED STATS DRIVE GAMEPLAY.
    // Server validates that LockedStats matches the canonical
    // GetLockedStatsForFaction(HeroFaction) on every ConfigureHero.
    // If a malicious client tries to send altered LockedStats, server rejects.
    UPROPERTY(Replicated)
    FArchonHeroPresentation Presentation;
};
```

The crucial invariant: **`LockedStats` is server-validated** against the
canonical-per-faction values. Paid presentation packs SHIP with the
default `FArchonHeroLockedStats` shape — a malicious or buggy presentation
pack can't ship custom stats. The presentation pack only ships
`FArchonHeroPresentation`.

## The two starting heroes

### Briar Saint (Verdant Choir hero)

Lore: a Verdant Choir priestess who's chosen by the bramble to grow
walls of living thorns mid-fight. Mid-range support hero. Fights at
the front but supports squad mates with terrain plays.

**Locked stats (`EArchonHeroFaction::BriarSaint`)**:
- `MaxHealth = 350.0f` — Verdant standard hero pool.
- `MovementSpeedMultiplier = 1.15f`.
- `WeaponDamageMultiplier = 1.3f` (applied to Verdant Thornsprout Bow).
- `AbilityOneKind = EArchonHeroAbilityKind::BriarWall_GrowCover` — spawn a 6m-long bramble wall 8m in front of you. Wall: 200 HP, lasts 12s, blocks projectiles, can be vaulted by Verdant root-vault. Cooldown 12s.
- `UltimateKind = EArchonHeroAbilityKind::BriarSaint_ChoirCircle` — spawn a 12m-radius circle of bramble columns at target location; allies within heal +5 HP/s, enemies within take 4 dmg/s; lasts 8s. Cooldown 60s.

**Default presentation**: green-cream robed silhouette, choir-hum audio loop while alive, leaf-flutter VFX on ability one, bramble-grow earth-rumble audio on ultimate.

**Paid pack idea (`briar_saint_storm_variant`)**: same mechanics, presentation is "Storm Briar Saint" — dark cloak, distant-thunder audio, lightning-cracked bramble VFX, ultimate plays a crack of thunder when triggered. SAME wall length, SAME damage, SAME cooldown, SAME heal. Buyer is paying for the *fantasy*, not power.

### Master Artificer (Lenswright Compact hero)

Lore: a Lenswright master who deploys clockwork constructs and
calibrates pressure traps. Mid-range support hero. Fights from
prepared positions; abilities prepare the battlefield.

**Locked stats (`EArchonHeroFaction::MasterArtificer`)**:
- `MaxHealth = 350.0f` — Lenswright standard hero pool.
- `MovementSpeedMultiplier = 1.15f`.
- `WeaponDamageMultiplier = 1.3f` (applied to Lenswright Pressure-Bolt Crossbow).
- `AbilityOneKind = EArchonHeroAbilityKind::PressureGate_Deploy` — deploy a 4m-square pressure pad at target location; Lenswright pressure-thrust on the pad doubles boost (mid-air access to highground). Lasts until destroyed. Cooldown 18s.
- `UltimateKind = EArchonHeroAbilityKind::MasterArtificer_OpticBarrage` — call an optic-guided ballista volley on a 10m-radius circle; 5 bolts over 4s, 35 dmg each; cooldown 60s. NO gunpowder — this is high-pressure crossbow artillery.

**Default presentation**: brass-oxblood plated silhouette with shoulder optic lens, clockwork-tick audio loop, pressure-vent hiss on deploy, gear-grind audio on ultimate firing.

**Paid pack idea (`master_artificer_clockwork_swarm_variant`)**: same mechanics, presentation is "Swarm Artificer" — many smaller clockwork bugs orbit the hero (purely visual), ultimate VFX shows bolts deploying from swarm-bugs that converge on target (same 5 bolts, same damage, just a different visual story). NO gunpowder — bolts still pressure-launched.

## Hero match-flow integration

Per design extensions §"Match flow patterns":

- Hero unlocks at **~8-9 minutes** match time, when team has accumulated enough Supply at side-resources. (Specific Supply cost: 600 — about two side-resource flips' worth.)
- Hero spawns at base spawn chamber. Player picks "Spawn as hero" at the respawn screen body picker.
- ~**25-40 seconds** to reach central resource (Briar Saint at 1.15× sprint = ~30s; Master Artificer ~32s; reads as "hero arrival is a Decision" not "hero arrival is automatic").
- One hero per faction per team at a time. If hero dies, team must wait 90s before respawning a hero (hero respawn penalty MUCH longer than regular).
- Hero death is **broadcast on the team's audio layer** ("Briar Saint has fallen") — strategic event per design extensions §"Audio scale" strategic layer.

## Files this contract will need (rung-3 implementation)

Not for now — listed so the rung-3 plan knows the scope:

- `Source/.../ArchonHeroTypes.h` (enums, structs above)
- `Source/.../ArchonHeroPolicyLibrary.h/.cpp` (pure ability cooldown / damage logic)
- `Source/.../ArchonHeroComponent.h/.cpp` (the contract surface)
- `Source/.../ArchonHeroBriarSaintActor.h/.cpp` (concrete hero subclass)
- `Source/.../ArchonHeroMasterArtificerActor.h/.cpp`
- `Source/.../Abilities/ArchonBriarWallActor.h/.cpp` (the grown wall)
- `Source/.../Abilities/ArchonChoirCircleActor.h/.cpp`
- `Source/.../Abilities/ArchonPressureGateActor.h/.cpp`
- `Source/.../Abilities/ArchonOpticBarrageActor.h/.cpp`
- Tests for each.

## Entitlement / monetization integration

The existing `FactoryContracts/entitlement_policy.json` already
defines the F2P substrate. Heroes integrate as follows:

- **Default heroes** (Briar Saint + Master Artificer in their default presentations) are **free for all players**, including online matc

> Import note: Issue #1054's source wiki body is truncated at this point. The remaining entitlement / monetization integration text was not present in the available request payload, so this page preserves only the supplied source rather than inventing missing plan content.
