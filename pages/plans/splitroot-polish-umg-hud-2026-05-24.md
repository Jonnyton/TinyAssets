---
title: SPLITROOT polish — UMG HUD (rung-2 final gate; health/ammo/respawn/squad/body-picker widgets)
type: plan
author: Rook (Claude Opus 4.7 lead session, Cowork)
author_org: anthropic
author_provider: cowork
authored_at_utc: 2026-05-24T10:50:00Z
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
  - pages/plans/splitroot-polish-art-direction-2026-05-24.md
  - pages/plans/splitroot-polish-audio-direction-2026-05-24.md
  - pages/plans/splitroot-second-60-seconds-combat-slice-2026-05-24.md
  - pages/plans/splitroot-c4-death-respawn-loop-contract-2026-05-24.md
  - pages/plans/splitroot-c5-command-while-you-wait-contract-2026-05-24.md
  - pages/plans/splitroot-s3-map-table-widget-contract-2026-05-23.md
sources:
  - pages/plans/splitroot-polish-art-direction-2026-05-24.md §"P5 — HUD palette discipline"
  - pages/plans/splitroot-c4-death-respawn-loop-contract-2026-05-24.md (state component exposes timer + spawn-point data for body picker)
  - pages/plans/splitroot-c5-command-while-you-wait-contract-2026-05-24.md (the glowing Tab button moment)
  - pages/notes/pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23.md §"FPS feel doctrine" #8 (respawn screen as strategic moment) + §"Map table — shared-control conflict resolution rules" (per-player colored arrows, last command + issuing player handle)
  - local Cowork session 2026-05-24 (Rook continuing rung-2 prep — final rung-2 gate plan)
tags: [splitroot, plan, polish, umg-hud, rung-2, health, ammo, respawn-timer, squad-state, body-picker, kill-feed, rook-authored]
---

# Polish — UMG HUD

[[index]] [[splitroot-polish-art-direction-2026-05-24]] [[splitroot-polish-audio-direction-2026-05-24]] [[splitroot-second-60-seconds-combat-slice-2026-05-24]] [[splitroot-c4-death-respawn-loop-contract-2026-05-24]] [[splitroot-c5-command-while-you-wait-contract-2026-05-24]]

Goal: `9171b100de33`. Target rung: **2 (Verified vertical slice)**.

**This is the fourth and final rung-2 gate slice plan.** After this
lands, rung-2 implementation work is fully scoped: combat C1-C6 +
art polish + audio polish + UMG HUD polish + manual playtest →
rung-2 claim.

## What's wrong without UMG HUD

Without a real HUD:
- Players can't see their health (must die to know they took damage).
- Players can't see ammo (must fire to know).
- Respawn screen is text-render on the map-table actor — readable but unspeakable.
- Command-while-you-wait moment has NO visual prompt ("Tab — open table" doesn't glow when you're dead).
- Kill-feed is log-only — players don't know who killed whom in the moment.

At rung-2, "representative" doesn't mean polished UI. It means
**enough visual feedback that the player's decisions are informed
without reading the dev log**.

## Widget inventory (8 widgets, ~all small)

| Widget | C++ base | Purpose | Always-visible |
|---|---|---|---|
| `UArchonHudRootWidget` | `UUserWidget` | Composite root; conditionally shows the other widgets based on life state | Yes |
| `UArchonHealthBarWidget` | `UUserWidget` | Player health bar + numeric | Alive |
| `UArchonAmmoWidget` | `UUserWidget` | Current weapon ammo / capacity + reload state | Alive |
| `UArchonReticleWidget` | `UUserWidget` | Crosshair with hit-confirm flash | Alive |
| `UArchonSquadStateWidget` | `UUserWidget` | Allied squads list with last command + sequence + issuing player | Alive |
| `UArchonRespawnScreenWidget` | `UUserWidget` | Body picker + respawn timer + team-state readout + glowing "Tab — open table" button | Dead |
| `UArchonKillFeedWidget` | `UUserWidget` | Recent kill-feed entries (faction-tinted) | Always |
| `UArchonStrategicEventBannerWidget` | `UUserWidget` | Brief banner for strategic events (resource flip, hero unlock, base under attack) | Always (transient) |

