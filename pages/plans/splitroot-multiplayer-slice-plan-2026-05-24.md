---
title: Multiplayer slice — two humans on one team
type: plan
status: working-draft
source_issue: 1056
wiki_source_path: pages/plans/splitroot-multiplayer-slice-plan-2026-05-24.md
wiki_source_updated: 2026-05-24T23:18:41Z
wiki_source_sha256: 7b8c2672f65a535aa8edb290a3ab02e49b26980d065f089c6407da07519f5a46
source_capture: truncated-in-issue
---

# Multiplayer slice — two humans on one team

[[index]] [[pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23]] [[splitroot-c5-command-while-you-wait-contract-2026-05-24]] [[splitroot-s3-map-table-widget-contract-2026-05-23]] [[splitroot-second-60-seconds-combat-slice-2026-05-24]]

Goal: `9171b100de33`. Target rung: **3 (Content-complete alpha)** — multiplayer is a rung-3 prerequisite.

## Why this slice IS the game

Per the Rook persona at `.claude/rook.md` §"Lineage":

> Warcraft 3 Archon mode — the original shared-control RTS feel
> we're chasing.

The whole project is named after the seam where two players' control
*splits the root* of one team. **Single-player SPLITROOT is a tech
demo of architecture.** Two-human SPLITROOT is the game.

Rung-1 + rung-2 prove the structural substrate. This slice
demonstrates that the substrate is correct by activating its primary
use case: two networked players sharing a team, both at the table,
both issuing orders that resolve correctly via the per-rule conflict
resolution from the design extensions.

## The two-human goosebumps moment this slice has to land

Player A (Rook) and Player B (Jonathan) join a private-host match.
Both spawn as Verdant Thornbound, both at the western homeland.
Rook hits Tab. The map opens. **He sees Jonathan's selection arrows
already on a squad** — green arrows tinted differently from Rook's
(Rook's mine-colored, Jonathan's player-2-colored). Jonathan is
queuing a defensive squad rally.

Rook drag-boxes a different squad. Right-clicks east toward the
central splitroot. A pulse marker fires; Jonathan SEES Rook's
mine-colored ping appear on his screen, knows what Rook is doing
without speaking. Jonathan's squad goes defensive west; Rook's
goes offensive east. Two players, one team, zero coordination
overhead. **No menus. No "request order" dialog. No commander
permission system.** Both just play.

A Bracewright detachment crosses the field. Rook charges, fires,
takes a pressure-bolt to the chest, dies. The respawn screen shows
**Jonathan's name** under "Team — currently alive" with his
position pinged. Rook Tabs from the respawn screen, sees Jonathan
already moving toward the engagement. Rook drops a flank order on
a third squad that Jonathan can SEE arrive at the central splitroot.
Rook picks a body, spawns at base. Sprints east, root-vaults across
cover stones. Arrives to find Jonathan firing on the second
Bracewright, Rook flanks, Bracewright dies in crossfire.

Neither player said anything in voice or text. Neither asked permission.
**That's Archon.**

## Sub-slices (eight — N1 through N8)

Each gets its own contract page Rook authors next. Same pattern that
worked for combat C1-C6.

### N1 — Replication audit + property setup on existing substrate

