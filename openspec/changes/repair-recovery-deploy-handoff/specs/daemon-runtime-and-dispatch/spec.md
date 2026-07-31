## ADDED Requirements

### Requirement: Finalized Recovery Hands Off Only Its Exact Fleet To Canonical Deploy

The transitional production deploy fence SHALL permit a normal deployment to
retire a finalized emergency-recovery container generation only when durable
recovery provenance and the current preflight independently prove the same
exact five stopped, restart-fenced container identities and Docker Compose
project. The handoff MUST preserve the production data volume, unrelated
containers, queue safety, and the unchanged receipt snapshot, and MUST record
removal intent before container mutation.

#### Scenario: Exact finalized recovery generation hands off

- **WHEN** a finalized recovery fleet is the exact running predecessor observed
  by normal preflight and the same exact five IDs and recovery project labels
  remain stopped with `restart=no` at target preparation
- **THEN** the fence records removal intent, removes only those exact container
  IDs without removing the data volume, proves the fleet inventory empty, and
  then permits the canonical service to start

#### Scenario: Ordinary canonical predecessor keeps its normal lifecycle

- **WHEN** normal preflight observes a predecessor with no durable finalized
  recovery handoff record
- **THEN** target preparation does not remove that predecessor through the
  recovery handoff path

#### Scenario: Fixed-name sidecars hand off without weakening recovery

- **WHEN** a finalized recovery leaves `tinyassets-tunnel` or
  `tinyassets-logs` holding a fixed name required by the next canonical Compose
  start
- **THEN** preflight records each present sidecar's exact ID, exact Compose
  project and service labels, non-writer mounts, and saved restart policy
- **AND** it restart-fences and stops those exact sidecars before recording
  removal intent and removing only the surviving recorded IDs without `-v`
- **AND** replay accepts only the exact remaining recorded subset or proved
  absence; foreign, running, restart-enabled, substituted, or unexpected
  sidecars fail before removal
- **AND** an ownership refusal exposes only the fixed sidecar name plus one
  fixed predicate class (`identity missing`, `project invalid`, `service
  invalid`, `recorded identity changed`, or `non-writer proof failed`), never
  the observed label, ID, mount, or other raw host value
- **AND** an invalid project predicate may expose only one fixed non-secret
  subcategory (`current-canonical`, `legacy-workflow`, `legacy-deploy`,
  `recorded-recovery`, `audited-full-compose-recovery`,
  `unrecorded-recovery`, `missing`, or `other`), never the observed project
  label
- **AND** a sidecar left by recovery before writer-only isolation may enter the
  handoff only when its project equals the deterministic project identity of
  one of the finite audited public recovery attempts, every present sidecar
  shares that same project, and the existing exact service, exact ID,
  non-writer, restart-fence, and replay requirements remain satisfied
- **AND** arbitrary recovery-shaped projects and mixed audited projects fail
  before mutation
- **AND** if forward start and ordinary rollback fail, emergency recovery
  removes only a newly proved canonical or recovery-owned sidecar generation,
  recreates both sidecars under its unique recovery project with `restart=no`,
  and binds their exact IDs before exposing the recovery result
- **AND** a partial recovery-sidecar start is durably captured by exact ID,
  stopped with `restart=no`, removed without volumes, and retried once within
  the same recovery invocation
- **AND** a zero-exit Compose result with an incomplete exact sidecar inventory
  is treated as the same partial-start failure and receives the bounded retry
- **AND** if the bounded retry also fails, its newly captured partial IDs remain
  restart-fenced and the writer fleet returns to `unsafe_fenced`
- **AND** fixed-name substitution after capture cannot preempt writer fencing;
  a still-present captured ID is stopped by exact ID without removal even if
  renamed, while the current fixed-name replacement remains untouched
- **AND** a sidecar restart-fence or stop failure is recorded but cannot preempt
  restart-fencing and stopping every current production-volume writer
- **AND** absent, foreign, identity-changed, or data-bearing sidecars are not
  removed or admitted to the retry cleanup path
- **AND** a foreign fixed-name blocker remains untouched while the proved
  recovery writers are refenced; a recovery-owned sidecar with an unexpected
  data mount is ID-bound and stopped but is not removed
- **AND** finalization restores the saved sidecar restart policies, while a
  later normal preflight can hand off the exact recorded recovery sidecars

#### Scenario: Unproved recovery ownership fails without removal

- **WHEN** the candidate fleet is partial, extra, running, restart-enabled,
  identity-changed, foreign-project, or inconsistent with durable recovery
  provenance
