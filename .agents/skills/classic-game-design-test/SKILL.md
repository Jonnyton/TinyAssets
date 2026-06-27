---
name: classic-game-design-test
description: Designs and verifies old/classic game experiences. Use when a user asks to identify, restore, emulate, port, remix, install, or prove playability of an old game, especially browser/MCP flows where the user expects the real game to become instantly playable.
---

# Classic Game Design and Test

## Overview

This skill protects the user's actual intent: "I want to play the old game I
remember" is not the same as "make a remake." A remake, remix, clone, or
browser-inspired fallback can be useful, but it must be labeled as such and
must not be counted as satisfying a request for the real childhood game.

The target experience is a chatbot/browser user saying the game they remember,
the workflow finding the rights-cleared original or best compatible public
release, adapting it to the current machine without manual emulator setup, and
ending with a single launch surface that plays immediately.

## Owns

- Identifying the intended classic game from partial memory.
- Choosing between original emulation, official release, source port,
  compatibility patch, remake, or fallback.
- Designing browser-first or one-click launch flows for old games.
- Defining playable-proof acceptance tests for input, audio, and actual
  gameplay.
- Recording blockers when rights, firmware, compatibility, or host capability
  prevent the real game path.

## Does Not Own

- Generic UI implementation details. Use `frontend-ui-engineering`.
- Generic browser debugging. Use `browser-testing-with-devtools`.
- Core test strategy outside game/runtime proof. Use `test-driven-development`.
- Public MCP chatbot acceptance. Use `ui-test` when the chatbot surface changes.
- Durable architectural decisions. Use `documentation-and-adrs`.

## Required Product Distinction

Before building, classify the requested outcome:

1. **Original game path** - the real historical game data runs in a compatible
   runtime, emulator, official web player, or source port.
2. **Compatibility port** - original code/assets are used where allowed, with a
   modern engine or wrapper.
3. **Remake or remix** - newly built gameplay inspired by the old game.
4. **Launcher only** - a wrapper that starts something already installed or
   externally acquired.

If the user asked for the real old game, pursue `Original game path` first.
Only switch to another class when the blocker is explicit and documented.

## Rights and Source Gate

Do not use warez, cracked images, copyrighted firmware, or private downloads.
For every game/runtime/media source, record:

- Public URL or local authoritative source.
- License or distribution status.
- Whether ROM/BIOS/firmware is required.
- Whether the emulator/runtime license allows this use.
- Any known limitations, such as trial firmware or missing save support.

If the only available route requires copyrighted firmware or game media the
project cannot provide, mark the task `NOT_PLAYABLE_YET` instead of pretending
a remake satisfies it.

## Build Workflow

1. **Identify the game precisely.** Use the user's clues, year/platform hints,
   screenshots, online references, and titles with similar names. Record the
   confidence and alternatives.
2. **Select the target class.** Prefer a rights-cleared original game path.
   Keep remakes/fallbacks subordinate unless the user explicitly requested one.
3. **Choose a proven runtime.** Use an established emulator, source port,
   compatibility layer, or library for the core platform logic. Do not
   hand-roll CPU, disk, audio, physics, parsing, or AI engines when a proven
   runtime exists.
4. **Design for browser/chatbot users.** The happy path must not require the
   user to install a desktop app, restart, manually boot an emulator, hunt for
   firmware, or copy files unless that limitation is explicitly accepted.
5. **Integrate media deterministically.** Loading a disk/archive is not enough.
   The launcher must wait for the runtime to be ready, inject media once, avoid
   reload loops, and expose status that distinguishes "loaded" from "playing."
   If the runtime stages media in a file slot, use its explicit boot/mount with
   reset semantics; do not count a post-boot insert as an autostart proof.
   For emulator APIs that acknowledge disk/ROM insertion asynchronously, wire a
   mount acknowledgement or bounded retry. Never schedule blind repeated resets;
   a reset loop is a blocker even when the disk eventually appears mounted.
