## MODIFIED Requirements

### Requirement: Host-Independent Public Canary And Incident Lifecycle

The platform SHALL request a five-minute Layer-1 public uptime schedule on
GitHub Actions, support manual dispatch, and react to every completed `Deploy
prod` workflow (`.github/workflows/uptime-canary.yml`). The requested schedule
SHALL NOT be represented as a guaranteed observation interval. For deploy
completion events, the probe job SHALL run only after a successful deploy,
while the alarm sink SHALL distinguish
the probe result as literal red, literal green, or unknown. The bundle SHALL
probe the canonical MCP handshake, a real tool call, daemon last activity,
sustained revert-loop state, and wiki persistence plus authorization policy.
The wiki sub-probe SHALL require `TINYASSETS_WIKI_CANARY_TOKEN` before network
access, assert that a separate tokenless `initialize` receives the OAuth 401
challenge, then use the named `canary` service principal for the MCP session,
an exact reserved `write_page` call, and its matching `read_page`. It SHALL
write a fresh per-run marker, require a successful response for
`drafts/notes/uptime-probe.md`, and verify the same marker and path through the
authenticated read. A missing or rejected credential, an accepted write to a
non-exact path, a read mismatch, an invalid tokenless challenge, or another
HTTP/network failure SHALL remain red with the existing step-specific
diagnostics. There is no unsigned fallback. The
`live-mcp-connector-surface` capability owns the underlying pre-dispatch
challenge and canary confinement; this requirement owns its uptime evidence
and workflow diagnostic propagation.

The bundle SHALL combine sub-probes as follows: any measured failure is red;
otherwise absent required observations are unknown; only positive green
observations for every required sub-probe establish green. Missing private
legacy REVERT evidence SHALL be unknown and SHALL NOT authorize access to user
logs or become fabricated empty evidence. Transport failures SHALL remain red
even when they share an exit code with missing evidence. Diagnostics SHALL
distinguish those causes explicitly, not by parsing human-readable text.

The sink SHALL open a `p0-outage` issue after two consecutive measured Layer-1
red observations, append evidence while red, and comment recovery then close
the issue only on literal green. Prior red SHALL be established by the
immediately preceding eligible production workflow run's exact-attempt
measured-red step receipt, not its overall workflow conclusion. Missing,
unknown, skipped, cancelled, wrong-source or ambiguous prior receipts SHALL
NOT establish prior red; the sink SHALL NOT skip unknown observations to join
nonconsecutive reds.

An unavailable, empty, or unrecognized current result, including a skipped
probe after a failed deploy, SHALL be unknown: the sink SHALL make no label or
issue mutation, SHALL not page, and SHALL complete successfully so unknown
cannot become red threshold evidence. Unknown SHALL remain visible with its
missing observation and prerequisite in the scheduled summary; successful
execution of classification SHALL NOT be reported as green uptime acceptance.
MCP protocol and handle correctness remain owned by
`live-mcp-connector-surface`; this requirement owns probe orchestration and
incident state.

#### Scenario: Second consecutive red opens a durable incident

- **WHEN** the combined Layer-1 bundle is red and the immediately prior eligible run has an exact-attempt measured Layer-1 red receipt
- **THEN** the alarm sink opens one GitHub issue labeled `p0-outage` with the probe exit and output
- **AND** subsequent red ticks append evidence to that open issue instead of creating a parallel incident

#### Scenario: Unrelated workflow failure does not cross the outage threshold

- **WHEN** current Layer-1 is red but the prior run failed only in Layer-2 or has no measured Layer-1 red receipt
- **THEN** the prior workflow conclusion does not count as a previous outage and no threshold-crossing page is fabricated

#### Scenario: Green closes the incident

- **WHEN** the combined Layer-1 bundle is literally green while a `p0-outage` issue is open
- **THEN** the alarm sink appends a `GREEN - RECOVERED` record and closes the issue as completed

