Reviewed the pinned heads on 2026-09-26 in the Windows worktree. No edits or delegation. Ran only:

`python -B -m pytest -q -p no:cacheprovider tests/test_backup_log_tier.py tests/test_log_aggregation.py`

**100 passed.** Additional in-memory probes exposed gaps those tests miss.

**§2 — AGREE.** The applied-stamp fixes the reported failed-restart convergence bug. A failed restart removes the stamp; missing or mismatched stamps force another attempt even when the drop-in bytes already match. A failed stamp write normally causes redundant retries rather than false convergence. Acceptable follow-up: the comment at `deploy/install-host-uptime-services.sh:628` still describes the old byte-only gate, and restart failure does not necessarily mean journald remains running with its previous configuration.

**§3 — DISAGREE_EVIDENCE. Landing blocker.** Runtime-provided units are detected but still not retired.

At `deploy/install-host-uptime-services.sh:559`, removal targets only `${SYSTEMD_DIR}/${unit}`, normally `/etc/systemd/system`. The subsequent search at line 568 has the same root.

Concrete sequence: a regular retired unit exists under `/run/systemd/system` → the predicate sees `LoadState=loaded` → `disable --now` stops/disables it but does not delete its regular unit file → the installer removes nothing under `/run` → `daemon-reload` leaves the unit loadable → the next invocation fails the same convergence predicate and repeats the transaction. This remains the runtime-unit case identified in round 1.

Separately, the `find` expression matches **every non-directory with that basename**, not specifically enablement symlinks. It can delete a regular saved copy in a nested directory. Tightening that scope is a follow-up. The extra reload itself is reasonably placed while managed timers remain paused.

**§4 — DISAGREE_EVIDENCE. Landing blocker.** Partial credential disclosure remains at `scripts/redact_log_bundle.py:102`.

Reproduced through `collect_source()`, returning `(1, 'ok')`:

```text
{"log": "{\"password\": \"alpha beta gamma\", \"status\": 503}"}
→
{"log": "{\"password\": \"[redacted] beta gamma\", \"status\": 503}"}
```

Also:

```text
password=alpha]beta}gamma
→
password=[redacted]]beta}gamma
```

Whitespace and closing brackets/braces are legitimate password characters. Recognizing quoted values without respecting their closing delimiter still exports credential fragments.

The optional separator and newly added `auth` matching also destroy ordinary evidence:

```text
authentication succeeded → authentication [redacted]
authorization failed     → authorization [redacted]
```

Both authentication outcomes disappear. `password=alpha,elapsed=17,status=503` also loses both diagnostic fields. The new over-redaction tests contain no credential-adjacent context, so they do not exercise this ambiguity.

The canonical test now checks that the specified secret value is absent. That change is present, but absence of the **whole original value** alone cannot detect partial disclosure; assertions on distinctive surviving fragments are still necessary.

Accepted limitations: arbitrary unlabelled blobs and arbitrary cross-record reconstruction remain defensible exclusions. The `MAX_LINE_CHARS` limitation is inaccurately documented: lines 140–143 redact the **entire input before truncating**. A 10,000-character labelled value was fully redacted in my probe; that case is already handled.

**§5 — DISAGREE_EVIDENCE. Landing blocker: memory bounds remain incomplete.**

`scripts/backup_log_tier.py:142` still captures the entire output; line 163 creates another full collection with `splitlines()`. `--lines=50000` limits **records**, not their byte size. For example, 50,000 printable 16-KiB records yield roughly 781 MiB before decoding, splitting and redaction allocations. The 64-MiB budget applies afterward. Systemd’s full-width short output does not impose the needed small per-record bound. See [journalctl implementation](https://github.com/systemd/systemd/blob/v255/src/journal/journalctl.c) and [short-output implementation](https://github.com/systemd/systemd/blob/v255/src/shared/logs-show.c).

The ordering fix is correct: log collection cannot delay the preceding state-upload attempts. Those attempts can fail independently, so “already shipped” is stronger than the code guarantees. The timeout handling and newest-first selection followed by chronological output are correct. `--lines` works appropriately with `--since`; it just does not replace a byte-bounded collection path.

**Cleanup is now an acceptable follow-up, not a landing blocker.** Manual interruption still leaves archives: `deploy/backup.sh:122` cleans only `BRAIN_STAGE`, while archive removal occurs at line 286. However, the scheduled unit uses `PrivateTmp=yes`, whose temporary files are removed when the service stops. That materially narrows the remaining exposure. [Systemd cleanup semantics](https://github.com/systemd/systemd/blob/v255/man/systemd.exec.xml).

**§6 — AGREE.** Generated timestamp names match both pruners; the forensic-hold and new manual names match neither. In-memory checks confirmed those results. `is_prunable_tag()` preserves existing state-tier prefix behavior. Leaving legacy state patterns unchanged is defensible within this fix’s scope.

**§7 — AGREE.** The false minimum-retention promise is removed and finite rate limiting is restored. I found no evidence that this setting drops normal daemon output.

Acceptable follow-ups: 100,000/30 seconds is a base per-service allowance, not a strict global 3,300/s ceiling; systemd multiplies it according to available disk space. Also, a manifest line count does not establish elapsed coverage. One GiB remains an unvalidated capacity choice for three days, but that limitation is now acknowledged rather than promised away. [Systemd rate-limit semantics](https://github.com/systemd/systemd/blob/v255/man/journald.conf.xml).

**`docker logs` note — AGREE.** The withdrawal is explicit. Retiring an unconfigured duplicate shipper in favor of the existing authenticated backup destination is sufficient justification independently of Docker cache behavior.

## Verdict

**ADAPT**

**Part 1 has no remaining landing blocker from this review. Part 2 still blocks on:**

- Complete labelled-value redaction, including quoted passphrases, while preserving authentication outcomes.
- A byte/memory-bounded collection path before whole-output allocation.
- Retirement that actually converges for runtime-provided units.

Manual-interruption cleanup, narrower `find` ownership, stale comments, and retention/rate calibration are acceptable follow-ups.