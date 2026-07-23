## ADDED Requirements

### Requirement: Auto-ship PR creation is scoped, idempotent, and stale-head safe
PR creation SHALL operate only on a recorded eligible auto-ship attempt and a validated same-repository `auto-change/*` head. An explicit token SHALL take precedence; a production call with universe and destination SHALL resolve a per-universe `vcs/github/write` credential; environment token fallback SHALL apply only when no scoped destination lookup is requested. An attempt already recorded as opened SHALL return its recorded PR evidence without another network write, and a head that is behind or diverged from base SHALL fail with `pr_create_stale_head` before PR creation.

#### Scenario: Scoped vault credential wins
- **WHEN** an eligible attempt requests PR creation with a universe, destination, both a vault credential and an environment token
- **THEN** the GitHub requests use the per-universe destination-scoped write credential and do not expose either token in result evidence

#### Scenario: Recorded open attempt is reused
- **WHEN** an attempt already has `ship_status=opened` and a PR URL
- **THEN** PR creation returns the recorded URL and commit evidence with `already_open=true` and performs no additional POST

#### Scenario: Stale head is refused before creation
- **WHEN** the GitHub comparison reports the auto-change head behind or diverged from its base
- **THEN** the attempt is marked failed with `pr_create_stale_head` and no PR-create POST occurs

### Requirement: Auto-ship health is a read-only status projection
`get_status.auto_ship_health` SHALL summarize the append-only attempt ledger without polling, rolling back, or mutating it. The projection SHALL include bounded recent attempts, opened-PR observation state, rollback recommendations for regressed opened or merged attempts, the observation window, ledger availability, and warnings; a ledger read failure SHALL return `ledger_available=false` with a warning rather than fail the status request.

#### Scenario: Recent and regressed attempts are summarized
- **WHEN** the ledger contains recent attempts plus an opened attempt whose observation status regressed
- **THEN** health lists bounded recent attempts and opened PRs and includes a rollback recommendation for the regressed attempt

#### Scenario: Ledger read failure stays observable
- **WHEN** the attempt ledger cannot be read
- **THEN** status still returns an `auto_ship_health` object with `ledger_available=false` and a `ledger_read_failed` warning

### Requirement: Branch-task restarts reuse completed runs and recover nested Patch Packets
The daemon branch-task executor SHALL derive the stable run name `branch-task-<branch_task_id>` and reuse a matching completed durable run rather than execute it again. It SHALL return metadata containing the reused run id, status, actor, branch definition, and reuse flag; the stored output is consumed internally rather than returned. For a completed bug-investigation task it SHALL find the first non-empty packet in `patch_packet`, `candidate_patch_packet`, or `child_candidate_patch_packet`, recursively inspect `attached_child_output`, or derive implementation/test fields from a `coding_packet`; non-empty strings SHALL become an implementation sketch. It SHALL attach the recovered packet to the source wiki page, while non-completed runs, non-investigation tasks, missing bug ids, and empty packets SHALL not write a false Patch Packet.

#### Scenario: Completed durable run is reused after restart
- **WHEN** a claimed branch task has a matching completed run under its stable run name
- **THEN** the executor returns reused-run metadata with that run id and `reused_existing_run=true`, uses stored output only for packet recovery, and does not invoke branch execution again

#### Scenario: Nested child packet is attached
- **WHEN** a completed bug-investigation output contains `attached_child_output.candidate_patch_packet`
- **THEN** the packet is normalized and attached to the referenced bug page under `## Patch Packet`

#### Scenario: String packet becomes an implementation sketch
- **WHEN** a recognized candidate packet field contains a non-empty string
- **THEN** the attached packet renders that string as the implementation sketch

#### Scenario: Failed investigation does not publish a packet
- **WHEN** a bug-investigation run is not completed
- **THEN** packet attachment returns a skipped reason and leaves the wiki page unchanged
