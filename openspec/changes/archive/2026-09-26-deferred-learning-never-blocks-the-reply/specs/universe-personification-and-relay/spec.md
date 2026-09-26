## MODIFIED Requirements

### Requirement: Learning is a separate tolerant model-extracted step with field-specific filtering, and reply delivery survives failures
Learning SHALL be a step separate from the reply. A turn that recorded what it was
taught IN-TURN, settling its conversation's learned cursor
(`deferred-turn-learning`), SHALL NOT then make a separate learning provider call.
A turn whose cursor is still unsettled when it ends SHALL run that separate call
after the reply turn, as before, whose prompt asks for durable facts explicitly
stated in the founder's latest message — so no lesson is lost and no turn is slower
than before.
Parsing SHALL tolerate fenced JSON or an embedded top-level object and return
an empty proposal when no dict can be recovered. `commit_learning` SHALL
string-coerce `name`, treat non-dict `soul` as empty, accept only governed soul
filenames with non-empty string bodies, apply the generic-boilerplate regex only
to `soul["identity.md"]`, and filter canon list items individually for non-empty
title/content. It SHALL NOT compare accepted non-generic name, soul, or canon
facts with the founder message, so unsupported extractor output can pass. A
`SoulEditError` while reading governed files SHALL become an empty governed set
without logging at that catch; rejected soul edits and failed canon items SHALL
be logged. Any other extraction/commit exception SHALL be logged, and no learning
failure SHALL prevent reply delivery or leave a lesson silently lost — an
unsettled cursor is the record that it is still owed.

#### Scenario: a turn that recorded its lesson does not pay for a second pass
- **WHEN** a founder turn recorded what it was taught and its cursor is settled at turn end
- **THEN** `converse` returns the reply with no further model round-trip

#### Scenario: a turn that recorded nothing keeps the guaranteed pass
- **WHEN** the cursor is still unsettled when the turn ends
- **THEN** the separate learning provider call runs after the reply turn, as before

#### Scenario: tolerant parsing and field-specific filtering
- **WHEN** extraction returns fenced or embedded JSON with mixed valid and invalid fields
- **THEN** the top-level dict is recovered when possible
- **AND** name, governed non-empty soul bodies, and non-empty canon items are handled by their field-specific coercion and filters rather than one strict schema validator

#### Scenario: accepted extractor output is not source-entailment checked
- **WHEN** field-specific filters accept a non-generic name, soul body, or canon item
- **THEN** commit does not compare that fact with the founder's latest message before persistence

#### Scenario: generic identity boilerplate is filtered only from identity.md
- **WHEN** a proposal contains only an `identity.md` body matched by the generic-boilerplate regex and no accepted name or canon item
- **THEN** commit makes no soul edit
- **AND** the regex is not applied to the separate name or canon fields

#### Scenario: governed-file read failure is silently narrowed
- **WHEN** `read_governed_files` raises `SoulEditError`
- **THEN** commit uses an empty governed-file set without logging at that catch
- **AND** continues processing any accepted name or canon fields

#### Scenario: persistence failure preserves the reply
- **WHEN** extraction or commit raises beyond the field-specific handled failures
- **THEN** the error is logged, the founder's reply is unaffected, and the cursor stays unsettled so the lesson is retried
