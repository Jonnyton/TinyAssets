## ADDED Requirements

### Requirement: Distinct kernel uids per runtime role

The production runtime SHALL run the owner (daemon), the credential broker, and engine/provider child processes as distinct kernel uids: 1001, 1002 and 1003 respectively. The daemon SHALL hold no Linux capability that lets it change uid. Only a root launcher holding `CAP_SETUID`/`CAP_SETGID` SHALL start other roles. The launcher SHALL start engine/provider children only from a static allowlist of kinds and argv templates, on request from peer uid 1001.

#### Scenario: A child cannot act as the owner
- **WHEN** an engine or provider child (uid 1003) tries to read the broker owner file or connect to the broker's owner channel
- **THEN** the read fails with a permission error and the broker refuses the connection as an unmapped uid

#### Scenario: The owner cannot become the broker
- **WHEN** the daemon process (uid 1001) tries to change its uid to the broker's
- **THEN** the kernel refuses, because the daemon holds no `CAP_SETUID`

#### Scenario: The broker fails closed without the split
- **WHEN** the broker is selected on a host where the roles share one uid
- **THEN** the daemon refuses to start it and says the per-role uid split is required

### Requirement: Volume ownership follows the roles

The data volume SHALL give the broker's state and vault directories to the broker uid with mode 0700. It SHALL make child-writable workspaces group-owned by a shared work group with setgid directories, and leave all other platform state owned by the owner uid. The ownership migration SHALL be idempotent and SHALL run under the exclusive data-layout lock before any role starts.

#### Scenario: Re-running the migration changes nothing
- **WHEN** the container restarts on a volume already migrated
- **THEN** the migration makes no ownership or mode changes and the roles start