All eight inherit a shared base for faction-tint plumbing:

```cpp
UCLASS(Abstract, Blueprintable)
class ARCHONFACTORYCANARY_API UArchonFactionTintedWidget : public UUserWidget
{
public:
    UFUNCTION(BlueprintCallable, Category = "Archon|HUD")
    void ConfigureFactionTint(EArchonFaction Faction);

    UFUNCTION(BlueprintPure, Category = "Archon|HUD")
    FLinearColor GetPrimaryTint() const;

    UFUNCTION(BlueprintPure, Category = "Archon|HUD")
    FLinearColor GetSecondaryTint() const;

    UFUNCTION(BlueprintPure, Category = "Archon|HUD")
    FLinearColor GetAccentTint() const;

protected:
    UFUNCTION(BlueprintImplementableEvent, Category = "Archon|HUD")
    void OnFactionTintChangedBP();

    UPROPERTY()
    EArchonFaction Faction = EArchonFaction::None;
};
```

`GetPrimaryTint` / etc. delegate to `UArchonFactionMaterialBuilder::GetFactionColor`
from the art-direction polish plan — single source of truth for the
faction palette. The UMG widgets use these in their BP layouts via
`OnFactionTintChangedBP` to recolor backgrounds, accents, fills.

## Per-widget data sources

| Widget | Polls / binds to |
|---|---|
| `UArchonHealthBarWidget` | `UArchonCombatHealthComponent::GetCurrentHealth()` + `GetMaxHealth()` + `OnHealthChanged` delegate |
| `UArchonAmmoWidget` | `UArchonRangedWeaponComponent::GetState()` + `GetStats()` + `OnWeaponFired` + `OnReloadStarted` + `OnReloadCompleted` |
| `UArchonReticleWidget` | `OnWeaponFired` for fire-flash; `OnHitConfirm` delegate (TBD on combat health component — small additive C1 follow-up: emit hit-confirm event back to instigator) |
| `UArchonSquadStateWidget` | `UArchonTeamRtsStateComponent::OnCommandAccepted` + `GetLastAcceptedCommandIntent()` per squad |
| `UArchonRespawnScreenWidget` | `UArchonRespawnStateComponent::GetState()` + `GetAvailableSpawnPoints()` + `OnLifeStateChanged` + team-state aggregator |
| `UArchonKillFeedWidget` | Subscribes to a NEW broadcaster: `UArchonKillFeedBroadcasterComponent` that emits events from each death |
| `UArchonStrategicEventBannerWidget` | Subscribes to `UArchonStrategicAudioBroadcasterComponent` (from audio plan — same event stream feeds visual banner) |

All widget bindings are server-replicated state OR delegate
subscriptions on local replicated component instances. No
client-authoritative state.

## Specific widget specs

### `UArchonRespawnScreenWidget` (the most important)

This is where command-while-you-wait visually lives. Per design
extensions §"FPS feel doctrine" #8: "Respawn screen as strategic
moment."

Layout (placeholder; final UMG by future polish):

```
+---------------------------------------------------+
|  TEAM STATE                                       |
|  Supply: 1240  | Sites: 2 (Verdant +1, ←C, +R→)  |
|  Core HP: 88%  | Hero: not yet unlocked           |
|                                                   |
|  RECENT                                           |
|  → Verdant Thornbound → overwatch (by you, 12s)  |
|  → Player Rook → KIA by Lenswright Bracewright    |
|  → Splitroot Central captured by Lenswright       |
+---------------------------------------------------+
|                                                   |
|  RESPAWN IN: ████░░░░░ 3.2s                       |
|                                                   |
|  BODY PICKER                                      |
|  [A] Base Spawn (safe, +0s)         ◄ selected    |
|  [B] Squad-A Forward Spawn (+1.5s)                |
|                                                   |
+---------------------------------------------------+
|                                                   |
|     [ TAB — OPEN TABLE ]   ← glows pulsing        |
|                                                   |
+---------------------------------------------------+
```

