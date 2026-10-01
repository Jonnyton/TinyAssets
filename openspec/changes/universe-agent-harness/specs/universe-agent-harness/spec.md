## ADDED Requirements

### Requirement: A universe agent works in a persisted session per thread or agent node
The platform SHALL keep one durable, append-only session per conversation thread and one per agent node (keyed by branch definition and node), recording every message, tool call, tool result, compaction and event, and SHALL build each model request from that session rather than from a re-rendered text summary of recent messages. The session log SHALL be held in platform-owned storage, exposed to the owning universe's agent only through a read-only view, and writable only by the platform.

#### Scenario: a follow-up sees the agent's own earlier tool work
- **WHEN** the founder sends a message after a turn in the same thread that called tools
- **THEN** the next model request contains those tool calls and their results (or a compaction summary that covers them)
- **AND** it does not depend on a fixed message-count or character cap on history

#### Scenario: one thread across surfaces
- **WHEN** the founder continues the same thread from the app, the phone and the connector
- **THEN** each message appends to the same session

#### Scenario: the agent cannot forge its history
- **WHEN** the agent writes to its session log path from a tool
- **THEN** the write is refused and the log is unchanged

### Requirement: Sessions compact automatically with a pre-compaction flush
When a session's projected context exceeds the model window minus a reserve, the platform SHALL first give the agent one round to write durable notes to its files, then, using the universe's own model and credentials with no platform fallback, replace older entries in model context with a structured summary that keeps tool call and result pairs together, while the original entries remain in the log. Thresholds SHALL be read from the universe's own settings file with defaults of a 16,000-token reserve and 20,000 recent tokens kept verbatim.

#### Scenario: a long session keeps working past the window
- **WHEN** a session grows beyond the model window minus the reserve
- **THEN** a flush round runs, a compaction entry is appended, and the next request carries the summary plus recent entries
- **AND** the full history is still in the log

#### Scenario: the owner tunes compaction
- **WHEN** the universe's settings file sets a different reserve
- **THEN** compaction uses that reserve

### Requirement: Native adapters continue sessions through a declared resume capability
An adapter SHALL declare whether it can resume a native session from an opaque handle and whether it compacts itself; the platform SHALL store the handle on the session and resume it when declared, and SHALL seed a new native session from the latest summary and recent entries when the adapter cannot resume or the model changed. No platform policy SHALL name a vendor.

#### Scenario: a resumable adapter continues instead of starting fresh
- **WHEN** a session served by an adapter that declares resume receives its next message
- **THEN** the adapter resumes the stored native handle rather than launching an ephemeral session

#### Scenario: model switch reseeds
- **WHEN** the next turn of a session runs on a different model or an adapter without resume
- **THEN** the platform seeds it from the session's summary and recent entries

### Requirement: Owner messages and owner-relevant events reach the live session
An owner message, or an event concerning the owner's session (a run that session started completing, a request it raised being answered), that arrives while a turn of that session is running SHALL be appended to the result of that turn's next tool call together with the current unread count; when the session is idle it SHALL open the session's next turn as one mechanical line computed by the platform. The platform SHALL NOT impose a wake policy on agents the universe builds.

#### Scenario: a message steers the agent mid-turn
- **WHEN** the owner sends a message while the agent's turn is running tools
- **THEN** the message text and unread count reach the model with the result of the next tool call, in the same turn

#### Scenario: a finished run is reported without being asked
- **WHEN** a run the session started completes while the session is idle
- **THEN** the session's next turn opens with a single line naming the run and its outcome

### Requirement: The agent's core tools are file and shell tools in its jailed universe with public network
The agent SHALL have `read`, `write`, `edit` and `bash` over its universe mounted in the tool jail, with the whole user root writable and platform-owned state held under `.runtime/` and absent from the jail, and `bash` SHALL have public network egress that refuses loopback, private, link-local and metadata addresses. The jail image SHALL provide a shell toolchain including a language runtime, git and a headless browser.

#### Scenario: the agent installs and runs a tool it needs
- **WHEN** the agent runs a package install and then the installed tool in bash
- **THEN** both succeed inside its universe and the bytes count to the account's storage

