---
title: F2P telemetry component contract
type: plan
status: working-draft
source_issue: 1052
wiki_source_path: pages/plans/splitroot-f2p-telemetry-component-contract-2026-05-24.md
source_completeness: partial
---

# F2P telemetry component contract

[[index]] [[splitroot-f2p-rung-4-evidence-map-2026-05-24]] [[f2p-expansion-monetization-model-2026-05-21]] [[splitroot-h1-hero-infrastructure-contract-2026-05-24]] [[splitroot-c5-command-while-you-wait-contract-2026-05-24]]

Goal: `9171b100de33`. Rung-4 evidence-supporting work.

## Source completeness note

Issue #1052's filed source body is truncated at 12000 characters, ending
inside the named-test table. This page preserves the recoverable contract text
and marks the missing tail rather than reconstructing unverified acceptance
criteria.

## What this contract does

`UArchonF2pTelemetryComponent` collects local-only behavioral data
during playtest sessions so the F2P model's perception checks (rung-4
evidence item #6) have a quantitative substrate alongside qualitative
playtester feedback.

**Local-only at v0**: data lands in `Saved/Telemetry/playtest-*.json`,
NOT sent to a Steam telemetry endpoint. Steam upload integration is
rung-9 launch-slice work. Local files are sufficient for Rook + Jonathan
playtest reviews.

**Privacy discipline**: no personally identifiable information. No
external network egress. The component is purely behavioral counters
+ event timestamps, all stored in plain-text JSON the player can
inspect.

## Why telemetry matters for rung-4

F2P evidence item #6 in [[splitroot-f2p-rung-4-evidence-map-2026-05-24]]:

> Playtest/perception proof - testers do not broadly interpret the
> model as unfair, bait-and-switch, or pay-to-win.

Qualitative feedback ("the playtester said it felt fair") is necessary
but not sufficient. Behavioral telemetry surfaces things players don't
articulate:

- Did free players actually USE the table-preview, or did they ignore it?
- Did paid players USE live RTS commands, or did they buy and not engage with that lane?
- Did command-while-you-wait happen ONCE per match, or hundreds (as the design extensions predict)?
- Did free players quit at HIGHER rates than paid? (signals model is felt as paywall)
- Did dead-state-table-open rate correlate with match duration? (signals heartbeat is felt as engaging)

A 10-match playtest with this telemetry produces a small dataset Rook
or Jonathan can review to spot model failures BEFORE shipping.

## Files

- `Source/ArchonFactoryCanary/Public/ArchonF2pTelemetryTypes.h` (new)
- `Source/ArchonFactoryCanary/Public/ArchonF2pTelemetryComponent.h` (new)
- `Source/ArchonFactoryCanary/Private/ArchonF2pTelemetryComponent.cpp` (new)
- `Source/ArchonFactoryCanary/Private/Tests/ArchonF2pTelemetryTests.cpp` (new - 8 tests)

## Public surface - `ArchonF2pTelemetryTypes.h`

```cpp
#pragma once

#include "CoreMinimal.h"
#include "ArchonF2pTelemetryTypes.generated.h"

UENUM(BlueprintType)
enum class EArchonF2pEntitlementContext : uint8
{
    Unknown UMETA(DisplayName = "Unknown"),
    OfflineFullFree UMETA(DisplayName = "Offline (full free)"),
    LanFullFree UMETA(DisplayName = "LAN (full free)"),
    PrivateHostFullFree UMETA(DisplayName = "Private Host (full free)"),
    SteamOnlineFree UMETA(DisplayName = "Steam Online (free - preview)"),
    SteamOnlinePaid UMETA(DisplayName = "Steam Online (paid - live RTS)")
};

USTRUCT(BlueprintType)
struct FArchonF2pTelemetryEvent
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|F2pTelemetry")
    FName EventId;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|F2pTelemetry")
    double TimestampSeconds = 0.0;  // GetWorld()->GetTimeSeconds()

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|F2pTelemetry")
    EArchonF2pEntitlementContext EntitlementContext = EArchonF2pEntitlementContext::Unknown;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Archon|F2pTelemetry")
    TMap<FName, FString> EventTags;  // Free-form key/values (squad_id, life_state, etc.)
};

USTRUCT(BlueprintType)
struct FArchonF2pTelemetrySessionSummary
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category = "Archon|F2pTelemetry")
    FName SessionId;

    UPROPERTY(BlueprintReadOnly, Category = "Archon|F2pTelemetry")
    double SessionDurationSeconds = 0.0;

    UPROPERTY(BlueprintReadOnly, Category = "Archon|F2pTelemetry")
    EArchonF2pEntitlementContext SessionContext = EArchonF2pEntitlementContext::Unknown;

    UPROPERTY(BlueprintReadOnly, Category = "Archon|F2pTelemetry")
    int32 TotalEvents = 0;

    UPROPERTY(BlueprintReadOnly, Category = "Archon|F2pTelemetry")
    int32 TableOpenCount = 0;

    UPROPERTY(BlueprintReadOnly, Category = "Archon|F2pTelemetry")
    int32 TableOpenWhileDeadCount = 0;

    UPROPERTY(BlueprintReadOnly, Category = "Archon|F2pTelemetry")
    int32 OrderSubmittedCount = 0;

    UPROPERTY(BlueprintReadOnly, Category = "Archon|F2pTelemetry")
    int32 OrderSubmittedWhileDeadCount = 0;

    UPROPERTY(BlueprintReadOnly, Category = "Archon|F2pTelemetry")
    int32 OrderPreviewBlockedCount = 0;  // SteamOnlineFree attempt that was preview-only

    UPROPERTY(BlueprintReadOnly, Category = "Archon|F2pTelemetry")
    int32 PlayerDeathCount = 0;

    UPROPERTY(BlueprintReadOnly, Category = "Archon|F2pTelemetry")
    int32 HeroSpawnCount = 0;

    UPROPERTY(BlueprintReadOnly, Category = "Archon|F2pTelemetry")
    int32 MatchAbandonCount = 0;  // Player quit mid-match (perception signal)
};
```

