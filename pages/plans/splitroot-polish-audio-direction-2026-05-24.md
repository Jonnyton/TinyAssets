---
title: SPLITROOT polish — representative audio direction (rung-2 gate; four-layer cue discipline + faction palettes)
type: plan
author: Rook (Claude Opus 4.7 lead session, Cowork)
author_org: anthropic
author_provider: cowork
authored_at_utc: 2026-05-24T10:35:00Z
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
  - pages/plans/splitroot-second-60-seconds-combat-slice-2026-05-24.md
  - pages/notes/pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23.md
sources:
  - pages/notes/pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23.md §"FPS feel doctrine" #7 (Audio scale — local / squad / strategic / table layers)
  - pages/plans/splitroot-polish-art-direction-2026-05-24.md (sister gate; same discipline pattern)
  - pages/plans/splitroot-c3-lenswright-units-ai-combat-contract-2026-05-24.md §"Lenswright no-gunpowder hill" (audio explicitly: pressure-vent hiss + bolt-thwap, NOT gunfire)
  - FactoryContracts/factions.json v2
  - local Cowork session 2026-05-24 (Rook continuing rung-2 prep)
tags: [splitroot, plan, polish, audio-direction, rung-2, four-layer-audio, faction-audio, cue-inventory, rook-authored]
---

# Polish — representative audio direction

[[index]] [[splitroot-polish-art-direction-2026-05-24]] [[splitroot-second-60-seconds-combat-slice-2026-05-24]] [[pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23]]

Goal: `9171b100de33`. Target rung: **2 (Verified vertical slice)**.

Rung-2 says **"representative audio direction"** — same discipline
as art: not final, not production-mixed, but enough that a listener
can identify faction (Verdant choir-hum vs Lenswright clockwork-tick),
read strategic events without needing the HUD, and feel like Splitroot
Valley is one coherent place.

## The four-layer cue discipline

Per design extensions §"FPS feel doctrine" #7:

> Audio scale. Local / squad / strategic / table — each layer has its
> own sonic identity. Strategic events (base core damage, hero
> unlock, site flip, faction power) clearly audible at all distances.

Every audio cue in SPLITROOT lives in exactly ONE layer:

| Layer | Distance | Examples | Mix priority |
|---|---|---|---|
| **Local** (≤10m) | Within breath/melee range | Footstep, weapon-handle creak, your own bowstring snap, your own pressure-vent | Low priority — drowned by squad+strategic when they fire |
| **Squad** (10-40m) | Squad-mate audible | Allied unit fire, enemy unit fire near you, ally hit-confirm, squad voice-line ("ENGAGING") | Medium priority |
| **Strategic** (any distance, position-agnostic) | Map-wide | Base core damaged, site flipped, hero unlocked, hero died, faction power activated, match-event chimes | HIGHEST priority — clearly audible over all combat |
| **Table** (RTS view) | When map table widget is open | Selection click, order-issued confirm, command-while-you-wait submit, drag-box rubber-band hum | Replaces local/squad layer ducking while table open |

Strategic-layer cues are 2D (no spatial attenuation) — they communicate
match state, not position. Local/squad cues are 3D-spatialized with
default Unreal attenuation. Table cues are 2D-UI sounds.

## Faction audio palettes

### Verdant Choir — choral organic

| Family | Description | Source ideas |
|---|---|---|
| Movement | Soft leaf-crunch footsteps, occasional twig-snap, faint bramble-rustle ambient | Foley wood/leaf packs from Freesound |
| Combat — weapon | Bowstring snap (taut, low-thump) + arrow leaf-rustle in flight + soft thud on body OR leaf-crunch on miss | Free wood/string foley + leaf-rustle layer |
| Combat — hit-received | Distant chord-tone + dampened drum (the body absorbs) | Choral pad samples |
| Ability — Briar Wall | Bramble-grow earth-rumble + wooden creak | Earth-rumble + wood-creak layer |
| Ambient (faction zone) | Distant choir-hum, faint wind through leaves | Choral drone pad |
| Hero — Briar Saint | Choir-hum always present when alive (5db quieter than ambient) | Choir loop |
| Death (your own Verdant) | Choir-pad swell + leaf-flutter cascade | Choral fade |

