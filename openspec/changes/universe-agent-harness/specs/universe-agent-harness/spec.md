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

### Requirement: Every agent has exactly four resident tools, with breadth behind one searchable command
Every universe agent SHALL have exactly `read`, `write`, `edit` and `bash` as its resident tools, over its universe mounted in the tool jail. The whole user root SHALL be writable, and platform-owned state SHALL be held under `.runtime/` and be absent from the jail. `bash` SHALL have public network egress that refuses loopback, private, link-local and metadata addresses. The jail image SHALL provide a shell toolchain including a language runtime and git.

No other tool schema SHALL be sent to the model. Native adapter built-in tools SHALL be disabled. Platform capabilities, the owner's connected-app operations, user extensions and MCP servers the user attached SHALL be reachable only through one command in the jail. That command SHALL provide search, describe and call over the same handlers as the public connector, and the base prompt SHALL carry one line naming it.

#### Scenario: the agent installs and runs a tool it needs
- **WHEN** the agent runs a package install and then the installed tool in bash
- **THEN** both succeed inside its universe and the bytes count to the account's storage

#### Scenario: egress cannot reach the host or another user
- **WHEN** bash connects to a loopback, private-range or metadata address
- **THEN** the connection is refused

#### Scenario: a capability is found and called without a resident schema
- **WHEN** the agent needs to start one of its workflows
- **THEN** it finds the capability by searching from bash and calls it there
- **AND** the model request on every round carried only the four tool schemas

### Requirement: Onboarding gives a new universe's agent a name and one responsibility
On a new universe's first conversation, from any surface, the agent SHALL ask for a name and a responsibility. The responsibility SHALL cover what the agent owns, where it learns from, its quality bar, what needs approval, and how often it reports. The answers SHALL be written to the universe's own files. Each approval item SHALL be proposed to the owner as an ask-first rule, and the report cadence SHALL become a scheduled activity. When no compute is connected, onboarding SHALL say so and SHALL NOT simulate a reply.

#### Scenario: a responsibility becomes files, rules and a schedule
- **WHEN** a new user names the agent and states a responsibility including "ask before emailing clients" and "report every Monday"
- **THEN** `AGENTS.md` carries the responsibility, a proposed ask-first rule for client email awaits the owner's confirmation, and a Monday report activity is scheduled

#### Scenario: no compute
- **WHEN** a new user starts onboarding with no compute connected
- **THEN** the reply states that no model is connected and how to connect one

### Requirement: An agent works on several activities at once, without a connected client
An agent SHALL be able to start activities. An activity is a child session with a title, an origin (owner ask, approved proposal or schedule), a status (`in_progress`, `waiting_on_you`, `scheduled`, `paused`, `completed` or `failed`), a result summary and receipts. Several activities SHALL run concurrently, each taking an agent seat from the account pool. An activity started when seats are full SHALL wait visibly rather than be refused. Activities SHALL run without any connected client, and status changes SHALL reach the agent's main session as a platform-computed line. Stopping an activity SHALL keep its partial result.

#### Scenario: two projects continue after the chat closes
- **WHEN** the owner asks for two tasks and closes the app
- **THEN** both activities run to completion and the owner's next visit shows both under Completed with receipts

#### Scenario: seats are full
- **WHEN** an activity starts while every seat is taken
- **THEN** it shows as waiting and starts when a seat frees

### Requirement: Idle proactive research is read-only by enforcement, and its output is proposals only
When an agent is not paused, has no in-progress activity, has not been messaged by its owner for its idle period, and is inside its active hours, the platform SHALL run a research turn. It runs at most at the agent's configured cadence, and also when a connected read source reports new items. A cadence of `off` SHALL disable it.

The research turn SHALL run in a read-only tool profile enforced by the tool layer and not by instructions:
- `write` and `edit` are refused;
- `bash` runs with the universe read-only and no network egress;
- the platform command answers only non-mutating capabilities;
- connected-app calls are limited to declared read operations;
- no browser is available.

