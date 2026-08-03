## ADDED Requirements

### Requirement: Production admission minting authority is daemon-only
The production deployment SHALL provide `TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY` only to the daemon service, and MUST exclude its dedicated environment file and value from the shared host environment and every worker or sidecar after Compose inheritance is resolved.

#### Scenario: resolved worker fleet has no minting secret
- **WHEN** the production Compose document is parsed with its worker anchors and inherited service values resolved
- **THEN** the daemon includes `/etc/tinyassets/request-idempotency.env`
- **AND** every worker, tunnel, and logging service excludes that file

#### Scenario: stale shared duplicate fails closed
- **WHEN** the fenced deploy prepares `/etc/tinyassets/env` before recreating the fleet
- **THEN** it deletes request-idempotency HMAC entries written as canonical assignments, `export` assignments, leading-whitespace assignments, or assignments with whitespace before `=`
- **AND** it fails before Compose synchronization if the shared file is unreadable or still contains that key

#### Scenario: running workers prove the boundary
- **WHEN** the corrected production worker fleet reports running
- **THEN** the deploy inspects every worker process environment without printing it
- **AND** deployment fails if any worker contains `TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY`

#### Scenario: ordinary execution remains dark
- **WHEN** the corrected deployment starts the daemon and legacy worker fleet
- **THEN** no custom-agent invocation, provider route, app ingress, or workflow-iteration capability is activated by this change

### Requirement: Exposed admission authority rotates only through an explicit recovery action
The production deploy workflow SHALL preserve immutable request-idempotency HMAC installation by default and MUST allow replacement only on an explicit manual rotation dispatch. The corrective production cutover MUST replace the exposed key before the corrected fleet is accepted.

#### Scenario: automatic deploy cannot rotate the trust root
- **WHEN** production deployment is triggered by a successful image build or by a manual dispatch without rotation enabled
- **THEN** the installer uses immutable `set-once` semantics and refuses a different existing value

#### Scenario: reviewed correction rotates the exposed trust root
- **WHEN** an operator manually dispatches the reviewed correction with rotation enabled and a newly generated repository secret
- **THEN** the workflow first proves the deployed Compose file exactly matches the reviewed correction, the shared env lacks the key, and all four running workers lack the key
- **AND** the workflow replaces the host request-idempotency HMAC only after those prerequisites pass
- **AND** the rotation path is visible in workflow inputs and run history without exposing the key

#### Scenario: stale or unproved boundary blocks rotation
- **WHEN** the deployed Compose hash differs, the shared env contains the key, a worker is absent, or a running worker contains the key
- **THEN** the manual rotation run fails before transmitting or replacing the host key
- **AND** the operator must complete the ordinary corrected-boundary deploy first

### Requirement: Protected-stdin installation creates no named plaintext value file
The environment installer SHALL construct updated content in the current Bash process without placing its protected-stdin value in process arguments, child environment, or a named plaintext filesystem object, and MUST NOT print the protected value.

#### Scenario: normal and error exits create no residue
- **WHEN** protected-stdin installation succeeds or its content builder fails
- **THEN** no matching value file exists beside the target environment file
- **AND** stdout and stderr contain no protected value

#### Scenario: construction has no child custody lifecycle
- **WHEN** the installer rewrites a protected value
- **THEN** no content-builder child or named plaintext value file exists to outlive the installer

#### Scenario: Compose-valid duplicate immutable assignments fail before mutation
- **WHEN** `set-once` reads more than one Compose-recognized assignment for its target key, including `export`, leading whitespace, whitespace before `=`, or a non-empty assignment followed by an empty assignment
- **THEN** it exits with immutable-refusal status before writing the environment file
- **AND** neither existing nor proposed values appear in output

### Requirement: Offsite production logs cover the complete runtime fleet
The default offsite archive SHALL collect the daemon, tunnel, and every fixed production worker container, and the operator runbook MUST use the deployed TinyAssets service, container, metadata, and archive identities.

#### Scenario: default archive includes all workers
- **WHEN** `ship-logs.sh` runs without a `LOG_CONTAINERS` override
- **THEN** its collection plan includes `tinyassets-daemon`, `tinyassets-tunnel`, `tinyassets-worker`, `tinyassets-worker-codex-2`, `tinyassets-worker-claude-1`, and `tinyassets-worker-claude-2`

#### Scenario: operator examples match deployed identities
- **WHEN** an operator follows the logging runbook to query, download, extract, or troubleshoot logs
- **THEN** the commands reference the current `tinyassets` project/service identities, `tinyassets-logs` container, and `tinyassets-logs-*` archive prefix
