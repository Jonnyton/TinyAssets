## ADDED Requirements

### Requirement: The broker authorizes every stream as it opens
The credential broker SHALL authorize each stream when it opens, with the same
checks `resolve_exact_scoped_proxy` applies today: the authenticated
principal, an active grant, the grant's owner and command center, the
connection's identity and owner, and revocation. On a box channel the
principal SHALL be derived from the box identity that `boxhostd`
authenticated, and any principal the request names SHALL be ignored. A stream
refused here SHALL end `refused` with `side_effect_state` `none`, and nothing
SHALL reach the network.

#### Scenario: a revoked grant refuses the next stream
- **WHEN** a grant is revoked while its owner's earlier stream is still open
- **THEN** the next stream opened on that grant is refused before any network
  activity

#### Scenario: a box cannot name another principal
- **WHEN** a box's request names a principal or connection other than its own
  command center's
- **THEN** the broker resolves against the box's own owner and refuses
  anything that owner was not granted

### Requirement: Responses stream with backpressure and cancellation
The broker SHALL send a stream's status and sanitized headers only after
redirects and the single OAuth refresh-and-retry are settled, and SHALL then
forward the response body as it arrives, never more than the caller's
outstanding credit, reading upstream only while credit remains. After the
status is sent the broker SHALL NOT send the request again. A caller's cancel
SHALL abort the upstream request and end the stream. A stream silent past its
idle bound, or running past its absolute reply budget, SHALL end with
`OutboundDeadlineExceeded`.

#### Scenario: the first token arrives before the last
- **WHEN** a model source streams its reply over several seconds
- **THEN** the caller receives the first body bytes before the upstream
  response has finished

#### Scenario: a slow consumer does not grow broker memory
- **WHEN** a caller stops granting credit
- **THEN** the broker stops reading that upstream stream and buffers no more
  than its window plus the scan hold-back

### Requirement: No prefix of a held secret is ever forwarded
The broker SHALL scan each stream's headers whole and its body incrementally
for every secret it holds for that request, with the same matcher as the
request/close path. It SHALL withhold the trailing bytes that could still
begin a match until more bytes arrive or the stream ends. On a match it SHALL
end the stream as an unsafe destination response, forward none of the
remaining bytes, and record an audit entry.

#### Scenario: a secret split across chunks is caught
- **WHEN** a destination echoes a held credential split across two upstream
  reads
- **THEN** no byte of the credential reaches the caller and the stream ends
  failed

### Requirement: A lost stream is resolved by op_id and never re-sent
The broker SHALL record each stream's outcome by `op_id` for a retention
window, SHALL answer a status query for it, and SHALL NOT send again a request
whose `op_id` it recorded as sent; an open reusing such an `op_id` SHALL
return the recorded outcome. Only a stream the broker proves never sent a
request byte SHALL report `side_effect_state` `none`.

#### Scenario: a reconnecting caller learns the outcome
- **WHEN** the caller's connection drops after the request was sent
- **THEN** a status query for its `op_id` reports it sent, and an open
  reusing the `op_id` does not reach the destination again

### Requirement: Streams below the owner fence are refused and cancelled
Every stream SHALL carry the execution owner's lease generation. The broker
SHALL refuse a stream below its persisted fence. On a fence barrier for
generation G it SHALL persist G, end every open stream below G, and only then
acknowledge. It SHALL reload the fence before serving after a restart.

#### Scenario: a stale owner cannot reach the network
- **WHEN** an owner at generation G-1 opens a stream after the broker
  acknowledged a fence at G
- **THEN** the stream is refused as fenced with no network activity

### Requirement: Request/close callers keep their contract
`ScopedConnectionProxy.request` SHALL keep its signature, return shape and
typed errors, implemented as one stream collected to its end. No per-request
or per-proxy process SHALL be spawned.

#### Scenario: an effector call is unchanged
- **WHEN** an effector calls `proxy.request("POST", {...})`
- **THEN** it receives the same `status`/`headers`/`body` document and the
  same typed errors as before this change
