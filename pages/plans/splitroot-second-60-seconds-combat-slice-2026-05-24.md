---
title: Second 60 Seconds - combat slice
type: plan
status: working-draft
source_issue: 1042
wiki_source_path: pages/plans/splitroot-second-60-seconds-combat-slice-2026-05-24.md
wiki_source_updated: 2026-05-24T12:46:35Z
wiki_source_sha256: dc8f2edc6d099f31ae964a3ff20125389772a2aee54c9f758d1b649e6a706cb0
---

# Second 60 Seconds — combat slice

[[index]] [[splitroot-first-60-seconds-slice-2026-05-23]] [[splitroot-rung-1-local-playable-prototype-earned-2026-05-23]] [[pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23]] [[pages-research-splitroot-rts-fps-hybrid-lineage-research-2026-05-23]]

Goal: `9171b100de33`. Target gate rung: **2 (Verified vertical slice)**.

## The goosebumps moment this slice has to land

Player arrives at the central splitroot (end of [[splitroot-first-60-seconds-slice-2026-05-23]]).
Their Thornbound squad takes overwatch. **A Lenswright Bracewright
detachment** emerges from the brass-oxblood ghost-keep to the south-east
— but it's no longer a ghost. Sight has reached it. Two Bracewrights
plus a Sundial Optic-scout cross the field, pressure-bolts hissing
forward.

The player swings up their **Verdant Thornsprout Bow** — a living wood
bow whose nocked arrow visibly grows from bramble at the limb. They
loose three living arrows. Two land — green leaf-flutter at impact —
one drops a Bracewright. The squad fires alongside. The other
Bracewright takes cover behind the splitroot trunk.

The player charges. A pressure-bolt thumps into their shoulder. Camera
kicks. Screen-edge briar pulse (the Verdant "you're bleeding" feedback).
They get one more arrow off before the second Bracewright's bolt drops
them. **Black-out.**

**Respawn screen.** Top-left: team supply, sites controlled, core HP,
recent events ("Thornbound squad → overwatch at Central Splitroot,"
"Player Rook → KIA by Lenswright Bracewright"). Bottom-right: body
picker — three friendly squads alive, two more in production. A
**"Tab — open table"** button glows.

They tap Tab. World goes top-down. They see the engagement: the
surviving Bracewright is reloading behind the splitroot trunk, exposed
flank visible from a second Thornbound squad spawned at base. They
drag-box that second squad, right-click flank — they see the order
land before they've even picked a respawn body. They pick the closest
body. World snaps back to FPS. They're now alongside the second squad,
rounding the flank. The Bracewright dies before reloading. The Sundial
falls back.

Player blinks: they were dead 8 seconds ago. The game kept going. The
order they gave from the respawn screen is already playing out. They
issued strategy through death — that's Archon.

## Why this slice is the right slice

- It exercises every system rung-1 didn't: damage model, hit feedback,
  weapon-fire authority, death state, respawn timer, body picker,
  command-while-you-wait, enemy unit, squad combat engagement, faction-
  weapon distinction (Verdant living arrow vs Lenswright pressure-bolt).
- It targets the **emotional core** of Archon: dying without losing
  strategic agency. The first 60 seconds proved you could Tab into
  the table from FPS; this slice proves you can Tab into the table
  from the *respawn screen*, which is the heartbeat per
  [[pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23]] §"Match flow patterns."
- It deliberately stays SINGLE-FACTION-VS-SINGLE-FACTION (Verdant vs
  Lenswright). Kinwild remains deferred for the THIRD slice.
- It honors the Lenswright "no gunpowder" hill explicitly — pressure-bolt
  crossbows + alchemical fire, not firearms.
- It earns rung-2 by adding the missing dimensions: combat, death,
  respawn. After this slice, the only gaps to rung-2 are real art +
  representative audio + UI polish, which are scoped as separate slices.

## Hard cuts from this slice

