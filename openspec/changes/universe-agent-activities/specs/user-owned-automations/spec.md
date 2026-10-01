## ADDED Requirements

### Requirement: An automation can target an activity
An automation SHALL carry a target kind, `branch` (the default for every existing row) or `activity`. A branch target SHALL name a branch and no activity template; an activity target SHALL carry an activity template (title, brief and agent) and no branch. Firing an activity target SHALL keep every guarantee of a branch target -- the authenticated owner from the row, the current serving assignment, foreground admission and budget, and the firing fence -- and SHALL create one activity whose origin is that automation. Overlap policies SHALL apply against the automation's previous activity.

#### Scenario: a weekly report is a scheduled activity
- **WHEN** the owner's agent creates an automation with an activity target for Mondays at 09:00
- **THEN** each Monday one activity starts under the owner's foreground budget and appears in the Scheduled and then In progress views

#### Scenario: an invalid target is refused loudly
- **WHEN** a registration names both a branch and an activity template, or neither
- **THEN** it is refused with a named reason and nothing is stored
