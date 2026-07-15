# Audit: old `workflow-data` docker volume (19 GB) — 2026-07-15

**Status:** audit complete; volume untouched (read-only inspection only). Deletion stays gated on the host decisions in §5.
**Auditor:** claude-code (live droplet inspection 2026-07-15 ~01:1x UTC); Codex cross-family review of this doc's recommendations logged in the landing PR.
**Context:** STATUS concern [filed:2026-07-13 verified:2026-07-14]. The Jun-27 rename migration created `tinyassets-data` as an effectively fresh volume; only the wiki was later restored (2026-07-13). This audit inventories everything else left behind.

## 1. Ground facts

- **No container mounts `workflow-data`** — verified via `docker inspect` across all containers. Nothing writes to it; content is frozen at 2026-06-27 05:29 (the migration moment). The only later mtimes are `.codex` sqlite WALs touched by read-only auth probes (Jul 13–15 sessions).
- **Wiki parity confirmed:** 1,484 `.md` files on old volume == 1,484 on live volume. The 2026-07-13 restore was complete; the wiki needs nothing further from this volume.
- **~18 of the 19 GB is machine state, not content** (breakdown below).

## 2. Inventory

| Item | Size | What it is | In current volume? | Class |
|---|---|---|---|---|
| `concordance/` | 6.6G | Universe. `checkpoints.db` 6.5G; **`output/` holds book-1 … book-18+** (authored novels), `artifacts/` 31M, `knowledge.db` 2.5M, `notes.json` 1.2M | no | content + state |
| `workflow-voice/` | 4.5G | Universe. `checkpoints.db` 4.5G; `artifacts/` 17M, `knowledge.db` 3.8M, `story.db` 2.6M, `notes.json` 1.4M | no | content + state |
| `team-standup-action-tracker/` | 1.8G | Universe. `checkpoints.db` 1.6G; `artifacts/` 191M, `canon/` 396K | no | content + state |
| `local-bubble-galactic-survival-model/` | 1.5G | Universe. `checkpoints.db` 1.3G; `artifacts/` 142M, `canon/` 2M | no | content + state |
| `echoes-of-the-cosmos/` | 574M | Universe. `checkpoints.db` 455M; `artifacts/` 61M, **`canon/` 59M** | no | content + state |
| `meridian-ashes/` | 307M | Universe. `checkpoints.db` 280M; `artifacts/` 26M, `canon/` 416K | no | content + state |
| `earthos/` | 15M | Universe (small) | no | content + state |
| `patch-loop-live/` | 9.4M | Universe; was `.active_universe` at migration. `branch_tasks.json` 8.5M, **own 4-page wiki** (not in main wiki) | no | content |
| `tiny/`, `grandma-bread-recipe/` | ~1.6M | Small universes (canon, notes, worldbuild signals) | no | content |
| `.langgraph_runs.db` | 1.98G | Run history (subsystem still live: `tinyassets/runs.py`; regenerates fresh) | fresh/empty | state |
| `.runs.db` | 1.17G | Run history (live volume has fresh 287K one) | fresh | state |
| `ledger.json` | 276K | **Platform action/provenance history since 2026-04-20** (goals.propose, build_branch, …). Live volume has a 193-byte stub | stub only | content |
| `.claude/` | 352M | Pre-rename worker Claude config: sessions, session-env, backups, shell-snapshots, mcp auth cache | superseded (fresh `.claude` live) | **credential-class** |
| `.codex/` | 90M | Pre-rename Codex home: the dead token (verified 401 2026-07-14) + state DBs | superseded (fresh login 2026-07-15) | **credential-class** |
| `daemon_wikis/` | 33M | Per-daemon wiki (`daemon-workflow-developer-…/WIKI.md`, claim_proofs). Subsystem live: `tinyassets/daemon_wiki.py` | no | content |
| `daemon_brain.db` | 84K | Daemon brain (subsystem live: `api/status.py`, `api/universe.py`) | no | content |
| `.workflow.db` (+bak), `.project_memory.db`, `.effector_consents.db`, `.external_write_receipts.db`, `wiki_trigger_attempts.db`, `.auth.db` | ~3.7M | Small state DBs; every subsystem still live in code and regenerates on the new volume. Old effector-consent + external-write-receipt rows are historical provenance | fresh equivalents | mixed |
| `community-pool/` | 24K | Near-empty scaffold. NOTE: current workers set `TINYASSETS_REPO_ROOT=/data/community-pool` but the live volume has NO such dir — community-pool posting paths will error `repo_root_not_resolvable` (loud, non-crashing; `api/universe.py:_repo_root`) | **missing entirely** | side-finding |
| `wiki/` | 13M | Already fully restored (1,484 == 1,484) | yes | migrated |
| `release-state.json`, `.active_universe` (+baks) | <8K | Deploy/runtime pointers, superseded | fresh | state |

## 3. What is irreplaceable vs regenerable

