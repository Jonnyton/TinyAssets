## D2a: records and runner
- [ ] 1.1 `agent_activities.py`: the store (schema, transitions, keyset reads, events), declared in `ROOT_ENTRIES`.
- [ ] 1.2 Seat kind `activity` (background class); runner acquires while running, releases when it rests.
- [ ] 1.3 The client-less runner: owner re-proof, the automation-style provider binding, the `activity:<id>` session, stop/pause at the next tool boundary.
- [ ] 1.4 Served tools: `write_graph target=activity` (start/stop/pause/resume) and `read_graph target=activities|activity`; nested start refused.
- [ ] 1.5 Status events into the main session as platform-composed lines.

## D2b: effects and resume
- [ ] 2.1 Record-before-send in `authenticated_external_call` while an activity is bound; key conflicts never send.
- [ ] 2.2 Boot resumer: dead-lease activities, sent -> unknown, owner question, then resume (native or record-built).

## D2c: scheduled activities
- [ ] 3.1 Automations `target_kind` and `activity_template_json` columns, validation, lease key, firing into an activity, overlap policies.

## D2d: the Activity tab
- [ ] 4.1 `/app/activities` owner door (own home, revision compare-and-set).
- [ ] 4.2 Activity tab: Waiting on you, In progress, Scheduled (complete, paged), Completed with receipts; stop, pause, resume.
- [ ] 4.3 Live proof: two activities in parallel after the chat is closed; one surviving a deploy with an effect in flight.
- [ ] 4.4 Sync these deltas into `openspec/specs/` and archive.