The turn's only outward output SHALL be zero or more proposal requests, each naming one planned action. Approving a proposal SHALL start an activity in which that exact action counts as pre-approved.

#### Scenario: research cannot change anything
- **WHEN** a research turn attempts a file write, a network connection from bash, a mutating platform call or a connected-app write
- **THEN** each attempt is refused by the platform and nothing changes

#### Scenario: a proposal is approved
- **WHEN** a research turn proposes sending an unsent invoice and the owner approves it
- **THEN** an activity starts in which sending that invoice is pre-approved and still passes auto-review

#### Scenario: nothing to propose
- **WHEN** a research turn finds nothing worth proposing
- **THEN** no request or notification is produced

### Requirement: Every consequential action is decided by the owner's Custom Rules
Before executing an action, every enforcement point SHALL call one decision function. The enforcement points are the tool layer, the platform command, the credential-blind effectors, the egress proxy and the browser command. The decision function takes the action's class and fields and returns the behaviour of the most specific matching rule; when two rules are equally specific, it returns the stricter one. There are four behaviours:
- **do:** proceed, after auto-review when the action is consequential.
- **do if pre-approved:** proceed only when an owner message in the session or an approved proposal names exactly this action. Otherwise the action is treated as ask first.
- **ask first:** raise one app request and set the activity to waiting on you, while the agent continues other work.
- **hand off:** raise a request for the owner to perform the action. The agent SHALL NOT execute it even after approval.

Rules SHALL be stored in owner-only platform state. The agent SHALL be able to read them and propose changes. Its writes to rules SHALL be refused.

New universes SHALL be seeded with rules that allow every action inside the universe, shell egress and connected-app reads, and that allow writes to destinations under an existing standing grant. The seed rules SHALL set ask first for new destinations, messaging people, publishing, sharing, spending over budget and browser submits. Standing destination grants and their call-time checks SHALL be preserved. An approval marked "always allow" SHALL write a do rule.

#### Scenario: approve once, then reuse
- **WHEN** the agent first emails a new client under an ask-first rule, the owner approves with "always allow", and a later activity emails the same client
- **THEN** the later email proceeds without a new request

#### Scenario: pre-approval is exact
- **WHEN** a do-if-pre-approved rule covers payments-page edits and the owner asked only to fix a typo
- **THEN** a typo fix proceeds and a price change becomes a request

#### Scenario: the agent cannot loosen its own rules
- **WHEN** the agent writes to its rules from any tool
- **THEN** the write is refused and the agent may instead raise a rule-change request

### Requirement: Consequential actions pass an auto-review on the universe's own model
Before any action outside the universe's own files, shell and workflows, other than a connected-app read, whose rule is do or do if pre-approved, the platform SHALL run a review. The review SHALL use the universe's own model and credentials and SHALL take as input the planned action, the agent's responsibility, recent owner messages, the matching rules and the built-in safety requirements. The review SHALL return proceed or needs approval with a reason. Needs approval SHALL convert the action to ask first. If the review cannot run, the action SHALL become a request naming the cause and SHALL NOT proceed. Actions inside the universe SHALL NOT be reviewed.

#### Scenario: review blocks an off-instruction send
- **WHEN** a do rule covers a channel but the planned message contradicts the owner's stated instructions
- **THEN** the review returns needs approval and the owner receives a request with the reason

#### Scenario: review cannot run
- **WHEN** the universe's model is unavailable at review time
- **THEN** the action becomes a request naming that cause and is not executed

### Requirement: Reserved actions always return to the owner
The following SHALL always resolve to hand off:
- changing a password, credential or security setting on an external account;
- moving money or making a payment;
- granting another person access to the owner's accounts or data.

No rule, imported bundle or agent edit SHALL change this. The request SHALL offer take-over when the step is in the agent's browser.

#### Scenario: a payment is handed back
- **WHEN** the agent reaches a payment step, even under a rule that says do
- **THEN** it is not executed, and the owner receives a hand-off request offering take-over

