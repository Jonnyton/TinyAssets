# The one file built for the universe to ship is mirrored, so it cannot ship it alone

**Filed:** 2026-08-28
**Verified:** 2026-08-28 — reproduced by the universe on PR #2655, twice, on its
first successful write to the repository.
**Severity:** P2 — the change still lands, but not without a human, which is the
one thing this file existed to avoid.

## What happened

`tinyassets/onboarding/request_theme.json` exists specifically so a universe can
ship a change by itself. Its own `_why` says so:

> The GitHub Contents API replaces a whole file and offers no patch parameter, so
> the universe can only ship a change to a file it can reproduce byte-for-byte.
> `app.html` is ~98KB; this is not. **Edit `request_text`, open a PR, and the live
> rail changes.**

The universe did exactly that — `GET` ref `200`, `GET` contents `200`, `POST
/git/refs` `201`, `PUT` contents, then opened PR #2655 with a clean one-line
diff. CI refused it twice, both for the same reason:

```
invariants: [VIOLATED] mirror-parity - 1 file(s) diverge between canonical and mirror
  evidence.mismatches: ['onboarding/request_theme.json']

Build packaging artifacts: Committed plugin runtime is stale.
  .../runtime/tinyassets/onboarding/request_theme.json | 2 +-
```

`request_theme.json` is under `tinyassets/`, so it is mirrored into
`packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/`. A
single-file edit always leaves the mirror stale.

## Why the agent cannot fix this itself

Not for lack of trying — the requirement is structurally out of its reach:

* it would have to know the mirror exists and that this file is in it;
* it would have to write **two** files, and the Contents API commits one file per
  call, so the branch is briefly inconsistent either way;
* the local `pre-commit` hook that regenerates the mirror never runs, because the
  agent commits over the API rather than through a working tree;
* `build_plugin.py` is a local script it has no way to execute.

So the file's instruction — *edit `request_text`, open a PR* — is true right up
to the point where CI rejects it, and the last step needs a human or a
CI-side job.

## What would fix it

1. **Exempt this file from mirror-parity and generate the mirror copy at build
   time**, so there is one source of truth and nothing to keep in sync. Cheapest,
   and it preserves the file's whole purpose.
2. **Or have CI regenerate the mirror and push it** onto the PR branch when the
   only divergence is a mirrored-file edit — the same thing a human does now.
3. **Or move the value out of the mirrored tree entirely** — the theme is
   config, not runtime code, and nothing in the plugin needs a copy of it.

Whichever, the test is the one the file already sets for itself: a universe edits
`request_text`, opens a PR, and it can go green without anybody helping.

## How to resolve this file

Delete it when a universe-authored change to `request_theme.json` reaches a
mergeable state with no human commit on the branch — observed once, on a real PR.
