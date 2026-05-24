---
title: C1 contract - combat fundamentals
type: plan
status: working-draft
source_issue: 1035
wiki_source_path: pages/plans/splitroot-c1-combat-fundamentals-contract-2026-05-24.md
wiki_source_updated: 2026-05-24
---

# C1 contract - combat fundamentals

[[index]] [[splitroot-second-60-seconds-combat-slice-2026-05-24]] [[pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23]]

Goal: `9171b100de33`. Target rung: **2 (Verified vertical slice)**.

This contract defines the exact C++ surface Hex implements to land
C1 - the load-bearing combat substrate that C2 (Verdant bow), C3
(Lenswright units + AI), C4 (death/respawn), C5 (command-while-you-wait),
and C6 (integration smoke) all depend on.

C1 is pure-policy + replicated state component, no weapons or units
yet. Same pattern that worked for S1 team visibility.

## Files

- `Source/ArchonFactoryCanary/Public/ArchonCombatTypes.h` (new)
- `Source/ArchonFactoryCanary/Public/ArchonCombatPolicyLibrary.h` (new)
- `Source/ArchonFactoryCanary/Private/ArchonCombatPolicyLibrary.cpp` (new)
- `Source/ArchonFactoryCanary/Public/ArchonCombatHealthComponent.h` (new)
- `Source/ArchonFactoryCanary/Private/ArchonCombatHealthComponent.cpp` (new)
- `Source/ArchonFactoryCanary/Private/Tests/ArchonCombatPolicyTests.cpp` (new)
- `Source/ArchonFactoryCanary/Private/Tests/ArchonCombatHealthComponentTests.cpp` (new)

## Public surface - `ArchonCombatTypes.h`

```cpp
#pragma once

#include "CoreMinimal.h"
#include "ArchonCombatTypes.generated.h"

UENUM(BlueprintType)
enum class EArchonHitType : uint8
{
	None UMETA(DisplayName = "None"),
	Body UMETA(DisplayName = "Body"),
	Head UMETA(DisplayName = "Head"),
	Limb UMETA(DisplayName = "Limb")
};

UENUM(BlueprintType)
enum class EArchonDamageType : uint8
{
	Generic UMETA(DisplayName = "Generic"),
	VerdantLivingArrow UMETA(DisplayName = "Verdant Living Arrow"),
	LenswrightPressureBolt UMETA(DisplayName = "Lenswright Pressure Bolt"),
	KinwildBeastBite UMETA(DisplayName = "Kinwild Beast Bite"),
	AlchemicalFire UMETA(DisplayName = "Alchemical Fire"),
	Environmental UMETA(DisplayName = "Environmental")
};

UENUM(BlueprintType)
enum class EArchonWeaponClass : uint8
{
	None UMETA(DisplayName = "None"),
	VerdantThornsproutBow UMETA(DisplayName = "Verdant Thornsprout Bow"),
	LenswrightPressureBoltCrossbow UMETA(DisplayName = "Lenswright Pressure-Bolt Crossbow")
};

USTRUCT(BlueprintType)
struct FArchonShotPayload
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Combat")
	int32 InstigatorTeamId = INDEX_NONE;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Combat")
	int32 InstigatorPlayerId = INDEX_NONE;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Combat")
	EArchonWeaponClass WeaponClass = EArchonWeaponClass::None;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Combat")
	EArchonDamageType DamageType = EArchonDamageType::Generic;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Combat")
	FVector ShotOrigin = FVector::ZeroVector;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Combat")
	FVector ShotDirection = FVector::ForwardVector;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Combat")
	FVector HitLocation = FVector::ZeroVector;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Combat")
	float DistanceTraveled = 0.0f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Combat")
	EArchonHitType HitType = EArchonHitType::Body;
};

USTRUCT(BlueprintType)
struct FArchonWeaponDamageProfile
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Combat")
	float BodyDamage = 35.0f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Combat")
	float HeadDamage = 80.0f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Combat")
	float LimbDamage = 22.0f;

	// Falloff: full damage from 0 to FalloffStart, linear ramp to MinDamage at FalloffEnd, MinDamage beyond.
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Combat")
	float FalloffStartUnits = 3000.0f;  // 30m

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Combat")
	float FalloffEndUnits = 6000.0f;  // 60m

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Combat")
	float MinDamage = 12.0f;
};

USTRUCT(BlueprintType)
struct FArchonHitResult
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Archon|Combat")
	bool bShouldHit = false;

	UPROPERTY(BlueprintReadOnly, Category = "Archon|Combat")
	float FinalDamage = 0.0f;

	UPROPERTY(BlueprintReadOnly, Category = "Archon|Combat")
	EArchonHitType HitType = EArchonHitType::None;

	UPROPERTY(BlueprintReadOnly, Category = "Archon|Combat")
	EArchonDamageType DamageType = EArchonDamageType::Generic;

	UPROPERTY(BlueprintReadOnly, Category = "Archon|Combat")
	int32 InstigatorTeamId = INDEX_NONE;

	UPROPERTY(BlueprintReadOnly, Category = "Archon|Combat")
	int32 InstigatorPlayerId = INDEX_NONE;

	UPROPERTY(BlueprintReadOnly, Category = "Archon|Combat")
	FName Reason;
};

USTRUCT(BlueprintType)
struct FArchonDamageApplicationResult
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Archon|Combat")
	bool bAccepted = false;

	UPROPERTY(BlueprintReadOnly, Category = "Archon|Combat")
	float DamageApplied = 0.0f;

	UPROPERTY(BlueprintReadOnly, Category = "Archon|Combat")
	float PreviousHealth = 0.0f;

	UPROPERTY(BlueprintReadOnly, Category = "Archon|Combat")
	float NewHealth = 0.0f;

	UPROPERTY(BlueprintReadOnly, Category = "Archon|Combat")
	bool bCausedDeath = false;

	UPROPERTY(BlueprintReadOnly, Category = "Archon|Combat")
	FName Reason;
};
```

