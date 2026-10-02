# Design: BoxProvider foundation

This design inherits `openspec/changes/target-architecture/design.md` D2, D3, D4 and D8a. Only
the decisions this slice adds on top of it are recorded here.

## D1. The interface module holds no driver logic

`provider.py` holds the protocol, the types, the errors and `box_relpath`.

`box_relpath` accepts only `/cc` itself or `/cc/<components>`. It refuses:
- any path outside `/cc`;
- empty, `.` and `..` components;
- NULs and backslashes.

This check runs before any driver is called, so no driver can ever be handed an escape. The
contract suite's `import_bundle` traversal test proved its worth by catching a real bug: the
driver normalised names with `lstrip("./")`, which turns `../escape.txt` into `escape.txt`. The
bug is fixed.

## D2. The box host keeps its own record

`BoxHostState` is one SQLite file in the box host's private state directory. It is neither platform state nor box content.

- **Epochs.** A box's epoch starts at 1. `destroy` bumps it, as re-import will later. A handle with a stale epoch is refused.
- **Generations.** Every write, remove, import and finished exec bumps the generation. An exec can change files the driver cannot see, so its completion bumps the generation conservatively. `committed_generation` reads this record and never contacts the box.
- **Operation outcomes, fenced to the host incarnation.**
  - Each host start takes a new incarnation number and marks every operation still `running` as `unknown_after_restore`.
  - An operation records the incarnation it began under. Its completion is written only if it is still `running` under that same incarnation, so a supervisor surviving from an older host cannot overwrite "unknown" with "done".
  - Reusing an `op_id` with a different payload is refused with `OpIdReuse`.
- **Nothing that may have had an effect is forgotten.**
  - Only refusals raised *before* any effect call `abandon`. Examples: a `create` conflict, a `cas` mismatch, a missing working directory.
  - A partial failure is recorded as done-with-error: a recursive remove that fails midway, or an import that fails after writing members. A retry gets the error back and nothing re-runs.
- **Pending work.**
  - Mutations and running execs hold an in-memory pending count per box. It describes this host incarnation only.
  - `read_many` and `export` run only while nothing is pending, and `cas` refuses while anything is.
  - Mutations take the box lock, and an exec can neither start nor finish without it. So with the lock held and nothing pending, the files cannot change under a snapshot.

Each call opens its own connection, inside `BEGIN IMMEDIATE`, and closes it.

## D3. The local driver is a reference, not a boundary

The local driver has no kernel isolation. Construction refuses unless the caller passes `allow_unisolated=True`, and production never selects it: driver selection is box-host configuration (target D1). The same descriptor-safe core is what `boxd` runs inside an isolating box. That is why the rules below hold even here.

**Every operation re-authenticates under the box lock.** It checks the owner, the epoch, and that the box is not being destroyed. A destroy marks the box *destroying*, cancels its execs, waits until each supervisor has killed and reaped its process group, removes the files, and bumps the epoch. An operation that authenticated earlier cannot interleave. A replayed `destroy`, with the same `op_id` through the original handle, returns the recorded receipt even though that handle's epoch is now stale.

**Mutation evidence, against the Linux oracle.** I removed each of fifteen guards in turn, and each removal turned its test red:

| Guard | Test that goes red without it |
|---|---|
| handle owner check | another owner's handle fails every operation |
| epoch check | destroy makes every earlier handle stale |
| `O_NOFOLLOW` on the leaf | planted links are never followed (read, read_many, download, list, stat, write, remove) |
| op-id replay | a retried write or exec runs once |
| `killpg` | cancel kills the whole process tree |
| restart sweep | an old host cannot overwrite unknown with done |
| incarnation fence on completion | same |
| stdin on its own thread | stdin a child never reads cannot stall the wall clock |
| group kill when the leader exits | the exec ends with its leader and takes its group with it |
| output check after exit | a fast exit over the output limit is still `output_limit` |
| read_many pending gate | read_many refuses while an exec may be changing files |
| cas pending gate | cas refuses while an exec is running |
| destroy waits for execs | destroy stops running execs before it returns |
| destroy replay before the epoch check | same |
| streaming input bound | streaming write input is bounded as it arrives |

## D4. Execution

- **Working directory.** It is opened by descriptor, with no link followed, and handed to the child as `/proc/self/fd/N` through a tiny `sh` shim. It is never re-resolved by name, so swapping the directory for a link after the check changes nothing.
- **A missing program is an exec result, not a refusal.** The shell exits with 127.
- **Output.** Stdout and stderr are merged in order. `stream` never yields bytes past the output limit, and an exec that exits fast over the limit is truncated and reported as `output_limit`.
- **Stdin** is fed by its own thread.
- **The exec ends when its leader exits.** Whatever else remains in its process group is killed.
- **Kills.** Wall clock, output limit and cancel each kill the whole group.
- **Downloads** return an iterator that owns its descriptor. Closing or dropping it always closes the fd.
- **Write input** is frozen into immutable bytes, and a streaming iterator is bounded as it arrives.

## D5. Export and import

**Export** is a tar of regular files and directories. Links and special files are left out.
Profile scrubbing (the harness §4.17 `share` manifest) belongs to the export layer above the
driver.

**Import** refuses, and lists in `refused`:
- traversal and absolute paths, and the box root itself;
- links, devices and FIFOs.

Import merges into the box and bumps its generation. Re-import with an epoch bump arrives with
S11.

## D6. The disk bound

The local driver declares no bound (`bound_bytes is None`), so the bound test skips for it with a
stated reason. Drivers that declare a bound must pass it: gVisor through an XFS project quota,
Firecracker through the image size.
