## D2a: records, authority, dispatch
- [ ] 1.1 `agent_activities.py`: the store (schema, checked transitions, generation fencing, keyset reads, bounded events), declared in `ROOT_ENTRIES` and charged to the universe's quota.
- [ ] 1.2 The `activity` work item kind and the foreground lane's activity subject (record, liveness token, generation, founder home, admin ACL).
- [ ] 1.3 Seat kind `activity`; the durable dispatcher (pump cadence plus on demand, liveness-based takeover, `try_acquire` queueing).
- [ ] 1.4 The runner: `activity:<id>` session, stop/pause at the next tool boundary, waiting releases the seat, answered-request re-queue.
- [ ] 1.5 Served tools: `write_graph target=activity` and `read_graph target=activities|activity`; nested start refused; status lines into the main session.

## D2b: effects and resume
- [ ] 2.1 Activity linkage on runs; effect intents committed before the wire, unknown on transport uncertainty; interrupted-run recovery of intents and the owner question.
- [ ] 2.2 Resume: native or record-built from the turn journal; account deletion fences activities first.

## D2c: scheduled activities
- [ ] 3.1 Automations `target_kind` and `activity_template_json`, validation, the activity lease key, idempotent `<automation_id>@<due_at>` firing, overlap policies, the pause-before-downgrade release step.

## D2d: the Activity tab
- [ ] 4.1 `/app/activities` owner door (own home, revision compare-and-set, delete).
- [ ] 4.2 Activity tab: Waiting on you, In progress, Scheduled (complete, paged), Completed with receipts; stop, pause, resume.
- [ ] 4.3 Live proof: two activities in parallel after the chat is closed; one surviving a deploy with an effect in flight.
- [ ] 4.4 Sync these deltas into `openspec/specs/` and archive.
