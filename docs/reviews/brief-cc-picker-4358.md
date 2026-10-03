# Refute brief: PR #4358, the command-center "Try one" picker

You are gpt-6-astra reviewing a TinyAssets PR. Your job is to REFUTE it: find
where it is wrong, not to summarise it. Read-only.

## HARD CONSTRAINTS ON HOW YOU WORK

- Do NOT dispatch sub-agents. No `scripts/peer_agent.py`, no `claude`/`codex`
  subprocess, no new worktree. You are the reviewer; review it yourself.
- Do NOT run the full suite. No `scripts/ci_required_tests.py`, no
  `pytest -m "not slow"`. Run at most the one or two test files you need.
- Do NOT write to any file outside your `--out` target.
- Budget ~10 minutes. Read the diff and the cited files and reason.

## What to review

Worktree: the current directory. Branch `feat/cc-picker`, PR #4358, based on
`main`. The diff under review:

    git diff origin/main...HEAD

Most of it (`command_center_picker.py`, the three bridge actions, the picker
tests) was built by another agent. Two changes were added on top and are the
ones I most want refuted:

### Claim 1 — deleting `#cc-blank` is safe

`#cc-blank` was an in-document stand-in for an empty command center. It is
deleted: markup, CSS, its two buttons, `refreshCommandCenter()`, and
`focusCommandCenter()`'s `else if($("cc-blank"))` fallback. The argument is
that `AppUI.mountDefault()` now always mounts the platform's blank bundle in
the iframe, so the frame always exists and `focusCommandCenter` only ever needs
the frame.

Refute by finding a reachable state where NO bundle is mounted and the app
still needs a keyboard target or a visible empty state. Specifically check:

- `read_app_ui` in `tinyassets/api/app_ui.py` returns `platform_default` only
  on the whole-row read (no `ui_id` selector). Is there a path where `adopt()`
  runs from a read that did NOT carry it, leaving `platformDefault` null and
  `mountDefault()` returning silently?
- `mountDefault()` THROWS when the bundle does not parse. Who catches it, and
  what is on screen if it throws?
- `AppUI.reset()`, a failed `verify()`, an unreadable library, a sign-out, and
  the `enabled=false` path: does any of them leave the stage with no frame?
- `focusCommandCenter()` now returns silently with no frame. Does anything
  depend on focus actually moving (the chat cloud's auto-shrink releases its
  hold only when focus leaves the composer)?

### Claim 2 — `packages.try` and `chat.prefill` cannot be reached by a third-party UI

`serve()` in `tinyassets/onboarding/app_ui.js` refuses any action in
`PLATFORM_ONLY` unless `isPlatformDefault()` is true, which requires
`this.active.ui_id === "platform:blank"` AND `this.defaultMounted`.

Refute by finding a way for a UI the owner installed (or a remixed/imported
one) to get either action served. Check at least:

- `parseBundle`'s `ui_id` check: `(!this.ID_RE.test(ui_id) && ui_id !== "platform:blank")`.
  Can a stored library row carry `ui_id: "platform:blank"` and reach `mount()`
  by any route — install, remix, import, `activate`, a server row, a conversation
  installation? If it can, is `defaultMounted` still false on that path?
- Ordering: `serve()` is `async` and `await this.verify()` happens AFTER the
  gate. Can the mounted bundle change between the gate and the method call,
  so the gate passes for the platform bundle and the METHOD runs for another?
  (`this.frameGen`/`fence` are checked on the way out, not before the method.)
- `defaultMounted` is cleared in `mount()` and set in `mountDefault()` after
  `mount()` returns. Is there any re-entrancy or exception path that leaves it
  true with a different bundle on screen?
- Is the server side also gated, or is this client-only? If client-only, say
  so plainly and say whether that is sufficient given the frame is sandboxed
  and cannot reach the parent except through `postMessage`.

## Also worth your attention

- `read_app_ui` now blends the whole blank bundle (several KB of markup, CSS
  and script) into every whole-row `app_ui` read. Is that a size or caching
  problem for the owner-door read, and does any caller compare a read against
  a write and now break?
- `tests/test_command_center_picker.py::test_only_the_platform_bundle_may_install_or_prefill`
  is the new gate's test. Does it actually exercise `serve()`, and would it
  fail if the gate were removed? (I checked it does, but verify the reasoning.)
- The picker's `tryPackage` sends `write_graph target="connection"
  operation="try_package"`. Does the SERVER authorise that against the caller's
  own command center, or does it trust the client's `graph_id`?

## Return contract

You are running READ-ONLY and cannot write files. Do NOT ask for an output
path and do NOT try to create one: PRINT the whole report as your final
message on stdout. The harness captures stdout; that is the deliverable.

Use this structure, and for each finding give a verdict token:

- `AGREE` — the claim holds, with the code citation that convinced you.
- `DISAGREE_EVIDENCE` — the claim is wrong, with a file:line citation and the
  concrete sequence that breaks it.
- `DISAGREE_CONCERN` — you cannot show it breaks, but something is unsound;
  say what would settle it.

Then: `VERDICT: LAND` / `VERDICT: ADAPT` / `VERDICT: BLOCK`, one paragraph why,
and a numbered list of only the findings you would act on before landing,
highest severity first. Be specific about files and lines. If you find nothing
in a section, say so in one line rather than padding.