### Lenswright Compact — clockwork mechanical (NO gunpowder)

| Family | Description | Source ideas |
|---|---|---|
| Movement | Metallic foot-plate clank, gear-tick during stride, occasional pressure-vent hiss | Mechanical foley packs |
| Combat — weapon | Pressure-vent hiss (compressed-gas release, 300ms) + bolt-thwap on body OR metallic ring on miss. **NEVER bang/crack/gunshot.** | Air-release samples + thwap impact |
| Combat — hit-received | Metal-plate clang + clockwork-skip stutter | Metal foley |
| Ability — Pressure Gate deploy | Hydraulic clunk + gear-lock click | Mechanical lock samples |
| Ambient (faction zone) | Distant clockwork-tick layer, pipe-hiss, gear-grind | Clockwork ambient pad |
| Hero — Master Artificer | Clockwork-tick always present when alive (5db quieter than ambient) | Tick loop |
| Death (your own Lenswright) | Mechanism-wind-down + final pressure-vent fade | Mechanical death |

**Lenswright audio hill — EXPLICITLY CHECKED**: every Lenswright cue is
*hiss/clank/grind/tick* — NEVER *bang/crack/pop*. Audio cross-review
rejects any sample tagged or sounding "gunshot," "rifle," "muzzle,"
"firearm." This protects the no-gunpowder hill at the audio layer.

### Kinwild Covenant — primal pack (rung-3+ but defined here)

| Family | Description |
|---|---|
| Movement | Soft paw-pad steps, distant hunt-horn occasional |
| Combat | Bowstring twang (lower-tension than Verdant) OR beast-bite snarl (melee) |
| Ambient | Distant pack-call, wind through grass, drum-pulse low |
| Hero — Pack-Caller | Distant hunt-horn layer always present |

### Neutral / world

| Family | Description |
|---|---|
| Splitroot tree | Deep wood-creak ambient near central trunk. Low-frequency hum suggests the tree is alive. |
| Wind | Soft valley-wind layer at all positions |
| Cover stone | Footstep echo when player is in stone-rich area |

## Strategic-layer event cues (faction-agnostic, position-agnostic)

All players hear these regardless of distance:

| Event | Cue description |
|---|---|
| Match start | Three rising tones (E-A-D) + low whoosh — "the match begins" |
| Side-resource captured (by your team) | Bright two-note rise (G-C) |
| Side-resource captured (by enemy) | Dim two-note fall (G-D) |
| Central resource flipped | Heavier four-note phrase (E-G-A-C, upward) + low rumble |
| Hero unlocked (your team) | Long shimmering pad sustain + bell |
| Hero unlocked (enemy team) | Same shimmer but lower-pitched + slight discord |
| Your hero arrived at battlefield | Faction-specific motif: Verdant choir-soar / Lenswright gear-ascend / Kinwild horn-call |
| Hero died (your team) | Dampened motif fall — somber, brief |
| Hero died (enemy team) | Brief tonal "ping" — neutral, acknowledgement |
| Base core under attack | Insistent pulsing low tone + clock-tick (urgency) |
| Base core destroyed (= match end) | Massive bass thud + room-rumble sustain |
| Faction power activated (your team) | Faction-specific signature: Verdant choir-chord / Lenswright pressure-burst / Kinwild howl |
| Match end (victory) | Triumphant motif over 6s |
| Match end (defeat) | Somber motif over 6s |

These are FEW (~15 cues) but every player hears every one, every
match. They form the match-state audio language.

## Combat-feel audio anatomy

Per [[pages-notes-splitroot-design-extensions-beyond-v0-spec-2026-05-23]] §"FPS feel doctrine" #3 (Weight):

Every weapon-hit needs THREE-LAYER audio confirmation:
1. **Weapon body cue** (your bowstring snap / your pressure-vent hiss).
2. **Travel cue** (leaf-rustle / bolt-tracer hum — short, low).
3. **Impact cue** (leaf-crunch flesh-thud / bolt-thwap metallic ring).

