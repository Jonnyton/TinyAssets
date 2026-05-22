# Archon fantasy RTS/FPS v0 unit sheet

[[index]] [[archon-fantasy-rts-fps-v0-prototype-spec-2026-05-20]] [[archon-fantasy-rts-fps-first-pass-2026-05-20]]

Goal: `9171b100de33` — Design and prototype a fantasy Archon RTS/FPS hybrid.
Branch: `56603af00516` — archon_fantasy_rts_fps_design_v0.

## Stat scale

These are prototype numbers, not balance commitments.

- Health: 100 is a normal unit baseline.
- Move speed: 1.0 is normal human speed.
- Damage: tuned for readable time-to-kill, not realism.
- Supply cost: RTS production cost from the shared team pool.
- Respawn availability: whether a player can choose this body at respawn.

## Plant faction: Verdant Choir

### Thornbound

Role: frontline melee / escort.

Stats:
- Health: 150
- Move speed: 0.95
- Primary: thorn cleaver, short melee arc, medium damage
- Secondary: bramble guard, brief frontal damage reduction
- Supply cost as AI squad: low
- Respawn availability: always available

FPS purpose: simple durable fighter for players who want to push with AI squads.
RTS purpose: cheap frontline bodies that protect Sporecasters and capture points.
Counterplay: kited by ranged units, weak against sustained focus fire.

### Sporecaster

Role: ranged pressure / area denial.

Stats:
- Health: 90
- Move speed: 1.0
- Primary: spore bolt, slow arcing projectile, medium ranged damage
- Secondary: spore bloom, small lingering cloud that slows or lightly damages enemies
- Supply cost as AI squad: medium
- Respawn availability: always available

FPS purpose: readable fantasy ranged unit without guns.
RTS purpose: ranged support for Thornbound squads.
Counterplay: fragile when rushed, projectile travel makes aim important.

### Grovekeeper

Role: support / cover / sustain.

Stats:
- Health: 110
- Move speed: 1.0
- Primary: vine lash, low damage short range
- Secondary: growth pulse, heals nearby allies or strengthens temporary plant cover
- Utility: grow cover patch, short-lived obstacle or shielded root mass
- Supply cost as AI squad: medium-high
- Respawn availability: available after production building is active

FPS purpose: gives players a non-DPS team role.
RTS purpose: helps pushes survive and makes plant assaults feel organic.
Counterplay: low direct damage, must be protected.

### Hero: Briar Saint

Role: durable hero / area control / team sustain.

Stats:
- Health: 350
- Move speed: 0.9
- Primary: thorn sweep, wide melee attack
- Ability 1: root snare, targeted ground bind
- Ability 2: bloom aura, short team heal/sustain pulse
- Ultimate candidate: briar eruption, large temporary root field
- Supply unlock: high
- Hero cooldown on death: long
- Respawn availability: one team slot when unlocked and not alive

Hero purpose: lets the plant team anchor a push or hold a resource site.
Counterplay: slow, large target, vulnerable if isolated from allies.

## Science faction: Lenswright Compact

### Gearguard

Role: frontline infantry / shield holder.

Stats:
- Health: 140
- Move speed: 0.95
- Primary: impact baton or pressure punch, short-range damage
- Secondary: brace shield, brief frontal block/reduction
- Supply cost as AI squad: low
- Respawn availability: always available

FPS purpose: simple brawler with strong readability.
RTS purpose: holds the line while Lens Arbalists fire.
Counterplay: limited range, weak from flanks.

### Lens Arbalist

Role: ranged damage / precision pressure.

Stats:
- Health: 85
- Move speed: 1.0
- Primary: lens-guided bolt, direct ranged shot with moderate reload
- Secondary: focus shot, brief charge for higher damage or armor pierce
- Supply cost as AI squad: medium
- Respawn availability: always available

FPS purpose: gives science a clean ranged unit without gunpowder.
RTS purpose: ranged line damage behind Gearguards.
Counterplay: fragile, reload/charge windows punish misses.

### Fieldwright

Role: support engineer / repair / device deployer.

Stats:
- Health: 100
- Move speed: 1.0
- Primary: wrench strike or spark prod, low damage
- Secondary: repair beam/tool, repairs structures or devices
- Utility: deploy pressure node, small temporary device that boosts allies or blocks a route
- Supply cost as AI squad: medium-high
- Respawn availability: available after production building is active

FPS purpose: science support role that reinforces the RTS/building identity.
RTS purpose: keeps structures alive and creates small tactical devices.
Counterplay: low combat threat, relies on allies/devices.

### Hero: Master Artificer

Role: engineer hero / device control / emergency repair.

Stats:
- Health: 280
- Move speed: 1.0
- Primary: pressure lance, short-to-mid range burst weapon
- Ability 1: deploy turret/device, temporary clockwork weapon or blocker
- Ability 2: repair pulse, heals nearby allied structures/devices and lightly repairs units if allowed
- Ultimate candidate: overpressure engine, temporary speed/fire-rate boost for nearby machines and squads
- Supply unlock: high
- Hero cooldown on death: long
- Respawn availability: one team slot when unlocked and not alive

Hero purpose: turns a science push into a constructed battlefield position.
Counterplay: less raw durability than Briar Saint, vulnerable if caught before devices deploy.

## AI squad packages

### Plant squads

Thornbound squad:
- 5 Thornbound AI
- cheap push/capture unit

Sporecaster squad:
- 3 Sporecaster AI
- ranged support

Mixed grove squad:
- 3 Thornbound, 2 Sporecaster, 1 Grovekeeper
- expensive all-purpose push

### Science squads

Gearguard squad:
- 5 Gearguard AI
- cheap push/capture unit

Lens squad:
- 3 Lens Arbalist AI
- ranged support

Field column:
- 3 Gearguard, 2 Lens Arbalist, 1 Fieldwright
- expensive all-purpose push

## Faction powers for v0

### Root Wall

Plant power. Place a temporary organic wall or cover mass in RTS view. Used to protect a push, block a side path, or stabilize a resource site.

### Pressure Gate

Science power. Place a temporary pressure device that boosts friendly movement through a short area or disrupts enemies passing through it.

## Initial tuning targets

- Basic unit time-to-kill should be long enough for players to react, roughly 3-6 seconds in direct fights.
- Hero should beat a basic unit cleanly but lose to concentrated squad fire and focused human players.
- Support units should matter only when near allies.
- AI squads should be useful but not better than human players.
- Resource-site fights should reward mixed human plus AI pushes.

## Implementation order

1. Implement Gearguard and Thornbound as mirrored melee/frontline units.
2. Add Lens Arbalist and Sporecaster as mirrored ranged units.
3. Add AI squad production and basic move/attack/capture orders.
4. Add Grovekeeper and Fieldwright support bodies.
5. Add one hero per side.
6. Add one faction power per side.

_Auto-filed by wiki-change-sync from wiki page `pages/plans/archon-fantasy-rts-fps-v0-unit-sheet-2026-05-20.md`._
