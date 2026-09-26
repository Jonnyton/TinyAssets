# Onboarding Web App

## Purpose

Define hosted model authorization and safe conversation recovery for the authenticated app.

## Requirements

### Requirement: Hosted model authorization survives daemon replacement
Hosted PKCE bindings SHALL survive process restart until their original expiry,
without persisting authorization codes, verifiers, keys or raw flow handles.
One valid owner/home/preset/verifier-matching callback SHALL atomically consume
the binding before exchange; no uncertain exchange SHALL automatically replay.

#### Scenario: Deploy while the user authorizes
- **WHEN** the daemon restarts after begin and before an unexpired callback
- **THEN** the same authorized owner/home/verifier can complete exactly once

#### Scenario: Multiple workers receive the same callback
- **WHEN** two processes attempt to consume one valid binding concurrently
- **THEN** exactly one can proceed to provider exchange

#### Scenario: A mismatched callback arrives
- **WHEN** owner, home, verifier or preset does not match the binding
- **THEN** the attempt is refused without consuming another valid owner's binding

### Requirement: Recovery distinguishes live turns from previous-page records
The app SHALL NOT restore a turn that its current page still owns as abandoned
work. Durable recovery SHALL remain owner/home-scoped and available on reload.

#### Scenario: Status or history completes during a live turn
- **WHEN** a typed or spoken request is still in progress on the current page
- **THEN** status/history restoration adds no duplicate message or false retry offer
- **AND** the original response can render once without a second invocation

#### Scenario: Previous-page observation finishes after a newer send
- **WHEN** a previous-page request is observed while a newer turn starts
- **THEN** clearing the observed request SHALL NOT erase the newer turn's recovery
- **AND** account/home changes fence recovery for any turn, and a typed or spoken turn's late reply or failure from another account or home paints nothing, offers no retry, signs nobody out, and hands no reply to the voice session now on screen

### Requirement: Response completion is correlated and does not wait for stream closure
The app SHALL accept only a JSON-RPC terminal response with the exact outgoing
request ID. It SHALL read SSE incrementally, ignore comment keepalives,
notifications and foreign response IDs, and settle as soon as its own result or
error arrives. Ordinary JSON responses SHALL retain the same correlation rule.

#### Scenario: A completed result arrives on an open connection
- **WHEN** a matching terminal response arrives after notifications or unrelated responses
- **THEN** the app settles that request and releases its reader without waiting for EOF
- **AND** arbitrary UTF-8, CRLF and multi-line SSE chunk boundaries preserve the result

### Requirement: Transport uncertainty is bounded without replaying user intent
The app SHALL bound missing response headers and silence between received bytes,
not the total duration of a healthy keepalive-producing turn. The defaults are
90 seconds for headers and 120 seconds for byte silence. Expiry SHALL be shown
as unconfirmed delivery, not proof of execution failure or cancellation.
Only existing explicitly idempotent reads or proven pre-dispatch refusals may
retry automatically; an ambiguous conversation or connection write SHALL NOT.

#### Scenario: A connection stops producing replies
- **WHEN** headers never arrive or an established response becomes silent
- **THEN** the waiting request settles with an unconfirmed transport outcome
- **AND** recovery data remains available and the composer is released under its owner fence
- **AND** another request's stream is not aborted

#### Scenario: A long turn continues to produce keepalives
- **WHEN** its total duration exceeds the byte-silence bound but bytes keep arriving
- **THEN** the client continues to wait for its matching terminal response

### Requirement: Unconfirmed recovery offers observation and explicit queue resumption
For an unconfirmed default conversation, the app SHALL offer an owner-fenced,
read-only saved-conversation snapshot preserving the draft and pending request.
It SHALL NOT attribute a saved reply to the request by matching text or time.
Messages queued behind an unconfirmed turn SHALL remain held until explicitly
resumed, including when the user sends a separate inspection question.

#### Scenario: Inspect progress before deciding whether to send again
- **WHEN** the user selects the saved-conversation check
- **THEN** saved messages and their available timestamps are shown as an uncorrelated snapshot
- **AND** no conversation is invoked and no pending request is marked complete

#### Scenario: A manual question follows an uncertain outcome
- **WHEN** the user asks another question while older queued messages remain held
- **THEN** finishing that question does not send the held messages
- **AND** an explicit queue-resume control sends them only within the same owner, home and login

### Requirement: Working state is the universe's, and waiting lines are ordered last
The app's working indicator SHALL reflect server-reported turn state for the
universe, whatever started the turn -- a typed message, an answered request, a
queued line, another window, another device, or the connector -- and SHALL NOT
depend on the current page having sent anything. `get_status` SHALL carry, gated
on write access to the universe, whether a turn is progressing, since when, and
its journal state, and no prompt, model or owner. A row past the cap the
coordinator already enforces SHALL be reported as stale and SHALL NOT be painted
as activity; a read that failed SHALL be reported as unreadable rather than as
idle. A message queued behind an in-flight turn SHALL render in the order the
agent will read it -- after that turn's reply -- and SHALL be marked as queued
until its own turn starts.

#### Scenario: A turn this page did not start
- **WHEN** a turn is running for the universe and this page sent nothing
- **THEN** the working indicator is shown, with how long, and that it started elsewhere
- **AND** the status poll asks more often until the universe is idle again

#### Scenario: A reload during a live turn
- **WHEN** the page loads while a turn is still running, so history has no record of it
- **THEN** the same read that returns history reports the turn and the indicator is shown

#### Scenario: A row no client can still verify
- **WHEN** the reported row is older than the served-turn cap, or the journal cannot be read
- **THEN** it is reported rather than hidden, and it is not painted as activity
- **AND** a status poll that fails neither clears the indicator nor claims it indefinitely

#### Scenario: An answer given while an earlier turn is running
- **WHEN** the user answers a request and the earlier turn's reply arrives afterwards
- **THEN** the reply renders above the queued answer, which stays marked queued
- **AND** the queued mark is removed when that answer's own turn starts