## Public surface - `ArchonCombatPolicyLibrary.h`

```cpp
#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "ArchonCombatTypes.h"
#include "ArchonCombatPolicyLibrary.generated.h"

UCLASS()
class ARCHONFACTORYCANARY_API UArchonCombatPolicyLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	// Resolve a shot payload against a target's team and the active weapon
	// damage profile. Pure function - no world side-effects.
	UFUNCTION(BlueprintCallable, Category = "Archon|Combat")
	static FArchonHitResult ResolveShot(
		const FArchonShotPayload& Shot,
		int32 TargetTeamId,
		bool bTargetIsAlive,
		float TargetArmorModifier,
		const FArchonWeaponDamageProfile& WeaponProfile);

	// Compute damage at a given distance using the profile's falloff curve.
	UFUNCTION(BlueprintPure, Category = "Archon|Combat")
	static float ComputeDistanceFalloff(
		float BaseDamage,
		float DistanceUnits,
		const FArchonWeaponDamageProfile& WeaponProfile);

	// Base damage by hit type before falloff and armor.
	UFUNCTION(BlueprintPure, Category = "Archon|Combat")
	static float GetBaseDamageForHitType(
		EArchonHitType HitType,
		const FArchonWeaponDamageProfile& WeaponProfile);

	// Friendly-fire policy: at v0, friendly fire is OFF (FF will return bShouldHit=false).
	UFUNCTION(BlueprintPure, Category = "Archon|Combat")
	static bool IsFriendlyFire(int32 InstigatorTeamId, int32 TargetTeamId);

	// Default weapon profile for each weapon class. Hex implements with
	// the values from the slice plan (Verdant: 35/80/22 + 30/60m falloff;
	// Lenswright: 40/90/25 + 25/50m falloff).
	UFUNCTION(BlueprintPure, Category = "Archon|Combat")
	static FArchonWeaponDamageProfile GetDefaultWeaponProfile(EArchonWeaponClass WeaponClass);
};
```

### Decision rules (load-bearing)

**`ResolveShot`** returns `bShouldHit = false` iff ANY of:
- `WeaponClass == None`
- `!bTargetIsAlive` (dead target - withhold subsequent damage)
- `IsFriendlyFire(InstigatorTeamId, TargetTeamId)` (v0 default off)
- `Shot.HitType == EArchonHitType::None`

Otherwise:
1. `BaseDamage = GetBaseDamageForHitType(Shot.HitType, WeaponProfile)`
2. `AfterFalloff = ComputeDistanceFalloff(BaseDamage, Shot.DistanceTraveled, WeaponProfile)`
3. `FinalDamage = AfterFalloff * TargetArmorModifier` (clamped >= 0)
4. Returns `bShouldHit = true`, `FinalDamage`, copies `HitType`, `DamageType`, `Instigator*`, `Reason = "accepted_combat_shot"`.

**`ComputeDistanceFalloff`**:
- `if DistanceUnits <= FalloffStartUnits: return BaseDamage`
- `if DistanceUnits >= FalloffEndUnits: return WeaponProfile.MinDamage`
- Else linear interp: `Alpha = (DistanceUnits - FalloffStartUnits) / (FalloffEndUnits - FalloffStartUnits)`, `return Lerp(BaseDamage, MinDamage, Alpha)`.

