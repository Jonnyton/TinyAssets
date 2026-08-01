# Agent interchange load evidence

- Date: 2026-07-31 PDT
- Revision: `7a7a4bf06f3f21e3d8b741474f4a80a28a30e6bb`
- Environment: Windows 11 build 26200, Python 3.14.3, Intel64 Family 6 Model 151
- Command: `python -m pytest tests/load/test_agent_interchange_load.py -q -s`
- Topology: 8 spawned worker processes, one shared WAL-mode SQLite database, 200 actor identities
- Distribution: 244 ordinary stages, 244 canonical imports, 244 remixes, 244 foreign exports, and 24 retry/conflict stage calls; 1,000 total calls
- Bounds represented: one exact 262,144-byte canonical candidate, one 64-component definition, opaque extension content, credential-like input, identical retries, and changed-input conflicts

## Result

```json
{"actors":200,"expected_conflicts":8,"p95_seconds":0.12580650000018068,"p99_seconds":0.25539360000402667,"processes":8,"requests":1000,"throughput_per_second":153.20202183830943,"unexpected_errors":[],"wall_seconds":6.527328999974998}
```

- Thresholds passed: throughput 153.20/s >= 3.33/s; p95 0.126s < 2s; p99 0.255s < 3s; unexpected error rate 0% < 1%.
- Eight changed-input idempotency conflicts were expected and counted separately.
- Every identical retry returned its first stage ID; the idempotency uniqueness query found zero duplicate logical rows.
- `PRAGMA integrity_check` returned `ok`; the focused injected-failure test separately proves stage publication rollback leaves no partial definition/stage mutation.
- The SQLite database and sidecars contained neither the credential fixture value nor an unkeyed raw-source digest.
