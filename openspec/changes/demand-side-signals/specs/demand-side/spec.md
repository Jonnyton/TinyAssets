## ADDED Requirements

### Requirement: Standing goals are durable demand independent of chat sessions
A standing goal SHALL persist its desired outcome, owning principal, universe, an explicit IANA-timezone cron-class schedule or event trigger, declared budget posture, success gates, and pause state independently of any open chatbot session, stored in the transactional catalog that `shared-goals-and-convergence` already owns for Goals rather than in a parallel store. Its schedule SHALL be part of the goal record and readable wherever the goal itself is readable, including from a commons archetype that publishes it. The daemon proactivity heartbeat SHALL execute due work for eligible standing goals, and an eligible goal SHALL continue to produce due work and demand observations while its owner is absent, bounded by the authority and declared limits recorded on the persisted record. Each due period SHALL expose a stable `(goal_id, schedule_period)` identity so downstream effect, receipt, and batch owners can derive a deterministic idempotency key from durable facts instead of minting one per attempt.

#### Scenario: demand scales with active goals rather than sessions
- **WHEN** users close their chatbot clients while authorized standing goals remain active
- **THEN** forecast demand and due work remain derived from those goals without requiring a live client connection
- **AND** no goal is paused, expired, or deprioritized as a side effect of the client disconnecting

#### Scenario: a due period carries a stable identity
- **WHEN** the same due period of the same standing goal is evaluated twice — by a retry, a restart, or a bounded replay
- **THEN** both evaluations report the same `(goal_id, schedule_period)` identity
- **AND** a downstream owner keyed on that identity deduplicates rather than firing a second effect

### Requirement: Standing-goal execution derives authority from the persisted record, never from the caller
When the heartbeat executes a due standing goal, the executing authority SHALL be derived from the owning principal recorded on the persisted goal, bound server-side from the authenticated actor at registration time. The runtime SHALL NOT accept an owner, actor, universe, or authority field supplied by the triggering caller, by a scheduler row written outside the registration path, or by an ambient environment fallback. If the persisted owner cannot be resolved, or its authority has been revoked, paused, or narrowed below what the due action requires, the run SHALL fail closed with a recorded reason and SHALL NOT fall back to a host, maintainer, platform, or previously cached identity.

#### Scenario: an absent owner's goal runs under the owner's own recorded authority
- **WHEN** the heartbeat fires a due standing goal with no live session for its owner
- **THEN** the run executes under the principal bound at registration and under that principal's current scope

#### Scenario: a caller cannot supply the owner
- **WHEN** a trigger request, an externally written scheduler row, or an environment variable presents an owner or actor field for a due standing goal
- **THEN** the supplied value is ignored and the persisted owner is used
- **AND** where the supplied value disagrees with the persisted owner, the discrepancy is recorded

#### Scenario: revoked authority fails closed rather than falling back
- **WHEN** a due standing goal's persisted owner is unresolvable, revoked, or no longer authorized for the due action
- **THEN** the run refuses with a recorded reason and takes no action under any other identity

### Requirement: Inbox items join exactly one scheduled batch under a timezone-evaluated cutoff
`outbound-boundary-layer` owns inbox addressing, ingress, receipt, typing, and eligibility cutoff for goal and universe inboxes. This capability owns the schedule that consumes those items and SHALL admit each eligible item into exactly one scheduled batch, evaluating the cutoff in the goal's recorded IANA timezone rather than in the daemon's local zone or in UTC. A fired batch SHALL record the inbox receipts it consumed, the cutoff instant and timezone applied, and the schedule-period identity, so a duplicate delivery, a late arrival, or a replayed period is decidable from records rather than inferred. An item arriving after its cutoff SHALL wait for the next period; it SHALL NOT be dropped and SHALL NOT be back-dated into a period that has already fired.

#### Scenario: a dropped item joins exactly one local-time batch
- **WHEN** an approved item reaches a goal inbox before the cutoff for the next period, evaluated in the goal's IANA timezone
- **THEN** that period's batch receives the item exactly once and records the receipt, cutoff instant, timezone, and period identity

#### Scenario: a late item waits rather than vanishing
- **WHEN** an eligible item arrives after the cutoff for the period that has already fired
- **THEN** the item remains pending and joins the next period's batch
- **AND** it is neither discarded nor inserted into the fired period

#### Scenario: a replayed period does not re-consume its items
- **WHEN** a period is replayed under the schedule's missed-tick policy after the daemon returns
- **THEN** the replay reuses that period's identity and its recorded item set rather than consuming pending items belonging to a later period

### Requirement: Onboarding terminates in a running standing goal built from remixable commons archetypes
An onboarding path SHALL terminate in at least one running standing goal rather than an empty universe. On completing an archetype path, the product SHALL show the attached goal, its next scheduled action rendered in the user's own timezone, and the outcome that goal is designed to claim first. An archetype SHALL attach two or three standing goals, of which the first SHALL be chosen so that its gate can plausibly be claimed inside the first week. Archetypes SHALL be commons artifacts — remixable pages and graph templates a user can fork, replace, or author from scratch through the canonical page and graph handles — and the platform SHALL ship at most a replaceable seed set, never a closed catalog. A user SHALL be able to complete onboarding from an archetype the platform did not author, with the same attachment, scheduling, and visibility behavior.

#### Scenario: onboarding ends with operational state
- **WHEN** a new founder completes an archetype path
- **THEN** the product shows the pre-attached running goal, its next scheduled action in the founder's own timezone, and the week-one outcome it is designed to claim, rather than an empty universe

#### Scenario: a community archetype is a first-class onboarding path
- **WHEN** a user completes onboarding from an archetype authored and published by another user rather than from the seed set
- **THEN** the goals attach, schedule, and become visible exactly as they would from a seeded archetype

