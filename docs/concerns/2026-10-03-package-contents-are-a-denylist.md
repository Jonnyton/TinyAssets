---
severity: P1
title: What a published package carries is a denylist, so the next private file travels by default
filed: '2026-10-03'
summary: 'command_center_packages decides what a published command center carries by walking the whole directory and removing known-private names. Two files were missing from those lists and shipped: orgchart.md (withheld from non-founders even when the command center is fully public) and requests.json (the owner''s pending request text, which the daemon turns into active work targets). Both are fixed, but the shape is the defect: anything added to a command center later is public by default, and the publish confirmation promises the opposite. The durable fix is an allowlist of what travels.'
---

# What a published package carries is a denylist

**Filed:** 2026-10-03, from the post-merge cross-family review of PR #4315
(command-center packages), which returned REJECT on two P1 leaks.
**Verified:** 2026-10-03 against `main` at `b024c872` (the squash that landed the
feature). The two instances are fixed in PR #4363; this file is about the shape that
produced them.
**Severity:** P1. Not because of the two known files -- those are closed -- but because
the default for an unknown file is "publish", on a surface where publishing is
irreversible and the confirmation tells the owner the opposite.

## What is true

`collect()` walks the command-center directory and includes every file that survives a
series of removals (`structural_exclusion`, `dir_exclusion`, the scrub). The removals
are name-based sets: `_BRAIN_FILES`, `_RUNTIME_FILES`, `NEVER_DIRS`, dot-prefixed
entries, `_DB_SUFFIXES`, and the wiki rule. Everything else is published.

That is a denylist, and it failed exactly as a denylist does -- twice, in the first
review that looked:

- **`orgchart.md`** was absent from `_BRAIN_FILES`. `api/interlocutor.py`'s
  `FOUNDER_PRIVATE_GROUNDING` withholds it from every non-founder interlocutor
  *regardless of the command center's visibility level* -- its comment says a command
  center may be fully public without the founder's private description becoming public.
  It records collaborators, delegations and reporting lines.
- **`requests.json`** was absent from `_RUNTIME_FILES`. It holds the owner's pending
  request text, and it is not inert on arrival: the daemon converts pending rows into
  active work targets, so an installed copy carried someone else's queue.

Neither was a subtle bug in the removal logic. Both lists simply did not name a file
that existed.

## Why the shape is the finding

1. **The default is wrong, not the lists.** A new file in a command-center directory --
   added by a future feature, a new governed grounding file, a new sidecar -- is public
   from the moment it exists. Nobody has to make a mistake for the next leak; somebody
   has to remember to prevent it.
2. **The confirmation promises the opposite.** `publish_requests.PACKAGE_SENTENCE` tells
   the owner: *"Files with a detected credential or contact details, your memory, your
   brain files and platform state were left out."* That is a categorical claim about
   kinds, served by lists of names. Both leaks were in categories the sentence named.
3. **Publishing is irreversible.** A package is copied by other users; withdrawing it
   does not unpublish what was taken.
4. **The ratchet only helps where it is wired.** #4363 derives the brain and request
   exclusions from their authoritative constants, which closes those two for good. There
   is no equivalent authority for "every private file", so the remaining categories are
   still literal lists.

## The durable fix

Invert the default: enumerate what **travels**, and let everything else stay. The
feature already knows what it is for -- the manifest is built from exactly these kinds:

- the UI bundle and its assets;
- workflows (installed as private copies, model policy cleared);
- automations (installed paused);
- roster agents and the harness root files `destination()` remaps into
  `agents/<slug>/`;
- curated `wiki/pages/`;
- files the publisher explicitly selects.

An unrecognised path is excluded and listed as such, rather than published because no
rule happened to name it. Then `PACKAGE_SENTENCE` can state what it actually means, and
a new file added anywhere in a command center is private until someone chooses to share
it.

Worth keeping from the current implementation when this is done: the scrub
(`classify`) and the review flags are good and should still run over the allowlisted
set -- an allowlist stops unknown *kinds*, not a credential pasted into a file that was
meant to travel.

## How to resolve

Replace default-inclusion in `collect()` with explicit shareable-path selection, keep
the scrub over the result, and show a test that a file of an unrecognised kind at the
command-center root is excluded without being named anywhere. Delete this file then.

## Related

- PR #4363 -- closes the two known instances and adds the derivation ratchets.
- `2026-10-01-pending-request-rows-are-agent-writable.md` -- landed with #4315; the
  same directory's contents being writable by the command center's own agent is what
  makes "publish whatever is there" the wrong default.