- **Irreplaceable (~0.5–1 GB total):** universe content — `output/` (the concordance books!), `canon/`, `artifacts/`, `notes.json`, `knowledge.db`, `story.db`, `activity.log`, `branch_tasks.json`, per-universe wikis/ledgers; top-level `ledger.json` history; `daemon_wikis/`; `daemon_brain.db`; effector-consent / external-write-receipt history.
- **Regenerable / format-dead (~18 GB):** every `checkpoints.db(-wal/-shm)` (pre-rename LangGraph resume state — current code will not resume pre-rename runs; no-shims rule), `.langgraph_runs.db`, `.runs.db`, `.workflow.db`, `.auth.db`, caches.
- **Credential-class (must NOT go into an archive):** `.claude/` (sessions + session-env + auth caches), `.codex/` (dead token). Both superseded by fresh live equivalents.

## 4. Recommendation — EXECUTED 2026-07-15 ~01:37Z

1. **Archive the content, skip the state.** ✅ DONE: `/root/volume-content-archive-workflow-data-2026-07-15.tar.gz` — 28,118,826 bytes (128,822 entries, 168 MB uncompressed; the audit's "<1 GB" estimate was `du` block-overhead on ~104k tiny artifact files), sha256 `0c9a248a70c1e8a2499ca5a3943f05675c862f83c1d5a7b583253cd64306c94e`. Two deviations from the original exclusion list, both toward caution: `.workflow.db*` **kept** (~3.5 MB insurance for the pending Phase-6 `.workflow.db`/`db_path()` migration row), `.auth.db` **excluded** (credential-class OAuth DB, superseded). Also excluded as planned: `checkpoints.db*`, `.langgraph_runs.db*`, `.runs.db*`, `.claude/`, `.codex/`, `.tmp/`.
   Off-droplet copy ✅: GH release asset `volume-content-archive-workflow-data-2026-07-15` in private `Jonnyton/tinyassets-backups` (verified 28,118,826 bytes; tag is non-prunable under the `PRUNABLE_TAG_PREFIXES` scoping fix landed with this PR).
2. **Verify the archive.** ✅ DONE: exclusion greps all zero; key-content greps non-zero (139 concordance `output/` files, notes.json ×10, daemon_wikis ×7,800, ledger.json ×11, `.workflow.db` ×5); spot-extract of `concordance/output/book-1/chapter-01/scene-01.md` (9,884 bytes) reads back clean prose.
3. **Deleting the volume is now safe pending §5** — frees ~19 GB; nothing mounts it; wiki already restored; credentials superseded; content archived + offsite.

## 5. Host decisions

- **D3 — deletion: EXECUTED 2026-07-15 ~01:55Z on explicit host directive.** Pre-deletion checks: local archive `gzip -t` OK; offsite GH asset downloaded back and sha256-compared — byte-identical (`0c9a248a…`); zero mounts. `docker volume rm workflow-data` freed ~18 GB (droplet disk 33G→15G used). D1/D2 were deliberately NOT foreclosed: the archive carries the full ledger history and all universe content, so both remain executable from the archive at any time.
- **D1 — ledger history: EXECUTED 2026-07-15 ~01:55Z on host directive.** Old ledger (1,357 entries, Apr-20 → Jun-26) extracted from the archive and merged ahead of the live ledger's entries (disjoint time ranges asserted; atomic tmp+replace with a mid-merge concurrent-write guard; ownership preserved). Live ledger now 1,358 entries; parse re-verified from inside the daemon container. Pre-merge rollback copy: droplet `/root/ledger-merge/live-pre-merge-backup.json`.
- **D2 — universe revival: `concordance` REVIVED 2026-07-15 ~02:0xZ on host directive.** Extracted from the archive to the live volume (37 MB content-only, chowned to container uid 1001; no collision; archived task queue held only 3 `succeeded` rows — nothing resumable; dispatcher only polls the active universe, so the dormant dir is inert). Live-verified via anonymous public MCP `read_graph target=graphs`: listed with `has_premise: true`, `word_count: 52,187`, `phase_human: paused`, `staleness: dormant`. `echoes-of-the-cosmos` (120 MB; 6,875 canon .md files confirmed on disk; word_count 0 is expected — it never reached prose, see BUG-039) and `workflow-voice` (26 MB, 47,910 words) REVIVED the same way 2026-07-15 ~02:1xZ; all three live-listed dormant via public MCP. ⚠ workflow-voice's restored queue carries 3 month-old `pending` rows — restored VERBATIM (inert while dormant; dispatcher polls the active universe only). Review/cancel them before ever making workflow-voice the active universe, or they will be claimed and executed. The seven smaller universes remain archive-only, revivable on request.

## 6. Side-findings

- `TINYASSETS_REPO_ROOT=/data/community-pool` points at a nonexistent dir on the live volume (§2). Smallest fix: `mkdir` the scaffold on the live volume (or drop the env override so it falls back to the checkout). Filed as a STATUS Work row.
- Backup lane RESTORED later the same session (2026-07-15 ~01:27Z, after this audit's inspection pass): nightly `tinyassets-backup.timer` (03:00 UTC) live on the droplet; two-tier local (`/var/backups/tinyassets`, retention 3/2/2) + GitHub-release offsite (`Jonnyton/tinyassets-backups`, renamed from `workflow-backups`, keep 30); proven green end-to-end including the retention prune (which live-exposed and fixed the `backup_ship_gh.py` 204 empty-body crash — same landing PR). §4.1's "download a copy off-droplet" advice for the pre-deletion archive stands.
