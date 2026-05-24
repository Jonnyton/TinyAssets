---
title: H1 contract - hero infrastructure
type: plan
status: working-draft
source_issue: 1053
wiki_source_path: pages/plans/splitroot-h1-hero-infrastructure-contract-2026-05-24.md
source_completeness: partial
---

# H1 contract - hero infrastructure

[[index]] [[splitroot-hero-plan-briar-saint-master-artificer-2026-05-24]] [[splitroot-kinwild-pack-caller-hero-contract-2026-05-24]] [[factory-branch-jsonify-faction-substrate-2026-05-24]]

Goal: `9171b100de33`. Rung: **3**. **Depends on C1 combat fundamentals shipping.**

## Source completeness note

Issue #1053's filed source body is truncated at 12000 characters, ending
inside the named-test table. This page preserves the recoverable contract text
and marks the missing tail rather than reconstructing unverified acceptance
criteria.

First hero implementation contract. Ships the base infrastructure
that H2 (Briar Saint), H3 (Master Artificer), H4 (Pack-Caller),
and any future paid hero packs all implement against. **Codifies
the horizontal-only paid discipline in code, not in policy.**

## Files

- `Source/ArchonFactoryCanary/Public/ArchonHeroTypes.h` (new - enums + structs from hero plan)
- `Source/ArchonFactoryCanary/Public/ArchonHeroComponent.h` (new)
- `Source/ArchonFactoryCanary/Private/ArchonHeroComponent.cpp` (new)
- `Source/ArchonFactoryCanary/Public/ArchonHeroLockedStatsCatalog.h` (new - canonical per-faction defaults)
- `Source/ArchonFactoryCanary/Private/ArchonHeroLockedStatsCatalog.cpp` (new)
- `Source/ArchonFactoryCanary/Private/Tests/ArchonHeroComponentTests.cpp` (new - 12 tests including the server-validation invariant)

## Public surface - `ArchonHeroTypes.h`

```cpp
#pragma once

#include "CoreMinimal.h"
#include "ArchonFactionTypes.h"
#include "ArchonHeroTypes.generated.h"

UENUM(BlueprintType)
enum class EArchonHeroFaction : uint8
{
    None UMETA(DisplayName = "None"),
    BriarSaint UMETA(DisplayName = "Briar Saint (Verdant)"),
    MasterArtificer UMETA(DisplayName = "Master Artificer (Lenswright)"),
    PackCaller UMETA(DisplayName = "Pack-Caller (Kinwild)")
};

UENUM(BlueprintType)
enum class EArchonHeroAbilityKind : uint8
{
    None UMETA(DisplayName = "None"),
    BriarWall_GrowCover UMETA(DisplayName = "Briar Wall - Grow Cover"),
    BriarSaint_ChoirCircle UMETA(DisplayName = "Briar Saint - Choir Circle"),
    PressureGate_Deploy UMETA(DisplayName = "Pressure Gate - Deploy"),
    MasterArtificer_OpticBarrage UMETA(DisplayName = "Master Artificer - Optic Barrage"),
    PackCaller_SummonHuntPack UMETA(DisplayName = "Pack-Caller - Summon Hunt Pack"),
    PackCaller_HuntFrenzy UMETA(DisplayName = "Pack-Caller - Hunt Frenzy")
};

USTRUCT(BlueprintType)
struct FArchonHeroLockedStats
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, EditAnywhere, Category = "Archon|Hero|Locked")
    EArchonHeroFaction HeroFaction = EArchonHeroFaction::None;

    UPROPERTY(BlueprintReadOnly, EditAnywhere, Category = "Archon|Hero|Locked")
    EArchonFaction BaseFaction = EArchonFaction::None;

    UPROPERTY(BlueprintReadOnly, EditAnywhere, Category = "Archon|Hero|Locked")
    float MaxHealth = 350.0f;

    UPROPERTY(BlueprintReadOnly, EditAnywhere, Category = "Archon|Hero|Locked")
    float ArmorModifier = 1.0f;

    UPROPERTY(BlueprintReadOnly, EditAnywhere, Category = "Archon|Hero|Locked")
    float MovementSpeedMultiplier = 1.15f;

    UPROPERTY(BlueprintReadOnly, EditAnywhere, Category = "Archon|Hero|Locked")
    float WeaponDamageMultiplier = 1.3f;

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

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Hero|Presentation")
    FName HeroDisplayId = TEXT("default");

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Hero|Presentation")
    FText DisplayName;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Hero|Presentation")
    TSoftObjectPtr<class USkeletalMesh> CharacterMesh;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Hero|Presentation")
    TSoftObjectPtr<class UMaterialInterface> CharacterMaterialOverride;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Hero|Presentation")
    TArray<TSoftObjectPtr<class USoundBase>> VoiceLineBank;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Hero|Presentation")
    TSoftObjectPtr<class UNiagaraSystem> AbilityOneVFX;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Hero|Presentation")
    TSoftObjectPtr<class UNiagaraSystem> UltimateVFX;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Hero|Presentation")
    FLinearColor AccentColorOverride = FLinearColor::White;
};

USTRUCT(BlueprintType)
struct FArchonHeroConfigureResult
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category = "Archon|Hero")
    bool bAccepted = false;

    UPROPERTY(BlueprintReadOnly, Category = "Archon|Hero")
    FName Reason;
};
```

