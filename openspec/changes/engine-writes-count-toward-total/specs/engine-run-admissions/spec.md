## MODIFIED Requirements

### Requirement: Engine run admissions are charged as writes and settled by what fired

The engine SHALL admit every engine-triggered run and every scheduled
automation run through one per-universe rolling ledger, charging each as
kind `write` atomically at admission time. The engine SHALL admit every
durable engine write (`write_graph`, remix, brain write) through the same
ledger as kind `engine`. The engine SHALL refuse a run admission when the
universe's `write` admissions in the window have reached the write cap (20
per 3600 s) OR its admissions of any kind have reached the total cap (60 per
3600 s); it SHALL refuse an `engine` admission only by the total cap. All
other clauses of this requirement are unchanged.

#### Scenario: Branch authoring does not spend the effect budget

- **WHEN** a universe's engine has made 30 `write_graph` calls in the rolling
  hour and then runs a job that writes externally
- **THEN** the job's writes are admitted against an untouched 20-write budget,
  and the 31st-plus engine writes are still refused once 60 admissions of any
  kind exist
