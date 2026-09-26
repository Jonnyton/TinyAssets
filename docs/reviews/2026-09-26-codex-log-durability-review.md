Reviewed `f79a7fda` on 2026-09-26 in this Windows worktree. No edits, agents, or pytest runs. Used read-only inspection and in-memory Python/Bash probes.

1. **AGREE** — `deploy/compose.yml:231` fixes the container name; Docker records `CONTAINER_NAME` independently of `tag`, so the query spans retained generations started under that name. Host networking and the Slack profile do not change this; pre-migration logs remain absent. [Docker documentation](https://docs.docker.com/engine/logging/drivers/journald/).

2. **DISAGREE_EVIDENCE** — **The split is self-contained, but installer convergence is false.** `.github/workflows/deploy-prod.yml:229` ships Compose from the checkout; line 342 ships the validator, and line 347 executes that `/tmp` copy. The installer manifest includes the drop-in, and `.github/workflows/install-host-services.yml:358` archives that manifest. No part-2 dependency found.

   However, `deploy/install-host-uptime-services.sh:568` tolerates a failed journald restart and marks installation successful. The next invocation checks only drop-in bytes/metadata at line 352, then exits at line 375. Sequence: install new policy → restart fails → subsequent installs report convergence indefinitely without applying it. The comment promising another attempt is contradicted by the code. This defect exists in part 1.

3. **DISAGREE_EVIDENCE** — `deploy/install-host-uptime-services.sh:346` checks only whether each retired unit’s file exists under `SYSTEMD_DIR`; line 496 also skips removal when that file is absent.

   Sequence: an enabled, loaded timer loses its unit file before being stopped/reloaded → its enablement symlink and systemd-loaded state remain → the otherwise-converged installer exits without inspecting or stopping it. A unit supplied from `/run/systemd/system` likewise escapes. Dangling symlinks also evade `-e`. Retirement needs to reconcile loaded/active/enabled state and symlinks, not merely the main file.

   The explicit `not-found` branch avoids `disable --now`; I did not establish a masked-unit abort. Permanent retirement without rollback is defensible as an intentional decommission, but that does not repair this incomplete convergence check.

4. **DISAGREE_EVIDENCE** — **Credentials survive the actual collection path.** `deploy/vector.yaml:75` uses JSON encoding; `scripts/redact_log_bundle.py:56` does not recognize escaped JSON field delimiters. Feeding `collect_source()` this Vector-shaped record returned status `ok` and preserved the entire credential in the file subsequently archived:

   ```text
   {"log": "{\"api_key\": \"opaquevalue123456\"}"}
   ```

   Additional reproduced failures:

   - `password=alpha,beta;gamma&delta` becomes `password=[redacted],beta;gamma&delta` because of line 58’s terminators. The canonical provider regex removes the whole value.
   - `prefix_sk-abcdefghijkl` survives because line 63 adds a word boundary absent from the canonical regex.
   - `--password opaquevalue123456`, an unlabeled base64-encoded secret, and a token split across records survive.

   `tests/test_backup_log_tier.py:144` only asserts that each selected input **changed**. Partial credential disclosure passes that assertion. Redacting before truncation at `scripts/redact_log_bundle.py:92` is correctly ordered, but does not fix escaped JSON or cross-record secrets.

5. **DISAGREE_EVIDENCE** — **Best-effort exit handling does not isolate resource consumption or elapsed time.** `scripts/backup_log_tier.py:113` captures the entire journal output without a timeout; line 128 allocates its split lines before the byte budget is enforced. The advertised 64 MiB limit does not bound journal output or memory.

   Sequence: slow journal query → backup remains inside section 4b → `deploy/tinyassets-backup.service:31` reaches its 30-minute timeout → systemd terminates the backup before the GitHub state uploads at `deploy/backup.sh:253`. A large query also creates host memory pressure. The additional rclone upload precedes those uploads too.

   Normal failure paths reach cleanup, but interruption before line 269 bypasses tarball removal; the EXIT trap at line 122 only removes `BRAIN_STAGE`. Manual invocation can leave archives in `/tmp`.

   **`PIPESTATUS[0]` is correct here.** The immediate assignment preserves Python’s status; a Bash probe returned `3` without aborting.

6. **DISAGREE_EVIDENCE** — **45 is correct for three nightly releases; ownership filtering is not exact.** `scripts/backup_ship_gh.py:352` accepts every matching prefix. It therefore prunes `tinyassets-logs-manual`, explicitly created and shipped by `docs/ops/log-aggregation-runbook.md:204`, despite line 229 claiming names outside the digit-based pattern are ignored by both pruners.

   `scripts/backup_prune.py:35` also accepts arbitrary digit-prefixed names. An in-memory probe with normal retention settings selected `tinyassets-logs-1-forensics-hold.tar.gz` for deletion. Neither implementation restricts deletion to the generated timestamp grammar. Also, 45 preserves 15 nights only at three releases per night without an overriding `BACKUP_GH_RETAIN`.

7. **DISAGREE_EVIDENCE** — `deploy/journald-tinyassets.conf:24` falsely claims the time setting prevents a noisy hour from reducing retention to minutes. `MaxRetentionSec=14day` is a **maximum age**, not a minimum retention guarantee; the byte/free-space limits can evict entries earlier. At 100 KiB/s of stored journal growth, 1 GiB represents roughly three hours, before accounting for other host logs. Nightly export cannot recover already-evicted evidence. [systemd configuration semantics](https://github.com/systemd/systemd/blob/v255/man/journald.conf.xml).

   Lines 46–47 disable rate limiting globally. Disk capacity limits do not bound compression CPU or write throughput, and `scripts/disk_watch.py:52` measures disk occupancy. Host degradation during a storm is a risk, not an outage I reproduced. There is no implemented Docker volume-rate limit supporting the comment at line 44.

8. **AGREE** — Vector’s journald source invokes `journalctl`; the [v0.40.0 Alpine Dockerfile](https://github.com/vectordotdev/vector/blob/v0.40.0/distribution/docker/alpine/Dockerfile) installs only certificates/timezone packages alongside Vector, consistent with the [documented subprocess requirement](https://vector.dev/docs/reference/configuration/sources/journald/#communication-strategy). Keeping this gap open is justified.

## Verdict

**ADAPT**

**Blocks landing:**

- **Part 1:** make failed journald policy application retryable; retain finite storm protection and correct the retention guarantee.
- **Part 2:** fix escaped JSON and partial-value redaction; assert credential absence, including in extracted archive contents.
- **Part 2:** stream collection with hard resource/time bounds, ship state before logs, and clean archives on interruption.
- **Part 2:** reconcile retired units’ systemd state and symlinks.
- **Part 2:** restrict pruning to explicitly owned archive/tag formats; define manual-bundle retention consistently.

**Notes:**

- The validator/Compose split itself holds.
- Byte-limited collection currently keeps the **oldest** portion of the window (`scripts/backup_log_tier.py:128`), discarding recent incident evidence first.
- The retirement rationale that fluentd makes `docker logs` impossible is false as a general statement: Docker enables a readable local cache by default. Verify cache configuration before repeating that claim. [Docker dual logging](https://docs.docker.com/engine/logging/dual-logging/).