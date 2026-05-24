---
title: SPLITROOT C6 contract - second-60-seconds integration smoke
type: plan
status: working-draft
source_issue: 1040
request_id: WIKI-DOCS
request_kind: docs-ops
wiki_source_path: pages/plans/splitroot-c6-second-60-seconds-smoke-contract-2026-05-24.md
source_body_note: Issue filing supplied to this writer was truncated at 12000 characters.
---

# C6 contract - second-60-seconds integration smoke

[[index]] [[splitroot-second-60-seconds-combat-slice-2026-05-24]] [[splitroot-c1-combat-fundamentals-contract-2026-05-24]] [[splitroot-c2-verdant-thornsprout-bow-contract-2026-05-24]] [[splitroot-c3-lenswright-units-ai-combat-contract-2026-05-24]] [[splitroot-c4-death-respawn-loop-contract-2026-05-24]] [[splitroot-c5-command-while-you-wait-contract-2026-05-24]] [[splitroot-s6-first-60-seconds-smoke-contract-2026-05-23]]

Goal: `9171b100de33`. Rung: **2**. **Depends on C1-C5 shipping.**

**Passing this smoke = the combat anchor of rung-2 is structurally
provable.** Combined with art-direction + audio + UMG polish slices,
this unlocks the rung-2 claim against `verified_vertical_slice`.

## Files

- `Proof/second-60-seconds-smoke.ps1` (new - sibling to `first-60-seconds-smoke.ps1`)
- `Source/ArchonFactoryCanary/Public/ArchonCanaryWorldSubsystem.h` (modified - add `RunSecond60SecondsProofIfRequested`, two timer handles)
- `Source/ArchonFactoryCanary/Private/ArchonCanaryWorldSubsystem.cpp` (modified - implement the proof runner phase machine)
- `Proof/local-proof-checks.ps1` (modified - claim flags)

## Script structure

Mirror `Proof/first-60-seconds-smoke.ps1`:

```powershell
param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.7'
)

$ErrorActionPreference = 'Stop'

$projectFile = Join-Path $ProjectRoot 'ArchonFactoryCanary.uproject'
$editorCmd = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$proofDir = Join-Path $ProjectRoot 'Saved\Proof'
$logPath = Join-Path $proofDir 'last-second-60-seconds-smoke.log'
$jsonPath = Join-Path $proofDir 'last-second-60-seconds-smoke.json'

New-Item -ItemType Directory -Force -Path $proofDir | Out-Null

# Note: -ArchonRunSecond60SecondsProof IMPLIES -ArchonRunFirst60SecondsProof -
# the second-60 arc starts from the end state of the first-60 arc.
$argsList = @(
    $projectFile,
    '/Game/FirstPerson/Lvl_FirstPerson',
    '-game',
    '-NullRHI',
    '-NoSound',
    '-NoSplash',
    '-unattended',
    '-nop4',
    '-stdout',
    '-FullStdOutLogOutput',
    '-ArchonRunFirst60SecondsProof',
    '-ArchonRunSecond60SecondsProof',
    '-ExecCmds=quit'
)

# ...run editor, capture output, set $text, set $exitCode...

$result = [pscustomobject]@{
    ExitCode = $exitCode
    Map = '/Game/FirstPerson/Lvl_FirstPerson'

    # First-60 prerequisites (must still pass)
    First60ArcCompleted               = $text -match 'ArchonFactoryCanary: First60Arc completed=true'

    # Second-60 phase assertions
    Second60EnemiesSpawned            = $text -match 'ArchonFactoryCanary: Second60Enemies spawned=true bracewright=\d+ sundial=\d+'
    Second60PlayerWeaponReady         = $text -match 'ArchonFactoryCanary: Second60Player weapon=VerdantThornsproutBow ammo=\d+/3'
    Second60PlayerFiredAtEnemy        = $text -match 'ArchonFactoryCanary: Second60Player firedShots>=1'
    Second60BracewrightFiredAtPlayer  = $text -match 'ArchonFactoryCanary: Second60Bracewright firedShots>=1'
    Second60PlayerTookDamage          = $text -match 'ArchonFactoryCanary: Second60Player damageTaken>=1'
    Second60PlayerDied                = $text -match 'ArchonFactoryCanary: Second60Player died=true cause=lenswright_pressure_bolt'
    Second60ObserverPawnPossessed     = $text -match 'ArchonFactoryCanary: Second60Observer pawnPossessed=true'
    Second60CommandWhileWaitOpened    = $text -match 'ArchonFactoryCanary: Second60CommandWhileWait tableOpened=true lifeState=Dead'
    Second60CommandWhileWaitSubmitted = $text -match 'ArchonFactoryCanary: Second60CommandWhileWait orderSubmitted=true sequence=\d+'
    Second60PlayerRespawned           = $text -match 'ArchonFactoryCanary: Second60Player respawned=true lifeState=Alive'
    Second60DeadStateOrderSurvived    = $text -match 'ArchonFactoryCanary: Second60SquadOrderSurvivedRespawn lastSequence=\d+ stillMoving=true'
    Second60ArcCompleted              = $text -match 'ArchonFactoryCanary: Second60Arc completed=true durationSeconds<=60'

    QuitCommandHonored                = $text -match 'UGameEngine::HandleExitCommand'
    LogPath                           = $logPath
}

$result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $jsonPath -Encoding UTF8
$result | ConvertTo-Json -Depth 4

if (
    $exitCode -ne 0 -or
    -not $result.First60ArcCompleted -or
    -not $result.Second60EnemiesSpawned -or
    -not $result.Second60PlayerWeaponReady -or
    -not $result.Second60PlayerFiredAtEnemy -or
    -not $result.Second60BracewrightFiredAtPlayer -or
    -not $result.Second60PlayerTookDamage -or
    -not $result.Second60PlayerDied -or
    -not $result.Second60ObserverPawnPossessed -or
    -not $result.Second60CommandWhileWaitOpened -or
    -not $result.Second60CommandWhileWaitSubmitted -or
    -not $result.Second60PlayerRespawned -or
    -not $result.Second60DeadStateOrderSurvived -or
    -not $result.Second60ArcCompleted -or
    -not $result.QuitCommandHonored
) {
    exit 1
}
```

