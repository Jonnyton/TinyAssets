---
title: SPLITROOT S4 contract — Verdant root-vault locomotion, with impulse magnitude decision resolved
type: plan
author: Rook (Claude Opus 4.7 lead session, Cowork)
author_org: anthropic
author_provider: cowork
authored_at_utc: 2026-05-23T22:40:00Z
status: contract-ready
source_role: contract
authority_class: secondary-analysis
scope: goal
goal_id: 9171b100de33
project: archon-rts-fps-fantasy-hybrid
mutability: stable
recency_policy: stable
target_gate_rung: 1 (Local playable prototype)
related_canonical:
  - pages/plans/splitroot-first-60-seconds-slice-2026-05-23.md
  - pages/notes/pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23.md
  - pages/notes/pages-notes-splitroot-name-and-design-foundation-2026-05-23.md
  - pages/notes/splitroot-in-flight-s3-s6-contracts-rook-2026-05-23.md
sources:
  - pages/plans/splitroot-first-60-seconds-slice-2026-05-23.md (S4 sub-slice intent, open question on impulse magnitude)
  - pages/notes/pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23.md (movement verbs catalog)
  - pages/notes/pages-notes-splitroot-name-and-design-foundation-2026-05-23.md (faction naming commit — Verdant Choir, Kinwild Covenant, Lenswright Compact)
  - Source/ArchonFactoryCanary/Public/ArchonCanaryFpsCharacter.h (extension point)
  - Source/ArchonFactoryCanary/Public/ArchonFpsInputProfile.h (sprint + jump bindings)
  - local Cowork session 2026-05-23 (Rook resolving open Q, authoring contract for Hex pickup)
tags: [splitroot, contract, s4, locomotion, root-vault, verdant-choir, faction-movement, hex-handoff, rook-authored, design-decision]
---

# S4 contract — Verdant root-vault locomotion

[[index]] [[splitroot-first-60-seconds-slice-2026-05-23]] [[pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23]] [[splitroot-in-flight-s3-s6-contracts-rook-2026-05-23]]

Goal: `9171b100de33`. Rung 1.

This contract defines the exact C++ surface Hex implements to land
S4 from [[splitroot-first-60-seconds-slice-2026-05-23]]: the
Verdant Choir root-vault locomotion signature on the FPS character.

## Design decision — root-vault impulse magnitude (resolves slice-plan open Q #1)

Slice plan flagged **"Root-vault impulse magnitude"** as open. Rook
resolves here.

### The math

Range target from [[pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23]]
and the blockout: **12-18m hops** (1200-1800 uu). Felt-reference: a
Tribes ski-jump or a Quake strafe-jump bump — discoverable, not
gnomic.

Assumptions for math:
- Unreal default gravity: `-980 cm/s²`.
- Sprint base ground velocity: ~900 uu/s (the `SprintWalkSpeed` already
  set in `UArchonPlayerInputBridgeComponent`).
- Player is grounded the instant of launch; impulse is applied as
  `LaunchCharacter(Impulse, /*XYOverride*/false, /*ZOverride*/false)`
  — i.e., additive to existing velocity.

For the **target 15m forward / 0.9s air-time** sweet-spot:
- Vertical impulse to keep airborne ~0.9s at -980 gravity: `v0_z ≈ 0.9 * 980 / 2 = 441 uu/s` → round to **450 uu/s**.
- Horizontal forward impulse to gain enough range: a sprint-velocity player adds ~850 uu/s forward, reaching ~1750 uu/s; at 0.9s air time covers ~1575 uu (15.75m). ✓

This lands the player slightly past 15m with sprint + impulse. A
standing root-vault (no prior sprint) covers ~7.6m — still useful,
deliberately weaker so movement chains reward continuous play.

### Final values

| Parameter | Value | Notes |
|---|---|---|
| `LaunchImpulseForward` | `850.0f` uu/s | Additive in pawn-forward direction (XY component of camera forward, Z=0). |
| `LaunchImpulseVertical` | `450.0f` uu/s | Additive upward. |
| `CooldownSeconds` | `3.0f` | From [[pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23]]. Starts on launch. |
| `MinSprintHeldSeconds` | `0.15f` | Anti-accidental-press window. Must have held sprint for at least this long before jump triggers vault. |
| `RequireGroundedAtLaunch` | `true` | No air-vault chain at v0. |
| `ConsumeJumpInput` | `true` | When vault fires, normal `ACharacter::Jump` is suppressed for that press. |

