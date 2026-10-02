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

`BoxHostState` is one SQLite file in the box host's private state directory. It is neither
platform state nor box content.

**Epochs.**
- A box's epoch starts at 1.
- `destroy` bumps it, and so will re-import later.
- A handle carrying a stale epoch is refused.

**Generations.**
- Every write, remove, import and finished exec bumps the generation.
- An exec can change files the driver cannot see, so its completion bumps the generation
  conservatively.
- `committed_generation` reads this record and never contacts the box.

**Operations.**
- Each operation is recorded as `running` before its effect, and as `done`, with its outcome,
  after it.
- Reusing an `op_id` with different arguments is refused with `OpIdReuse`.
- An operation refused *before* any effect, such as a `create` conflict or a `cas` mismatch, is
  forgotten, so a corrected retry can reuse its id.
- At startup, every operation still `running` becomes `unknown_after_restore`. A retry of such an
  operation is told "unknown" and never re-runs. This is the same rule as the turn journal.

**Connections.** Each call opens its own connection, inside a `BEGIN IMMEDIATE` transaction, and
closes it. No handle leaks (memory `sqlite-with-block-never-closes`).

## D3. The local driver is a reference, not a boundary

The local driver has no kernel isolation. It is the reference implementation of the contract, and
a dev convenience.
- Construction refuses unless the caller passes `allow_unisolated=True`.
- Production never selects it. The driver is box-host configuration (target D1), and production
  configures gVisor or Firecracker.

What it does guarantee is checked by the suite, with mutation evidence: each guard was removed in
turn, and its test went red.

| Guard | Test | Mutation evidence |
|---|---|---|
| handle owner check | a valid handle presented for another owner fails every operation | removing the check turns it red |
| epoch check | destroy makes every earlier handle stale | removing the check turns it red |
| `O_NOFOLLOW` on the leaf | a planted link to another box is never followed: absolute and `../` links; a remove deletes the link, never its target | dropping `O_NOFOLLOW` turns it red |
| op-id replay | a retried write or exec runs once | disabling the lookup turns 2 tests red |
| process-group kill | cancel kills the whole process tree | `proc.kill()` instead of `killpg` turns it red |
| restart semantics | an exec in flight across a restart reports unknown and is not re-run | disabling the startup sweep turns it red |

## D4. Execution

- Stdout and stderr are merged, in order, into one output stream.
- `stream` never yields bytes past the exec's output limit, even before the supervisor has
  truncated the spool file.
- A wall-clock timeout, the output limit and `cancel` each kill the process group. The cause is
  reported as `killed`.

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
