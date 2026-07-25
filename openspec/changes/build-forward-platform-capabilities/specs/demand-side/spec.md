## ADDED Requirements

### Requirement: Standing goals are durable demand independent of chat sessions
A standing goal SHALL persist desired outcome, owner, universe, explicit IANA-timezone cron-class schedule or event trigger, budget posture, success gates, and pause state independently of any open chatbot session. Its schedule SHALL be part of the goal spec and visible in the commons archetype, and the proactivity heartbeat SHALL execute due work. Eligible goals SHALL continue to forecast and request work while their owners are absent, within explicit authority and spend limits.

#### Scenario: demand scales with active goals rather than sessions
- **WHEN** users close their chatbot clients while authorized standing goals remain active
- **THEN** forecast demand and due work remain derived from those goals without requiring a live client connection

### Requirement: Onboarding terminates in a useful running goal
Each commons launch archetype SHALL ship with two or three standing goals pre-attached. The first SHALL be designed to produce a felt, gate-claimed win inside week one. Onboarding SHALL terminate in a running standing goal rather than an empty universe, and the leading demand metric SHALL be standing goals per active universe, ahead of the north-star weekly gate-claims metric.

#### Scenario: onboarding ends with operational state
- **WHEN** a new founder completes an archetype path
- **THEN** the product shows the pre-attached running goal, its next scheduled action, and the first week-one gate-claimed outcome rather than an empty universe

### Requirement: Goal bounties transfer demand through exact escrowed claims
A goal owner SHALL be able to post a machine-verifiable goal bounty that any authenticated principal or universe satisfying the published eligibility rules can discover, claim, satisfy, and settle without an invitation-only list. This preserves the target's open “ANYONE may claim” market while explicitly refusing anonymous money movement. The bounty SHALL bind immutable goal/gate/version identity and SHALL not transfer control of the owner's universe or credentials.

#### Scenario: money summons another universe's work
- **WHEN** an eligible universe claims an open bounty and produces evidence satisfying its frozen gate
- **THEN** the verified claim settles under the bounty terms while ownership and credentials remain with their original principals

### Requirement: Bounty composition rules are enforced at the boundary
Bounty posting and settlement SHALL enforce all six pinned rules: machine-evaluable gates only with no human-acceptance surface; `escrow_lock_entries` into `escrow:bounty:<id>` at post with gate-ladder tranche weights apportioned exactly; first verified claim per tranche ordered by `(gate-verification timestamp, claim id)` under an atomic compare-and-swap; standard 99/1 settlement using `FEE_PPM`, standard ledger adapters, and `assert_drained`; full no-fee refund of unclaimed expired tranches; the standard evidence dispute window; and claimant authorship plus standard attribution while the poster receives usage rights under license terms composed fail-closed at post.

#### Scenario: a subjective-only goal cannot carry money
- **WHEN** a bounty lacks a machine-evaluable frozen gate
- **THEN** posting is rejected before escrow is locked

#### Scenario: one verified winner drains one tranche
- **WHEN** concurrent claims satisfy the same open tranche
- **THEN** exactly one claim wins by `(gate-verification timestamp, claim id)`, settles 99/1 through standard adapters, and leaves `assert_drained` true while later claims receive a closed result

### Requirement: Direct universe services wait for measured bounty demand
The platform SHALL keep direct paid universe-service products disabled until an explicit, executable launch gate observes sustained qualifying bounty volume and successful settlement quality. The gate's window, threshold, and evidence SHALL be versioned; a prose assertion or absence of services is insufficient.

#### Scenario: services remain dark below the volume gate
- **WHEN** measured qualifying bounty activity does not meet the versioned launch threshold
- **THEN** direct service listing and purchase actions remain unavailable while bounties continue to operate