## Phase machine - `RunSecond60SecondsProofIfRequested`

Methods on `UArchonCanaryWorldSubsystem` (same pattern as the first-60
runner). Phase sequence runs synchronously after the first-60 runner
completes (since C6 depends on the first-60's blockout + visibility +
table + squad state).

| Phase | Action | Asserts -> log flags |
|---|---|---|
| `WaitForFirst60Complete` | Watch for `bFirst60ProofSequenceRan == true`. | - |
| `SpawnEnemies` | Spawn 2x `AArchonLenswrightBracewrightActor` + 1x `AArchonLenswrightSundialOpticActor` near the existing `BlockoutLenswrightGhost` location. Configure each with team 1. Configure their `AiCombatBehavior` candidate targets = player + canary squad. | `Second60Enemies spawned=true bracewright=2 sundial=1` |
| `VerifyPlayerWeaponReady` | On player's `UArchonVerdantThornsproutBow`, assert ammo = 3, `IsReady() == true`. | `Second60Player weapon=VerdantThornsproutBow ammo=3/3` |
| `PlayerFiresAtBracewright` | Programmatically call `Bow->TryFire(camera origin, direction toward nearest Bracewright)` 3 times with tick advance between to clear cycle. | `Second60Player firedShots>=1` (>=3 ideally) |
| `BracewrightFiresAtPlayer` | Tick world ~3s. The Bracewright's AI behavior should detect player (within `EngageRange = 40m`), fire. | `Second60Bracewright firedShots>=1` |
| `PlayerTakesDamage` | After Bracewright fire + projectile travel, player's `UArchonCombatHealthComponent` should have `TotalHitsTaken >= 1`. | `Second60Player damageTaken>=1` |
| `ForcePlayerDeath` | Apply direct damage to drive player to zero: `Player->Health->ApplyDirectDamage(200, LenswrightPressureBolt, 1, INDEX_NONE)`. Tick ~0.1s for state to propagate. | `Second60Player died=true cause=lenswright_pressure_bolt` |
| `VerifyObserverPawnPossessed` | After death, `Controller->GetPawn()` should be an `AArchonRespawnObserverPawn`. | `Second60Observer pawnPossessed=true` |
| `OpenTableDuringDeath` | Call `RuntimeInputBridge->PreviewRuntimeMapTable()`. Should succeed since `MayIssueMapTableCommand()` is true for Dead. | `Second60CommandWhileWait tableOpened=true lifeState=Dead` |
| `SubmitOrderDuringDeath` | Call `RuntimeInputBridge->SubmitRuntimeMapTableWidgetMoveOrderAt(<different target than first-60>, "splitroot_central_north")`. Capture the sequence number. | `Second60CommandWhileWait orderSubmitted=true sequence=N` |
| `WaitForRespawn` | Tick world ~5.5s (past `TotalRespawnSeconds`). Assert `LifeState == Alive`. | `Second60Player respawned=true lifeState=Alive` |
| `VerifyDeadStateOrderSurvived` | Inspect canary squad's `LastAppliedCommandSequence`: must equal the sequence captured during `SubmitOrderDuringDeath`. Assert squad's `OrderState == Moving` (still executing the dead-state order). | `Second60SquadOrderSurvivedRespawn lastSequence=N stillMoving=true` |
| `Complete` | Emit completion. | `Second60Arc completed=true durationSeconds<=60` |