## Public surface - `UArchonF2pTelemetryComponent`

```cpp
UCLASS(ClassGroup=(Archon), Blueprintable, meta=(BlueprintSpawnableComponent))
class ARCHONFACTORYCANARY_API UArchonF2pTelemetryComponent : public UActorComponent
{
    GENERATED_BODY()

public:
    UArchonF2pTelemetryComponent();

    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

    UFUNCTION(BlueprintCallable, Category = "Archon|F2pTelemetry")
    void StartSession(FName InSessionId, EArchonF2pEntitlementContext InContext);

    UFUNCTION(BlueprintCallable, Category = "Archon|F2pTelemetry")
    void EndSession();

    UFUNCTION(BlueprintCallable, Category = "Archon|F2pTelemetry")
    void RecordEvent(const FArchonF2pTelemetryEvent& Event);

    // Convenience wrappers for the canonical event types - keeps event-id strings consistent.
    UFUNCTION(BlueprintCallable, Category = "Archon|F2pTelemetry")
    void RecordTableOpen();

    UFUNCTION(BlueprintCallable, Category = "Archon|F2pTelemetry")
    void RecordTableOpenWhileDead();

    UFUNCTION(BlueprintCallable, Category = "Archon|F2pTelemetry")
    void RecordOrderSubmitted(FName SquadId, bool bIssuedWhileDead);

    UFUNCTION(BlueprintCallable, Category = "Archon|F2pTelemetry")
    void RecordOrderPreviewBlocked(FName SquadId);

    UFUNCTION(BlueprintCallable, Category = "Archon|F2pTelemetry")
    void RecordPlayerDeath(FName KillerName);

    UFUNCTION(BlueprintCallable, Category = "Archon|F2pTelemetry")
    void RecordHeroSpawn(FName HeroFactionName);

    UFUNCTION(BlueprintCallable, Category = "Archon|F2pTelemetry")
    void RecordMatchAbandon();

    UFUNCTION(BlueprintPure, Category = "Archon|F2pTelemetry")
    FArchonF2pTelemetrySessionSummary GetCurrentSessionSummary() const;

    UFUNCTION(BlueprintPure, Category = "Archon|F2pTelemetry")
    TArray<FArchonF2pTelemetryEvent> GetSessionEvents() const { return Events; }

    // Write the current session's events + summary to Saved/Telemetry/<sessionId>.json
    UFUNCTION(BlueprintCallable, Category = "Archon|F2pTelemetry")
    bool FlushToDisk();

private:
    UPROPERTY()
    FName SessionId;

    UPROPERTY()
    EArchonF2pEntitlementContext SessionContext = EArchonF2pEntitlementContext::Unknown;

    UPROPERTY()
    double SessionStartTimeSeconds = 0.0;

    UPROPERTY()
    bool bSessionActive = false;

    UPROPERTY()
    TArray<FArchonF2pTelemetryEvent> Events;
};
```

### Behavior