#### Scenario: Unknown result preserves incident state

- **WHEN** the probe result is unavailable, empty, or unrecognized, including when a failed `Deploy prod` completion skips the probe job
- **THEN** the alarm sink records an Actions warning and summary without creating or querying labels or issues, without paging, and without failing the canary workflow
- **AND** an open `p0-outage` issue remains open until a literal green result is observed

#### Scenario: Missing legacy evidence leaves coverage explicitly incomplete

- **WHEN** the current named canary projection lacks the legacy private activity tail while the other probes pass
- **THEN** the result is unknown with the current-engine execution-quality observation named as an open prerequisite, not green or a platform outage

#### Scenario: A real failure outranks a separate unavailable observation

- **WHEN** a current endpoint, tool, expected coordinator, or wiki probe measures failure while legacy revert evidence is unavailable
- **THEN** Layer-1 remains red with the real failure diagnostic and the unavailable coverage remains visible

#### Scenario: Downstream sub-probes respect upstream health

- **WHEN** the MCP handshake or real-tool probe fails
- **THEN** dependent activity, revert-loop, and wiki probes are skipped where they cannot produce meaningful evidence
- **AND** the upstream failure keeps the combined result red

#### Scenario: Canary wiki write is read back

- **WHEN** the scoped service token is present and the reserved `write_page` call reports `drafts/notes/uptime-probe.md`
- **THEN** the wiki sub-probe reads that page as the same `canary` principal and requires the written canary content to match
- **AND** any rejected write, different path, or read mismatch is red

#### Scenario: Missing credential fails before network access

- **WHEN** the scoped service token is absent or empty in the canary environment
- **THEN** the wiki sub-probe exits 2 naming `TINYASSETS_WIKI_CANARY_TOKEN` before making a network request
- **AND** it does not attempt an anonymous read or write

## ADDED Requirements

### Requirement: Community Watch Preserves Typed Canary Observation

The community watch SHALL consume explicit measured Layer-1 receipts from the
exact current Actions attempt, bound to the production workflow source, head,
run and freshness. Whole-workflow success alone SHALL NOT establish green.
Missing, malformed, ambiguous or superseded receipts SHALL remain unknown.
Existing measured-red receipts and other red watch stages SHALL remain red;
unknown SHALL NOT override them. Missing cadence remains a distinct monitoring
failure, not a fabricated measurement of endpoint health. This internal
consumer SHALL reuse Actions metadata without new runtime storage or authority.

#### Scenario: Successful classification recorded unavailable coverage

- **WHEN** the Uptime workflow succeeds without a positive measured-green receipt
- **THEN** community watch reports the Layer-1 observation as unknown rather than green
- **AND** its alarm sink makes no incident or dispatch mutation for unknown or yellow overall status

#### Scenario: Exact measured result controls incident state

- **WHEN** an exact, current, unambiguous measured-red receipt is read
- **THEN** existing red alarm actions remain available and unknown elsewhere cannot hide the red
- **AND** recovery remains restricted to literal green, including positive measured-green evidence for the observation stage

### Requirement: Absent Scheduled Rendered Acceptance Is Explicit

The scheduled monitor SHALL report Layer-2 unknown when its runner lacks an
authorized rendered-user acceptance session. It SHALL do so before invoking
the browser/LLM harness and SHALL NOT provision a platform LLM actor, reuse
an owner's browser or subscriptions, or label the absent capability as a
provider outage. Layer-1 results and Layer-2 coverage SHALL remain separately
visible. Full hostless acceptance SHALL remain incomplete while required
rendered evidence is unavailable, regardless of the classifier process exit.

#### Scenario: Hosted runner lacks the rendered session

- **WHEN** the scheduled runner has no authorized rendered-user session
- **THEN** the summary identifies that prerequisite and records Layer-2 unknown without calling `claude_chat.py`
- **AND** Layer-1 measurements are preserved, no provider outage is inferred, and rendered acceptance remains open
