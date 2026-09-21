## MODIFIED Requirements

### Requirement: A served interactive completion is judged by progress, not a total wall-clock

A served writer completion SHALL be read as an incremental event stream and judged
by an idle watchdog: its deadline resets on ANY recognized protocol event that
proves the provider is actively working — an assistant text delta, a tool
start/result, a documented provider retry event, the terminal result, OR a
recognized non-relayed liveness event (provider/reasoning heartbeat, thinking
progress, hooks, status, stream framing, tool progress, an informational
rate-limit event). It SHALL NOT reset on whitespace, stderr, or unparseable
output. Internal reasoning MAY reset the watchdog as a liveness signal but SHALL
NEVER be relayed into the assembled reply; only assistant text and the terminal
result are relayed. When a documented provider retry event states a retry delay,
the idle budget for that wait SHALL be extended to cover it (so a real provider
retry is not misclassified as a hang). A completion that keeps making progress
SHALL NOT be failed for total elapsed time; a completion that stops making progress
SHALL be ended at the applicable idle boundary, except that identified pending
native tools receive the bounded tool-work allowance described below. An absolute safety cap MAY end an over-long
interactive turn, but it SHALL be generous enough that a genuinely progressing turn
survives well past the old total deadline, and reaching it SHALL be reported as an
interactive-deadline outcome, not as provider unavailability.

#### Scenario: A long but progressing turn is not timed out

- **WHEN** a served completion keeps emitting protocol events past the old total
  deadline
- **THEN** it continues and is not failed for elapsed time

#### Scenario: A reasoning-only stretch keeps the turn alive

- **WHEN** a served completion emits only recognized reasoning/heartbeat events
  (no assistant text) for longer than the idle interval
- **THEN** the attempt continues (the events are liveness) and their content is
  not relayed into the reply

#### Scenario: A known provider retry wait is not misclassified as a hang

- **WHEN** a documented provider retry event states a retry delay longer than the
  idle interval and the stream then recovers
- **THEN** the attempt is not ended as `provider_idle_timeout` during that wait

#### Scenario: A hung turn is ended at the idle boundary

- **WHEN** a served completion emits no recognized protocol event for the idle
  interval, with no identified tool work or documented retry wait pending
- **THEN** the attempt is ended and classified `provider_idle_timeout`

#### Scenario: Silence inside a codex turn is the model generating, not idle

- **GIVEN** a codex-served completion (`codex exec --json`), which emits NO
  reasoning or assistant-text deltas — between one protocol event and the next
  there is one whole model round-trip of silence (31s live on 2026-08-29;
  ~100s per round-trip observed), and whose `turn.started` / `item.started` /
  `item.completed` are delivered best-effort (the in-process queue of
  codex-cli 0.146.0 guarantees only `TurnCompleted`, projected as
  `turn.completed` / `turn.failed`; `thread.started` is printed by exec itself
  before the turn is requested)
- **WHEN** any protocol event has been read and no terminal turn event
  (`turn.completed` / `turn.failed`) has arrived yet
- **THEN** the turn is running (`codex exec` runs exactly one) and silence is
  allowed for `min(absolute cap, 900s)` (`_TURN_WAIT_S`, the same bound as a
  tool wait `_TOOL_WAIT_S` — with `item.started` equally droppable, "in a tool"
  and "generating" are not reliably distinguishable); the profile's idle
  interval guards only the launch edge (no event at all within `init_s`)
- **NOTE (as-built boundary):** for codex the idle boundary inside a turn IS
  900s — the CLI offers no finer liveness signal to judge progress by. Two
  signal-less windows share that bound rather than a shorter one: a stall
  between `thread.started` and the `turn/start` request (an in-process RPC,
  never a model wait), and a shutdown that stalls after
  `TurnCompleted(Interrupted)`, which projects no terminal JSONL event (only
  SIGINT interrupts an exec turn; the daemon never sends one). A finished
  stream whose `agent_message` item was dropped under backpressure fails loud
  in `complete()` ("omitted result or usage") —
  `docs/concerns/2026-08-29-codex-agent-message-can-be-dropped-under-backpressure.md`.
  The Claude reader pairs native tool starts/results by identity and honors a
  bounded pending-tool allowance without changing Codex turn semantics.

#### Scenario: A completed codex turn is never failed by its own shutdown

- **GIVEN** the reader has read `turn.completed` (or `turn.failed`) — the
  projections of the one guaranteed notification, `TurnCompleted`
- **WHEN** the child has not exited `_TAIL_WAIT_S` (60s) later — codex exec
  unsubscribes the thread and awaits `client.shutdown()`, bounded at 45s in
  0.146.0
- **THEN** the reader ends the child and RETURNS the finished stream; any tool
  left open is closed with the turn; and the caller treats a non-zero exit code
  after a stream that carries `turn.completed` as process trivia (logged, never
  raised — the protocol's word beats the exit code)

#### Scenario: A provider `error` event that may retry is liveness, not termination

- **WHEN** codex emits a top-level `error` event (its `will_retry` flag is not
  projected into the JSONL) while a tool is in flight
- **THEN** the tool stays in flight and the watchdog treats the event as liveness;
  only the terminal `turn.completed` / `turn.failed` close the turn and its
  in-flight tools (verified on codex-cli 0.146.0)

#### Scenario: The served absolute cap is a runaway backstop with per-universe overrides

- **GIVEN** a granted served founder turn (`_sandboxed_config(..., granted=True)`)
- **THEN** its absolute cap is 3600s (`_SERVED_ABSOLUTE_CAP_S`) unless the universe
  context carries a numeric `absolute_cap_s` / `idle_timeout_s`; a non-numeric
  override falls back to the default rather than disabling the cap; non-granted
  paths (the learning extractor) keep the library default profile

#### Scenario: Identified native tool work is not model-idle silence

- **WHEN** a Claude stream has an identified tool start without its matching result
- **THEN** silence receives a tool-work allowance bounded by the existing absolute cap and 900 seconds
- **AND** one tool finishing, interleaved text, heartbeats, or duplicate start frames do not close a different pending tool
- **AND** matching all results restores ordinary model-idle behavior; terminal result clears pending tools

#### Scenario: Missing identities and runaway work remain bounded

- **WHEN** tool identities are missing or malformed, or the existing absolute deadline is reached
- **THEN** missing identity does not earn a tool-work allowance and the absolute deadline still ends execution
- **AND** cancellation still terminates/reaps the process without automatic replay


## ADDED Requirements

### Requirement: Persisted provider failures retain safe tool-wait evidence

Attempt diagnostics SHALL retain known finite nonnegative last-progress age and
an admitted tool-phase enum through existing router, held-error, run persistence
and authorized read projections. Missing or malformed evidence SHALL remain
unknown; diagnostic fields SHALL never contain tool arguments, credentials,
reasoning, arbitrary provider strings or tool identifiers. This evidence SHALL
NOT authorize replay, a fallback, a grant or a cooldown.

#### Scenario: A pending-tool timeout can be distinguished from post-tool silence

- **WHEN** the reader supplies valid tool-phase and progress-age evidence for a timeout
- **THEN** the persisted served run failure exposes that evidence through its existing diagnostic chain
- **AND** malformed, unknown, non-finite or sensitive values are omitted without changing the failure class

#### Scenario: Existing historical evidence is not invented

- **WHEN** a stored failure lacks tool-phase evidence
- **THEN** later reads do not infer a pending tool from committed side-effect state or a successful retry
