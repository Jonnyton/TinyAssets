---
title: Archon fantasy RTS/FPS v0 prototype spec
type: plan
status: working-draft
source_issue: 948
wiki_source_path: pages/plans/archon-fantasy-rts-fps-v0-prototype-spec-2026-05-20.md
wiki_source_updated: 2026-05-20T12:13:42Z
---

# Archon fantasy RTS/FPS v0 prototype spec

[[index]] [[archon-fantasy-rts-fps-first-pass-2026-05-20]]

Goal: `9171b100de33` — Design and prototype a fantasy Archon RTS/FPS hybrid.
Branch: `56603af00516` — archon_fantasy_rts_fps_design_v0.
Latest design-branch version at time of this spec: `56603af00516@d3739b4a`.

## V0 thesis
Build a small playable multiplayer slice where the RTS side is just regular RTS control shared by the team, and the ground side is first-person combat inside the same battle. The prototype succeeds if the map table, AI squads, respawn choices, and base assault feel like one continuous game.

## Hard locks
- RTS control is normal RTS control.
- Any teammate at a map table can input RTS commands into the same team state.
- Commands finalize as if one person controlled the RTS side.
- No command tokens, commander elections, voting, soft-locks, or anti-grief command systems in v0.
- Human players are not puppeteered by RTS commands; RTS commands affect AI units, buildings, production, rally points, faction powers, and objective markers.
- First playable uses two factions only: plant faction vs science faction.
- Animal faction is reserved until the core loop works.

## Target match
- Players: 8v8 target, with support for smaller internal tests.
- AI: each team can field several RTS-produced squads so the battle feels larger than the human count.
- Match length: 15-25 minutes for v0.
- Win condition: destroy the enemy base core.
- Resource pressure: three neutral resource sites force teams out of base.

## Map: V0 valley
A mirrored valley with two fortified bases, one central lane, two side routes, and three resource sites.

### Layout
- Team base A and Team base B at opposite ends.
- Each base contains: core, command hall with map table, barracks/growth or workshop building, defensive entry chokepoint, and spawn area.
- Central resource site in the main lane.
- Two side resource sites on flank paths.
- Sightlines allow FPS skirmishes around resources without making base-to-base sniping dominant.

### Design intent
The central lane teaches the core loop. The side paths let human players make flanks matter. Resource sites give RTS command a reason to produce AI squads and give FPS players a reason to escort them.

## Team base objects
### Base core
Primary objective. When destroyed, the team loses.

### Map table
Interactable object inside the command hall. Entering it switches the player into RTS camera/UI. Leaving it returns the player to their body if alive, or to the respawn screen if dead.

### Production building
Each team has one v0 production structure:
- Plant: Heartgrove
- Science: Field Workshop

It produces the three basic unit classes and AI squads.

### Resource store
Team resource pool. Resources are shared and spent by the RTS side on units, squads, and upgrades.

## Resource model
Use one resource in v0: **Supply**.

Supply income comes from controlled resource sites. Each site periodically adds Supply to the team pool. The team spends Supply on AI squads, replacement units, and hero unlocks.

V0 should avoid worker economy complexity. Resource sites are captured by presence: friendly humans or AI units hold the zone long enough to flip it.

## RTS table controls
The RTS view should be familiar:
- select AI units/squads
- box select
- right-click move/attack if engine supports it
- queue production
- set rally point
- place simple defensive/building objects only if implemented
- trigger faction power if available
- ping location/objective

Multiple teammates may be in RTS view at once. They are simply issuing commands to the same team state. Latest command/order edits apply normally.

## FPS controls
- Move, jump, sprint, crouch if supported.
- Primary attack.
- Secondary attack or class ability.
- Interact/use.
- Ping or quick objective marker.
- Open scoreboard/team status.
- Respawn selection after death.

## Respawn flow
On join or death, the player opens a respawn screen.

