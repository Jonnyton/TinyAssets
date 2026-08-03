## ADDED Requirements

### Requirement: Production admission minting authority is daemon-only
The production deployment SHALL provide `TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY` only to the daemon service, and MUST exclude its dedicated environment file and value from the shared host environment and every worker or sidecar after Compose inheritance is resolved.

#### Scenario: resolved worker fleet has no minting secret
- **WHEN** the production Compose document is parsed with its worker anchors and inherited service values resolved
- **THEN** the daemon includes `/etc/tinyassets/request-idempotency.env`
- **AND** every worker, tunnel, and logging service excludes that file

#### Scenario: stale shared duplicate fails closed
- **WHEN** the fenced deploy prepares `/etc/tinyassets/env` before recreating the fleet
- **THEN** it deletes request-idempotency HMAC entries written as canonical assignments, UTF-8-BOM-prefixed first assignments, `export` assignments, assignments using Compose's complete accepted Unicode White_Space set before the declaration or supported whitespace before the delimiter, or assignments using either Compose-supported `=` or `:` delimiters
- **AND** it fails before Compose synchronization if the shared file is unreadable or still contains that key

#### Scenario: running workers prove the boundary
- **WHEN** the corrected production worker fleet reports running
- **THEN** the deploy inspects every worker's configured environment through host-controlled Docker metadata without printing it
- **AND** the proof executes no worker-controlled Python or other in-container oracle
- **AND** deployment fails if any worker contains `TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY`

#### Scenario: worker-controlled startup customization cannot falsify absence
- **WHEN** an approved source node has planted `/app/sitecustomize.py` that removes the key from Python's environment before `python -c`
- **THEN** the old in-container oracle can report false absence but the deployment proof still reads the unchanged Docker configuration from the host
- **AND** deployment fails before accepting that worker

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
- **THEN** before quiescence the workflow proves the deployed Compose file exactly matches the reviewed correction, the shared env lacks the key, and host-controlled Docker metadata shows all four running workers lack the key, and it records their exact container IDs
- **AND** the stop-writer preflight disables restart paths and stops that fleet
- **AND** immediately before transmission the workflow rechecks the Compose/shared-env boundary and proves those same four recorded IDs remain present and stopped
- **AND** the workflow replaces the host request-idempotency HMAC only after all pre-quiescence and post-quiescence prerequisites pass
- **AND** the rotation path is visible in workflow inputs and run history without exposing the key

#### Scenario: stale or unproved boundary blocks rotation
- **WHEN** the deployed Compose hash differs, the shared env contains the key, a worker is absent, a running worker contains the key, a recorded worker identity changes, or a recorded worker restarts after quiescence
- **THEN** the manual rotation run fails before transmitting or replacing the host key
- **AND** the operator must complete the ordinary corrected-boundary deploy first

### Requirement: Protected-stdin installation atomically preserves the live environment
The environment installer SHALL construct updated content in the current Bash process without placing its protected-stdin value in process arguments, child environment, or a secret-only staging file; SHALL protect any complete-file sibling transaction at mode 0600 until final metadata is applied; MUST atomically rename only after a complete write and sync; and MUST NOT print the protected value.

#### Scenario: normal and error exits create no transaction residue
- **WHEN** protected-stdin installation succeeds or any pre-rename write, metadata, sync, or rename operation fails
- **THEN** no matching sibling transaction exists beside the target environment file
- **AND** stdout and stderr contain no protected value

#### Scenario: failed transaction preserves the live file
- **WHEN** a real resource or I/O limit interrupts candidate construction before rename
- **THEN** the installer returns failure and the prior target remains byte-for-byte unchanged
- **AND** EXIT or signal cleanup removes the incomplete sibling transaction

#### Scenario: construction has no secret child custody lifecycle
- **WHEN** the installer rewrites a protected value
- **THEN** no content-builder child or secret-only value file exists to outlive the installer

#### Scenario: parent-only termination cannot orphan protected input custody
- **WHEN** stdin remains open and TERM is delivered only to the installer while it waits for the protected value
- **THEN** the installer terminates from TERM with the live file unchanged
- **AND** no child process survives with the protected-input descriptor

#### Scenario: Compose-valid duplicate immutable assignments fail before mutation
- **WHEN** `set-once` reads more than one Compose-recognized assignment for its target key, including a UTF-8-BOM-prefixed first assignment, `export`, the complete accepted Unicode White_Space set before a declaration, supported delimiter whitespace, `=` or `:`, or a non-empty assignment followed by an empty assignment
- **THEN** it exits with immutable-refusal status before writing the environment file
- **AND** neither existing nor proposed values appear in output

### Requirement: Offsite production logs cover the complete runtime fleet
The default offsite archive SHALL collect the daemon, tunnel, and every fixed production worker container, and the operator runbook MUST use the deployed TinyAssets service, container, metadata, and archive identities.

#### Scenario: default archive includes all workers
- **WHEN** `ship-logs.sh` runs without a `LOG_CONTAINERS` override
- **THEN** its collection plan includes `tinyassets-daemon`, `tinyassets-tunnel`, `tinyassets-worker`, `tinyassets-worker-codex-2`, `tinyassets-worker-claude-1`, and `tinyassets-worker-claude-2`

#### Scenario: stopped workers remain visible and omissions fail closed
- **WHEN** a required container is stopped but inspectable
- **THEN** the collector pins its exact container ID, reads logs by that immutable ID, rechecks the name still maps to the same ID after the read and again for the complete fleet before archiving or upload, and records its ID, stopped state, and log filename in the uploaded fleet manifest and archive
- **AND** if any required container is missing, changes generation during collection, or has unreadable logs, the script fails before upload instead of publishing a partial archive

#### Scenario: normal production deployment installs the reviewed log closure
- **WHEN** a successful production deploy triggers host-services convergence
- **THEN** the content-addressed host release includes `deploy/ship-logs.sh` and its service/timer units
- **AND** the service executes the script through `/opt/tinyassets-host-uptime/current`
- **AND** installation fails before timer acceptance if any installed runtime or unit differs from the reviewed source
- **AND** application deployment preserves the host-owned `LOG_DEST` read by the timer service

#### Scenario: operator examples match deployed identities
- **WHEN** an operator follows the logging runbook to query, download, extract, or troubleshoot logs
- **THEN** the commands reference the current `tinyassets` project/service identities, `tinyassets-logs` container, and `tinyassets-logs-*` archive prefix