## Public surface - `UArchonHeroLockedStatsCatalog`

```cpp
UCLASS()
class ARCHONFACTORYCANARY_API UArchonHeroLockedStatsCatalog : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    // Canonical per-faction defaults. Server validates against this on ConfigureHero.
    UFUNCTION(BlueprintPure, Category = "Archon|Hero")
    static FArchonHeroLockedStats GetCanonicalLockedStats(EArchonHeroFaction HeroFaction);

    // Compare two locked-stats blocks for byte-for-byte equality.
    // (Server-validation primitive - used to detect mutated client payloads.)
    UFUNCTION(BlueprintPure, Category = "Archon|Hero")
    static bool LockedStatsExactlyMatch(
        const FArchonHeroLockedStats& A,
        const FArchonHeroLockedStats& B);
};
```

Implementation:

```cpp
FArchonHeroLockedStats UArchonHeroLockedStatsCatalog::GetCanonicalLockedStats(EArchonHeroFaction HeroFaction)
{
    FArchonHeroLockedStats Stats;
    Stats.HeroFaction = HeroFaction;
    // Shared numbers (all heroes - horizontal-only discipline):
    Stats.MaxHealth = 350.0f;
    Stats.ArmorModifier = 1.0f;
    Stats.MovementSpeedMultiplier = 1.15f;
    Stats.WeaponDamageMultiplier = 1.3f;
    Stats.AbilityOneCooldownSeconds = 12.0f;
    Stats.UltimateCooldownSeconds = 60.0f;

    switch (HeroFaction)
    {
    case EArchonHeroFaction::BriarSaint:
        Stats.BaseFaction = EArchonFaction::VerdantChoir;
        Stats.AbilityOneKind = EArchonHeroAbilityKind::BriarWall_GrowCover;
        Stats.UltimateKind = EArchonHeroAbilityKind::BriarSaint_ChoirCircle;
        break;
    case EArchonHeroFaction::MasterArtificer:
        Stats.BaseFaction = EArchonFaction::LenswrightCompact;
        Stats.AbilityOneKind = EArchonHeroAbilityKind::PressureGate_Deploy;
        // Master Artificer Pressure Gate has a longer ability-one cooldown
        // (persistent deployable per hero plan). Override:
        Stats.AbilityOneCooldownSeconds = 18.0f;
        Stats.UltimateKind = EArchonHeroAbilityKind::MasterArtificer_OpticBarrage;
        break;
    case EArchonHeroFaction::PackCaller:
        Stats.BaseFaction = EArchonFaction::KinwildCovenant;
        Stats.AbilityOneKind = EArchonHeroAbilityKind::PackCaller_SummonHuntPack;
        Stats.UltimateKind = EArchonHeroAbilityKind::PackCaller_HuntFrenzy;
        break;
    default:
        Stats.HeroFaction = EArchonHeroFaction::None;
        break;
    }
    return Stats;
}
```

## Public surface - `UArchonHeroComponent`

