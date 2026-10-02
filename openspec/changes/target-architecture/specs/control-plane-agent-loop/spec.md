## ADDED Requirements

### Requirement: Agent turns over HTTP model protocols run in the control plane's loop

The agent turn SHALL run in the control plane's shared asynchronous loop, not
in a per-turn process inside the box, for every connection that speaks a
standard HTTP model protocol. The loop SHALL forward each tool call over the turn's
bound box handle, and SHALL NOT execute model output itself. The turn journal
SHALL record each round as today. After a failover, an interrupted turn SHALL
reconcile into a held state and SHALL NOT be replayed.

#### Scenario: A tool call runs in the user's box
- **WHEN** a model response in a turn contains a `bash` tool call
- **THEN** the loop sends that command to the turn's bound box over `BoxProvider.exec`, and the command runs in that box only

#### Scenario: Failover does not replay a turn
- **WHEN** the primary cell fails mid-turn and the standby is promoted
- **THEN** the journaled turn reconciles into a held state on the standby, and no tool call or external effect is re-issued

### Requirement: Model credentials stay outside the box and outside the loop process

Header-auth model and API credentials SHALL be injected by the egress proxy
into requests bound for the endpoint the connection names. The loop process
and every box process SHALL hold only a placeholder. The egress proxy SHALL
substitute a credential only for its named endpoint, and SHALL tunnel
connections without a placeholder unmodified.

#### Scenario: A prompt-injected command cannot read the model key
- **WHEN** a prompt-injected `bash` in a box prints its environment and every file it can read
- **THEN** it finds no real model credential

### Requirement: A CLI runs in a box only where its credential type needs it

A provider CLI SHALL run inside the owning command center's box only for a
command adapter, or for a credential that the CLI must hold and refresh itself,
such as file-based OAuth. One CLI process SHALL never serve two accounts. A
Claude subscription credential SHALL be used server-side only for its owner's
own command center, and only while the owner-scoped
`claude_subscription_serving` setting is on. That setting SHALL default to off.

#### Scenario: A subscription stays with its owner
- **WHEN** any account other than the subscription's owner asks a turn to use that Claude subscription
- **THEN** the turn refuses to use it

#### Scenario: A file-OAuth CLI keeps its credential in its own box
- **WHEN** a command center connects Codex through its own login
- **THEN** the CLI's credential file lives encrypted on that box's disk, and on no shared host path