Missing any of the three breaks the "I shot something" reading. The
audio polish slice ships all three for both factions at rung-2; the
hit-confirm tone (you scored a hit) is shared across factions — a brief
clear "thunk" played AT the listener position, not 3D-spatialized,
mixed slightly above local layer.

## Sourcing strategy (free-tier)

For rung-2 polish, source from:

- **Freesound.org** (CC0 / CC-BY). Search faction-specific terms (e.g., "bowstring," "leaf rustle," "pressure release," "gear tick").
- **Unreal Engine Marketplace** free monthly assets — fantasy/sci-fi audio packs.
- **Bensound** royalty-free background music (for ambient choral / clockwork pads).
- **Free Music Archive** for ambient drones.

Rule: every sourced sample MUST get a per-faction EQ/pitch pass so it
fits its palette family. A raw "leaf rustle" from Freesound isn't a
Verdant cue until it's pitched/filtered to sit in the Verdant palette
range. EQ discipline IS the production value at rung-2 audio.

## Implementation contracts

### A1 — `UArchonFactionAudioLibrary` (Blueprint function library)

```cpp
UCLASS()
class ARCHONFACTORYCANARY_API UArchonFactionAudioLibrary : public UBlueprintFunctionLibrary
{
public:
    UFUNCTION(BlueprintPure, Category = "Archon|Audio")
    static USoundBase* GetFactionWeaponFireCue(EArchonFaction Faction);

    UFUNCTION(BlueprintPure, Category = "Archon|Audio")
    static USoundBase* GetFactionWeaponImpactCue(EArchonFaction Faction);

    UFUNCTION(BlueprintPure, Category = "Archon|Audio")
    static USoundBase* GetFactionFootstepCue(EArchonFaction Faction);

    UFUNCTION(BlueprintPure, Category = "Archon|Audio")
    static USoundBase* GetFactionHeroAmbientLoop(EArchonFaction Faction);

    UFUNCTION(BlueprintPure, Category = "Archon|Audio")
    static USoundBase* GetFactionDeathCue(EArchonFaction Faction);

    UFUNCTION(BlueprintPure, Category = "Archon|Audio")
    static USoundBase* GetStrategicEventCue(EArchonStrategicAudioEvent Event);

    // Test: assert NO Lenswright cue is tagged "gunshot," "muzzle," "firearm."
    UFUNCTION(BlueprintPure, Category = "Archon|Audio")
    static bool ValidateLenswrightCuesAreNotGunpowder();
};

UENUM(BlueprintType)
enum class EArchonStrategicAudioEvent : uint8
{
    MatchStart, SideResourceCapturedAlly, SideResourceCapturedEnemy,
    CentralResourceFlipped, HeroUnlockedAlly, HeroUnlockedEnemy,
    HeroArrivedAlly, HeroDeathAlly, HeroDeathEnemy,
    BaseCoreUnderAttack, BaseCoreDestroyed,
    FactionPowerActivatedAlly, MatchVictory, MatchDefeat
};
```