Audit every component that already shipped:
- `UArchonTeamRtsStateComponent` — already replicated; verify all relevant UPROPERTYs marked.
- `UArchonTeamVisibilityStateComponent` — already replicated; verify per-team owner relevancy filter is wired.
- `UArchonCombatHealthComponent` (C1) — verify replicated.
- `UArchonRespawnStateComponent` (C4) — verify per-player owner relevancy (each player's respawn state replicates only to that player).
- `UArchonRangedWeaponComponent` (C2) — verify replicated, fire delegate fires on server then multicasts to clients.
- `UArchonAiCombatBehaviorComponent` (C3) — server-only ticking; clients observe via squad state.
- `UArchonFactionMovementComponent` — server-authoritative launch; clients see impulse via `LaunchCharacter` replication.

Add `bAlwaysRelevant=true` to strategic actors (map table, central splitroot, base cores). Per-team relevancy on visibility cells (already designed in S1 replication-policy predicate).

Output: a **replication audit page** on the connector listing each component + its replication state + tests asserting the property survives a client/server round-trip.

### N2 — Per-player input bridge isolation

`UArchonPlayerInputBridgeComponent` currently lives on `APlayerController`.
In multiplayer, each player has their own controller; each gets their
own bridge naturally. Verify:
- Player A's Tab opens THEIR widget instance.
- Player B's Tab opens THEIR widget instance.
- Both widgets read the SAME `UArchonTeamRtsStateComponent` and `UArchonTeamVisibilityStateComponent`.
- Selection state is PER-PLAYER (not replicated team-wide).
- Orders are submitted via server RPC; both clients see the result.

### N3 — Per-player map table selection sets + colored arrows

Per design extensions §"Map table — shared-control conflict resolution":

> Selection is per-player. Each player has their own selection set.
> Player-colored arrows above units, opaque when multiple players
> select the same unit.

Implementation:
- Extend `UArchonMapTableWidget` to track selection PER LOCAL PLAYER (already the case — selections are widget-local state).
- Each player gets a `EArchonPlayerSlotColor` from a small palette (mine-yellow, ally-blue, ally-green, ally-purple). Slot color is server-assigned at join.
- When a unit is selected on the widget, draw a colored arrow above it tinted by the selecting player's slot color.
- Multi-player selection: when multiple players select the same unit, draw N arrows side-by-side (one per selecting player).
- The arrow UMG widget lives at the unit's location in world-space, projected onto the table view.

`UArchonSelectionArrowWidget` — new widget; one per selected unit per player. Faction-tinted via the player slot color.

### N4 — Order pipeline conflict resolution (load-bearing test slice)

Per design extensions §"Map table — shared-control conflict resolution":

1. **Last order wins on the unit.** Two move orders 0.4s apart → server applies latest, discards earlier. No queue.
2. **Production queue is FIFO across players.** Order of insertion preserved; per-structure queue.
3. **Structure placement is first-commit-wins** within a resolution window. Second player gets a brief cursor flicker.
4. **Faction powers have shared global cooldowns.** Lowest player-slot-ID wins same-tick ties.
5. **Rally points are last-write-wins.**
6. **Pings are additive** and fade after ~8s.

Implementation:
- `UArchonTeamRtsStateComponent::SubmitMapTableCommand` already accepts `FArchonRtsCommandIntent` with `IssuingPlayerId`. Extend rejection/acceptance logic per the six rules above. Existing `LastAcceptedReason` / `LastRejectedReason` are the seams.
- New pure policy library `UArchonSharedControlPolicyLibrary` with the six rules as pure functions. ~20 tests covering each rule's outcome under conflict.
- Existing squad actor's `LastAppliedCommandSequence` already provides the per-unit last-order-wins guard.

This is the policy library that EXISTS most clearly to fulfill the
Archon shared-control contract. Tests are the design's authority.

### N5 — Per-player respawn state (own-owner relevancy)

`UArchonRespawnStateComponent` currently per-player but rung-1 didn't
test multi-player owner relevancy. Add tests:
- Player A's respawn state replicates only to Player A's client + server.
- Player B does NOT see Player A's respawn timer details (cosmetic only — Player A's NAME + alive-status visible in team-state aggregator).
- Player A's body-picker selection is private until they spawn (avoids "I see you're spawning forward, I'll cover" cheese).

Actually the design-extensions DON'T explicitly forbid that visibility; for SPLITROOT the team-trust premise suggests **team-mate respawn details are visible to teammates**. Default: respawn state replicates to OWN team. Add config flag for testing.

### N6 — Session routes (listen-server first, dedicated later)

`FactoryContracts/session_routes.json` already enumerates routes
including `PrivateHost`, `SteamOnline`. The multiplayer slice
implements **listen-server** path first (one player hosts, others
join via direct IP or Steam friend invite).

- Hosting player: standard `UEngine::Browse` to map URL.
- Joining player: `OpenLevel` with host's IP + port.
- Steam P2P matchmaking: deferred to a later sub-slice; Steamworks integration is rung-9+.
- Dedicated server: deferred to a later phase.