The screen shows:
- available regular unit bodies
- available specialist bodies if unlocked
- available hero body if unlocked and not currently taken
- team status: base core health, Supply, controlled resource sites

The player chooses a body and spawns at the base spawn point. Later versions can add forward spawns, but v0 should keep spawn logic simple.

## Hero rule
Each team has one hero slot in v0.

A hero becomes available when the team has enough Supply and the hero cooldown is ready. A living hero body can be controlled by one player at a time. If the hero dies, the slot enters cooldown and may require Supply again.

Hero should be powerful but not match-ending alone. The point is to test the respawn-as-hero fantasy, not solve the whole combat design.

## Factions in v0
### Plant faction: Verdant Choir
Identity: living structures, roots, thorns, spores, healing terrain.

Regular unit classes:
- Thornbound: melee/frontline unit with thorn shield and short lunge.
- Sporecaster: ranged unit with slow projectile or area spore burst.
- Grovekeeper: support unit that heals allies or grows temporary cover.

Hero:
- Briar Saint: durable plant champion with root snare, thorn sweep, and short aura heal.

RTS squad examples:
- Thornbound squad: cheap frontline push.
- Sporecaster squad: ranged support.

Faction power for v0:
- Root Wall: creates temporary organic cover or blocks a narrow route.

### Science faction: Lenswright Compact
Identity: clockwork, optics, pressure engines, alchemy, field workshops. No gunpowder.

Regular unit classes:
- Gearguard: frontline unit with shielded melee/short-range pressure weapon.
- Lens Arbalist: ranged unit using optic-assisted bolts or heat lenses.
- Fieldwright: support engineer that repairs structures or deploys a small device.

Hero:
- Master Artificer: mobile engineer hero with pressure burst, deployable turret/device, and emergency repair pulse.

RTS squad examples:
- Gearguard squad: steady line infantry.
- Lens Arbalist squad: ranged fire support.

Faction power for v0:
- Pressure Gate: temporary speed/launch boost or deployable force device that helps a push.

## AI squad behavior
Keep AI simple:
- idle at rally point
- move to ordered location
- attack visible enemies in range
- capture resource zones by presence
- attack enemy core or nearby structures when ordered
- retreat behavior can be skipped in v0

The prototype should not depend on advanced tactical AI. RTS control plus human players should create the interesting behavior.

## Buildings and upgrades
For v0, buildings are mostly fixed. Avoid full base construction until the loop works.

Required:
- base core
- map table
- one production building
- resource sites

Optional v0 if cheap:
- one simple defensive turret or plant/watchpost per faction
- one upgrade per faction that unlocks hero or specialist body

## Acceptance test
A successful v0 session proves this chain:
1. Player joins a team.
2. Player spawns as a regular unit.
3. Player fights in first person near a resource site.
4. Player dies and reaches respawn screen.
5. Player respawns as a different unit.
6. Player enters the base map table.
7. Player queues an AI squad.
8. Player orders the AI squad to a resource site.
9. Another teammate can also enter the map table and issue regular RTS commands into the same team state.
10. Player exits the table and fights alongside the AI squad.
11. Team earns Supply from a captured site.
12. Team unlocks or spawns the hero.
13. Team assaults the enemy base.
14. Enemy core is destroyed and the match ends.

## Explicit cuts from v0
- Full three-faction balance.
- Animal faction.
- Full base-building economy.
- Worker units.
- Multiple resources.
- Commander role systems.
- Command-token systems.
- Anti-grief command permissions.
- Hero progression/meta-progression.
- Complex AI tactics.
- Large Total War-scale formations.

## Next design artifacts
1. Unit stat sheet for the six regular unit classes and two heroes.
2. RTS command/UI mock list.
3. V0 map blockout with distances, lanes, and resource site timing.
4. Prototype technical plan by engine.
5. Playtest script focused on whether RTS/FPS feels unified.

_Auto-filed by wiki-change-sync from wiki page `pages/plans/archon-fantasy-rts-fps-v0-prototype-spec-2026-05-20.md`._
