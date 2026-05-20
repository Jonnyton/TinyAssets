---
title: Archon fantasy RTS/FPS v0 technical prototype plan
type: plan
status: working-draft
source_issue: 949
wiki_source_path: pages/plans/archon-fantasy-rts-fps-v0-technical-plan-2026-05-20.md
wiki_source_updated: 2026-05-20T14:16:38Z
---

# Archon fantasy RTS/FPS v0 technical prototype plan

[[index]] [[archon-fantasy-rts-fps-v0-prototype-spec-2026-05-20]] [[archon-fantasy-rts-fps-v0-unit-sheet-2026-05-20]] [[archon-fantasy-rts-fps-v0-map-blockout-2026-05-20]]

Goal: `9171b100de33` — Design and prototype a fantasy Archon RTS/FPS hybrid.

## Technical thesis

Build the smallest networked simulation where human-controlled FPS bodies and RTS-controlled AI squads interact with the same resources, objectives, and base core.

The hard technical problem is not fancy faction content. It is one authoritative match state that accepts both first-person inputs and shared RTS commands.

## Engine recommendation

For a serious multiplayer FPS/RTS prototype, start in Unreal if the team is comfortable with it. Unreal gives stronger defaults for replicated characters, movement, animation, AI navigation, and dedicated-server thinking.

Unity is viable if the team already has networking and FPS experience there. Godot is viable for a lean local/limited prototype but becomes riskier for networked FPS plus RTS at this scope.

Do not choose the engine for faction art. Choose it for multiplayer character control, AI pathing, and authoritative server workflow.

## Network authority model

Use server authority for:
- player body spawning
- player movement validation
- damage and death
- RTS command acceptance
- AI squad movement/orders
- production queues
- resource income
- capture zones
- hero availability
- base core health
- match end

Clients send inputs:
- FPS movement/combat inputs while controlling a body
- RTS commands while using a map table
- respawn body selections

The server owns final state. This matches the design rule: many teammates can input RTS commands, and the resulting team state resolves like normal RTS control.

## Milestone 0: project shell

Goal: create a runnable empty multiplayer test map.

Must have:
- one listen-server or dedicated-server test flow
- two teams
- join team command or auto-assignment
- placeholder player pawn
- basic movement
- basic test map

Done when:
- two clients can join and see each other moving.

## Milestone 1: FPS body loop

Goal: spawn, fight, die, respawn.

Must have:
- base spawn points
- two placeholder unit bodies, one per team
- health
- damage
- death
- respawn screen or simple respawn menu
- body selection

Done when:
- a player can kill another player and the dead player can respawn as a selected body.

## Milestone 2: map table mode

Goal: enter RTS view from a base object.

Must have:
- command hall map table actor
- interact key enters RTS camera/UI
- leave command mode returns to body control
- RTS camera can pan/zoom over map
- RTS cursor can select test objects

Done when:
- a player can walk to the table, enter RTS view, inspect the battlefield, leave, and keep playing.

## Milestone 3: shared RTS commands

Goal: make team-shared RTS input real.

Must have:
- team production queue placeholder
- AI squad spawn command
- AI squad select/order command
- rally point command
- server applies RTS commands to team state
- two teammates can issue commands from the same table/team

Done when:
- two players on one team can both enter RTS view and issue commands to the same AI squad/queue, with final state resolving normally.

No command ownership layer is required.

## Milestone 4: AI squad basics

Goal: AI squads can move, attack, and capture.

Must have:
- AI squad unit prefab/blueprint
- move order
- attack visible enemies
- capture zone presence
- death/despawn
- simple formation or loose group behavior

Done when:
- RTS-produced squads can move to a resource site, fight enemy squads/players, and flip the site.

## Milestone 5: resource and production loop

Goal: resource sites fund production.

Must have:
- three capture zones
- Supply income tick
- team Supply pool
- squad production costs
- production queue timing
- default rally point

Done when:
- holding resource sites increases Supply and lets the team produce more squads.

## Milestone 6: two prototype factions

Goal: plant vs science units are playable enough to test role contrast.

Must have:
- Thornbound and Gearguard frontline units
- Sporecaster and Lens Arbalist ranged units
- Grovekeeper and Fieldwright support units if time allows
- minimal VFX placeholders for attack readability
- team-colored silhouettes/materials

Done when:
- players can distinguish roles and teams in motion without final art.

## Milestone 7: hero slot

Goal: test respawn-as-hero.

Must have:
- one hero body per team
- hero availability state
- hero cooldown on death
- hero selection on respawn screen
- basic hero ability set

Done when:
- a team can unlock a hero, one player can spawn as it, the hero can die, and the slot later becomes available again.

## Milestone 8: base core win condition

Goal: complete a full match loop.

Must have:
- base cores
- core health and damage
- AI and players can damage core
- match end on core death
- victory/defeat screen

Done when:
- a full match can start, escalate through resource/AI production, and end with one base core destroyed.

## Milestone 9: first playtest build

Goal: find out whether the hybrid premise works.

Must have:
- stable enough 4v4 internal test, scaling toward 8v8
- readable UI for Supply, resource ownership, base health, hero status
- known issue list
- simple playtest questionnaire

Done when:
- testers can complete two matches and answer whether RTS command and FPS combat feel connected.

## Main risks

- Network complexity grows quickly once FPS combat and RTS AI share a server state.
- RTS camera/UI can become a second full game if scoped too broadly.
- AI pathing can dominate development time if the map is too complex.
- Heroes can distort the whole prototype if they are added before the base loop works.
- Support classes may feel useless until squad and objective play exists.

## Scope discipline

Build in this order:
1. FPS bodies
2. Map table camera
3. Shared RTS commands
4. AI squad movement
5. Resource capture
6. Production loop
7. Faction differentiation
8. Heroes
9. Base win condition polish

Do not begin with full faction kits, beautiful bases, or complete hero design. The first proof is shared RTS plus FPS combat in one match.

_Auto-filed by wiki-change-sync from wiki page `pages/plans/archon-fantasy-rts-fps-v0-technical-plan-2026-05-20.md`._