- **THEN** the fence fails before `docker rm` and keeps the canonical service
  from starting

#### Scenario: Removal-intent replay completes only the exact remaining subset

- **WHEN** the process restarts after durable exact-fleet removal intent and
  `docker rm` already removed zero or more of the recorded containers
- **THEN** the fence proves every missing recorded ID absent, proves every
  survivor has its original ID, recovery project label, stopped state, and
  `restart=no`, removes only those exact survivors, and records completion only
  after the production-volume inventory is empty
- **AND** any pre-intent partial fleet, extra writer, substituted identity,
  running survivor, restart-enabled survivor, or foreign-project survivor
  fails closed

#### Scenario: Unsafe recovery replaces a proved partial canonical target

- **WHEN** a failed normal start leaves a strict subset of expected container
  names on the production volume
- **AND** every survivor has the exact recorded target image and revision,
  canonical Compose project label, stopped state, and `restart=no`
- **AND** every missing expected canonical name is absent in every container
  state
- **THEN** recovery records the exact survivor IDs before mutation, removes
  only those IDs without `-v`, proves the volume inventory empty, and may start
  the admitted recovery image
- **AND** interruption may replay only the exact remaining recorded subset
- **AND** any extra, substituted, foreign, running, restart-enabled, or
  same-name off-volume container fails before removal

### Requirement: Failed Candidate Startup Evidence Precedes Rollback

The deploy workflow SHALL capture a bounded, allowlisted candidate startup
diagnosis before rollback can replace or remove a normal production candidate
that fails before health convergence. Raw logs and commands MUST NOT enter the
artifact, capture MUST have hard local and remote deadlines, and publication
MUST occur only after rollback and cleanup have restored or safely fenced the
fleet.

#### Scenario: Failed candidate is captured without environment disclosure

- **WHEN** the candidate daemon does not reach the public health gate
- **THEN** the workflow captures only allowlisted daemon state fields and
  repository-proved public Python source-path identities plus fixed exception
  classifications from at most the final 128 KiB of the last 200 daemon log
  lines
- **AND** neither raw logs, container commands, environment values, arbitrary
  exception messages, raw line numbers/functions, nor unapproved paths enter
  the artifact
- **AND** local SSH and remote Docker collection have hard deadlines
- **AND** the fixed-field Docker inspection transport uses an unambiguous
  separator that the validator parses identically
- **AND** an identity-matched Docker pre-start error is reduced to a fixed
  classification while raw error text and host paths remain unpublished
- **AND** an operator can classify a bounded past systemd/Compose journal
  window read-only, with raw journal bytes piped only into a fixed-signal
  sanitizer and never printed, persisted, or uploaded
- **AND** the journal transport is capped at 256 KiB before SSH while carrying
  a truthful source-truncation flag inside that same cap
- **AND** classification uses only the terminal attempt beginning at the last
  daemon `Creating` or `Starting` marker, including a retry with no new create
- **AND** container-name conflict has a fixed class and an unclassified failure
  remains visible as `other_failure` even when another known class is present
- **AND** a container-name conflict extracts only Docker's quoted conflicting
  name operand, strips at most one leading slash, and exposes it only on exact
  case-sensitive equality with the fixed canonical container allowlist, never
  arbitrary conflicting-name text or unrelated names from the same line
- **AND** a failed diagnostic reports only fixed numeric SSH and sanitizer
  statuses before failing, never raw stderr or journal text
- **AND** the remote pipeline runs as explicit Bash and maps journal versus
  framing failure to distinct fixed exit codes
- **AND** strict UTC workflow inputs are validated and normalized to
  unambiguous Unix-epoch timestamp arguments before crossing SSH, so deployed
  systemd parser age and host-local timezone cannot change the selected window
- **AND** raw log collection occurs only when the inspected container's
  immutable image reference and OCI revision exactly match the fence-proved
  candidate
- **AND** cancellation after candidate mutation takes the same bounded capture
  and post-safety publication path
- **AND** a deploy or intervening assertion failure after image mutation enters
  the same identity-bound capture path even when the named health step is
  skipped
- **AND** the workflow publishes the sanitized artifact only after rollback and
  restart-racer cleanup emits an explicit proof that the fleet is restored or
  authoritatively restart-fenced and the terminal release-state receipt is
  published
- **AND** failed or missing cleanup/fence proof suppresses artifact publication
- **AND** a mismatched observed image or revision is reported only as
  unavailable, never copied into the artifact
- **AND** retains the artifact for no more than seven days