The **"Tab — open table" button glows pulsing** while in Dead state.
That visual is the design's heartbeat. When the player Tabs from
this screen, the table widget opens on top — the respawn screen
stays visible behind it; players can drag-box, right-click, then
close the table to return to the respawn screen + pick a body.

Behavior:
- On `LifeState=Dead`: widget fades in over 0.3s.
- Timer bar updates every tick.
- Body picker entries: read from `GetAvailableSpawnPoints()`; show name + time penalty. Up/Down keys cycle; Enter confirms (calls `RespawnState->RequestSpawnPointChoice`).
- "Tab — open table" button: animated pulse (BP-driven). When player presses Tab, opens the existing `UArchonMapTableWidget` overlaying this respawn screen.
- On `LifeState=Alive`: widget fades out over 0.2s.

### `UArchonSquadStateWidget` (the Archon transparency)

Per design extensions §"Map table — shared-control conflict resolution":

> Each AI squad's HUD shows last command + issuing player handle.
> "Move → Central Resource (by Rook, 2.1s ago)."

Bottom-left of the FPS HUD. One entry per allied squad. Each entry:

```
[●●●●] Thornbound A  →  Move (by Rook, 4s)
[●●○○] Thornbound B  →  Overwatch (by Jonathan, 12s)
[●○○○] Thornbound C  →  Engage (by Rook, 1s)
```

Dots = squad strength (filled / total). Color of dots = squad's
faction tint. Issuing player handle uses the per-player selection
color from the map table widget (when MP lands; v0 single-player =
"you").

This widget is the **visual continuation** of the order pipeline from
the table into the FPS view. The player can see at all times what
their team's squads are doing without opening the table.

### `UArchonKillFeedWidget`

Top-right. Recent kill entries fade in / fade out after 6s.

```
[Verdant Player Rook]  [Verdant Living Arrow]  [Lenswright Bracewright]
[Lenswright Bracewright]  [Lenswright Pressure Bolt]  [Verdant Player Rook]
```

Each entry: instigator name (faction-tinted) — weapon icon —
victim name (faction-tinted). Pressure-bolt cue icon is the
cyan-tinted bolt mesh, NOT a gun icon. Hill check.

### `UArchonStrategicEventBannerWidget`

Top-center, transient. Cross-fades for ~3s on strategic events:

```
        ╔══════════════════════════════════╗
        ║   CENTRAL SPLITROOT  CAPTURED    ║
        ║   by Lenswright Compact          ║
        ╚══════════════════════════════════╝
```

Tinted in the event's faction palette. Plays alongside the
strategic-layer audio cue.

## Build.cs and dependency

Add `UMG`, `Slate`, `SlateCore` to `Source/ArchonFactoryCanary/ArchonFactoryCanary.Build.cs`
public dependencies (already added per S3b widget plan — verify still present
post-Hex parallel work).

## Implementation contracts

H1 — `UArchonFactionTintedWidget` shared base (small; ~5 tests).
H2 — `UArchonHealthBarWidget` + `UArchonAmmoWidget` + `UArchonReticleWidget` (FPS HUD core; ~8 tests for state-binding).
H3 — `UArchonSquadStateWidget` (~5 tests for command-display formatting).
H4 — `UArchonRespawnScreenWidget` (the big one; ~10 tests for body-picker + timer + Tab-button states).
H5 — `UArchonKillFeedWidget` (~4 tests for entry insertion + fade).
H6 — `UArchonStrategicEventBannerWidget` (~3 tests for event → banner mapping).
H7 — `UArchonHudRootWidget` (composite that conditionally shows the others by life state).
H8 — Wire `UArchonHudRootWidget` into the player controller / pawn — created on `BeginPlay`, `AddToViewport`.

Most widgets are SMALL — the BP layouts (final visual look) defer
to a later polish slice; the C++ surface + data binding + faction
tint application is the rung-2 deliverable. A widget showing
"Health: 150 / 150" in default Slate font is acceptable rung-2
polish; designed visual aesthetic is rung-4+.

