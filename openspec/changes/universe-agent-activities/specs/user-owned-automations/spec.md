## ADDED Requirements

### Requirement: An automation can target an activity
An automation SHALL carry a target kind, `branch` (the default for every existing row) or `activity`. A branch target SHALL name a branch and no activity template; an activity target SHALL carry an activity template (title, brief and agent) and no branch, and its owner SHALL be the authenticated creator, never a value in the template. An activity target's lease key SHALL be distinct from every branch target's. Firing an activity target SHALL keep every guarantee of a branch target -- owner revalidation, the current serving assignment, foreground admission and budget, and the firing fence -- and SHALL create exactly one activity per due time, linked by the automation id and due time so that re-firing the same attempt returns the same activity. Overlap policies SHALL apply against the automation's latest activity.

#### Scenario: a weekly report is a scheduled activity
- **WHEN** the owner's agent creates an automation with an activity target for Mondays at 09:00
- **THEN** each Monday exactly one activity starts under the owner's foreground budget and appears in the Scheduled and then In progress views

#### Scenario: an invalid target is refused loudly
- **WHEN** a registration names both a branch and an activity template, or neither
- **THEN** it is refused with a named reason and nothing is stored

#### Scenario: a crash between the fence and the activity
- **WHEN** the daemon stops after claiming an activity target's attempt but before the activity exists
- **THEN** the next fire of that attempt creates it once
