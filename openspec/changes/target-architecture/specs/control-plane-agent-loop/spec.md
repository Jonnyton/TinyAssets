## ADDED Requirements

### Requirement: Agent turns over HTTP model protocols run in the execution owner's loop

The agent turn SHALL run in the cell's execution owner, as part of its shared
asynchronous loop, for every connection that speaks a standard HTTP model
protocol, not in a per-turn process inside the box. The loop SHALL forward each
tool call over the turn's bound box handle with an operation id, and SHALL NOT
execute model output itself. Only the execution owner SHALL write the turn
journal. After a failover or crash, an interrupted turn SHALL reconcile into a
held state, its unknown-outcome operations SHALL stay unknown, and nothing
SHALL be replayed.

#### Scenario: A tool call runs in the user's box
- **WHEN** a model response contains a `bash` tool call
- **THEN** the loop starts that command in the turn's bound box with an operation id, and it runs in that box only

#### Scenario: Failover does not replay a turn
- **WHEN** the primary fails mid-turn and the standby is promoted
- **THEN** the journaled turn reconciles into a held state, and no tool call or external effect is re-issued

### Requirement: Model calls go through the credential broker; the loop and boxes hold no credential

The loop SHALL make model and API calls through the credential broker, with
each request bound to its exact owner, connection and grant. The broker SHALL
perform the upstream call itself. A CLI in a box that uses an API-key
credential SHALL reach its provider through a broker endpoint inside that box,
with no key in its environment. The loop process SHALL hold no model or API
credential. So SHALL every box process, with one exception: a CLI that must
hold and refresh its own token file, during its run, inside its owner's box.

#### Scenario: A prompt-injected command cannot read the model key
- **WHEN** a prompt-injected `bash` in a box prints its environment and every file it can read, while no file-OAuth CLI is running
- **THEN** it finds no model or API credential

### Requirement: A CLI runs in a box only where its credential type needs it

A provider CLI SHALL run inside the owning command center's box only for a
command adapter, or for a credential the CLI must hold itself, such as file
OAuth. One CLI process SHALL never serve two accounts. A Claude subscription
credential SHALL be used server-side only for its owner's own command center,
and only while the owner-scoped `claude_subscription_serving` setting is on,
which SHALL default to off.

#### Scenario: A subscription stays with its owner
- **WHEN** any account other than the subscription's owner asks a turn to use that Claude subscription
- **THEN** the turn refuses to use it

#### Scenario: A file-OAuth CLI's credential reaches only its own box
- **WHEN** a command center connects Codex through its own login and runs it
- **THEN** the credential is stored in that command center's platform directory, materialised only into its box for the run, and copied back through the broker afterwards