- **Heroes** (`Briar Saint`, `Master Artificer`) — deferred to the third slice.
- **Kinwild faction** (units, weapon, movement integrated into combat) — deferred to the fourth slice; [[splitroot-kinwild-bound-leap-contract-2026-05-24]] is the prep.
- **Multiplayer / network** — single-player canary still. Order payload tracks `issuingPlayer` so future MP is a small change.
- **Multiple weapon types per faction.** One weapon per playable faction this slice.
- **Site capture mechanics.** Central splitroot is still geometry, not a captureable resource node.
- **Production / supply / training economy.** Squads pre-spawn at start; no real-time training.
- **Vehicles, mounts, abilities, faction powers.** All deferred.
- **Real production art and audio.** Placeholder hit decals, placeholder bowstring sound, placeholder pressure-vent sound. Functional first; polish later.
- **Real respawn UI.** A debug HUD shows the body-picker info as text; the visual UMG widget is a polish slice.
- **Squad voice-line acknowledgments.** Placeholder text-render lines only ("ENGAGING", "DOWN").

## Sub-slices (six — C1 through C6)

Each sub-slice has its own contract page Rook authors next; Hex
implements against. Mirror the S1-S6 pattern that earned rung-1.

### C1 — Combat fundamentals (damage, health, hit registration)

The load-bearing piece. Pure policy library + replicated state
component. Hex implements after Rook contract lands.

Native seam shape:
- `ArchonCombatPolicyLibrary` — pure C++: given
  `{shotDirection, hitTarget, weaponDamage, armorModifier, falloff}`,
  return `{shouldHit, finalDamage, hitLocation, hitType}`.
  Server-authoritative; client-side prediction is a polish concern.
- `UArchonCombatHealthComponent` — runtime: HP pool, damage application,
  death event, server-authoritative. Replicated. Emits `OnDamaged`,
  `OnDeath` native delegates.
- `ArchonCombatTypes` — UENUMs (`EHitType`, `EDamageType`,
  `EArchonWeaponClass`), USTRUCTs (`FArchonShotPayload`, `FArchonHitResult`).

Damage model defaults (resolves design-doc TTK 3-6s):
- Default player HP: **150**.
- Default unit HP (Thornbound, Bracewright): **80**.
- Verdant living arrow: **35 dmg body, 80 dmg head**, falloff start 30m, falloff end 60m, min damage 12.
- Lenswright pressure-bolt: **40 dmg body, 90 dmg head**, falloff start 25m, falloff end 50m, min damage 15.
- Per-shot fire cycle: ~1.2s (bow nock + draw + release).
- Armor modifier: 1.0 default (heroes later add 0.7 or 1.3).

TTK check: 150hp player taking 35dmg arrows = ~4.3 hits to kill. At 1.2s cycle, ~5.2s combat time. Within 3-6s target.

### C2 — Verdant Thornsprout Bow (player weapon)

`UArchonVerdantThornsproutBow` ActorComponent on the FPS character.
Three-shot quiver (placeholder; not real magazine system). Reload =
1.8s. Living-arrow projectile that pursues a straight line, no
gravity at v0 (gravity arc is polish).

Native seam:
- `UArchonWeaponPolicyLibrary` — pure: fire rate gate, reload state, ammo check.
- `UArchonRangedWeaponComponent` — runtime: holds ammo state, accepts fire input, spawns projectile, applies hit via `ArchonCombatPolicyLibrary`.
- `AArchonArrowProjectile` — actor: straight-line travel, hit detection, calls `UArchonCombatHealthComponent::ApplyDamage` on hit.

Faction-specific shape:
- Verdant arrows: green leaf-flutter VFX on hit (placeholder decal).
- Sound: bowstring snap + leaf-rustle in flight + soft thud on body, leaf-crunch on miss. (Placeholder audio cues from engine.)

### C3 — Lenswright Bracewright (enemy AI unit) + Sundial Optic (scout)

Two Lenswright unit types deployable as the enemy in this slice.

`AArchonLenswrightBracewrightActor` — pressure-bolt crossbow user, slow-fire (1.5s cycle), defensive cover-seeker.
`AArchonLenswrightSundialOpticActor` — long-range optic-vision scout, no weapon at v0 (just spots), tagged for AI behavior to scout/observe.

Native seam:
- `UArchonAiCombatPolicyLibrary` — pure: target selection, cover seek, retreat trigger.
- `UArchonAiCombatBehaviorComponent` — runtime: drives behavior on top of the squad's existing move behavior.

Faction-specific shape:
- Bracewright pressure-vent sound + bolt-thwap on hit. Bolt placeholder: simple cyan-tinted cylinder mesh (no muzzle flash, no powder smoke — explicit hill check).
- Sundial: brass-tinted, taller silhouette, no fire VFX, just glints at the lens.