**`GetBaseDamageForHitType`**:
- `Body -> WeaponProfile.BodyDamage`
- `Head -> WeaponProfile.HeadDamage`
- `Limb -> WeaponProfile.LimbDamage`
- `None -> 0.0f`

**`IsFriendlyFire`**: `InstigatorTeamId == TargetTeamId && InstigatorTeamId != INDEX_NONE`.

**`GetDefaultWeaponProfile`**: switch returning preset profiles per class (Verdant bow: 35/80/22 + 3000/6000/12; Lenswright crossbow: 40/90/25 + 2500/5000/15; Kinwild beast-bite stub: 25/55/15 + 0/1500/8 for melee).

## Public surface - `UArchonCombatHealthComponent`

```cpp
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "ArchonCombatTypes.h"
#include "ArchonCombatHealthComponent.generated.h"

DECLARE_MULTICAST_DELEGATE_OneParam(FArchonHealthChangedNative, const FArchonDamageApplicationResult&);
DECLARE_MULTICAST_DELEGATE_OneParam(FArchonHealthDeathNative, const FArchonDamageApplicationResult&);

UCLASS(ClassGroup=(Archon), Blueprintable, meta=(BlueprintSpawnableComponent))
class ARCHONFACTORYCANARY_API UArchonCombatHealthComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UArchonCombatHealthComponent();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	UFUNCTION(BlueprintCallable, Category = "Archon|Combat")
	void ConfigureHealth(int32 InTeamId, float InMaxHealth, float InArmorModifier);

	// Apply a resolved hit. Server-authoritative: returns Accepted=false
	// if not authority. Caller should only invoke from server context.
	UFUNCTION(BlueprintCallable, Category = "Archon|Combat")
	FArchonDamageApplicationResult ApplyHit(const FArchonHitResult& HitResult);

	// Direct apply (no shot resolution) - used for environmental damage,
	// scripted death (e.g., proof runner force-kill), or tests.
	UFUNCTION(BlueprintCallable, Category = "Archon|Combat")
	FArchonDamageApplicationResult ApplyDirectDamage(float DamageAmount, EArchonDamageType DamageType, int32 InstigatorTeamId, int32 InstigatorPlayerId);

	UFUNCTION(BlueprintCallable, Category = "Archon|Combat")
	void HealToFull();

	UFUNCTION(BlueprintCallable, Category = "Archon|Combat")
	void ResetProofState();

	UFUNCTION(BlueprintPure, Category = "Archon|Combat")
	int32 GetTeamId() const { return TeamId; }

	UFUNCTION(BlueprintPure, Category = "Archon|Combat")
	float GetCurrentHealth() const { return CurrentHealth; }

	UFUNCTION(BlueprintPure, Category = "Archon|Combat")
	float GetMaxHealth() const { return MaxHealth; }

	UFUNCTION(BlueprintPure, Category = "Archon|Combat")
	float GetHealthFraction() const { return MaxHealth > 0.0f ? FMath::Clamp(CurrentHealth / MaxHealth, 0.0f, 1.0f) : 0.0f; }

	UFUNCTION(BlueprintPure, Category = "Archon|Combat")
	bool IsAlive() const { return CurrentHealth > 0.0f; }

	UFUNCTION(BlueprintPure, Category = "Archon|Combat")
	float GetArmorModifier() const { return ArmorModifier; }

	UFUNCTION(BlueprintPure, Category = "Archon|Combat")
	int32 GetTotalHitsTaken() const { return TotalHitsTaken; }

	UFUNCTION(BlueprintPure, Category = "Archon|Combat")
	int32 GetTotalDeaths() const { return TotalDeaths; }

	UFUNCTION(BlueprintPure, Category = "Archon|Combat")
	FArchonDamageApplicationResult GetLastDamageApplication() const { return LastDamageApplication; }

	FArchonHealthChangedNative OnHealthChanged;
	FArchonHealthDeathNative OnDeath;

private:
	UPROPERTY(Replicated)
	int32 TeamId = INDEX_NONE;

	UPROPERTY(Replicated)
	float MaxHealth = 150.0f;

	UPROPERTY(Replicated)
	float CurrentHealth = 150.0f;

	UPROPERTY(Replicated)
	float ArmorModifier = 1.0f;

	UPROPERTY(Replicated)
	int32 TotalHitsTaken = 0;

	UPROPERTY(Replicated)
	int32 TotalDeaths = 0;

	UPROPERTY(Replicated)
	FArchonDamageApplicationResult LastDamageApplication;
};
```

## Source truncation note

Issue #1035 and the provided request body both stop at the incomplete heading
`### Component behavior (load-bearin` because `wiki-change-sync` truncated the
source wiki body at 12000 characters. This repository projection preserves the
available authoritative source and does not infer the missing component behavior,
test cases, or gate ladder text.
