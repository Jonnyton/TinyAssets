## RENAMED Requirements

- FROM: `Status And Loop Presentation Keep Distinct Operational Truths`
- TO: `Status And Workflow Presentation Keep Distinct Operational Truths`

## MODIFIED Requirements

### Requirement: The Public Site Ships As A Static Multi-Route Application

The public website SHALL ship as a static multi-route application. The current
production deployment source is the React/Next static export under
`WebSite/site-react`; the SvelteKit tree under `WebSite/site` is the retained
rollback source until a separate approved migration removes or restores it.
Both present trees SHALL expose or preserve the checked-in public route set,
including the home, start, goals, host, wiki, graph, loop, commons, catalog,
economy, alliance, contribute, notebook, soul, patterns, fine-print, legal,
and account surfaces, and both SHALL remain scan-clean so rollback cannot
resurrect the retired product.
The retired `/patch-loop` route SHALL be a static soft landing that explains
task automations are user-authored/remixable designs and directs visitors to
patterns or commons; it MUST NOT load a hidden compatibility application or
status feed. Retired `connect`, `status`, and `proof` routes SHALL remain
soft-landing aliases that direct visitors to their current destinations rather
than becoming dead links. Generated static assets SHALL include the canonical
hostname, crawler policy, sitemap, brand marks, and machine-readable `llms.txt`
committed with the deployed site.

#### Scenario: Retired patch-loop route is visited

- **WHEN** a visitor opens `/patch-loop`
- **THEN** the page explains that task automations are ordinary user-authored and remixable designs and directs the visitor to generic patterns or commons
- **AND** it loads no community-loop status, workflow, issue, label, or compatibility-loop data

#### Scenario: Static production build is requested

- **WHEN** the website build script runs successfully
- **THEN** the React/Next production tree emits a static application containing the checked-in public routes and assets without requiring a website application server
- **AND** the retained Svelte rollback tree also builds and remains free of retired product behavior

### Requirement: Status And Workflow Presentation Keep Distinct Operational Truths

The website SHALL distinguish server reachability, platform uptime evidence,
and user-authored workflow activity. Its vital-sign read SHALL require
`get_status` and the public universe list to succeed before reporting the
server as reachable, while failed goals or extension-run reads SHALL degrade
to absent optional evidence. The generic `/loop` presentation MAY derive
workflow activity from active runs, running queue items, or recent
run/universe signals only when it labels their live/snapshot provenance. It
MUST NOT present those signals as a privileged platform loop.

Both production and rollback site trees SHALL remove checked-in
`community-loop-status.json`, all `community_change_context` callers, the homepage
`ChatDemo.svelte` file-to-daemon-to-gates-to-live narrative, community-loop
workflow/label/issue assumptions, patch-loop feeds, and fine-print branding. A
generic platform-uptime snapshot MAY be displayed only when it is produced by
the independently owned uptime/alarm contract and clearly labeled as platform
observation; it MUST NOT be used as evidence that user task work is moving.

#### Scenario: Server is reachable but no recent work exists

- **WHEN** status and public reads succeed but there is no active or recent user-authored workflow signal
- **THEN** the site reports the server as reachable and workflow activity as absent or asleep
- **AND** generic uptime evidence is not relabeled as task-loop movement

#### Scenario: Last extension run is historical

- **WHEN** the most recent user-authored workflow run is terminal and older than the historical cutoff
- **THEN** the site labels it as historical rather than active workflow evidence
- **AND** it does not seek a patch-loop feed, community-watch fallback, or platform-owned task route

#### Scenario: Legacy community-loop fallback is absent

- **WHEN** live workflow activity is unavailable
- **THEN** the site renders unavailable/snapshot truth without reading a community-loop JSON, workflow, label, issue, or patch-loop feed
- **AND** it does not infer a platform-owned automation loop from GitHub monitor evidence

#### Scenario: Production and rollback sources are scan-clean

- **WHEN** website source, static assets, fine print, tests, and build output for the React production tree and Svelte rollback tree are scanned
- **THEN** no shipped community-loop status artifact, patch-loop application, `community_change_context` caller, homepage privileged-loop narrative, workflow/label fallback, or privileged-loop promise remains
- **AND** neither deploy nor rollback can resurrect the retired product