#### Scenario: egress cannot reach the host or another user
- **WHEN** bash connects to a loopback, private-range or metadata address
- **THEN** the connection is refused

### Requirement: The platform reaches the agent as one extension, not a resident tool block
Platform capabilities (graphs, runs, automations, requests, commons, connections) SHALL be reachable from the jail as one command-line tool with self-describing help and, for adapters that load tool schemas on demand, as deferred tools, using the same handlers as the public connector; the resident per-round tool definitions SHALL be limited to the core tools plus one line naming the platform extension.

#### Scenario: a platform capability with no resident schema
- **WHEN** the agent needs to start one of its workflows
- **THEN** it can do so through the platform extension without that capability's schema having been sent on every round

### Requirement: Inside its universe the agent acts without asking; outside it asks once through the app
A primary agent's default authority SHALL include every action inside its own universe (files, shell, network egress, browser, its workflows and agents, its own harness and brain, use of already-granted connections within their scope, and its own seats and compute). The agent SHALL ask only for a credential or wider grant it does not hold, for acting toward other people or their property without a standing grant for that destination, or for spending beyond a budget the user set, and SHALL ask by raising an app request rather than in chat. An approval SHALL be a standing, revocable grant checked at call time, not consent for a single action or turn.

#### Scenario: no consent replay for a granted destination
- **WHEN** the agent posts to a destination its owner already granted, from a later turn or a run with the owner signed out
- **THEN** the call proceeds under the standing grant without a new request

#### Scenario: a new destination is asked for once
- **WHEN** the agent needs to reach a destination with no grant
- **THEN** it raises one app request covering the job's needs and continues other work until it is answered

#### Scenario: an owner narrows an agent
- **WHEN** the owner restricts an agent node's tools
- **THEN** that agent is refused the removed tools and other agents keep the default

### Requirement: The harness is files the agent edits, versioned with rollback
Turn assembly SHALL be mechanical: a base prompt, then the universe's `AGENTS.md`, then a bounded `MEMORY.md`, then the skill index, then the session. The agent SHALL be able to edit `AGENTS.md`, `MEMORY.md`, its skills, prompts, extensions and settings file, and the platform SHALL record every turn's changes to tracked universe files in a platform-owned history store the agent cannot write, with any version-control process run inside a credential-free jail rather than on the host, and the owner SHALL be able to roll back from the app.

#### Scenario: a told preference changes the next turn
- **WHEN** the founder tells the agent how to work and the agent edits `AGENTS.md`
- **THEN** the next turn's request contains the edited text

#### Scenario: a bad self-edit is undone
- **WHEN** a turn empties or more than halves a loaded harness or brain file
- **THEN** the change is committed, the app offers an Undo for it, and the agent's next event line names it
- **AND** Undo restores the previous content

#### Scenario: a saved skill is used in a new session
- **WHEN** the agent writes `skills/<name>/SKILL.md` and a later session's task matches its description
- **THEN** the skill appears in that session's index and its body is readable on demand

### Requirement: Tool results are truthful, fast and never silently truncated
Every adapter's tool calls SHALL be journaled into the session log. A tool failure SHALL return its actual cause, and a result larger than the model budget SHALL be written to a file in the session's output area and returned as a head plus that path.

#### Scenario: an oversized read is still complete
- **WHEN** a platform read returns more than the model budget
- **THEN** the agent receives the beginning and a path from which it reads the full result

#### Scenario: native tool calls are visible
- **WHEN** a native adapter turn calls tools
- **THEN** each call and its result appear in the session log and the app's activity view

### Requirement: The default voice is concise and result-first
The seed `AGENTS.md` given to a new universe SHALL instruct reporting results first in a few lines, verifying effects before reporting them, and stating unverified items only when they change what the owner should do; the platform's base prompt SHALL NOT add persona, warmth, curiosity or ask-to-clarify instructions of its own.

#### Scenario: the base prompt carries no persona policy
- **WHEN** a turn is assembled for a universe whose `AGENTS.md` is empty
- **THEN** the request contains the base prompt's tool, folder and untrusted-envelope lines and no platform-authored persona or tone instructions
