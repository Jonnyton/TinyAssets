# Archon fantasy RTS/FPS v0 map blockout

[[index]] [[archon-fantasy-rts-fps-v0-prototype-spec-2026-05-20]] [[archon-fantasy-rts-fps-v0-unit-sheet-2026-05-20]]

Goal: `9171b100de33` -- Design and prototype a fantasy Archon RTS/FPS hybrid.

## Map name

Working name: **Splitroot Valley**.

## Purpose

This map exists to prove the core hybrid loop:

- fight in first person
- enter a base map table
- issue normal RTS commands into the shared team state
- produce and move AI squads
- capture resource sites
- respawn as different bodies or a hero
- assault and destroy the enemy base core

## Scale target

For greybox, use a compact battlefield that supports 8v8 humans plus AI squads without feeling empty.

Recommended initial dimensions:

- Full map length: 900-1100 meters equivalent
- Full map width: 450-650 meters equivalent
- Base-to-center travel time on foot: 45-70 seconds
- Base-to-nearest side resource travel time: 25-40 seconds
- Central site to enemy base outer choke: 35-50 seconds

If testing feels slow, shrink the map before adding mounts, vehicles, teleports, or forward spawns.

## High-level layout

Mirrored two-base valley:

```text
[Plant/Team A Base]
      |  left flank path     central lane      right flank path  |
      |  side resource A     central resource  side resource B   |
[Science/Team B Base]
```

More detailed topology:

```text
                 North ridge overlook
        Side A resource ---- Central resource ---- Side B resource
          /        \             |             /        \
 Team A base ---- A outer choke - mid ruins - B outer choke ---- Team B base
          \        /             |             \        /
        low ravine route ---- contested underpass ---- low ravine route
                 South low path / streambed
```

## Bases

Each base should be playable in first person and readable from RTS view.

### Base zones

- Spawn chamber: safe-ish respawn area behind the command hall.
- Command hall: contains the map table.
- Production yard: contains the faction production structure.
- Core chamber: contains the base core objective.
- Outer choke: main defensive entry into the base.
- Side breach path: smaller secondary route that becomes valuable after teams control side resources.

### Command table placement

Place the map table inside the command hall, close enough that respawned players can reach it quickly, but not directly on the spawn point.

Target travel times:

- spawn to map table: 5-8 seconds
- spawn to base exit: 8-12 seconds
- map table to base exit after leaving table: 8-12 seconds

Design reason: a dead or newly spawned player can quickly choose to command, but using the table still costs presence on the battlefield.

### Core placement

The base core should be deeper than the outer choke, not visible from outside the base. Teams must break into the base before damaging it.

V0 core health should be high enough that one unnoticed player cannot solo-kill it quickly. A coordinated human plus AI squad push should threaten it.

## Resource sites

Three sites:

- Left/side resource
- Center resource
- Right/side resource

### Capture rule

A site flips when friendly humans or AI hold the capture area uncontested for a short timer.

Suggested timers:

- Neutral to controlled: 12 seconds
- Enemy controlled to neutral: 8 seconds
- Neutral to controlled after decap: 12 seconds

Use one capture radius at first. Avoid multi-ring capture logic.

### Income timing

Each controlled site grants Supply every 20 seconds.

Initial placeholder values:

- side site: +25 Supply / tick
- center site: +40 Supply / tick

Design reason: center is worth more, but side control matters enough to split teams.

## Lanes

### Central lane

Primary AI path and easiest route to understand.

Features:

- wide enough for AI squads and human movement
- broken ruins/cover around the central resource
- enough vertical variation for FPS interest but not enough to confuse AI pathing
- no long base-to-base sightline

Purpose: teaches players that AI squads, resource capture, and human escorts work together.

### Left and right flank paths

Secondary routes to side resources and side breach approaches.

Features:

- narrower, more FPS-focused
- partial cover and turns
- useful for human flanks
- AI can path through them, but central lane remains the default rally route

Purpose: lets skilled players matter without requiring complex RTS micro.

### Low ravine / underpass

Optional if cheap in greybox. A lower path under or beside the center that creates ambush opportunities.

Keep it simple. If it creates pathing problems, cut it.

## Sightline rules

- No direct line of sight from one base core to the other.
- No sniper lane from spawn to central resource.
- Central resource should have 3-5 meaningful cover pieces.
- Side resources should have 2-3 cover pieces and one clear flank entrance.
- RTS camera must clearly see resource ownership and squad routes.

## RTS readability

From RTS view, the map must show:

- base core
- map table / command hall icon
- production structure
- controlled resource sites
- AI squad selection rings
- rally points
- attack/move order markers
- enemy squads when visible
- human teammates as distinct icons or dots if feasible

Do not solve fog of war deeply in v0. Use simple shared team vision or always-visible greybox info until the core loop works.

## Spawn and respawn

V0 uses base spawn only.

Spawn chamber should have:

- clear route to command table
- clear route to base exit
- class/body selection terminal or UI-only respawn screen
- no enemy access in v0, unless base is already effectively breached

Forward spawns are cut from v0.

## Hero flow on map

Hero spawns at base spawn like regular bodies.

The hero should need 25-40 seconds to reach the central resource. This prevents instant hero impact and makes map control matter.

## AI rally defaults

Each production building should have a default rally point toward the central lane.

RTS table users can move the rally point to:

- central resource
- left resource
- right resource
- own base defense marker
- enemy outer choke

Keep rally targets as named markers in v0 to reduce UI complexity.

## Base assault flow

The intended attack sequence:

1. Team captures at least one resource site.
2. Team produces AI squads.
3. Humans escort or flank with the AI push.
4. Push reaches enemy outer choke.
5. Defenders fight in first person while RTS users reinforce.
6. Attackers break into core chamber.
7. Base core takes sustained damage.
8. Core dies; match ends.

## Greybox geometry checklist

Required pieces:

- Two mirrored bases
- Two command halls with map tables
- Two spawn chambers
- Two base cores
- Two production structures
- Three capture zones
- Central ruins/cover set
- Two side paths
- Outer chokes at both bases
- Clear AI navigation path through central lane

Optional pieces:

- Low ravine/underpass
- Side breach route into bases
- Faction-themed silhouette dressing
- Temporary base turrets/watchposts

## First playtest questions

- Do players understand where to go after spawning?
- Can a player find and use the map table quickly?
- Does entering RTS view feel connected to the battlefield rather than like a separate minigame?
- Do AI squads reach resource sites reliably?
- Do humans naturally escort or exploit AI squad movements?
- Is the center too dominant compared with side paths?
- Can teams recover after losing the first resource fight?
- Does base assault require enough coordination without becoming a slog?

## Cut conditions

Cut or simplify any map feature that blocks the main loop:

- If AI pathing fails on side routes, keep AI central-only for v0.
- If base interiors are confusing, make bases smaller and more direct.
- If the underpass creates navigation bugs, remove it.
- If resource capture splits attention too much, temporarily run one center site only.
- If match time exceeds 25 minutes repeatedly, reduce core health or shorten travel time.