For v0 multiplayer, **listen-server with 2 players** is the proof. 2v2 and beyond are scaling work.

### N7 — Per-player FPS pawn / spawn-point management

Each player gets a unique FPS pawn at session start. The world subsystem's
existing per-player flow (`InstallRuntimePlayerBridge` runs per
controller) already accommodates this; verify:
- Two controllers → two FPS character spawns → two input bridges.
- Each pawn's combat health is independent.
- Each pawn's weapon ammo is independent.
- Each pawn's death triggers ITS OWN respawn state, not the other's.

Test: two pawns, one dies, the other stays alive + functional.

### N8 — Integration smoke (two-player headless test)

Multiplayer headless smoke is hard but possible:
- Spawn a listen-server in the same process.
- Spawn a second `APlayerController` as if a second human joined (via the existing automation primitives — `UWorld::SpawnPlayActor`).
- Drive both controllers' inputs programmatically.
- Assert both pawns spawn, both bridges install, both widgets work, an order from Player A reaches Player B's view, conflict resolution rules fire when both submit simultaneously.

Output: `Proof/multiplayer-two-player-smoke.ps1`.

This is the **rung-3 demonstration**: structural multiplayer asserted
end-to-end headless. Manual two-human playtest is still required for
the goosebumps moment; smoke just proves the substrate plumbing.

## Hard cuts from this slice

- **Steam matchmaking / Steamworks SDK** — deferred to rung-9+ Steam slice.
- **Dedicated server** — listen-server first.
- **Anti-cheat** — out of scope; team-trust premise per "standard Archon" hill.
- **Voice chat** — out of scope; team-trust via shared map table is the design.
- **More than 2 players per team** — substrate supports it, but rung-3 ships 2v2 minimum (8v8 is rung-4+).
- **Cross-faction parties** — each match has fixed team faction assignments.
- **Player-vs-player ranking / matchmaking rating** — rung-7+.
- **Reconnection / disconnect handling** — rung-3+ polish.
- **Spectator mode for non-participating viewers** — rung-7+.

## Existing local code this slice extends

Inventory (post-rung-1 + planned rung-2):

| Existing | Slice uses it for |
|---|---|
| `UArchonTeamRtsStateComponent` | N1 audit + N4 conflict-resolution extension |
| `UArchonTeamVisibilityStateComponent` | N1 audit + per-team relevancy verification |
| `UArchonPlayerInputBridgeComponent` | N2 per-controller isolation verified |
| `UArchonMapTableWidget` | N3 selection-arrow extension |
| `FArchonRtsCommandIntent` | N4 — `IssuingPlayerId` is already the seam |
| `UArchonCombatHealthComponent` (rung-2) | N1 audit + N7 per-pawn independence |
| `UArchonRespawnStateComponent` (rung-2) | N5 own-owner relevancy verification |
| `FactoryContracts/session_routes.json` | N6 listen-server route |

New native modules: `ArchonSharedControlPolicyLibrary`, `ArchonSelectionArrowWidget`, `ArchonPlayerSlotColor` enum.

## Hills check

- **Standard Archon — THE TEST**: ✓ This slice IS the Archon test. Two players, no commander tokens, no votes, no permission asks, no anti-grief. Conflict resolution is six small deterministic rules — that's all the governance the design wants.
- **Standard FPS controls**: ✓ Both players use identical controls; multiplayer adds nothing new to the input surface.
- **Movement before content**: ✓ Movement and combat shipped before MP; MP doesn't change verbs.
- **Faction verbs matter**: ✓ Two players on same team see each other's verbs in play (Verdant root-vault, Lenswright pressure-thrust). Reads as same faction, same vocabulary, same team.
- **Paid heroes horizontal-only**: ✓ Hero in MP works identically for paid and free; F2P invariant tested in multiplayer context.
- **Factory branch is product**: ✓ `UArchonSharedControlPolicyLibrary` is a GENERIC remix surface.

## Sync note

Issue #1056's embedded source wiki body ends with `_Source wiki body truncated at 12000 characters._` after the Hills check. This repo projection preserves the complete source available from the issue and stops before the incomplete trailing fragment, rather than inventing missing text.
