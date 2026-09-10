# Private served-agent journal verification

September10,2026, candidate6ce30ad0dd20aab49cb7434a6f2449f51aeb8a30.
Shape8480ec10 independently ADAPT352s, applied7470b3d4 before code. Exact-head
implementation review65296 returned APPROVE432s with no mandatory fixes and
48 independently reproduced cases,zero skips. Full review recovered from this
dispatch's own transcript because the stop-hook recap again replaced its stdout;
see agent-turn-journal-implementation-review.md in this directory. No rerun.

Canonical storage/agent_turn_records.py and agent_turn_journal.py preserve
versioned owner-scoped turn/round/call data, CAS starts and exact repeated
finalization, known nontext results, and ambiguous outcomes without replay.
Account deletion counts cascades/current+former homes; reset preserves terminal
evidence and blocks matching active/ambiguous/corrupt history. No live caller,
credential/authority mint, workflow mutation or model selection activation.

## Commands and results

Windows Python3.14, candidate:

`python -m pytest -q tests/test_agent_turn_journal.py tests/test_agent_chat_codec.py tests/test_account_deletion.py tests/test_scoped_identity_reset.py tests/test_mirror_parity_gate.py --tb=short -rs`

261passed,zero skips,47.86s. Separate first runs87journal/account passed6.43s;
68reset passed39.19s. Ruff, diff check,411 plugin mirrors/import and commit gates pass.

Actual Ubuntu Docker Python3.11.16/git2.47.3/bwrap0.12.0, same five-file command
via scripts/linux_oracle.py, image tinyassets-linux-oracle:ce0e83fb15a8:
258passed/3failed,zero skips,45.83s. All journal/codec/account/mirror cases passed.
The exact pre-code7470b3d4 archive, run in the IDENTICAL image, has65passed/3failed
for the unchanged scoped-reset file,38.54s. Failure IDs and reasons exactly match:

- test_operator_cli_loads_private_roster_and_emits_redacted_plan: roster mode.
- test_roster_rejects_credentials_and_unexpected_fields: roster mode.
- test_apply_resets_exact_founder_home_and_subject_grants_only: raw SQLite bytes.

No newly failing test in this group. Do not call the entire Linux suite green.
Baseline snapshot remains /tmp/tinyassets-journal-base.unuBtD in Ubuntu. The first
archive attempt hashed LF files differently from Windows and began an unwanted
image rebuild; its exact builder PID706 was terminated, session59615 exit1.
It produced no test evidence. Corrected fixed-image run51931 is the comparison;
candidate24625 and Windows35143 are terminal. No source was overwritten for baseline.

Coverage includes actual SQLite concurrent start/finalize, rollback faults on
second tool insertion and frontier update, crash after committed intent, strict
snapshot corruption, ordered multi-call batches, reused wire IDs across rounds,
nullable actual usage and nontext/isError result retention. No network effect or
automatic resume is performed. Full runtime integration/live user proof remains
the next step, not implied by this storage-only evidence.

Integration notes retained from review: define authorized abandon/retry without
reviving ambiguous work; establish current-home/foreign-owner deletion policy
at the executor ingress; avoid history-linear validation under the global write
lock as turns grow; make shared codec validation an explicit internal interface.
Smaller notes: explicit get transaction rollback, tolerate a vanished row in
reset inspection, and add begin-round race coverage. These were nongating; the
Linux evidence above subsequently fills the review's missing-Linux observation.
No storage/runtime approval is inferred beyond unchanged6ce30ad0.