```cpp
UCLASS(ClassGroup=(Archon), Blueprintable, meta=(BlueprintSpawnableComponent))
class ARCHONFACTORYCANARY_API UArchonHeroComponent : public UActorComponent
{
    GENERATED_BODY()

public:
    UArchonHeroComponent();

    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

    // Server-only. Client RPC sends the requested presentation; server
    // validates the locked-stats payload matches the canonical, then
    // accepts presentation override. Rejects if locked-stats differ
    // from canonical for the named HeroFaction.
    UFUNCTION(BlueprintCallable, Category = "Archon|Hero")
    FArchonHeroConfigureResult ConfigureHero(
        const FArchonHeroLockedStats& RequestedLockedStats,
        const FArchonHeroPresentation& RequestedPresentation);

    UFUNCTION(BlueprintPure, Category = "Archon|Hero")
    FArchonHeroLockedStats GetLockedStats() const { return LockedStats; }

    UFUNCTION(BlueprintPure, Category = "Archon|Hero")
    FArchonHeroPresentation GetPresentation() const { return Presentation; }

    UFUNCTION(BlueprintPure, Category = "Archon|Hero")
    EArchonHeroFaction GetHeroFaction() const { return LockedStats.HeroFaction; }

    UFUNCTION(BlueprintPure, Category = "Archon|Hero")
    EArchonFaction GetBaseFaction() const { return LockedStats.BaseFaction; }

    UFUNCTION(BlueprintPure, Category = "Archon|Hero")
    FName GetActiveHeroDisplayId() const { return Presentation.HeroDisplayId; }

    UFUNCTION(BlueprintPure, Category = "Archon|Hero")
    bool IsConfigured() const { return LockedStats.HeroFaction != EArchonHeroFaction::None; }

private:
    UPROPERTY(Replicated)
    FArchonHeroLockedStats LockedStats;

    UPROPERTY(Replicated)
    FArchonHeroPresentation Presentation;
};
```

### Behavior - the critical server-validation invariant

```cpp
FArchonHeroConfigureResult UArchonHeroComponent::ConfigureHero(
    const FArchonHeroLockedStats& RequestedLockedStats,
    const FArchonHeroPresentation& RequestedPresentation)
{
    FArchonHeroConfigureResult Result;

    // 1. Authority gate. ConfigureHero is server-authoritative.
    if (!GetOwner()->HasAuthority())
    {
        Result.bAccepted = false;
        Result.Reason = TEXT("not_authority");
        return Result;
    }

    // 2. Hero-faction must be valid.
    if (RequestedLockedStats.HeroFaction == EArchonHeroFaction::None)
    {
        Result.bAccepted = false;
        Result.Reason = TEXT("hero_faction_none");
        return Result;
    }

    // 3. THE HORIZONTAL-ONLY DISCIPLINE GATE. Validate that the
    // requested locked stats EXACTLY match the canonical for the
    // requested HeroFaction. Reject if any field differs.
    const FArchonHeroLockedStats Canonical =
        UArchonHeroLockedStatsCatalog::GetCanonicalLockedStats(RequestedLockedStats.HeroFaction);
    if (!UArchonHeroLockedStatsCatalog::LockedStatsExactlyMatch(RequestedLockedStats, Canonical))
    {
        Result.bAccepted = false;
        Result.Reason = TEXT("locked_stats_mutated_rejected");
        UE_LOG(
            LogTemp,
            Warning,
            TEXT("ArchonFactoryCanary: HeroConfigureRejected reason=locked_stats_mutated heroFaction=%d"),
            static_cast<int32>(RequestedLockedStats.HeroFaction));
        return Result;
    }

    // 4. Presentation is ALWAYS accepted as-is (it's the
    // entire entitlement-payload surface).
    LockedStats = Canonical;  // Use canonical, not the requested (defense in depth)
    Presentation = RequestedPresentation;

    Result.bAccepted = true;
    Result.Reason = TEXT("accepted");

    UE_LOG(
        LogTemp,
        Display,
        TEXT("ArchonFactoryCanary: HeroConfigured heroFaction=%d displayId=%s"),
        static_cast<int32>(LockedStats.HeroFaction),
        *Presentation.HeroDisplayId.ToString());
    return Result;
}
```

The KEY pattern: even when `RequestedLockedStats` matches canonical,
the server **stores the canonical** (not the requested). This is
**defense in depth** - if a future code path bypasses the
validation check, the server still falls back to the
canonical-from-catalog. Locked stats are NEVER stored as
client-supplied data.

## Named tests (12) - `ArchonHeroComponentTests.cpp`

| Test | Expected outcome |
|---|---|
| `ArchonFactory.Hero.CanonicalBriarSaintStatsMatchHeroPlan` | `GetCanonicalLockedStats(BriarSaint)` returns MaxHealth=350, SpeedMult=1.15, WeaponMult=1.3, Ability1=BriarWall_GrowCover, Ability1CD=12, Ultimate=BriarSaint_ChoirCirc |

Remaining named-test rows and any trailing contract sections were not present
in issue #1053's recoverable source body.
