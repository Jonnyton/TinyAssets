## MODIFIED Requirements

### Requirement: Engine run admissions are charged as writes and settled by what fired

The engine SHALL admit every engine-triggered run and every scheduled
automation run through one per-universe rolling ledger, charging each as
kind `write` atomically at admission time. The engine SHALL admit every
durable engine write (`write_graph`, remix, brain write) through the same
ledger as kind `engine`. The engine SHALL refuse a run admission when the
universe's `write` admissions in the window have reached the write cap (20
per 3600 s) OR its admissions of any kind have reached the total cap (60 per
3600 s); it SHALL refuse an `engine` admission when the universe's `engine`
admissions in the window have reached the engine cap (40 per 3600 s, two
thirds of the total, so runs always keep at least 20) OR the total cap. An
`engine` row SHALL never be bound to a run or reclassified. A refusal caused
by an unusable or untrusted ledger SHALL say so and SHALL NOT be reported as
a quota. Rows outside the window SHALL be pruned on the next admission. All
other clauses of this requirement are unchanged.

#### Scenario: Branch authoring does not spend the effect budget

- **WHEN** a universe's engine has made 30 `write_graph` calls in the rolling
  hour and then runs a job that writes externally
- **THEN** the job's writes are admitted against an untouched 20-write budget

#### Scenario: A burst of engine writes cannot starve runs

- **WHEN** a universe's engine has made 40 `write_graph` calls in the rolling
  hour (failed validations included - they charged their admission)
- **THEN** the 41st is refused by the engine cap while runs are still admitted
  until 60 admissions of any kind exist
