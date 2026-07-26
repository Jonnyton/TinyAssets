## ADDED Requirements

> **⚠ Target requirements — NOT as-built.** The *instrument* is built and tested (tasks §1–2:
> `tests/data/connector_tool_selection_v1.jsonl`, `scripts/connector_tool_selection_eval.py`,
> `tests/test_connector_tool_selection.py`). What does not exist is the *measurement*: no baseline
> has been recorded, so no connector-prose change is gated on anything and these requirements are
> not in force. They MUST NOT be synced into `openspec/specs/live-mcp-connector-surface/` until a
> recorded baseline exists (`openspec/config.yaml`: *"do not spec aspirations"*; AGENTS.md
> § Spec-driven development) — syncing a defined-but-unenforced gate asserts an enforcement that is
> not happening. Note that `openspec archive` performs that sync — archiving this change before
> task 3.1 lands is the same failure. Provenance: task 6.3 of
> `reconcile-universe-personification-relay`, itself the residual of retired task 2.9.

### Requirement: Connector tool-selection accuracy is measured against a fixed labelled dataset
Tool-selection accuracy SHALL be measured against a fixed, versioned, labelled dataset of
prompt→expected-handle pairs, so that a change to the connector's behavioral prose is evaluated
against an instrument that did not change with it. The dataset SHALL label every prompt with
exactly one expected handle drawn from the canonical advertised set (`read_graph`, `write_graph`,
`run_graph`, `read_page`, `write_page`, `converse`, `get_status`), SHALL cover every canonical
handle at least once, and SHALL contain no duplicate prompts. A dataset violating any of these
rules SHALL fail loudly rather than be scored, because a silently malformed instrument produces a
number that looks like evidence.

The dataset SHALL be versioned, and a revision SHALL be a new version rather than an edit to an
existing one — editing the instrument in the same change that moves the metric makes the comparison
meaningless.

#### Scenario: A label outside the canonical handle set is rejected
- **WHEN** the dataset labels a prompt with a handle that is not in the canonical advertised set
- **THEN** loading the dataset fails with an error naming the offending prompt and label
- **AND** no accuracy number is produced

#### Scenario: An uncovered canonical handle is rejected
- **WHEN** the dataset omits any canonical handle from its labels
- **THEN** loading the dataset fails and names the uncovered handle

#### Scenario: A duplicate prompt is rejected
- **WHEN** two dataset entries carry the same prompt text
- **THEN** loading the dataset fails and names the duplicated prompt

### Requirement: Tool-selection accuracy reports top-1 and opening-turn rates separately
The scoring harness SHALL report the top-1 correct-handle rate over the whole dataset AND the
`converse`-first-on-opening rate over the subset of prompts marked as opening turns, as two
separate numbers. The opening-turn rate SHALL NOT be pooled into the top-1 rate alone, because the
`first-contact` flow depends specifically on `converse` being chosen on an opening message, and a
regression confined to that subset would be masked by a whole-dataset average.

A recorded run SHALL cover every prompt in the dataset. The harness SHALL refuse to score a partial
run rather than reporting a rate over the subset it happens to have, so the gate cannot be passed by
omitting the prompts that fail.

#### Scenario: Both rates are reported for a complete run
- **WHEN** a recorded run covering every dataset prompt is scored
- **THEN** the result carries the top-1 correct-handle rate and the opening-turn `converse` rate as
  separate fields

#### Scenario: A partial run is refused, not scored
- **WHEN** a recorded run omits one or more dataset prompts
- **THEN** the harness fails and names the missing prompts
- **AND** no accuracy number is produced

#### Scenario: An observed handle outside the canonical set is scored as incorrect
- **WHEN** a recorded run observes a handle that is not in the canonical advertised set
- **THEN** that entry is scored incorrect rather than discarded, and the observed value is reported

