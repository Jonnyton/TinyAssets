# Provider routing — streamed attempts + timeout taxonomy deltas

## ADDED Requirements

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
SHALL be ended at the idle boundary. An absolute safety cap MAY end an over-long
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
  interval
- **THEN** the attempt is ended and classified `provider_idle_timeout`

### Requirement: Provider failures are classified, and transient attempt timeouts do not cool the provider

Each served attempt outcome SHALL carry a `failure_class` derived from the stream
and process exit — at least `provider_rate_limited`, `provider_overloaded`,
`authority_held`, `provider_idle_timeout`, `interactive_deadline`, and
`provider_protocol_error`. A `provider_idle_timeout` or `interactive_deadline`
SHALL NOT place the sole served writer on a provider-wide cooldown; the next turn
SHALL remain eligible. A genuine `provider_rate_limited`/`provider_overloaded`
SHALL cool the provider until its own retry-after. The interactive request path
SHALL NOT sleep (no synchronous backoff) while holding the inbound request or a
turn-worker slot.

#### Scenario: One idle timeout does not poison the next messages

- **WHEN** a served turn ends with `provider_idle_timeout`
- **THEN** no provider-wide cooldown is applied and the user's next message is
  attempted normally

#### Scenario: A real rate limit is honored

- **WHEN** the stream reports a documented rate-limit/overload retry event
- **THEN** the provider is cooled until its retry-after and the outcome is
  classified `provider_rate_limited`/`provider_overloaded`

### Requirement: The user notice reflects the true failure class, never mislabeling a timeout as capacity

The failure notice delivered to the user SHALL be derived from the structured
`failure_class`. A timeout or interactive-deadline outcome SHALL NOT be presented as
"model capacity" or a rate limit. A completion SHALL NOT be recorded as a completed
assistant response unless a terminal provider result was produced.

#### Scenario: A timeout is described honestly

- **WHEN** a turn ends with `provider_idle_timeout` or `interactive_deadline`
- **THEN** the user notice states the model stopped making progress / the reply
  exceeded the interactive window — not that the model is at capacity
