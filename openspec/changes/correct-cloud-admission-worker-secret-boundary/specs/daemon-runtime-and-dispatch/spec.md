## ADDED Requirements

### Requirement: Production admission minting authority is daemon-only
The production deployment SHALL provide `TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY` only to the daemon service, and MUST exclude its dedicated environment file and value from every worker and sidecar after Compose inheritance is resolved.

#### Scenario: resolved worker fleet has no minting secret
- **WHEN** the production Compose document is parsed with its worker anchors and inherited service values resolved
- **THEN** the daemon includes `/etc/tinyassets/request-idempotency.env`
- **AND** every worker, tunnel, and logging service excludes that file

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
- **THEN** the workflow replaces the host request-idempotency HMAC before recreating the corrected fleet
- **AND** the rotation path is visible in workflow inputs and run history without exposing the key

### Requirement: Protected-stdin installation leaves no plaintext value file
The environment installer SHALL remove its mode-600 protected-stdin value file on successful completion, construction failure, shell exit, and HUP, INT, or TERM termination, and MUST NOT print the protected value.

#### Scenario: normal and error exits clean up
- **WHEN** protected-stdin installation succeeds or fails after creating its value file
- **THEN** no matching value file remains beside the target environment file
- **AND** stdout and stderr contain no protected value

#### Scenario: termination cleans up and preserves signal semantics
- **WHEN** HUP, INT, or TERM arrives after the protected value file is created
- **THEN** the file is removed before the process terminates
- **AND** the script re-raises the original signal rather than reporting success

### Requirement: Offsite production logs cover the complete runtime fleet
The default offsite archive SHALL collect the daemon, tunnel, and every fixed production worker container, and the operator runbook MUST use the deployed TinyAssets service, container, metadata, and archive identities.

#### Scenario: default archive includes all workers
- **WHEN** `ship-logs.sh` runs without a `LOG_CONTAINERS` override
- **THEN** its collection plan includes `tinyassets-daemon`, `tinyassets-tunnel`, `tinyassets-worker`, `tinyassets-worker-codex-2`, `tinyassets-worker-claude-1`, and `tinyassets-worker-claude-2`

#### Scenario: operator examples match deployed identities
- **WHEN** an operator follows the logging runbook to query, download, extract, or troubleshoot logs
- **THEN** the commands reference the current `tinyassets` project/service identities, `tinyassets-logs` container, and `tinyassets-logs-*` archive prefix