- `StartSession(id, context)`: capture session id + context + start time; set `bSessionActive=true`.
- `EndSession()`: set `bSessionActive=false`; call `FlushToDisk` automatically.
- `RecordEvent(event)`: append to `Events` array; auto-fill `TimestampSeconds` from world time + `EntitlementContext` from `SessionContext` if not already set on the event.
- Convenience recorders (`RecordTableOpen`, etc.): build a canonical event with the appropriate `EventId` (e.g. `table_open`, `table_open_while_dead`, `order_submitted`, `order_preview_blocked`, `player_death`, `hero_spawn`, `match_abandon`).
- `GetCurrentSessionSummary()`: aggregate events into summary counters (count by event-id).
- `FlushToDisk()`: serialize `Events` + summary to `Saved/Telemetry/<SessionId>.json`. Create directory if absent. Return true on success.

### Integration hooks

- `UArchonPlayerInputBridgeComponent::PreviewRuntimeMapTable` calls `RecordTableOpen` / `RecordTableOpenWhileDead` based on life-state.
- `UArchonPlayerInputBridgeComponent::SubmitRuntimeRtsOrder` calls `RecordOrderSubmitted` (with `bIssuedWhileDead = (LifeState == Dead)`).
- `UArchonMapTablePolicyLibrary::EvaluateMapTableCommand` returning preview-only decision triggers a `RecordOrderPreviewBlocked` via the bridge.
- `UArchonCombatHealthComponent::OnDeath` calls `RecordPlayerDeath`.
- Future hero spawn flow calls `RecordHeroSpawn`.
- Quit-mid-match (player closes the game) triggers `EndSession` -> `FlushToDisk` via `EndPlay`.

These hooks are added in this contract; the relevant components get one-line `Telemetry->RecordX()` calls at the right moments.

## File output format - `Saved/Telemetry/<sessionId>.json`

```json
{
  "schema": "archon.f2p_telemetry.session.v1",
  "session_id": "playtest_2026_05_24_2030z_rook",
  "context": "PrivateHostFullFree",
  "session_start_unix": 1748637000,
  "session_duration_seconds": 423.5,
  "summary": {
    "total_events": 47,
    "table_open_count": 11,
    "table_open_while_dead_count": 7,
    "order_submitted_count": 23,
    "order_submitted_while_dead_count": 5,
    "order_preview_blocked_count": 0,
    "player_death_count": 4,
    "hero_spawn_count": 1,
    "match_abandon_count": 0
  },
  "events": [
    {
      "event_id": "table_open",
      "timestamp_seconds": 12.3,
      "entitlement_context": "PrivateHostFullFree",
      "event_tags": {}
    },
    {
      "event_id": "order_submitted",
      "timestamp_seconds": 14.7,
      "entitlement_context": "PrivateHostFullFree",
      "event_tags": {
        "squad_id": "canary_squad",
        "while_dead": "false"
      }
    }
  ]
}
```

After a playtest, Jonathan or Rook can read these JSONs (or compute
aggregates across multiple session files) to validate the perception
hypothesis.

## Privacy + non-misleading guarantees

- **No PII**: session IDs are caller-supplied (Rook supplies "playtest_<date>_<name>" for tracking; production play would use Steam UID or anonymized hash if/when network-uploaded - out of scope for v0).
- **No external network calls** at this contract's scope. Component writes to local disk only.
- **All data inspectable**: JSON in `Saved/Telemetry/` is plain text the player can read, modify, or delete.
- **No anti-cheat coupling**: this is BEHAVIORAL telemetry for design-fairness measurement, not cheat-detection. Per Rook persona "Hills" and standard-Archon team-trust premise, no anti-cheat.

## Named tests (8) - `ArchonF2pTelemetryTests.cpp`

| Test | Expected outcome |
|---|---|
| `ArchonFactory.F2pTelemetry.StartSessionInitializesCounters` | After `StartSession`, summary counters all zero, `bSessionActive=true`. |
| `ArchonFactory.F2pTelemetry.RecordTableOpenIncrementsCount` | Call `RecordTableOpen` 3 times; summary has TableOpenCount=3, TotalEvents=3. |
| `ArchonFactory.F2pTelemetry.TableOpenWhileDeadIsSeparateCounter` | `RecordTableOpenWhileDead` increments TableOpenWhileDeadCount but NOT TableOpenCount. (Each measurement isolated.) |
| `ArchonFactory.F2pTelemetry.OrderSubmittedWhileDeadFlagged` | `RecordOrderSubmitted("squad1", bIssuedWhileDead=true)` increments BOTH OrderSubmittedCount AND OrderSubmittedWhileDeadCount. |
| `ArchonFactory.F2pTelemetry.ContextPropagatesToEvent` | StartSession with context=SteamOnlineFree; RecordEvent with default-init context; flushed event has EntitlementContext=SteamOnlineFree (inherited from session). |

Remaining named-test rows and any trailing contract sections were not present
in issue #1052's recoverable source body.
