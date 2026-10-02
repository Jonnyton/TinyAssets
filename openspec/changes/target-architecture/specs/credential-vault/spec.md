## ADDED Requirements

### Requirement: Each secret lives only in the one process that consumes it

A platform or cloud-account secret SHALL be present only in the environment or
memory of the single process that consumes it. That covers the hosting-provider
API token, the payment secret key, the identity-provider management key, the
tunnel token and the vault decryption key. No process that handles tenant
input SHALL hold any of them. That includes the request-serving daemon, the
agent loop, engine MCP children, boxes and CLIs. The hosting-provider API token
SHALL be held only by CI. The vault decryption key SHALL be held only by the
egress proxy.

#### Scenario: The daemon environment carries no platform secret
- **WHEN** the environment variable names of every process handling tenant input are listed
- **THEN** none of them names a hosting-provider token, payment secret key, identity-provider management key or tunnel token

#### Scenario: The vault key never reaches the loop
- **WHEN** the agent loop process's memory and environment are inspected
- **THEN** the vault decryption key is absent, and model calls still succeed through the egress proxy
