## ADDED Requirements

### Requirement: The local box driver is for tests and development only

The local `BoxProvider` driver SHALL refuse to start unless the caller explicitly acknowledges
that it has no kernel boundary. No production box-host configuration SHALL select it.

For every operation, it SHALL still enforce:
- handle ownership;
- placement epochs;
- operation-id idempotency, with an operation's outcome reported as unknown after a restart;
- link-free path resolution beneath the box directory.

It SHALL pass the same driver-agnostic contract suite as every isolating driver.

#### Scenario: Unacknowledged use is refused
- **WHEN** code constructs the local driver without acknowledging that it has no kernel boundary
- **THEN** construction fails with a box error, and no box directory is used

#### Scenario: A planted link is not followed even by the local driver
- **WHEN** a command run in a local box creates a link to another box's file, and the daemon reads that path through the driver
- **THEN** the read is refused as crossing a link, and no other box's bytes are returned

### Requirement: Every box call is bounded and says whether it ran

Every caller-facing `BoxProvider` call SHALL finish within the provider's call timeout, or the
tighter deadline the caller set. A call that runs out of time before it could have had any
effect SHALL raise an error that is both a deadline error and a never-ran refusal, leaving its
operation id free. A call that runs out of time after it may have started SHALL raise a
deadline error whose outcome is unknown. Cancelling an exec SHALL NOT wait behind other calls
on the same box.

#### Scenario: A held box fails fast and says nothing ran
- **WHEN** a write is made with a 0.3 second deadline while the box is held by another call
- **THEN** it raises the never-ran deadline error within the deadline, and the same op id runs normally afterwards

#### Scenario: Cancel reaches a running exec while the box is held
- **WHEN** an exec is running and another call holds the box
- **THEN** cancelling the exec returns at once, and the exec ends as cancelled

### Requirement: The execution owner's fence and the idle proof

A box handle SHALL carry the execution owner's generation for its command center. A box SHALL
refuse writes, removes, imports, execs and destroy from a handle whose owner generation is
below the box's fence; reads SHALL NOT be fenced. The provider SHALL offer an idle proof that
raises the fence only if nothing is pending or running in the box, as one atomic step, and
otherwise changes nothing.

#### Scenario: An idle box is fenced and the old owner is refused
- **WHEN** the idle proof runs at generation 2 on a box with nothing running
- **THEN** it returns true, and a write or exec from a generation-1 handle is refused as a stale owner

#### Scenario: An exec racing the fence never both proceed
- **WHEN** an exec start and the idle proof race on the same box
- **THEN** either the exec started and the proof returned false, or the proof returned true and the exec was refused

### Requirement: The gVisor driver contains a box by ending the box

The gVisor box driver SHALL run every command inside its box's sandbox. The sandbox SHALL
have:
- no network;
- a host uid range that no other box shares;
- its own cgroup with a memory limit that swap cannot exceed and a process limit;
- when a disk bound is configured, a hard filesystem quota.

Destroy, any call whose outcome is unknown, and the start of a new box host SHALL end the
whole sandbox, so no process started in a box outlives it. The driver SHALL pass the
driver-agnostic contract suite, including the disk-bound test.

#### Scenario: A detached background process dies with its box
- **WHEN** a command in a box starts a background process in its own session and exits, and the box is then destroyed
- **THEN** no process belonging to that box's sandbox remains on the host

#### Scenario: A new box host ends what a crashed host left running
- **WHEN** a box host is killed while an exec runs in a box, and a new box host starts on the same state
- **THEN** the new host ends that box before serving, reports the exec's outcome as unknown, and the box's files remain
