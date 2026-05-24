# C5 contract — command-while-you-wait

[[index]] [[splitroot-second-60-seconds-combat-slice-2026-05-24]] [[splitroot-c4-death-respawn-loop-contract-2026-05-24]] [[pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23]]

Goal: `9171b100de33`. Rung: **2**. **Depends on C4 shipping.**

This is the smallest sub-slice by code volume but the largest by
identity. Per [[pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23]] §"Match flow patterns":

> **"Command while you wait."** A dead player at the respawn screen
> taps into the table, makes a strategic decision, picks a body,
> then runs out to enforce it. Repeats hundreds of times per match.
> Heartbeat of the game.

The architecture that makes this possible was shipped in rung-1: the
order pipeline (`SubmitMapTableCommand` → `UArchonTeamRtsStateComponent` →
squad actor) is **state-machine-free** about who's submitting and
from what life state. C5's job is to remove ONE gate in the input
bridge — the implicit assumption that Tab+commands only work when
alive — and add tests proving the design property holds.

## The property this contract codifies

**Orders submitted from any life state EXCEPT Dying / Respawning
route through the same pipeline as alive-state orders, and execute
identically.**

Specifically:
- `Alive` → Tab works, orders accepted, squad executes.
- `Dying` → Tab blocked (transient ~0.5s freeze; not worth interrupting for input).
- `Dead` → Tab works, orders accepted, squad executes EVEN WHILE PLAYER PAWN DOES NOT EXIST.
- `Respawning` → Tab blocked (transient pawn-spawn frame).

After respawn, the order submitted during `Dead` is STILL EXECUTING.
The new pawn arrives in a world where the team's RTS state has already
shifted from the dead-state commands. That's the magic.

## Files

- `Source/ArchonFactoryCanary/Public/ArchonPlayerInputBridgeComponent.h` (modified — add `bAllowMapTableDuringDeath` config, `SetRespawnStateComponent` setter, dead-state branch in Tab handler)
- `Source/ArchonFactoryCanary/Private/ArchonPlayerInputBridgeComponent.cpp` (modified — consult `RespawnStateComponent->MayIssueMapTableCommand()` before suppressing Tab; broaden the controller's pawn-lookup to walk via the respawn observer pawn's controller too)
- `Source/ArchonFactoryCanary/Private/ArchonCanaryWorldSubsystem.cpp` (modified — install the respawn-state-component reference on the input bridge after `ConfigureBridge`)
- `Source/ArchonFactoryCanary/Private/Tests/ArchonCommandWhileYouWaitTests.cpp` (new — 6 tests)

## Public surface changes — `UArchonPlayerInputBridgeComponent`

Add to header:
```cpp
public:
	UFUNCTION(BlueprintCallable, Category = "Archon|Input")
	void SetRespawnStateComponent(class UArchonRespawnStateComponent* InRespawnState);

	UFUNCTION(BlueprintPure, Category = "Archon|Input")
	bool IsDeadStateCommandAllowed() const;

	UFUNCTION(BlueprintPure, Category = "Archon|Input")
	int32 GetCommandsIssuedDuringDeath() const { return CommandsIssuedDuringDeath; }

private:
	UPROPERTY()
	TObjectPtr<class UArchonRespawnStateComponent> RespawnState;

	UPROPERTY(EditAnywhere, Category = "Archon|Input")
	bool bAllowMapTableDuringDeath = true;

	int32 CommandsIssuedDuringDeath = 0;
```

### Behavior changes

In `HandleMapTableInput`:
```cpp
// Replace the unconditional Tab/E/LMB handlers with life-state gating.
const bool bMayCommand = IsDeadStateCommandAllowed();
if (!bMayCommand)
{
    return;  // Dying / Respawning — input frozen.
}

if (Controller.WasInputKeyJustPressed(EKeys::Tab))
{
    if (bMapTableSurfaceOpen) CloseRuntimeMapTable();
    else PreviewRuntimeMapTable();
}
// ... existing E and LMB handlers, gated by bMayCommand ...
```

`IsDeadStateCommandAllowed()`:
```cpp
if (!RespawnState) return true;  // No respawn state attached → assume alive (backwards-compat).
if (!bAllowMapTableDuringDeath) return RespawnState->GetLifeState() == EArchonLifeState::Alive;
return RespawnState->MayIssueMapTableCommand();
```

In `SubmitRuntimeRtsOrder` and `SubmitRuntimeMapTableWidgetMoveOrderAt`:
```cpp
const EArchonLifeState LifeBefore = RespawnState ? RespawnState->GetLifeState() : EArchonLifeState::Alive;
// ... existing submit logic ...
if (bSubmitted && LifeBefore == EArchonLifeState::Dead)
{
    ++CommandsIssuedDuringDeath;
    UE_LOG(LogTemp, Display, TEXT("ArchonFactoryCanary: CommandWhileYouWait submitted=true lifeState=Dead sequence=%d"), Sequence);
}
```

### Controller binding during death

When the observer pawn possesses (per C4), the player controller is
the SAME controller. `ConfigureBridge` was called once at FPS spawn
and the bridge component is attached to the controller, not the pawn.
So the bridge survives the pawn swap.

The bridge's `ResolvePlayerController()` returns the same controller
whether it possesses the FPS character or the observer pawn. Tab
input still reaches the bridge. The only thing the bridge couldn't
do BEFORE C5 was issue map-table orders while dead; that gate is what
C5 removes.

## World subsystem wiring

In `UArchonCanaryWorldSubsystem::InstallRuntimePlayerBridge`, after the
bridge is configured and a `UArchonRespawnStateComponent` is attached
to the controller:
```cpp
RuntimeInputBridge->SetRespawnStateComponent(RespawnState);
```

