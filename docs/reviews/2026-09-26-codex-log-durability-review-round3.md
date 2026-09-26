Reviewed `9a5160668c6a36792c23a605b8e6af5d33cc62e0` against `4cea8d91` on 2026-09-26, Windows. No edits, delegation, or worktrees. Part 1 was not re-reviewed.

Ran only:

```text
python -B -m pytest -q -p no:cacheprovider tests/test_backup_log_tier.py tests/test_log_aggregation.py
```

**118 passed.** Additional in-memory and real subprocess probes reproduced the failures below.

**§3 retirement — AGREE on the fix; one non-blocking DISAGREE_EVIDENCE.**

Masking the two explicitly retired units is appropriate even when their files belong to another tree. The new migration stops them before removal, reloads, then masks remaining definitions while managed timers remain paused. The narrowed search preserves saved copies outside dependency directories.

The remaining edge is [deploy/install-host-uptime-services.sh:342](C:/Users/Jonathan/Projects/ta-logs/deploy/install-host-uptime-services.sh:342): an **already masked but still active** unit passes immediately, so line 571 skips stopping it. Masking alone does not stop an existing process; systemd documents `--now` separately for that purpose. [Systemd documentation](https://raw.githubusercontent.com/systemd/systemd/v255/man/systemctl.xml).

I accept this as a **follow-up**, because the new migration stops units before creating its masks. Tighten the terminal predicate to require inactivity, and stop an active masked unit without removing its mask.

**§4 labelled-value redaction — DISAGREE_EVIDENCE. Blocking.**

At [scripts/redact_log_bundle.py:180](C:/Users/Jonathan/Projects/ta-logs/scripts/redact_log_bundle.py:180), `line.find(quote, value_start)` treats an escaped interior quote as the closing quote.

Reproduced:

```text
{"password": "alpha\"BRAVO_FRAGMENT", "status": 503}
→
{"password": "[redacted]"BRAVO_FRAGMENT", "status": 503}
```

Wrapping that JSON in Vector-shaped `{"log": ...}` still exports `BRAVO_FRAGMENT`. **The actual `collect_source()` path returned `(1, 'ok')`.** An additional JSON string-encoding layer left the entire planted password untouched.

The prose correction works: `authentication succeeded` and `authorization failed` survive. Leading whitespace inside quoted values is also consumed correctly.

I **disagree with accepting `password=a]b}c` as resolved**. Unquoted diagnostic text has no universal grammar prohibiting those password characters. Preserving `elapsed=17` after a recognizable sibling-field separator does not require preserving `]b}c` after a credential label. Documentation acknowledges this disclosure; it does not prevent it.

**Smallest correct change:** make quote termination escape-aware, including the supported JSON wrapping; distinguish recognizable sibling fields from ambiguous credential continuations. Where parsing is uncertain, redact the ambiguous span or omit the record with an explicit diagnostic rather than exporting credential fragments.

**Quadratic fix — DISAGREE_EVIDENCE on coverage; AGREE that it fixes the demonstrated performance problem. Blocking as part of redaction.**

The anchor and bounded search remove the reported long-identifier blowup. However, [scripts/redact_log_bundle.py:142](C:/Users/Jonathan/Projects/ta-logs/scripts/redact_log_bundle.py:142) introduces silent exclusions. Both probes survive unchanged:

```python
"x" * 41 + "password=LONG_PREFIX_SECRET"
"password" + "x" * 41 + "=LONG_SUFFIX_SECRET"
```

The prefix case also contradicts the stated superset relationship: the canonical provider expression finds `password=` inside that identifier.

**Smallest correct change:** scan each complete identifier once, then classify its name for credential keywords. This preserves linear work without imposing an undocumented key-length exclusion.

**§5 lazy reader — DISAGREE_EVIDENCE. Blocking.**

The sliding tail fixes whole-query retention, but the subprocess lifecycle regresses the timeout:

- [scripts/backup_log_tier.py:149](C:/Users/Jonathan/Projects/ta-logs/scripts/backup_log_tier.py:149) blocks awaiting stdout **before** checking the deadline.
- [scripts/backup_log_tier.py:161](C:/Users/Jonathan/Projects/ta-logs/scripts/backup_log_tier.py:161) reads stderr to EOF **before** the timed wait. Undrained stderr can also block the child while stdout consumption waits.
- [scripts/backup_log_tier.py:238](C:/Users/Jonathan/Projects/ta-logs/scripts/backup_log_tier.py:238) returns after a read error without terminating or reaping the child.

With `timeout=1`, real Python children sleeping two seconds produced:

```text
silent stdout:           2.03s → (0, 'empty')
stdout closed first:     2.03s → (0, 'empty')
one line, then stall:    2.03s → (1, 'ok')
```

A simulated mid-read `OSError` returned `error:OSError` while its real child remained running. I terminated that probe child afterward.

Memory also remains dependent on the largest raw line and total stderr. A two-million-character record with a 1-KiB budget peaked at **4,286,837 Python-allocated bytes** before truncation.

**Smallest correct change:** enforce the deadline independently of blocking reads, drain both pipes with bounded buffers, cap raw-record buffering before materialization, and always close, terminate when necessary, and reap the child in cleanup.

The tail arithmetic itself does not accumulate drift, but [line 223](C:/Users/Jonathan/Projects/ta-logs/scripts/backup_log_tier.py:223) slices characters rather than bytes. A 100-byte budget with emoji input wrote **221 bytes**, reported `ok`, and escaped eviction because one record remained. **Follow-up:** truncate by encoded byte budget, reserve marker space, and set the truncation status. This does not independently block the default 64-MiB configuration.

**Follow-ups:**

- **Stale byte-only comment — DISAGREE_EVIDENCE, non-blocking.** It survives at [deploy/install-host-uptime-services.sh:670](C:/Users/Jonathan/Projects/ta-logs/deploy/install-host-uptime-services.sh:670): “the gate compares bytes on disk, so a failed restart still reads as converged.” Line 619 also incorrectly says restarts occur only when bytes change.
- **`MAX_LINE_CHARS` documentation — AGREE.** It now correctly states that redaction precedes truncation.
- **Manual-interruption temporary-file cleanup — AGREE to defer.** The scheduled unit still has `PrivateTmp=yes`; the remaining manual-invocation gap does not block landing.
- **Rate-limit calibration — AGREE to defer.** No new evidence justifies reopening the cleared configuration.
- **1-GiB capacity choice — AGREE to defer.** It remains an acknowledged, unvalidated capacity choice rather than a minimum-retention guarantee.

## Verdict

**ADAPT**

**Blocks part 2 landing:**

1. Credential disclosure through escaped/nested quotes, ambiguous bare values, and the new key-length exclusions.
2. Ineffective subprocess deadlines, incomplete child cleanup, and unbounded raw-line/stderr buffering.

**Accepted follow-ups:** pre-existing active masks, small-budget UTF-8 truncation/status, stale comments, manual cleanup, and retention/rate calibration.

**Part 1 remains cleared.** These unresolved blockers go to the founder; I am not requesting a fourth review round.