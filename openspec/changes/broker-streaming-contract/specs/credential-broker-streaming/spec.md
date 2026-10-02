## ADDED Requirements

### Requirement: The broker authorizes every stream as it opens
The credential broker SHALL authorize each stream when it opens, with the same
checks `resolve_exact_scoped_proxy` applies today: the authenticated
principal, an active grant, the grant's owner and command center, the
connection's identity and owner, and revocation. It SHALL identify the
caller's role from the connecting process's authenticated identity against its
own configuration, refuse unmapped callers, and refuse frames the role may not
send. On a box channel the principal SHALL be derived from the box identity
that `boxhostd` authenticated, and any principal the request names SHALL be
refused. A stream refused here SHALL end `refused` with `side_effect_state`
`none`, and nothing SHALL reach the network.

#### Scenario: a revoked grant refuses the next stream
- **WHEN** a grant is revoked while its owner's earlier stream is still open
- **THEN** the next stream opened on that grant is refused before any network
  activity

#### Scenario: a box cannot name another principal
- **WHEN** a request relayed for a box names a principal or a connection its
  command center was not granted
- **THEN** the broker refuses it without network activity

### Requirement: Responses stream with backpressure and cancellation
The broker SHALL send a stream's status, reason and sanitized headers only
after the redirect chain and the OAuth refresh-once are settled, and SHALL
then forward the response body as it arrives, never more than the caller's
outstanding credit, reading upstream only while credit remains. After the
status is sent the broker SHALL NOT send the request again. Request bodies in
this version SHALL be collected within today's bound before sending. A
caller's cancel SHALL abort the upstream request and end the stream. An
absolute deadline SHALL run from admission through every phase; an idle bound
SHALL count bytes read from upstream and SHALL pause while reading is stopped
for lack of credit.

#### Scenario: the first token arrives before the last
- **WHEN** a model source streams its reply over several seconds
- **THEN** the caller receives the first body bytes before the upstream
  response has finished

#### Scenario: a slow consumer does not grow broker memory or look idle
- **WHEN** a caller stops granting credit while the provider is still sending
- **THEN** the broker stops reading that stream, buffers no more than its
  window plus the scan hold-back, and does not end it as idle

### Requirement: No byte of a held sensitive value is forwarded
The broker SHALL scan, for each stream, every sensitive value the
request/close path scans today, including values it derives for the request
and material accumulated across redirects. It SHALL scan intermediate
redirect responses and targets before following them, the final headers
whole, and the body incrementally, withholding the trailing bytes that could
still begin an occurrence until more bytes arrive or the stream ends cleanly.
On a match it SHALL end the stream as an unsafe destination response, forward
none of the withheld bytes, and record an audit entry. No forwarded byte SHALL
belong to a complete occurrence of a held value.

#### Scenario: a value split across reads is caught
- **WHEN** a destination echoes a held credential split across two upstream
  reads
- **THEN** no byte of the credential reaches the caller and the stream ends
  failed

#### Scenario: a derived authorization value is still held
- **WHEN** a destination echoes only the encoded Basic authorization payload
- **THEN** the stream ends failed exactly as the request/close path refuses it

### Requirement: Transmission uncertainty is reported, never guessed
A stream SHALL report `side_effect_state` `none` only when the broker proves no
request byte left it. After the first write it SHALL report `unknown`, and that
SHALL hold through the OAuth resend, redirects, cancellation and any later
refusal. The broker SHALL NOT infer `none` from a response status.

#### Scenario: a cancelled stream after sending is unknown
- **WHEN** a caller cancels a stream whose request was already written
- **THEN** the stream ends `cancelled` with `side_effect_state` `unknown`

### Requirement: An operation is recorded durably and never sent twice
The broker SHALL record each stream's operation by authority namespace and
`op_id`, bound to the request's identity, SHALL persist that a request may
have been sent before its first byte is written, and SHALL NOT send a recorded
operation again; a concurrent or later open of the same `op_id` SHALL return
the recorded state, and one with a different request identity SHALL be refused.
A status query SHALL distinguish not sent, unknown, the terminal states and
expired, and SHALL find nothing outside the caller's namespace. An `op_id`
older than the retention window SHALL be refused.

#### Scenario: a crash after sending reads as unknown
- **WHEN** the broker crashes after writing a request and restarts
- **THEN** a status query for its `op_id` reports unknown and an open reusing
  the `op_id` does not reach the destination

### Requirement: Streams below the owner fence are refused and stopped
Every owner-channel stream SHALL carry the generation and the token the
broker's last fence barrier issued, and relayed box streams SHALL carry the
pair `boxhostd` received from its own barrier. The broker SHALL admit a stream
only if both equal its persisted fence, and SHALL re-check them immediately
before every write to the network. On a barrier for generation G it SHALL
durably persist the greater of its fence and G with a new token, stop every
older stream, and acknowledge only once no older stream can write again. It
SHALL enforce the persisted fence after a restart whether or not the
acknowledgement was delivered.

#### Scenario: a stale owner cannot reach the network
- **WHEN** an owner of an older generation opens a stream after a newer
  barrier, whatever generation number it states
- **THEN** the stream is refused as fenced with no network activity

### Requirement: Request/close callers keep their contract
`ScopedConnectionProxy.request` SHALL keep its signature, return document,
redirect fields, typed errors and closed-proxy refusal, implemented as one
stream collected to its end and checked with today's matcher on the decoded
body. No per-request or per-proxy process SHALL be spawned.

#### Scenario: an effector call is unchanged
- **WHEN** an effector calls `proxy.request("POST", {...})`
- **THEN** it receives the same document and the same typed errors as before
  this change

### Requirement: The in-box endpoint never reports a failed stream as success
The box's base-URL endpoint SHALL select the grant from the box's command
center and the connection named in its path, SHALL send only to that
connection's declared host and allowed endpoints, SHALL map a failure before
the status to an HTTP error status naming only the error class, and SHALL end
a response that fails after its status by aborting the connection without a
successful terminator.

#### Scenario: a scan hit after the status reaches the CLI as truncation
- **WHEN** the broker ends a stream failed after the CLI already received a
  200 status and part of the body
- **THEN** the CLI's connection is aborted without the terminating chunk
