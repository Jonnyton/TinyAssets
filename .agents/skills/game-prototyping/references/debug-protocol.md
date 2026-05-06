# Game Debug Protocol

Use this when verifying or repairing a browser game/prototype.

## Pre-Build Checks

### Asset Keys

- [ ] Every image/audio key referenced in code exists in the asset manifest.
- [ ] Every physical file referenced by the manifest exists.
- [ ] Placeholder keys are not mixed with final keys by accident.

### Animation Keys

- [ ] Frame keys exist in the manifest.
- [ ] Animation definitions reference valid frame keys.
- [ ] Code references animation keys that exist.
- [ ] Static UI-heavy portraits are not accidentally treated as animations.

### Config Keys

- [ ] Every config path referenced in code exists.
- [ ] Every required entity stat exists for player/enemy/tower/card/question.
- [ ] Numeric values use the intended unit: pixels, seconds, milliseconds,
      frames, grid cells, or percentages.

### Scene And Level Registration

- [ ] Every `start`, `launch`, route, or transition target is registered.
- [ ] Level order references real scene keys.
- [ ] First scene/level is not still a template default.

### Hook And Type Integrity

- [ ] Every override/hook name exists in the base class/component.
- [ ] Overrides do not narrow visibility or change required signatures.
- [ ] Imported types/classes actually exist in the source file.
- [ ] Type-only imports are marked correctly when the project requires it.

### State Cleanup

- [ ] Event listeners added on scene creation are removed or scoped to scene
      shutdown.
- [ ] Dynamic UI elements are destroyed before recreation.
- [ ] Per-round/per-level mutable state resets at the start of the next round.
- [ ] Projectiles, timers, tweens, and physics bodies clean up.

## Execution Order

1. Build/typecheck.
2. Run tests.
3. Start the dev server in the background.
4. Open the game in a browser.
5. Check console and network errors.
6. Verify a visible, nonblank canvas or UI.
7. Exercise the first playable loop.
8. Check desktop and mobile viewport framing.

Do not run long-lived dev servers in the foreground. Keep terminal control.

## Failure Record

When a failure is fixed, capture a record if it is likely to recur:

```yaml
signature:
  stage: build | test | browser | visual | gameplay
  error_code: string-or-null
  message_pattern: short regex or exact text
  file_context: path/glob if useful
root_cause: one sentence
verified_fix: what changed and how it was verified
proactive_check: optional future validation
first_seen: YYYY-MM-DD
last_seen: YYYY-MM-DD
occurrences: 1
```

If the same signature appears three times, promote it into a proactive check,
test, lint rule, or skill instruction. If the recurring failure is agent
behavior rather than game code, use `auto-iterate`.

## Common Signatures

| Signature | Likely cause | First place to inspect |
|---|---|---|
| Missing import/module | Wrong relative path or export name | Import line and target file |
| Property does not exist | Config/type drift or invented API | Type/interface and caller |
| Texture/image not found | Key mismatch or missing manifest entry | Asset manifest and code key |
| Animation not found | Animation definition missing or wrong key | Animation JSON and anim map |
| Scene not found | Transition target not registered | Engine scene config/level order |
| Cannot read property of undefined | Initialization order or missing data | Constructor/create lifecycle |
| Blank canvas | Boot failure, hidden canvas, missing assets | Console, network, canvas pixels |
| Input ignored | Focus, event binding, scene pause, overlay | Browser events and scene state |
| State repeats/duplicates | Event listener leak or missing cleanup | Scene restart and shutdown hooks |

## Browser Acceptance

A game is not verified just because it builds. Acceptance needs browser
evidence:

- Canvas/UI is nonblank.
- Primary controls work.
- One win/loss or completion path works.
- Console has no relevant errors.
- Assets visibly match the intended archetype.
- Text fits on desktop and mobile.
- Animation or movement is visible when expected.