### Requirement: Each agent has a profile with Activity, its computer, Pause and push
Each agent SHALL have a profile showing its name, responsibility, status, model and usage, with these tabs:
- **Activity:** waiting on you first, then in progress, scheduled, and completed with receipts. Each activity can be steered, paused or stopped.
- **Computer:** a live view of its browser and current shell output, with take over and return control.
- **Memory**, **Rules** and **Harness**.

Pausing an agent SHALL stop its new turns, research and scheduled activities, and SHALL stop the running turn at its next tool boundary. While the owner has taken over, the agent's browser commands SHALL wait. On return the session SHALL receive a platform-computed line. Input typed during take-over SHALL NOT enter the session or the model.

The agent's browser profile SHALL NOT be readable from the tool jail. The platform SHALL push notifications for completed, waiting-on-you and new-proposal events. A roster view SHALL show every agent with status, waiting count, current activity and next scheduled run, with inline approve and pause. Both views SHALL be built on the user-editable custom-UI layer.

#### Scenario: the owner logs in for the agent
- **WHEN** the agent hits a login page, the owner takes over, signs in and returns control
- **THEN** the agent continues with the logged-in session, and the password appears in no session log or model request

#### Scenario: pause holds everything
- **WHEN** the owner pauses an agent with a running activity and a scheduled one
- **THEN** the running turn stops at its next tool boundary, the scheduled activity does not start, and no research turn runs until resume

### Requirement: Memory is editable item by item
Agent memory SHALL be held as items with stable ids. The owner SHALL be able to view, edit and delete any single item. Each change SHALL be recorded in the universe's file history with undo, and deleting an item SHALL NOT require deleting the agent.

#### Scenario: one memory is removed
- **WHEN** the owner deletes one memory item from the profile
- **THEN** the next turn's memory lacks that item and every other item is unchanged

### Requirement: The harness layer is user-configurable for any roster of agents
A universe SHALL support any number of agents. Each agent SHALL have its own instructions, identity, memory, skills, extensions, settings (model, research cadence, idle period, active hours, compaction, channels), rules, sessions, activities and profile. A per-agent skill or extension SHALL override a universe-level one of the same name. An agent SHALL be able to start an activity on another agent in the same universe. New universes SHALL be seeded from an explicitly published starter template.

#### Scenario: a lead hands work to a specialist
- **WHEN** the owner's main agent starts an activity on a specialist agent with narrower rules
- **THEN** the activity runs under the specialist's rules and appears in the specialist's profile

### Requirement: Harness bundles and command-center layouts are shareable through a quarantined import
An owner SHALL be able to export one agent's or a roster's harness, optionally with profile and roster layouts, as a public agent definition. The export SHALL be published only after the owner confirms a scrubbed preview. It SHALL exclude memory unless the owner opts in item by item, and SHALL always exclude session logs, credentials and browser state.

An import SHALL be copied to an inert quarantine in which no rules apply, no extensions run, no schedules register and no channels connect until the owner activates it. Imported rule suggestions SHALL activate only as written or stricter, unless the owner edits them. Imported text SHALL reach agents inside the untrusted-content envelope.

#### Scenario: an imported bundle does nothing until activated
- **WHEN** a user imports another user's bundle that contains a schedule and an extension
- **THEN** nothing is scheduled or executed until the user activates the bundle

#### Scenario: export never carries secrets
- **WHEN** an owner exports an agent
- **THEN** the bundle contains no session log, credential, browser state or unselected memory, and the owner's contact details are scrubbed from its text

### Requirement: The harness is files the agent edits, versioned with rollback
Turn assembly SHALL be mechanical: a base prompt, then the universe's `AGENTS.md`, then a bounded `MEMORY.md`, then the skill index, then the session. The agent SHALL be able to edit `AGENTS.md`, `MEMORY.md`, its skills, prompts, extensions and settings file (but not its rules, which are owner-only), and the platform SHALL record every turn's changes to tracked universe files in a platform-owned history store the agent cannot write, with any version-control process run inside a credential-free jail rather than on the host, and the owner SHALL be able to roll back from the app.

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
