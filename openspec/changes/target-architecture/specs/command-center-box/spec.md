## ADDED Requirements

### Requirement: Every command center runs in exactly one sealed box

The platform SHALL give each command center exactly one box with its own kernel
boundary: a microVM guest kernel on the primary driver, or the gVisor
user-space kernel on the fallback driver. The box SHALL hold the command
center's files: workspace, brain/wiki, notes, skills, prompts, workflows and
agent-owned harness files. Every tool call and every CLI run on the command
center's behalf SHALL execute inside that box and nowhere else. A box SHALL
never hold another account's files, processes or credentials. The driver SHALL
be a box-host configuration, and no code path SHALL branch on it or on the
account's tier.

#### Scenario: Two users' tools run in two boxes
- **WHEN** user A's agent and user B's agent each run `bash` at the same time
- **THEN** each command runs in its own command center's box, under a different host uid and kernel boundary, and neither box can list the other's files

#### Scenario: A second agent of the same command center shares the box
- **WHEN** two agents of one command center run tools concurrently
- **THEN** both run inside that command center's one box

### Requirement: The platform reaches box contents only through BoxProvider

The daemon SHALL read, write, list, stat, export and execute against a command
center's contents only through the `BoxProvider` interface. Paths SHALL be box
paths and SHALL be resolved inside the box. The daemon process SHALL have no
filesystem permission on box disk images, snapshots or their directories. A
ratchet test SHALL fail the build on any daemon-side open of command-center
content outside `BoxProvider`. Everything read from a box SHALL be treated as
untrusted input.

#### Scenario: A planted link cannot reach another user
- **WHEN** an agent creates `founder.md` as a symlink to another command center's path and the daemon then reads `founder.md` for persona grounding
- **THEN** the read resolves inside the box's own filesystem, where the target does not exist, and no other command center's bytes are returned

#### Scenario: The daemon cannot open a box image
- **WHEN** daemon code attempts to open a file under the box host's image directory
- **THEN** the operating system refuses it (different uid, mode 0700), and the ratchet test fails the build if such code is committed

### Requirement: A box handle is bound to its turn and generation

`ensure_awake` SHALL return a handle bound to the command center, its owning
account and the box generation. A turn SHALL carry the handle it obtained at
turn start for every tool call, and SHALL NOT look a box up by name per call.
`BoxProvider` SHALL refuse a handle whose generation is stale, and SHALL refuse
a handle used for a command center other than the one it names.

#### Scenario: A stale handle is refused
- **WHEN** a command center is re-imported (its generation bumps) while an old turn still holds the previous handle
- **THEN** the old turn's next tool call is refused, and nothing executes in the new box

### Requirement: Each box has a fixed-size disk allocated from its account's storage quota

Each box SHALL have one disk image created as a fresh sparse file, never reused
storage, whose size is the box's allocation. The sum of an account's box
allocations SHALL NOT exceed the account's storage quota. The cell's allocator
SHALL be the only writer of allocations, and SHALL grow a box's allocation
online only within the account's remaining quota. A box that fills its
allocation SHALL see `ENOSPC` inside the box, and no other box or host
filesystem SHALL be affected. A denied grow SHALL surface to the user as the
visible storage-quota refusal with its inline Upgrade link.

#### Scenario: One account cannot exhaust the host
- **WHEN** an agent writes until its box's disk is full
- **THEN** its writes fail with `ENOSPC` inside its box, and every other box and the control plane keep writing normally

#### Scenario: The pool stays one per account
- **WHEN** an account with a 2 GiB quota has two command centers allocated 1.5 GiB and 0.3 GiB, and the second asks to grow by 0.5 GiB
- **THEN** the grow is denied as storage-quota exceeded, and the first box is untouched

### Requirement: Boxes are awake only while acting and keep no timers

A box SHALL be woken only by the control plane calling `ensure_awake`. It SHALL
suspend (snapshot and stop) after an idle period of at most 60 seconds with no
exec or file RPC in flight. A box SHALL run no scheduler or cron that the
platform relies on. At host capacity a wake SHALL wait in the box host's
admission queue and SHALL NOT be refused, and the waiting state SHALL be
visible to the user.

#### Scenario: An idle box suspends
- **WHEN** a box finishes its last tool call and nothing calls it for the configured idle period
- **THEN** it is snapshotted and stopped, and its awake-time metering stops

#### Scenario: A full host makes a wake wait
- **WHEN** a wake arrives while the box host has no memory headroom
- **THEN** the wake waits, with a visible waiting state, until headroom frees, and it is not refused

### Requirement: A box has no network interface; its egress goes through the cell's egress proxy

A box SHALL have no network interface. Its only egress SHALL be a single
socket to the cell's egress proxy, which SHALL enforce the egress floor:
globally routable destinations only, no metadata or private ranges, no host
loopback, SMTP ports refused, and a per-box connection cap.

#### Scenario: Metadata is unreachable
- **WHEN** a process in a box requests `http://169.254.169.254/`
- **THEN** the egress proxy refuses it, and no direct path exists

### Requirement: Destroying a command center destroys its box and backups

`BoxProvider.destroy` SHALL remove the box's disk image, its snapshots and its
off-region backup set, and SHALL return a receipt. Account deletion SHALL
complete only when every one of the account's boxes has a destroy receipt.

#### Scenario: Account deletion leaves no box bytes
- **WHEN** an account with two command centers is deleted
- **THEN** both images, all their snapshots and both backup sets are removed, and deletion reports complete only after both receipts exist
