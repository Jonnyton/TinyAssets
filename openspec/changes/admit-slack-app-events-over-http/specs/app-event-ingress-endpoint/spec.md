# app-event-ingress-endpoint Specification

## ADDED Requirements

### Requirement: Slack events are admitted only over a signature-verified HTTP route
The platform SHALL expose `POST /mcp/app/slack/events` on the universe server, SHALL admit a request only through the existing Slack app-event boundary (provider signature verification plus the durable replay ledger), and SHALL NOT expose any other path, method, or bypass that reaches the boundary's downstream authority chain.

#### Scenario: A correctly signed event is admitted exactly once
- **WHEN** Slack POSTs an `event_callback` whose `X-Slack-Signature` matches the configured signing secret and whose `api_app_id` matches the configured app id
- **THEN** the endpoint responds `200` within the acknowledgement budget
- **AND** the boundary records one admission receipt for that `event_id`

#### Scenario: A replayed event is acknowledged without re-admission
- **WHEN** Slack redelivers an event whose `event_id` already holds an admission receipt
- **THEN** the endpoint responds `200`
- **AND** the boundary reports the delivery as a replay rather than creating a second receipt

#### Scenario: A forged or tampered request is refused
- **WHEN** the signature is absent, malformed, computed over different bytes, older than the boundary's staleness window, or valid for a different app id
- **THEN** the endpoint responds `401` with no body detail beyond a fixed refusal
- **AND** no admission receipt, mapping lookup, custody grant, or outbound delivery occurs

#### Scenario: A non-POST method is refused
- **WHEN** any method other than `POST` is issued against the ingress path
- **THEN** the endpoint responds `405`
- **AND** the boundary is not invoked

### Requirement: The URL verification challenge is answered ahead of the event boundary
The platform SHALL answer Slack's `url_verification` handshake on the ingress path, SHALL verify that request's signature with the same secret before answering, and SHALL echo only the supplied `challenge` value.

#### Scenario: A signed handshake is answered
- **WHEN** Slack POSTs a correctly signed `url_verification` body containing a `challenge`
- **THEN** the endpoint responds `200` echoing exactly that challenge value and nothing else
- **AND** no admission receipt is written, because a handshake is not an event

#### Scenario: An unsigned handshake is refused
- **WHEN** a `url_verification` body arrives without a valid signature
- **THEN** the endpoint responds `401`
- **AND** no challenge value is echoed

#### Scenario: The handshake does not become an envelope bypass
- **WHEN** a request declares `type: url_verification` but also carries `event`, `event_id`, or other `event_callback` fields
- **THEN** the endpoint treats it strictly as a handshake, echoing only the challenge
- **AND** no event is admitted from that request

### Requirement: Missing ingress configuration disables the route rather than relaxing verification
The platform SHALL resolve the Slack signing secret and expected app id from server-owned configuration, and SHALL refuse every request on the ingress path when either is absent, empty, or malformed.

#### Scenario: Unconfigured deployment refuses ingress
- **WHEN** the signing secret or expected app id is unset, empty, or malformed and any request arrives on the ingress path
- **THEN** the endpoint responds with a fixed refusal
- **AND** it never treats an unverifiable request as authentic, and never accepts a signature computed with a default, empty, or request-supplied secret

#### Scenario: Configuration is never disclosed
- **WHEN** any request on the ingress path is refused for any reason
- **THEN** the response body distinguishes neither "not configured" from "bad signature", nor a known from an unknown app id

### Requirement: Acknowledgement is bounded and independent of downstream work
The platform SHALL acknowledge an admitted event within Slack's retry budget, and SHALL NOT make the acknowledgement wait on agent execution, provider calls, or outbound delivery.

#### Scenario: Downstream slowness does not cause Slack retries
- **WHEN** an event is admitted and downstream processing would take longer than the acknowledgement budget
- **THEN** the endpoint has already acknowledged the delivery
- **AND** Slack does not redeliver the event on a timeout

#### Scenario: A downstream failure does not resurface as an unsigned retry loop
- **WHEN** downstream processing of an admitted event fails
- **THEN** the failure is recorded against that admission
- **AND** the endpoint does not answer the original delivery with a retryable status that would replay signature verification
