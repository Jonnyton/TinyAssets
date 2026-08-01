# Agent interchange load evidence

- Date: 2026-07-31 PDT
- Revision: `07a947bd4fb986b4605e5142ab190aed26a7533a`
- Environment: Windows 11 build 26200, Python 3.14.3, Intel64 Family 6 Model 151
- Command: `python -m pytest tests/load/test_agent_interchange_load.py -q -s`
- Topology: 8 spawned worker processes, one shared WAL-mode SQLite database, 200 actor identities
- Distribution: 244 ordinary stages, 244 canonical imports, 244 remixes, 244 foreign exports, and 24 retry/conflict stage calls; 1,000 total calls
- Bounds represented: one exact 262,144-byte canonical candidate, one 64-component definition, opaque extension content, credential-like input, identical retries, and changed-input conflicts

## Result

```json
{"actors":200,"expected_conflicts":8,"p95_seconds":0.12019970000255853,"p99_seconds":0.23327279998920858,"processes":8,"requests":1000,"throughput_per_second":143.7811007507196,"unexpected_errors":[],"wall_seconds":6.955017000000225}
```

- Thresholds passed: throughput 143.78/s >= 3.33/s; p95 0.120s < 2s; p99 0.233s < 3s; unexpected error rate 0% < 1%.
- Eight changed-input idempotency conflicts were expected and counted separately.
- Every identical retry returned its first stage ID; the idempotency uniqueness query found zero duplicate logical rows.
- `PRAGMA integrity_check` returned `ok`; the focused injected-failure test separately proves stage publication rollback leaves no partial definition/stage mutation.
- The SQLite database and sidecars contained neither the credential fixture value nor an unkeyed raw-source digest.