6. **Map input deliberately.** Define mouse, keyboard, touch, and gamepad
   mappings needed by the target game. Include a real browser click/tap path
   for any action the user naturally expects to perform with the mouse.
7. **Unlock and prove audio.** Browser audio usually needs a user gesture.
   Provide an explicit launch/play gesture, then verify the audio context is
   running and unmuted. Do not claim sound works from code inspection alone.
8. **Instrument launch state.** Emit concise runtime status for media loaded,
   emulator ready, game started, input accepted, audio running, and fatal
   blockers. Avoid mock success states that look playable.
9. **Keep fallbacks honest.** If a remake or quick browser clone exists, label
   it as a fallback/remix and keep it separate from the real-game acceptance
   result.

## Playable-Proof Acceptance

"Playable" means a real gameplay objective was achieved in the live runtime.
For an artillery/tank game, the minimum proof is:

- A match starts from the real game path.
- The user can aim or otherwise control the shot.
- A mouse click or equivalent user-facing action fires.
- The projectile or action hits a tank.
- The game visibly changes state, such as damage, health, score, turn advance,
  or explosion.
- Audio is enabled and verified after a user gesture.

For other genres, replace "hit a tank" with the smallest genre-authentic proof:
move a character and collect an item, complete a menu-start-to-gameplay loop,
win/lose a round, enter a level, or trigger a visible scored action.

Never claim final playability from:

- The launcher page rendering.
- A canvas being nonblank.
- A disk/archive being assigned.
- An emulator boot screen.
- A title screen only.
- A remake running when the user requested the original.
- Code inspection without live runtime evidence.

Observation-only test instrumentation is allowed, but it must not change game
state to manufacture the proof. The user-facing input path, such as a real
button or canvas click, still has to trigger the gameplay action.

## Browser Verification Checklist

Use `browser-testing-with-devtools` or an equivalent real browser path.
Capture evidence with date, environment, URL, and exact build/version.

- [ ] Desktop viewport reaches gameplay without manual emulator setup.
- [ ] Mobile or narrow viewport is usable when the experience is public web.
- [ ] Canvas/frame fills the intended window or tab; no tiny default viewport.
- [ ] Runtime does not restart, reload, or lose media after start.
- [ ] Bootable media actually boots after injection; a shell prompt with a
      mounted disk is not proof that Startup-Sequence ran.
- [ ] Console and network logs have no fatal load/input/audio errors.
- [ ] Input proof uses real browser events, not only internal function calls.
- [ ] Audio proof shows user gesture, `AudioContext` running/unmuted, and
      observable runtime audio activity; use headed/manual proof when needed.
- [ ] Emulator pages that monkey-patch browser globals can break object
      serialization in test tools; read proof/state as JSON strings before
      parsing in the test process.
- [ ] Screenshots or video show before/action/after gameplay state.
- [ ] The original/remake/fallback class is stated in the verification note.

For canvas-heavy games, include a pixel or screenshot check so a blank canvas
cannot pass. For public TinyAssets/MCP behavior, supporting probes are not final:
run the live chatbot `ui-test` when connector behavior changed.

## Failure Handling

If the game is not fully playable:

1. Mark the result `NOT_PLAYABLE_YET`.
2. State the exact blocker: rights, firmware, media, emulator compatibility,
   browser autoplay, input mapping, restart loop, performance, or platform
   install capability.
3. Preserve any working fallback, but label it accurately.
4. Add the smallest next work item to `STATUS.md` if the blocker remains active.
5. Do not remove or downgrade the acceptance standard to make the result pass.

## Handoff Pattern

Typical sequence:

```text
classic-game-design-test
  -> frontend-ui-engineering
  -> browser-testing-with-devtools
  -> test-driven-development
  -> code-review-and-quality
```

Add `security-and-hardening` when handling user uploads, external archives, or
remote game metadata. Add `documentation-and-adrs` when the solution changes
the product architecture for browser-only game delivery.
