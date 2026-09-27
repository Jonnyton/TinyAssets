# user-owned-automations (delta)

## ADDED Requirements

### Requirement: A node can wake one of its owner's branches, now or not before a time

A node with `enqueue_branch_run` in `tools_allowed` SHALL be able to store a
one-shot automation, trigger kind `once`, in its run's own universe. The row is
owned by the run's owner and runs one of that owner's authored branches, private
ones included. The row SHALL carry an optional `not_before`, given either as an
ISO instant or as `delay_seconds`. It SHALL be stored durably and fired by the
automation pump once `not_before` has passed. The pump SHALL apply every
run-time check an automation already has. A row whose run started SHALL retire
itself. The capability SHALL be on by default. It SHALL be limited by usage (the
per-universe pending-automation count and run admission), never by spawn depth
or fan-out.

#### Scenario: A delayed wake fires once, after its time
- **WHEN** a node enqueues its owner's branch with `delay_seconds: 600`
- **THEN** no run starts before 600 seconds have passed, one run starts after that, and the row is retired

#### Scenario: A branch can reschedule itself indefinitely
- **WHEN** every run of a branch enqueues that same branch
- **THEN** each hop is accepted, subject only to the per-universe limits

#### Scenario: Another user's universe, identity or branch is refused
- **WHEN** a node names another universe, runs without its universe's owner bound, or targets a branch its owner did not author
- **THEN** nothing is stored and the node receives the refusal

#### Scenario: A wake survives a deploy
- **GIVEN** a stored wake whose run was killed with its process
- **WHEN** a later process holds the universe lease
- **THEN** the wake is retried under a new key, up to a bounded number of attempts