#### Scenario: the seed set is replaceable, not frozen
- **WHEN** a user forks a seeded archetype and changes its attached goals, schedules, or gates
- **THEN** the forked archetype is usable for onboarding without platform approval and without editing platform code

### Requirement: Demand metrics are owner-scoped derived evidence, not a new reporting surface
Per-universe demand metrics — standing goals per active universe as the leading indicator, ahead of the weekly gate-claim north star — SHALL be derived on read from records this capability already persists, and SHALL be returned through the canonical read-only evidence handle and existing graph reads rather than through a new tool, action namespace, or metrics service. The metric's terms SHALL be defined rather than left to the reader: the numerator counts standing goals in a **non-paused** state whose schedule or trigger is currently eligible to fire, excluding paused, expired, and soft-deleted goals; a **paused count SHALL be reported alongside it rather than folded into it**, so pausing a goal never looks like deleting one; and the denominator counts universes with at least one such non-paused standing goal. Every metric response SHALL state the window it covers and the definitions it applied, so two readers of the same universe get the same number. A metric SHALL be visible to a principal only within the scope that principal can already read under the rules `identity-auth-and-access-control` enforces; a metric SHALL never widen the visibility of the goal it counts, and SHALL never surface a counted goal's title, outcome text, gate content, schedule detail, or inbox item content to a principal who could not read that goal directly. Any cross-universe or published aggregate SHALL remain off by default and SHALL be emitted only under the bucketed, k-anonymized demand-signal contract owned by `paid-market-live-price-discovery`; this capability SHALL NOT define a second aggregation, publication, or export path for demand data.

#### Scenario: an owner sees their own counts
- **WHEN** a principal reads demand metrics for a universe it owns
- **THEN** it receives the non-paused standing-goal count, the paused count reported separately, and gate-claim counts for that universe
- **AND** the response states the window covered and the definitions applied

#### Scenario: pausing a goal moves it between counts rather than erasing it
- **WHEN** an owner pauses a standing goal and re-reads the metric
- **THEN** the non-paused count decreases by one and the paused count increases by one
- **AND** the goal is not silently dropped from both

#### Scenario: a metric does not leak a restricted goal
- **WHEN** a universe contains standing goals the reading principal is not authorized to read
- **THEN** the response neither names, describes, nor otherwise discloses those goals through counts, labels, schedules, or derived breakdowns that would identify them

#### Scenario: no aggregate is published by default
- **WHEN** no operator has deliberately enabled the k-anonymized demand signal owned by `paid-market-live-price-discovery`
- **THEN** no cross-universe or public demand aggregate is emitted from this capability

### Requirement: Demand records name their custody assumption and stay exportable
Private-data custody is an open research question and this capability SHALL NOT encode an answer to it. This requirement adds no product capability: it is the compliance statement PLAN.md Scoping Rule 4 (as amended by the host-approved 2026-07-25 reopening) obliges **every** lane touching private data to make, and it binds only records this capability already persists under its own umbrella-task-4.1 scope. It SHALL scope itself to the *coordination record* — goal identity, schedule, timezone, trigger, pause state, gate reference, period identity, batch receipts, and counts — and SHALL record explicitly that it assumes those coordination records are platform-held under the transactional catalog's stated boundaries. It SHALL NOT require the *content* a standing goal reads or produces to be platform-held: a goal whose content lives on a host machine, in the user's own brain bundle, in a vault, or platform-held SHALL register, schedule, fire, and be counted identically, with content resolved through whatever custody mode its owner chose. Every record this capability persists SHALL be exportable in a documented format the user can take elsewhere, and no behavior here SHALL depend on a custody mode the user cannot change.

#### Scenario: a host-resident goal schedules identically
- **WHEN** a standing goal's working content is resolved from a custody mode the platform does not hold
- **THEN** registration, schedule persistence, firing, batch admission, and metric counting behave the same as for a platform-held goal
- **AND** where the content is unreachable because no host is online, the run reports that condition rather than degrading to a different custody mode

#### Scenario: coordination records export whole
- **WHEN** a user exports their standing goals
- **THEN** the export contains every coordination field needed to reconstruct the schedule, trigger, gates, pause state, and period history elsewhere, in a documented format

### Requirement: The standing-goal half of demand-side is non-monetary and fails closed at the money edge
Standing-goal registration, scheduling, firing, inbox consumption, onboarding attachment, and metric derivation SHALL create no escrow, fee, price, ledger, or settlement record, and SHALL NOT constitute a payment surface. A standing goal's declared budget posture SHALL be a recorded limit, not an authorization to spend: it constrains what the goal may request and is enforced by whichever owner performs the spend. A due action whose execution would move value SHALL refuse and name the capability it requires — the single authenticated double-entry transaction boundary owned by `paid-market-economy` — rather than opening a second accounting path or degrading to a best-effort local debit. The refusal SHALL name that capability, not a change slug: change names are provenance and expire on archive, while the capability is the durable contract. Goal-bounty posting, escrowed tranches, first-verified-claim settlement, and the measured direct-service launch gate are out of scope for this capability and SHALL NOT be specified, implemented, or partially staged here.

#### Scenario: a value-moving due action refuses and names its owner
- **WHEN** a due standing goal's action would create or move a balance, escrow, fee, or settlement record
- **THEN** the action refuses, records the refusal, and names the `paid-market-economy` transaction boundary it requires
- **AND** no local balance, escrow, or ledger row is written as a substitute

#### Scenario: budget posture alone does not authorize spend
- **WHEN** a standing goal declares a budget posture and becomes due
- **THEN** the declared posture is persisted and readable as a limit
- **AND** it grants no spending authority by itself and is not accepted by any spend path as authorization
