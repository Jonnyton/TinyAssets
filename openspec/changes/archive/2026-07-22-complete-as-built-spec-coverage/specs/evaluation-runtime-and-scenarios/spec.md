# Evaluation runtime and scenarios

## ADDED Requirements

### Requirement: Evaluators return a bounded unified result where the protocol applies

The current evaluation runtime SHALL define `EvalResult` with score, verdict,
kind, label, and details. Every `EvalResult` score MUST be in `[-1.0, 1.0]`;
protocol-conformant evaluators SHALL expose `evaluate(state) -> EvalResult`
using one of the current structural, editorial, process, numeric, or custom
kinds. Current adapters commonly pair `-1.0` with skip or error outcomes, but
the dataclass MUST NOT be represented as enforcing that semantic pairing.

#### Scenario: An out-of-range result is rejected

- **GIVEN** a caller constructs `EvalResult(score=1.001, ...)`
- **WHEN** dataclass validation runs
- **THEN** construction SHALL raise `ValueError` rather than return an invalid
  evaluation result.

#### Scenario: Structural subtyping is accepted

- **GIVEN** an object that implements `evaluate(state)` and returns an
  `EvalResult`
- **WHEN** the runtime checks it against `Evaluator`
- **THEN** it SHALL satisfy the protocol without inheriting a TinyAssets base
  class.

#### Scenario: Negative one is not reserved by the result type

- **GIVEN** a caller constructs `EvalResult(score=-1.0, verdict="pass", ...)`
- **WHEN** dataclass validation runs
- **THEN** construction SHALL succeed because the current type validates the
  numeric range but does not constrain verdict-score combinations.

### Requirement: Layered evaluation preserves native evidence and explicit adapters

The current runtime SHALL retain native structural, process, and coding
trajectory evidence while exposing explicit process adapters to `EvalResult`.
Process evaluation MUST report its weighted check results and failures; coding
trajectory evaluation MUST return `skip` with score `-1.0` when insufficient
applicable trajectory signals make it inconclusive, rather than treating absent
evidence as failure.

#### Scenario: Process failure is visible in the unified adapter

- **GIVEN** a scene process evaluation with one or more failing checks
- **WHEN** it is converted with `to_eval_result()`
- **THEN** the result SHALL use kind `process`, verdict `fail`, and include the
  aggregate score and failing check names in details.

#### Scenario: Sparse coding evidence is inconclusive

- **GIVEN** a coding trajectory with fewer applicable checks than the current
  conclusive threshold
- **WHEN** it is evaluated and converted to `EvalResult`
- **THEN** the result SHALL have verdict `skip` and score `-1.0`, not `fail`.

### Requirement: Outcome adapters remain probe-free unless a caller supplies a prober

The current real-world outcome evaluators SHALL implement the unified
`Evaluator` protocol for their declared state fields. Network-backed outcome
checks MUST use their injected prober when one is supplied and MUST otherwise
return an unverified/skip-style result without making an ambient network call.

#### Scenario: An outcome URL is not silently probed

- **GIVEN** a `PublishedPaperEvaluator` without a prober and state containing
  a DOI or URL
- **WHEN** it evaluates the state
- **THEN** it SHALL return an `EvalResult` describing unverified evidence and
  SHALL not perform a network request itself.

#### Scenario: A supplied prober determines the recorded verification status

- **GIVEN** an outcome evaluator configured with a prober that reports a
  negative result
- **WHEN** it evaluates a syntactically present outcome reference
- **THEN** it SHALL return the adapter's failed or unverified outcome according
  to that prober result rather than claiming verified success.

### Requirement: Acceptance scenarios validate the minimum evidence contract before dispatch

The current `AcceptanceScenario` SHALL validate a `scenario:` ID, one of the
five current target surfaces, a 200–2000-character user story, at least one
evaluator ID and artifact requirement, a `min_score`, both declared cost-budget
fields, a declared idempotency-key constructor, and one of the current privacy
scopes. A scenario that omits any required field MUST fail construction before
dispatch.

#### Scenario: An evidence-free scenario is rejected

- **GIVEN** a proposed acceptance scenario with an empty evaluator chain or no
  artifact requirements
- **WHEN** the dataclass validates it
- **THEN** construction SHALL raise `ValueError` and no dispatcher SHALL run.

#### Scenario: A valid scenario has bounded autonomous-spend declarations

- **GIVEN** a scenario for `mcp_call` with a valid story, artifact requirement,
  evaluator chain, threshold, privacy scope, and idempotency constructor
- **WHEN** it includes `max_tokens` and `max_wall_time_seconds`
- **THEN** scenario construction SHALL succeed and preserve those declared
  fields for the dispatcher.

### Requirement: Scenario dispatch is registry based and normalizes every terminal result

The current scenario runner SHALL route a valid scenario only through the
in-process dispatcher registered for its target surface and SHALL normalize a
dispatcher return to a custom `EvalResult`. An unregistered target surface MUST
return `skip` with `no_dispatcher_registered`; a raised dispatcher exception
MUST return `error` with its type and message; absent an explicit valid verdict,
the runner SHALL derive pass/fail from `min_score`.

#### Scenario: An unregistered surface is a visible skip

- **GIVEN** a valid scenario whose target surface has no registered dispatcher
- **WHEN** `run_scenario` is called
- **THEN** it SHALL return custom `EvalResult(score=-1.0, verdict=skip)` with
  the scenario, candidate, and registered-surface context in details.

#### Scenario: A dispatcher without a verdict is threshold-normalized

- **GIVEN** a registered dispatcher that returns a numeric score but no verdict
- **WHEN** its score meets the scenario's `min_score`
- **THEN** the runner SHALL return verdict `pass` and preserve scenario,
  candidate, privacy, and threshold context in details.

### Requirement: The shipped MCP-call dispatcher is synchronous and reports, rather than enforces, budgets

The current `mcp_call` dispatcher SHALL synchronously invoke one supplied action
handler, parse its JSON response when possible, run supplied evaluators or the
default status evaluator, and aggregate scores by the current mean, minimum, or
mean-fallback weighted modes. It MUST clamp evaluator scores to `[-1.0, 1.0]`
and report over-wall-time budget in details, but it SHALL NOT be represented as
enforcing token budgets, enforcing wall-time termination, running in parallel,
or providing a sandbox.

#### Scenario: A slow handler produces evidence but is not terminated by the runtime

- **GIVEN** an `mcp_call` scenario whose action handler exceeds its declared
  `max_wall_time_seconds`
- **WHEN** the handler returns and the dispatcher completes evaluation
- **THEN** the result details SHALL report the elapsed time and `over_budget`,
  while the current dispatcher SHALL not claim that it terminated the handler.

#### Scenario: Unsupported future scenario execution is not claimed as shipped

- **GIVEN** a review of acceptance-scenario execution beyond a registered
  `mcp_call` dispatcher
- **WHEN** it describes the as-built runtime
- **THEN** it SHALL state that unregistered surfaces return `skip` and SHALL
  NOT claim distributed workers, parallel scenario execution, a new sandbox,
  or generic realtime scenario orchestration as implemented.