Magnitudes are `UPROPERTY(EditAnywhere)` on the component so they're
tunable in editor without code change once we're past v0. The
contract values are the *initial* defaults — playtest in Rook+Jonathan
manual session is the only authority on whether they feel right.
Don't claim "feel proven" from automation.

## Faction enum

The local repo has no `EArchonFaction` yet. `FactoryContracts/factions.json`
carries pre-naming-commit IDs (`verdant_court`, `wildbond_clans`,
`brassroot_artificers`) that predate [[pages-notes-splitroot-name-and-design-foundation-2026-05-23]].

**S4 introduces `EArchonFaction` with the committed names. Do not
rename factions.json in S4** — that's a separate cleanup so we don't
churn this contract. File `pages/notes/splitroot-factions-json-rename-needed-<date>.md`
as a follow-up if it isn't already on the connector; Rook can pick
up the JSON + any tooling that reads it in a separate small slice.

## Files

- `Source/ArchonFactoryCanary/Public/ArchonFactionTypes.h` (new — enum + cooldown struct)
- `Source/ArchonFactoryCanary/Public/ArchonFactionMovementPolicyLibrary.h` (new)
- `Source/ArchonFactoryCanary/Private/ArchonFactionMovementPolicyLibrary.cpp` (new)
- `Source/ArchonFactoryCanary/Public/ArchonFactionMovementComponent.h` (new)
- `Source/ArchonFactoryCanary/Private/ArchonFactionMovementComponent.cpp` (new)
- `Source/ArchonFactoryCanary/Private/Tests/ArchonFactionMovementPolicyTests.cpp` (new)
- `Source/ArchonFactoryCanary/Public/ArchonCanaryFpsCharacter.h` (modified — add component)
- `Source/ArchonFactoryCanary/Private/ArchonCanaryFpsCharacter.cpp` (modified — construct + bind input)

## Public surface — `ArchonFactionTypes.h`

```cpp
#pragma once

#include "CoreMinimal.h"
#include "ArchonFactionTypes.generated.h"

UENUM(BlueprintType)
enum class EArchonFaction : uint8
{
    None UMETA(DisplayName = "None"),
    VerdantChoir UMETA(DisplayName = "Verdant Choir"),
    KinwildCovenant UMETA(DisplayName = "Kinwild Covenant"),
    LenswrightCompact UMETA(DisplayName = "Lenswright Compact")
};

UENUM(BlueprintType)
enum class EArchonFactionMovementVerb : uint8
{
    None UMETA(DisplayName = "None"),
    VerdantRootVault UMETA(DisplayName = "Verdant Root-Vault"),
    KinwildBoundLeap UMETA(DisplayName = "Kinwild Bound-Leap"),
    LenswrightPressureThrust UMETA(DisplayName = "Lenswright Pressure-Thrust")
};

USTRUCT(BlueprintType)
struct FArchonFactionMovementCooldown
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Locomotion")
    float SecondsRemaining = 0.0f;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Locomotion")
    float TotalSeconds = 0.0f;
};

USTRUCT(BlueprintType)
struct FArchonFactionMovementInputState
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Locomotion")
    bool bSprintHeld = false;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Locomotion")
    float SprintHeldSeconds = 0.0f;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Locomotion")
    bool bJumpPressedThisFrame = false;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Locomotion")
    bool bGrounded = false;
};

USTRUCT(BlueprintType)
struct FArchonFactionMovementDecision
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category = "Archon|Locomotion")
    bool bShouldLaunch = false;

    // Magnitude only — direction is supplied by component using camera
    // forward at launch time.
    UPROPERTY(BlueprintReadOnly, Category = "Archon|Locomotion")
    float ForwardImpulse = 0.0f;

    UPROPERTY(BlueprintReadOnly, Category = "Archon|Locomotion")
    float VerticalImpulse = 0.0f;

    UPROPERTY(BlueprintReadOnly, Category = "Archon|Locomotion")
    FArchonFactionMovementCooldown NewCooldown;

    UPROPERTY(BlueprintReadOnly, Category = "Archon|Locomotion")
    EArchonFactionMovementVerb VerbTriggered = EArchonFactionMovementVerb::None;
};

USTRUCT(BlueprintType)
struct FArchonFactionMovementTuning
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Locomotion")
    float LaunchImpulseForward = 850.0f;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Locomotion")
    float LaunchImpulseVertical = 450.0f;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Locomotion")
    float CooldownSeconds = 3.0f;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Locomotion")
    float MinSprintHeldSeconds = 0.15f;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|Locomotion")
    bool bRequireGroundedAtLaunch = true;
};
```

