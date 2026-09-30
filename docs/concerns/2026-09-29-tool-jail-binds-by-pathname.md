---
severity: P3
title: The tool jail binds universe entries by pathname, so a link swapped in before launch would be followed
filed: '2026-09-29'
summary: Every per-entry bind in the universe tool jail is a pathname that bubblewrap resolves again at launch. A process outside the jail that swapped a root entry for a symlink in that window would get the link's target bound into /u. No such writer exists today.
---

# The tool jail binds universe entries by pathname

**Filed:** 2026-09-29, from the gpt-6-astra refute round on the fix for the background
tool-jail startup failure (`/u` changed from a read-only root bind with per-file masks
to a read-only tmpfs of `-try` binds).
**Severity:** P3. It needs a writer outside the tool jail that can create symlinks in a
universe root. None exists: the tool jail's seccomp filter refuses `symlink`/`mknod`
and io_uring, the daemon writes no links, and provider CLIs run with their file and
shell builtins denied.

## Source (verbatim, gpt-6-astra, 2026-09-29)

> 1. DISAGREE_EVIDENCE — A raced visible entry can expose hidden credentials. At
> universe_tools.py:278, symlink rejection happens during scanning; mounting later
> follows the pathname. Concrete interleaving: scan ordinary `report.txt`, then an
> outside writer replaces it with `report.txt -> .credential-vault.json`. [...] This
> exposes the credential through a visible name. Previously, this non-owned file had no
> individual bind [...] It requires a writer outside the tool jail; I have not
> demonstrated the jailed agent can perform that replacement itself.
>
> 2. DISAGREE_EVIDENCE — Containment validation does not cover the source ultimately
> bound. [...] The double-resolution race already existed with `strict=True` [...]
> Preserve verified source identity through mounting, rather than relying on another
> pathname check.

## What was done, and what was not

- The Python-side double resolution is gone: `provider_jail._validated_view` resolves
  each bind source once, checks it, and `jail_argv` emits that resolved path.
- bubblewrap still resolves every source path itself at launch (its "Can't find source
  path" error, below, comes from that step), so the
  window between the scan and bubblewrap's mount remains. The owned entries (brain files,
  harness dirs) were already bound this way before the change; it now covers every
  visible entry.

## The fix, when a writer appears

Pin each entry with `os.open(name, O_PATH | O_NOFOLLOW, dir_fd=root_fd)` at the scan
and bind it with `--bind-fd` / `--ro-bind-fd`. Measured in the Linux oracle
(bubblewrap 0.12, 2026-09-29):

- bubblewrap closes each fd it binds, so none reaches the jailed process. An fd passed
  but NOT consumed by a bind does leak into the jail, and an `O_PATH` directory fd
  there is a way out of the mount namespace (`openat(fd, "..")`). Every passed fd must
  be consumed.
- A pinned file that is unlinked before launch fails the whole jail ("Can't find
  source path /proc/self/fd/N"; `--ro-bind-try /proc/self/fd/N` fails with EINVAL).
  So fd pinning brings back the vanished-entry refusal this change fixed, and needs a
  rescan-and-retry on that startup failure.
- `O_PATH` does not exist on Windows, so the argv unit tests become POSIX-only.
