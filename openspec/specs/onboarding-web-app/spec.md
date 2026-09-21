# Onboarding Web App

## Purpose

Define restart-safe hosted model authorization for the authenticated onboarding app.

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