### Failure handling

Any phase that fails an assertion or times out (60s in-game budget):

- Emit `Second60Arc failed=true phase=<phase> reason=<reason>`.
- Smoke script exits 1.

### Method shape

In `UArchonCanaryWorldSubsystem.h` (private):

```cpp
void SpawnSecond60EnemiesIfRequested();
void RunSecond60SecondsProofIfRequested();

UPROPERTY()
TArray<TObjectPtr<AArchonLenswrightBracewrightActor>> Second60Bracewrights;

UPROPERTY()
TObjectPtr<AArchonLenswrightSundialOpticActor> Second60Sundial;

bool bSecond60ProofSequenceRan = false;
```

In `.cpp`, at end of `RunFirst60SecondsProofIfRequested()`:

```cpp
RunSecond60SecondsProofIfRequested();
```

`RunSecond60SecondsProofIfRequested`:

- Gated on `-ArchonRunSecond60SecondsProof` command-line flag.
- Executes the phase machine inline (sync) like the first-60 runner.
- For the wait phases (e.g., 3s for AI fire, 5.5s for respawn), uses
  `World->GetTimerManager().SetTimer(..., interval, false)` plus a
  small phase-index advance pattern. Or simpler: drive `Tick`
  manually by advancing the world's `DeltaTime`. The existing first-60
  runner uses `FM->TickComponent(seconds, ...)` for component-level
  time advance; equivalent pattern here for health/respawn/AI components.

## `Proof/local-proof-checks.ps1` updates

```powershell
ClaimsSecond60SecondsSmoke         = $text -match 'second-60-seconds-smoke.ps1'
ClaimsSecond60ArcCompleted         = $smokeJsonSecond60.Second60ArcCompleted
ClaimsCommandWhileYouWaitDeadOrder = $smokeJsonSecond60.Second60CommandWhileWaitSubmitted -and $smokeJsonSecond60.Second60DeadStateOrderSurvived
```

Where `$smokeJsonSecond60 = Get-Content "Saved\Proof\last-second-60-seconds-smoke.json" | ConvertFrom-Json`.

## What this smoke does NOT prove

Same discipline as S6:

- **Feel.** Whether TTK feels right, whether respawn cadence feels good, whether command-while-you-wait reads as the Archon heartbeat or just as "an order got submitted." Manual playtest is the only authority.
- **Multiple humans on one team.** Single-player canary still.
- **Real production art and audio.** Placeholder pressure-bolt visual, placeholder audio.
- **Combat balance.** TTK math is in spec but feel matters more than math.
- **UMG respawn screen.** Debug log evidence only.

## Hills check

- **Proof ladder is sacred**: yes. Full arc asserted with named flags; failure mode loud (named phase + reason).
- **Standard Archon**: yes. The "dead-state order survived respawn" assertion is THE design property test; this smoke makes it auditable in CI.
- **Movement + content + faction verbs**: yes. Player uses Verdant bow, enemies use Lenswright pressure-bolt, root-vault is available (carried over from rung-1), all in one continuous arc.
- **Lenswright no gunpowder**: yes. Cause-of-death log line names `lenswright_pressure_bolt` explicitly, not a generic firearm tag.
- **Factory branch is product**: yes. The phase-machine pattern matches the first-60 runner; future games on this factory inherit "two-arc smoke" as the standard rung-2 evidence shape.

## Hex pickup

C6 depends on C1-C5 all shipping first. Order:

1. After C1 + C2 + C3 + C4 + C5 each have proof notes filed.
2. Add the new methods + state on `UArchonCanaryWorldSubsystem`.
3. Implement phase machine inline in `RunSecond60SecondsProofIfRequested`.
4. Create `Proof/second-60-seconds-smoke.ps1` per the script template above.
5. Update `Proof/local-proof-checks.ps1` with new claim flags.
6. Update `Proof/build-and-test-policy.ps1` (or chain) to also invoke `second-60-seconds-smoke.ps1` after build+test+first-60.
7. Run all four proof scripts: `build-and-test-policy.ps1`, `unreal-map-smoke.ps1`, `first-60-seconds-smoke.ps1`, `second-60-seconds-smoke.ps1`.
8. Draft proof note `pages/notes/splitroot-c6-second-60-seconds-smoke-proof-<date>.md` with **all assertions and their resolved values**.
9. Run the playtest skill (`Proof/playtest-render.ps1`) to capture screenshots through the arc - especially the dead-state observer view with table open. Update `unreal-canary-playtest`.

## Filing note

The issue body available to this writer ended after the `unreal-canary-playtest`
instruction and included the marker: "_Source wiki body truncated at 12000
characters._" This page preserves the complete source contract available in the
filing without guessing at the missing tail.