### Requirement: Connector prose changes are gated on a recorded baseline and a permitted regression
A change to the connector's behavioral prose SHALL be evaluated against a recorded baseline
measurement, and SHALL fail the gate when either reported rate falls below its baseline by more
than the permitted regression. Behavioral prose means the server `instructions` block and the
`control_station` prompt. The permitted regression SHALL default to **0 percentage points** (no
regression tolerated) until the connector-surface owner records a different tolerance, and the
tolerance in force SHALL be recorded alongside the baseline rather than passed per-invocation, so a
failing run cannot be rescued by loosening the threshold at the call site.

A baseline SHALL record the dataset version it was measured against, and a comparison across
different dataset versions SHALL fail rather than silently compare incomparable numbers.

Both recorded rates and the permitted regression SHALL be finite numbers inside the range a rate can
occupy, and a baseline carrying a non-numeric, non-finite, or out-of-range value SHALL be refused as
unusable rather than compared against. A non-finite tolerance is the sharp case: every comparison
against it is vacuously satisfied, so a real regression is reported as a passing gate without any
part of the comparison appearing to malfunction.

#### Scenario: A baseline carrying an unusable threshold is refused, not tolerated
- **WHEN** a baseline records a non-numeric, non-finite, or out-of-range rate or permitted regression
- **THEN** the comparison is refused as unusable input and no gate verdict is produced
- **AND** the refusal is distinguishable from a failed gate, so an unusable threshold is never read
  as a regression that merely failed

#### Scenario: A regression beyond tolerance fails the gate
- **WHEN** a candidate measurement's top-1 rate is below the baseline by more than the permitted
  regression
- **THEN** the gate fails and reports the baseline rate, the candidate rate, and the tolerance

#### Scenario: An opening-turn regression fails the gate independently
- **WHEN** the top-1 rate is unchanged but the opening-turn `converse` rate falls below its baseline
  by more than the permitted regression
- **THEN** the gate fails on the opening-turn rate alone

#### Scenario: A cross-version comparison is refused
- **WHEN** a candidate measured on one dataset version is compared to a baseline recorded on another
- **THEN** the comparison fails and names both versions

### Requirement: Measurements come from a rendered chatbot session, not a simulated one
A measurement SHALL be recorded from a real browser-rendered chatbot conversation through the live
connector at `https://tinyassets.io/mcp`, following the `ui-test` skill, because handle choice is a
property of the host chatbot and cannot be observed by calling the MCP server directly. Direct MCP
calls, local scripts, and canary probes SHALL be treated as supporting evidence and SHALL NOT be
recorded as a measurement.

The recorded source SHALL be treated as a **trusted transcription**, not as proof of provenance. The
harness SHALL refuse a run whose declared source is not a rendered surface, but it cannot verify
that an accepted declaration is truthful — a fabricated observation file declaring a rendered
surface is indistinguishable from a transcribed one. A recorded baseline SHALL therefore carry a
reviewable reference to its rendered-session evidence (the `ui-test` session log entry plus a trace
or screenshot path), and provenance SHALL be established by review of that reference rather than by
the declared label. A baseline recorded without reviewable evidence SHALL NOT be treated as a
measurement.

A recorded measurement SHALL carry the surface it was observed on (for example `claude.ai` or
`chatgpt`) and the date observed, and rates from different surfaces SHALL NOT be averaged into a
single number — they are different subjects under test.

#### Scenario: A run declaring a non-rendered source is refused
- **WHEN** a run is submitted whose declared source is not a rendered chatbot session
- **THEN** it is refused as a measurement and no baseline is recorded from it

#### Scenario: A baseline without reviewable rendered-session evidence is not a measurement
- **WHEN** a baseline is recorded whose rendered-session evidence reference is absent or does not
  resolve to a reviewable `ui-test` session log, trace, or screenshot
- **THEN** it is rejected in review as unprovenanced, regardless of the source label it declares

#### Scenario: Per-surface rates stay separate
- **WHEN** measurements exist for more than one chatbot surface
- **THEN** each surface's rates are reported and compared against that surface's own baseline