12 named tests in `ArchonFactionAudioLibraryTests.cpp` covering:
- Each (faction, cue-type) tuple returns a non-null sound (after assets are imported).
- `ValidateLenswrightCuesAreNotGunpowder()` returns true — searches asset metadata for forbidden tags.
- Strategic event lookups all succeed.
- Cross-faction footstep cues are AUDIBLY DIFFERENT (file hash mismatch — proves we didn't accidentally share the same sample across factions).

### A2 — apply to existing actors

- `AArchonArrowProjectile`: play `GetFactionWeaponImpactCue` on hit, faction = shot's instigator faction.
- `AArchonCanaryRtsSquadActor`: footstep timer plays `GetFactionFootstepCue`.
- `AArchonLenswrightBracewrightActor`: same.
- Player FPS character: footstep cue via animation notify or velocity-based timer.
- `UArchonRangedWeaponComponent`: on `OnWeaponFired` delegate, play `GetFactionWeaponFireCue`.

### A3 — strategic-event broadcaster

`UArchonStrategicAudioBroadcasterComponent` on `AGameModeBase` or
`UArchonCanaryWorldSubsystem`. Listens to events from the match state
(site flip, core damage, hero unlock, match end) and plays the
strategic cue 2D on all clients.

### A4 — ambient zones

Per-faction-homeland ambient sound spheres. When player is within
N meters of a faction base, the faction ambient loop plays. Crossfades
between zones. Implementation: `AArchonAmbientAudioZone` actor with
`USphereComponent` trigger + `UAudioComponent` looping the
faction's ambient pad.

## What this slice does NOT cover

- **Voice acting / spoken lines.** Placeholder text/beep at rung-2.
- **Dynamic music system.** Static ambient at rung-2; reactive music is rung-4+.
- **Audio mixing pass** (loudness leveling, ducking curves). Engine defaults at rung-2.
- **3D audio occlusion / reverb.** Engine defaults at rung-2.
- **Audio compression / spatialization tuning.** Engine defaults at rung-2.
- **Custom audio middleware** (Wwise, FMOD). Unreal native at rung-2.

## Cross-iteration with `unreal-canary-playtest` skill

The playtest skill currently captures only PNGs — audio doesn't show
up in screenshots. Substrate improvement queued for the skill:

- **Audio cue capture**: after playtest, dump the names of all
  `USoundBase` assets that played during the proof arc into a JSON
  list. Cross-reference against `ValidateLenswrightCuesAreNotGunpowder`
  to assert no gunpowder cues played.
- **Audio iteration log**: same per-iteration log shape as the visual
  log; each iteration captures which cues were heard, which were
  missing, which were misfaction.

This substrate improvement is its own follow-up; not blocking the
audio polish itself.

## Hills check

- **Lenswright no gunpowder** — AUDIO LAYER: ✓ Every Lenswright cue is hiss/clank/grind/tick; `ValidateLenswrightCuesAreNotGunpowder()` test is the audit. The audio cross-review will reject any pull-request that adds a Lenswright cue tagged with firearm terms.
- **Faction verbs matter** — AUDIO: ✓ Faction footstep cues are different files (test). Faction ambient is different. A blind player can identify which faction's zone they're in.
- **Standard FPS** — AUDIO: ✓ Three-layer hit confirmation (fire/travel/impact) matches Halo, NS2, Tribes conventions.
- **Standard Archon** — AUDIO: ✓ Strategic-event cues are PLAYED FOR THE WHOLE TEAM regardless of who triggered. Match state is shared; audio reflects that.
- **Movement before content**: ✓ Movement-related audio (footstep cues per faction, vault landings) is in this plan.
- **Factory branch is product**: ✓ `UArchonFactionAudioLibrary` is GENERIC. Future games swap the sound assets + the strategic-event enum; inherit the four-layer discipline + the faction-audit pattern.
- **Proof ladder sacred**: ✓ 12 named tests + audio-cue capture in playtest iteration. Audio FEEL stays manual-playtest.

## Hex / Rook pickup

A1 (audio library) is the load-bearing piece — pure lookup + tests
+ no-gunpowder validation. Hex or Rook implements (similar weight to
the material builder in art direction polish).

A2-A4 are application work that follows.

Asset import is a separate manual task: someone (Jonathan or a Rook
crossing-over session) downloads the sound files from Freesound /
Marketplace and imports them into `Content/Audio/Verdant/`,
`Content/Audio/Lenswright/`, `Content/Audio/Strategic/`,
`Content/Audio/World/`. The library's `GetXxxCue` functions reference
those imported assets by name.

After audio polish lands + art direction polish lands + combat C1-C6
ships + UMG HUD poli

<!-- local-sync-note: live wiki read on 2026-05-24 returned 15000 of 15122 chars; the final 122 chars were unavailable through wiki action=read. Do not infer the missing tail; re-sync from the source wiki if exact ending matters. -->