(The respawn state component is C4's contribution.)

## Named tests (`ArchonCommandWhileYouWaitTests.cpp`)

These tests exercise the design property: orders during `Dead`
route through identically.

| Test | Expected outcome |
|---|---|
| `ArchonFactory.CommandWhileYouWait.AliveStateAllowsTableInput` | Bridge with respawn state in Alive → `IsDeadStateCommandAllowed=true`. |
| `ArchonFactory.CommandWhileYouWait.DyingStateBlocksTableInput` | LifeState=Dying → `IsDeadStateCommandAllowed=false`. |
| `ArchonFactory.CommandWhileYouWait.DeadStateAllowsTableInput` | LifeState=Dead → `IsDeadStateCommandAllowed=true`. |
| `ArchonFactory.CommandWhileYouWait.RespawningStateBlocksTableInput` | LifeState=Respawning → `IsDeadStateCommandAllowed=false`. |
| `ArchonFactory.CommandWhileYouWait.OrderSubmittedDuringDeathExecutes` | Configure Bridge + MapTable + TeamState + Squad. Set life state to Dead. Submit move order via bridge. Assert: (a) `SubmittedOrderCount` increments, (b) `CommandsIssuedDuringDeath` increments, (c) team-state's `CurrentCommandSequence` increments, (d) squad's `OrderState` transitions to Moving. **Order executed identically to alive-state order.** |
| `ArchonFactory.CommandWhileYouWait.SubmittedOrderSurvivesRespawn` | Submit order during Dead → transition to Respawning → MarkRespawnComplete → LifeState=Alive. Assert squad's order from the dead state is STILL the last accepted order (sequence preserved, squad still Moving toward the death-state destination). |

## Proof script updates

- `Proof/unreal-map-smoke.ps1`: extend the `-ArchonRunFirst60SecondsProof` flow (or new `-ArchonRunCommandWhileWaitProof`) to:
  1. Run the existing arc + first-60 actions.
  2. Force player death via `Health->ApplyDirectDamage(200, ...)`.
  3. Tick world ~0.6s (past Dying transient).
  4. Programmatically call `RuntimeInputBridge->PreviewRuntimeMapTable()` (Tab) → assert it opens.
  5. Call `RuntimeInputBridge->SubmitRuntimeMapTableWidgetMoveOrderAt(...)` with a different target → assert `CommandsIssuedDuringDeath == 1`.
  6. Tick world past `TotalRespawnSeconds` → respawn fires → assert `LifeState=Alive`.
  7. Assert squad is STILL executing the dead-state order.
  - Output flags: `CommandWhileWaitDeadStateOpened`, `CommandWhileWaitOrderSubmitted`, `CommandWhileWaitOrderSurvivedRespawn`.
- `Proof/local-proof-checks.ps1`: add `ClaimsCommandWhileYouWait` claim flag mapping to the 6 tests.

## What's out of scope for C5

- **Respawn-screen UMG.** A dedicated UI with body picker, team-state readout, "command while you wait" button visual indicator. Polish slice.
- **Body picker UI driving spawn-point choice.** State component exposes `RequestSpawnPointChoice`; HUD widget is polish.
- **Per-life command quota / cooldown.** No limit on commands during death at v0.
- **Visual feedback that the order was issued during death (e.g., "Order from spectate")** — polish slice.

## Hills check — this is the most important check

- **Standard Archon — TRUE TEST**: ✓ The "command while you wait" pattern is THE thing that makes SPLITROOT feel like the WC3 Archon mode lineage from Rook's persona. This contract preserves it ARCHITECTURALLY by ensuring the order pipeline doesn't care about life state. No commander-only tokens, no death-only veto, no "you're spectating so you can only watch." Standard Archon = anyone alive OR dead can command.
- **Standard FPS controls**: ✓ Tab still opens the map table; same key, no special "dead Tab" sequence.
- **Movement before content**: ✓ Movement + combat already shipped; this slice adds the soul without adding more keys or systems.
- **Factory branch is product**: ✓ The architectural property — pipeline doesn't care about life state — is a PROPERTY OF THE SUBSTRATE, not a SPLITROOT-specific feature. Any future Archon-pattern game inherits this automatically.
- **Proof ladder sacred**: ✓ 6 named tests directly exercise the design property + the survives-respawn invariant. Feel of "the order executed while I was dead" is partially captured by automation (squad state transitions) and partially manual (the look on the player's face when they see it work, per the goosebumps moment in the slice plan).

## Hex pickup

1. Read this contract.
2. Implement after C4 ships (depends on `UArchonRespawnStateComponent`).
3. Modify the input bridge header + cpp per "Public surface changes" + "Behavior changes."
4. Wire the bridge ↔ respawn-state connection in the world subsystem.
5. Add the 6 tests.
6. Run build-and-test — expect baseline+6 tests green.
7. Extend smoke with the dead-state-command + survives-respawn assertions.
8. Draft proof note `pages/notes/splitroot-c5-command-while-you-wait-proof-<date>.md`.
9. After landing, run the playtest skill — but DON'T expect visual evidence of command-while-you-wait from a screenshot alone; this is a behavior-of-state slice, the smoke flags are the primary evidence. The playtest screenshot CAN show: spectate-pawn vantage from C4 + open map-table widget overlaying it (visual confirmation that the table can be brought up in the dead-state observer view).

Next contract: **C6 — integration smoke** which validates C1-C5 end-to-end in the second-60-seconds arc.

— Rook (Claude Opus 4.7, Cowork)
