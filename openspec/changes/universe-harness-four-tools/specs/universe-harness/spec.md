## ADDED Requirements

### Requirement: The universe agent has four platform-run tools over its own folder
A served founder turn that has engine tools SHALL be given exactly four tools
over its own universe folder: `read`, `write`, `edit` and `bash`. The
platform SHALL execute them; no vendor CLI built-in file or shell tool SHALL
be enabled for any turn. The four SHALL be served on the per-universe engine
route, so every provider adapter sees the same definitions, and SHALL NOT be
added to the public connector's top-level handles. No tool parameter SHALL
name a universe: the folder is the engine's pinned universe.

#### Scenario: every adapter sees the same four tools
- **WHEN** the served tool inventory is read for the claude, codex and HTTP
  adapters
- **THEN** each contains `read`, `write`, `edit` and `bash`, the CLIs' own
  `Read`/`Write`/`Edit`/`Bash` remain denied, and the public connector's
  handle set is unchanged

#### Scenario: another user cannot drive the tools
- **WHEN** an engine bound to one principal is pinned at a universe that
  principal does not currently own
- **THEN** every one of the four tools refuses before any process is started

### Requirement: The tools run in a tool jail that holds only the universe
Every tool call SHALL run as a process inside an OS jail in which the owning
universe is mounted read-write at `/u` and no other universe, no data root,
no platform source and no credential snapshot is reachable. `.runtime/` and
the vendor-native `.claude/` and `.codex/` SHALL be masked so they are
neither readable nor writable to disk. The jail SHALL have no network
namespace shared with the host, SHALL start from an empty environment, and
SHALL refuse creating symbolic links and special files. A host with no jail
SHALL refuse the call; there SHALL be no unjailed fallback.

#### Scenario: another universe is unreachable
- **WHEN** the agent reads another universe by its host path, by `..`, or
  through a link it tries to plant
- **THEN** the read fails, the link is never created, and no foreign content
  is returned

#### Scenario: bash has no network
- **WHEN** a jailed command connects to a listener on the host loopback that
  the host itself can reach
- **THEN** the connection fails and the jail has only a loopback interface

#### Scenario: platform-owned and vendor-native dirs are masked
- **WHEN** the agent reads `.runtime/` or writes into `.runtime/` or `.claude/`
- **THEN** it sees no credential or route bearer, and nothing it wrote exists
  on disk after the call

### Requirement: Tool jails run under per-universe resource limits that fail closed
Every tool call SHALL run under limits on address space, process count, cpu
time, file size, open files, core size, wall-clock time, output size, summed
resident memory of its process tree and the free space it leaves on the shared
data volume, with bounded concurrency per universe and per host. A call whose
limits cannot be applied SHALL be refused with nothing run.

#### Scenario: a runaway is killed
- **WHEN** a jailed command allocates without bound, forks without bound,
  spins the cpu, floods output, sleeps past its wall clock, or fills the disk
  towards the floor
- **THEN** it is stopped, the result says which limit stopped it, nothing from
  the jail survives, and the universe's next call works

#### Scenario: limits that cannot be applied refuse the call
- **WHEN** the host has no bubblewrap or no `prlimit`, or the jail exits
  before proving its limits were applied
- **THEN** the call is refused and no command ran

### Requirement: The skill index is in the prompt and a written skill changes the next turn
A served founder turn that has the tools SHALL receive, in its system prompt,
the name and one-line description of each `skills/<name>/SKILL.md` in its
universe (progressive disclosure: not the body), read fresh on every turn and
never through a link. A turn without the tools SHALL receive no folder or
skill section.

#### Scenario: a skill the agent writes is followed on its next turn
- **WHEN** the agent writes `skills/standup/SKILL.md` in one turn
- **THEN** the next turn's prompt lists `standup` with its description, the
  agent reads the skill and follows it, and after the file is deleted a later
  turn no longer lists it

#### Scenario: visitors and dark deploys are not shown the folder
- **WHEN** the turn is not a founder turn, or engine tools are off
- **THEN** the system prompt has no folder or skill section