### C4 — Death + respawn loop

`UArchonCombatHealthComponent` already emits `OnDeath`. Death wires
into `AArchonCanaryFpsCharacter` to:
1. Disable input.
2. Detach camera; spawn `AArchonRespawnObserverPawn` at last death location for spectate.
3. Show debug-HUD respawn timer countdown (5s at v0; design says 5-8s).
4. After timer: respawn player at appropriate spawn point (anchored to outpost). Restore input.

Native seam:
- `UArchonRespawnPolicyLibrary` — pure: spawn-point selection, timer countdown logic.
- `UArchonRespawnStateComponent` — runtime: holds timer state, replicated.
- `AArchonRespawnObserverPawn` — minimal pawn for spectate during death state.

### C5 — Command-while-you-wait (the heartbeat)

The most distinctly-SPLITROOT piece of this slice. While dead and
spectating:
- `Tab` opens the map table widget exactly like in FPS state.
- The widget reads the existing team-vision state + squad list.
- Drag-box select + right-click order works identically.
- Orders submitted from the respawn screen route through the same
  `SubmitMapTableCommand` pipeline as FPS-state orders (no separate code path).
- When timer expires, respawn closes the table widget, reattaches
  camera, restores FPS input. The order submitted during death state
  continues executing.

Native seam:
- Modify `UArchonPlayerInputBridgeComponent` to handle Tab during death state — bind to the spectate pawn's controller.
- Add `bool bAllowTableDuringDeath = true` config on the bridge.
- Existing widget surface unchanged.

The "you commanded through death" feel comes from the fact that the
order pipeline DOES NOT CARE if you're alive. That's a design property
of the existing rung-1 architecture; this slice just removes the
input-bridge gate.

### C6 — Second-60-seconds integration smoke

Extend the existing first-60-seconds proof runner to chain into the
combat arc, OR create a sibling `UArchonSecond60SecondsProofRunner`.

Phase machine:

1. **Resume from end of first-60.** Player at central splitroot, squad in overwatch.
2. **Spawn enemy detachment.** 2× Bracewright + 1× Sundial at Lenswright ghost-keep location (which is no longer ghost — was lit at end of first-60).
3. **Engagement.** Enemy AI behavior fires; player fires. Drive player input via direct component calls (same pattern as rung-1 root-vault testing).
4. **Player death.** Force-apply damage to player health to drive to zero; assert `OnDeath` fires; assert `RespawnTimerStarted=true`.
5. **Command-while-you-wait.** During death state, programmatically open the map table widget via the input bridge; assert widget opens; submit a flank-order to a second squad; close widget; assert order accepted.
6. **Respawn.** Tick timer to expiration; assert player respawn at expected location; input restored.
7. **Cleanup engagement.** Assert second squad flank-order is executing.

Output flags: `Second60EnemiesSpawned`, `Second60PlayerEngaged`, `Second60PlayerDied`, `Second60CommandWhileWaitOrderSubmitted`, `Second60PlayerRespawned`, `Second60ArcCompleted`.

New PowerShell smoke: `Proof/second-60-seconds-smoke.ps1`.

## Existing local code this slice extends

Inventory from the current `Source/ArchonFactoryCanary/` after rung-1:

| Existing | Slice uses it for |
|---|---|
| `AArchonCanaryFpsCharacter` | C2 adds `UArchonVerdantThornsproutBow`; C4 wires death/respawn |
| `AArchonCanaryRtsSquadActor` | C3 extends with `UArchonAiCombatBehaviorComponent` |
| `UArchonPlayerInputBridgeComponent` | C5 unlocks Tab during death state |
| `UArchonTeamVisibilityStateComponent` | C3 reads — enemy enters Lit when sighted |
| `UArchonTeamRtsStateComponent` | C5 routes command-while-you-wait orders |
| `UArchonMapTableWidget` | C5 reuses unchanged |
| `UArchonFactionMovementComponent` | C2 movement during fire — sprint cancels fire windup at v0 |

New native modules: `ArchonCombat*`, `ArchonWeapon*`, `ArchonLenswright*`,
`ArchonAiCombat*`, `ArchonRespawn*`. New tests: matching `Tests/` for
each new policy library.

## Open questions to surface during the work

Flag in code comments and in the smoke log when hit; do not silently
decide:

1. **

_Source wiki body truncated at 12000 characters._