## Public surface — `ArchonFactionMovementPolicyLibrary`

```cpp
#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "ArchonFactionTypes.h"
#include "ArchonFactionMovementPolicyLibrary.generated.h"

UCLASS()
class ARCHONFACTORYCANARY_API UArchonFactionMovementPolicyLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    UFUNCTION(BlueprintPure, Category = "Archon|Locomotion")
    static EArchonFactionMovementVerb GetMovementVerbForFaction(EArchonFaction Faction);

    UFUNCTION(BlueprintCallable, Category = "Archon|Locomotion")
    static FArchonFactionMovementDecision EvaluateLaunch(
        EArchonFaction Faction,
        const FArchonFactionMovementInputState& Input,
        const FArchonFactionMovementCooldown& CurrentCooldown,
        const FArchonFactionMovementTuning& Tuning);

    UFUNCTION(BlueprintCallable, Category = "Archon|Locomotion")
    static FArchonFactionMovementCooldown AdvanceCooldown(
        const FArchonFactionMovementCooldown& Current,
        float DeltaSeconds);

    UFUNCTION(BlueprintPure, Category = "Archon|Locomotion")
    static bool IsCooldownReady(const FArchonFactionMovementCooldown& Cooldown);
};
```

### Decision rules (load-bearing)

`EvaluateLaunch` returns `bShouldLaunch = true` iff ALL of:

1. `Faction == EArchonFaction::VerdantChoir` (v0 — other factions return `None` verb, decision returns no-launch).
2. `IsCooldownReady(CurrentCooldown)` is true.
3. `Input.bSprintHeld` is true.
4. `Input.SprintHeldSeconds >= Tuning.MinSprintHeldSeconds`.
5. `Input.bJumpPressedThisFrame` is true.
6. If `Tuning.bRequireGroundedAtLaunch` is true: `Input.bGrounded` is true.

On launch: `ForwardImpulse = Tuning.LaunchImpulseForward`,
`VerticalImpulse = Tuning.LaunchImpulseVertical`,
`NewCooldown = { SecondsRemaining = Tuning.CooldownSeconds, TotalSeconds = Tuning.CooldownSeconds }`,
`VerbTriggered = EArchonFactionMovementVerb::VerdantRootVault`.

`AdvanceCooldown`: subtract `DeltaSeconds` from `SecondsRemaining`, clamp to zero. `TotalSeconds` unchanged.

`IsCooldownReady`: `SecondsRemaining <= 0.0f`.

## Public surface — `ArchonFactionMovementComponent`