## Named tests target (~35 total)

Each widget's tests cover:
- Construction + initial state.
- Data-source binding (mock the source component, assert widget reads it correctly).
- Faction tint application (assert `OnFactionTintChangedBP` is called when faction set).
- State transitions (e.g., respawn-screen Alive↔Dead, ammo Ready↔Reloading).
- Edge cases per widget (health at 0, ammo at empty, no available spawn points, kill feed full).

## Proof script updates

- `Proof/local-proof-checks.ps1`: claim flag `ClaimsHudPolishSurface` mapping to the ~35 widget tests.
- `Proof/first-60-seconds-smoke.ps1`: no change — HUD widgets are visual; smoke is log-based.
- `Proof/playtest-render.ps1`: enable HUD rendering in the captured screenshot. Should now SEE the health bar + ammo + reticle in the screenshot. Iteration target.

## Cross-iteration with `unreal-canary-playtest` skill

After H1-H7 ship, the playtest skill's screenshot SHOULD show:

- Health bar bottom-left, faction-tinted.
- Ammo bottom-right.
- Reticle center.
- Squad state widget bottom-left below health.

After H4 ships + a forced-death proof:
- Respawn screen overlaying spectate view.
- Body picker visible.
- "Tab — open table" button pulsing.

Update playtest learning log accordingly. By the time all four
rung-2 gate slices land (combat + art + audio + HUD), the playtest
screenshot reads as "a game," not "a debug viewer."

## Hills check

- **Standard FPS controls / HUD**: ✓ Health bottom-left, ammo bottom-right, reticle center, kill-feed top-right, banners top-center — standard FPS layout.
- **Standard Archon transparency**: ✓ `UArchonSquadStateWidget` exposes who-ordered-what-when at all times, fulfilling the design extensions' "Each AI squad's HUD shows last command + issuing player handle" requirement.
- **Faction palettes uniform**: ✓ Every widget tints through `UArchonFactionMaterialBuilder::GetFactionColor`. No hardcoded hex anywhere; one source of truth.
- **Paid heroes horizontal-only**: ✓ HUD widgets don't differentiate paid-pack heroes from free heroes other than via `FArchonHeroPresentation.DisplayName` and `AccentColorOverride`. Same widget renders both; no "paid-only" widget element. Gameplay-affecting HUD elements (health, ammo, cooldowns) read from locked stats.
- **Lenswright no gunpowder** — HUD: ✓ Kill-feed weapon icons for Lenswright are the cyan-tinted pressure-bolt mesh, NOT firearm. Cross-review check.
- **Movement before content**: ✓ HUD doesn't introduce new mechanics; it surfaces existing systems.
- **Factory branch is product**: ✓ Every widget inherits `UArchonFactionTintedWidget`. Future games on the substrate add new widgets that ALSO inherit; faction-palette discipline propagates automatically.
- **Proof ladder sacred**: ✓ ~35 named tests for widget surface + data binding. Visual feel of the HUD waits for manual playtest.

## What this slice does NOT cover

- **Final visual design** (typography, iconography, color depth beyond palette tints).
- **Animation polish** (timer bar smooth-tween, banner slide-in curves, kill-feed cascade) — engine defaults at rung-2.
- **Localization** — English-only at rung-2.
- **Accessibility** (colorblind palettes, font scaling) — rung-4+.
- **Spectator-mode HUD** (different layout for watching match recordings) — out of scope.
- **Hero ability cooldown widgets** — pairs with hero implementation; rung-3.

## Implementation prerequisite

C1 combat fundamentals + C4 death/respawn must ship FIRST so the
widgets have data sources to bi

<!-- Repo projection note, 2026-05-24 UTC: public wiki action=read returned truncated=true, total_chars=15768, source sha256=4b7e6d57df90e3849bcb4a34a50b70e070ec6b9c06b6f98949178eef7dd59e7d. The final upstream tail was not available through the bounded read surface in this runner. -->
