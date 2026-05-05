---
title: RetroLab seed recipes v1
type: plan
request_kind: docs-ops
status: draft
issue: 353
updated: 2026-05-05
---

# RetroLab Seed Recipes v1

RetroLab seeds are exact-game launch plans, not remakes. Each recipe must keep
the original-media state honest, name the public source or user-owned-media
requirement, and define the smallest real gameplay proof before any launcher is
called playable.

## Shared Gates

- Do not bundle warez, retail ROMs, proprietary firmware, or media from a
  mirror that lacks a clear redistribution basis.
- Prefer browser runtimes that run original media directly: source ports for
  DOS-era PC titles, ScummVM for supported adventure games, and an established
  NES emulator for homebrew NES ROMs.
- Store source URL, upstream hash when published, fetched hash, runtime version,
  launch command/config, and proof artifacts beside each seed.
- Label each outcome with the classic-game branch states from
  `docs/design-notes/2026-04-30-exact-classic-game-browser-runtime.md`.
- Final proof requires gameplay, input, and audio where the original game has
  audio. A title screen, nonblank canvas, boot prompt, or mounted archive is
  not enough.

## Seed Matrix

| Seed | Target class | Public media posture | Browser runtime | Expected state |
|---|---|---|---|---|
| Doom shareware E1 | Original game path | Use the shareware IWAD only, not retail `doom.wad`/`doom2.wad`. | Chocolate Doom-family WebAssembly or another vanilla-compatible Doom port. | `ORIGINAL_MEDIA_PLAYABLE` after shareware IWAD hash + E1 gameplay proof. |
| Lure of the Temptress | Original game path | Use ScummVM's freeware English package or another ScummVM-listed freeware language package. | ScummVM Web/HTML5 build. | `ORIGINAL_MEDIA_PLAYABLE` after intro-to-control proof. |
| Jill of the Jungle vol. 1 | Original game path | Use only the shareware `jill1.zip`/episode-one package or the free GOG trilogy if license review allows redistribution. | DOSBox Staging/js-dos-style browser runtime. | `ORIGINAL_MEDIA_PLAYABLE` for shareware episode; full trilogy needs separate store/package gate. |
| Alter Ego NES | Original homebrew path | Use Shiru/RetroSouls public homebrew package, not Activision's 1986 `Alter Ego`. | EmulatorJS/JSNES/NESBox-style browser runtime with mapper verified. | `ORIGINAL_MEDIA_PLAYABLE` after level-start, swap, collect, and exit proof. |

## Doom Shareware E1

Source gate:

- Candidate media: `doom19s.zip` from Doomworld `/idgames/idstuff/doom/` or
  another idgames mirror; expected playable data is `DOOM1.WAD`.
- License posture: shareware episode only. Do not substitute registered Doom,
  Ultimate Doom, Doom II, or retail WADs.
- Runtime: prefer a vanilla-compatible source port in WebAssembly so E1M1
  behavior stays close to DOS Doom.

Build notes:

- Extract only `DOOM1.WAD`.
- Record the fetched archive hash and IWAD hash. Common catalog entries list
  `DOOM1.WAD` as a shareware IWAD with E1M1-E1M9.
- Disable loading PWAD mods against the shareware IWAD unless a later recipe
  explicitly validates that policy.

Acceptance:

- Launch reaches Doom menu, starts episode one, enters E1M1, accepts keyboard
  and pointer/mouse-turn input, fires the pistol, opens the first door or kills
  the first enemy, and confirms audio after a user gesture.

References:

- https://www.doomworld.com/idgames/idstuff/doom/
- https://doomwiki.org/wiki/DOOM1.WAD
- https://ftp.netbsd.org/pub/pkgsrc/current/pkgsrc/games/doom1/index.html

## Lure of the Temptress

Source gate:

- Candidate media: ScummVM's freeware Lure of the Temptress package, starting
  with the English package unless a user asks for another supported language.
- License posture: freeware game data distributed by ScummVM; keep package
  intact and record ScummVM's published SHA-256 when available.
- Runtime: ScummVM Web/HTML5 build pinned to a known version.

Build notes:

- Use ScummVM game id/config detection instead of hand-launching DOS files.
- Keep language packages separate so proof artifacts name the exact package.
- Save support is nice-to-have for seed v1; first playable proof only needs the
  opening control loop.

Acceptance:

- Launch reaches the game, passes intro/startup into direct player control,
  moves the character, opens an interaction or inventory path, and confirms
  audio after a user gesture.

References:

- https://www.scummvm.org/games/
- https://sourceforge.net/projects/scummvm/files/extras/Lure%20of%20the%20Temptress/

## Jill of the Jungle Vol. 1

Source gate:

- Candidate media: `jill1.zip` shareware episode-one package. DOS Games
  Archive identifies the file as shareware and lists `JILL.EXE`.
- Alternative media: GOG's free Complete Trilogy package can be considered only
  after a separate redistribution/install review; do not silently vendor a GOG
  installer into the public site.
- Runtime: DOSBox Staging, js-dos, or another established DOS runtime.

Build notes:

- Start with the episode-one shareware ZIP because it is the narrowest public
  seed and matches the request for volume 1.
- Persist the ZIP hash and extracted executable hash.
- Configure keyboard defaults for movement, jump, transform/actions, pause, and
  restart. Add touch/gamepad later only after keyboard proof is green.

Acceptance:

- Launch reaches gameplay, moves Jill, jumps, collects a gem/key or reaches a
  visible score/item state change, takes or avoids an enemy hazard under user
  input, and confirms audio after a user gesture.

References:

- https://www.dosgamesarchive.com/download/jill-of-the-jungle

## Alter Ego NES

Source gate:

- Candidate media: Shiru's NES `Alter Ego` package and source, or the
  RetroSouls package that includes PC, ZX Spectrum, and NES versions.
- License posture: this is the 2011 homebrew puzzle-platform game by
  Denis Grachev/RetroSouls and Shiru, not Activision's 1986 life simulator.
- Runtime: an established browser NES emulator with mapper and audio support
  verified against the exact ROM.

Build notes:

- Name the seed `alter-ego-nes-homebrew` internally to avoid collision with
  Activision Alter Ego.
- Prefer the developer-hosted package over ROM aggregation sites.
- Record NES header/mapper, PRG/CHR sizes, and fetched ROM hash.

Acceptance:

- Launch reaches level one, accepts D-pad movement, performs the alter-ego swap
  mechanic, collects at least one pixel/item, completes or visibly advances a
  level objective, and confirms audio after a user gesture.

References:

- https://shiru.untergrund.net/software.shtml
- https://www.retrosouls.net/?page_id=614

## Not In V1

- Retail Doom, Doom II, or Ultimate Doom WAD support.
- Bundled GOG installers or store-protected packages.
- Activision's 1986 Alter Ego under NES labeling.
- Save synchronization, leaderboards, achievements, multiplayer, or cloud
  library management.