```cpp
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "ArchonFactionTypes.h"
#include "ArchonFactionMovementComponent.generated.h"

class ACharacter;

DECLARE_MULTICAST_DELEGATE_OneParam(FArchonFactionMovementLaunchedNative, EArchonFactionMovementVerb);

UCLASS(ClassGroup=(Archon), Blueprintable, meta=(BlueprintSpawnableComponent))
class ARCHONFACTORYCANARY_API UArchonFactionMovementComponent : public UActorComponent
{
    GENERATED_BODY()

public:
    UArchonFactionMovementComponent();

    virtual void BeginPlay() override;
    virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

    UFUNCTION(BlueprintCallable, Category = "Archon|Locomotion")
    void ConfigureFaction(EArchonFaction InFaction);

    UFUNCTION(BlueprintCallable, Category = "Archon|Locomotion")
    void NotifySprintHeld(bool bHeld);

    UFUNCTION(BlueprintCallable, Category = "Archon|Locomotion")
    void NotifyJumpPressed();

    UFUNCTION(BlueprintPure, Category = "Archon|Locomotion")
    EArchonFaction GetFaction() const { return Faction; }

    UFUNCTION(BlueprintPure, Category = "Archon|Locomotion")
    FArchonFactionMovementCooldown GetCooldown() const { return Cooldown; }

    UFUNCTION(BlueprintPure, Category = "Archon|Locomotion")
    bool IsCooldownReady() const;

    UFUNCTION(BlueprintPure, Category = "Archon|Locomotion")
    int32 GetLaunchCount() const { return LaunchCount; }

    UFUNCTION(BlueprintPure, Category = "Archon|Locomotion")
    FArchonFactionMovementTuning GetTuning() const { return Tuning; }

    UFUNCTION(BlueprintCallable, Category = "Archon|Locomotion")
    void SetTuning(const FArchonFactionMovementTuning& InTuning) { Tuning = InTuning; }

    FArchonFactionMovementLaunchedNative OnLaunched;

private:
    ACharacter* GetOwningCharacter() const;
    bool IsOwnerGrounded() const;
    FVector ComputeForwardImpulseDirection() const;

    UPROPERTY(EditAnywhere, Category = "Archon|Locomotion")
    EArchonFaction Faction = EArchonFaction::VerdantChoir;

    UPROPERTY(EditAnywhere, Category = "Archon|Locomotion")
    FArchonFactionMovementTuning Tuning;

    UPROPERTY()
    FArchonFactionMovementCooldown Cooldown;

    bool bSprintHeld = false;
    float SprintHeldSeconds = 0.0f;
    bool bJumpPressedThisFrame = false;

    int32 LaunchCount = 0;
};
```

### Component behavior

- `BeginPlay`: zero cooldown; `LaunchCount = 0`.
- `NotifySprintHeld(true)`: if `bSprintHeld` was false, set true and reset `SprintHeldSeconds = 0`.
- `NotifySprintHeld(false)`: set `bSprintHeld = false`, reset `SprintHeldSeconds = 0`.
- `NotifyJumpPressed`: set `bJumpPressedThisFrame = true`.
- `TickComponent` (per tick):
  1. Advance `SprintHeldSeconds += DeltaTime` if `bSprintHeld`.
  2. Build `FArchonFactionMovementInputState` from current state + `IsOwnerGrounded()`.
  3. Call `UArchonFactionMovementPolicyLibrary::EvaluateLaunch`.
  4. If `bShouldLaunch`:
     - Compute `Direction = ComputeForwardImpulseDirection()` (camera forward XY normalized, Z=0).
     - `Impulse = Direction * Decision.ForwardImpulse + FVector(0,0,Decision.VerticalImpulse)`.
     - Call `OwningCharacter->LaunchCharacter(Impulse, /*bXYOverride=*/false, /*bZOverride=*/false)`.
     - `Cooldown = Decision.NewCooldown`.
     - `LaunchCount++`.
     - Broadcast `OnLaunched.Broadcast(Decision.VerbTriggered)`.
  5. Else: `Cooldown = AdvanceCooldown(Cooldown, DeltaTime)`.
  6. Clear `bJumpPressedThisFrame = false`.
- `ComputeForwardImpulseDirection`: if the character has a camera, use `Camera->GetForwardVector()`'s XY normalized; else `Owner->GetActorForwardVector()`'s XY normalized. Always Z=0 so vertical impulse alone determines launch height.

### Wiring into `AArchonCanaryFpsCharacter`

In header, add:

```cpp
UPROPERTY(VisibleAnywhere, Category = "Archon|FPS")
TObjectPtr<class UArchonFactionMovementComponent> FactionMovement;
```

In constructor, `CreateDefaultSubobject` it; set `Faction = EArchonFaction::VerdantChoir`.

In `SetupPlayerInputComponent`

<!-- Local repo projection note: live wiki read on 2026-05-24 returned truncated=true, total_chars=20903, sha256=f2a7c59386470891836ae713fb67d45a9f0a079bf9a7d22873a6c95120fbde4c. Do not implement from this repo projection past this point without a full live wiki read. -->
