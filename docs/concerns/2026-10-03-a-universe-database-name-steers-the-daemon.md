---
severity: P1
title: A command center's database name can steer the daemon into another command center
filed: '2026-10-03'
summary: 'A per-command-center hidden database sits in a folder the command center''s own processes can write, and the daemon opens it by NAME. Measured: with a link planted at the name, the daemon read another command center''s rows AND committed a row into its database. The jail''s masking is the current mitigation and covers jailed provider launches only. There is no in-place fix: Python''s sqlite3 cannot be given a descriptor or SQLITE_OPEN_NOFOLLOW, a ?nofollow=1 URI parameter is silently ignored, and /proc/self/fd is path-resolved (SQLite creates a new empty database named "x.db (deleted)"). The closures are structural -- move platform databases out of command-center-writable folders, or the per-role uid split plus a sticky parent.'
---

# A command center's database name can steer the daemon into another command center

**Filed:** 2026-10-03, from the review of PR #4330 and the measurements that
followed it.
**Verified:** 2026-10-03 in the Linux oracle (`scripts/linux_oracle.py`, SQLite
3.46.1). Every claim below is from a run, not from reading.
**Severity:** P1. A cross-command-center read *and write* when the preconditions
are met; the preconditions are partly covered today, which is why it is not P0.

## Already known, and understated

The threat is named verbatim in the code. `tinyassets/providers/provider_jail.py`
(the `hidden_root_masks` docstring) says the daemon reads and WRITES a command
center's hidden databases from outside the jail, so "a provider that could
replace one with a link (`.runs.db -> /data/<other>/.runs.db`) would steer the
daemon's own `sqlite3.connect` into another universe."

"Steer" is too mild. Running exactly that order -- open the leaf `O_NOFOLLOW`
under a held parent descriptor, verify it, let the name be replaced by a link,
then `sqlite3.connect(name)` -- the daemon **read the other database's rows and
committed `DAEMON-WROTE-HERE` into it.** A write, not a peek.

## What covers it today, and what does not

- **Covered:** a jailed provider cannot replace a masked entry while the jail
  holds it, and `hidden_root_masks` refuses a launch outright if a hidden root
  entry is already a link. That is a real mitigation for the provider path.
- **Not covered by that:** the daemon's own opens happen outside any jail and at
  any time. The mitigation is indirect -- it depends on no other write path
  reaching a command center's root. **No live unjailed write path has been
  identified**, and this concern does not claim one; it records that the
  property is held by the absence of such a path rather than by the open itself.
- `tinyassets/api/resource_usage.py` previously checked `is_symlink()` and then
  connected by name -- textbook check-then-use, and the window the measurement
  above exploits.

## Why there is no in-place fix

Three mechanisms, all measured dead:

1. **`?nofollow=1` as a URI parameter: ignored.** `SQLITE_OPEN_NOFOLLOW` is a C
   open flag. The recognised URI parameters are `vfs`, `mode`, `cache`, `psow`,
   `nolock`, `immutable`; anything else is accepted silently, including an
   invented name -- so nothing ever surfaced the mistake. This was PR #4330's
   proposed guarantee.
2. **`sqlite3.connect("/proc/self/fd/<n>")`: not a substitute.** It passes every
   test in isolation -- reads the verified inode, writes, survives a WAL switch
   -- and fails in exactly the case it exists for. SQLite resolves the string as
   a *path*; once the name is replaced, `/proc/self/fd/<n>` reads
   `".../x.db (deleted)"`, and SQLite creates a **new empty database** under
   that literal name. The daemon would then operate on an empty file and litter
   `x.db (deleted)` into the folder.
3. **The flag, or a custom VFS:** C-only. Python's `sqlite3` exposes neither and
   cannot take a descriptor.

So no amount of care at the call site produces a no-follow open from Python.

## What is in the tree now (the partial mitigation)

`universe_files.connect_guarded` opens the leaf `O_NOFOLLOW` beneath a parent
descriptor opened the same way per component, holds that descriptor, and
re-compares device and inode after `connect` returns and before any statement
runs. A link at the name or on the path refuses outright; a swap inside the
window is detected before a row is read, and the connection is closed. Its
docstring states plainly that this is detection in a narrow window, not the
guarantee a reader might assume. `tests/test_universe_sqlite_identity.py`
holds all of it, including the `?nofollow=1` disproof as a tombstone so nobody
retries it.

## The closures

1. **Move platform databases out of command-center-writable folders.** No
   plantable name, so the class disappears rather than being detected. This is
   a storage-shape change with a migration, so it needs a proposal -- and it is
   what `2026-10-01-platform-state-inside-the-universe-dir` already argues.
2. **The per-role uid split (`openspec/changes/per-role-uid-split`) plus a
   sticky parent.** Today a command center's processes share the daemon's uid,
   so `+t` buys nothing: a same-uid process may rename the daemon's entry. Once
   engine and provider children run as their own uid and the folder is owned by
   the daemon's, the sticky bit stops them renaming it. Cheap, and it follows
   that change rather than leading it.

(1) is the real fix; (2) is a strong second line that arrives with work already
in the queue.

## How to resolve

Land (1), or (2) with a test proving a child uid cannot rename a daemon-owned
database name. Then the identity comparison becomes belt-and-braces rather than
the only line, and this file goes.

## Related

- `2026-10-01-platform-state-inside-the-universe-dir.md` -- the same root cause,
  argued from storage shape.
- PR #4330 -- attempted the in-place guarantee; its mechanism is disproved
  above. Its other review findings (delayed grandfathering trusting post-epoch
  writes, mode parsing, unrecoverable interruption) are defects in provenance
  machinery that closure (1) would make unnecessary, and are not carried
  forward.
