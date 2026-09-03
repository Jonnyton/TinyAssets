# Cross-family review: a universe needs an owner, and a prune cuts

**Branch** `claude/universe-list-is-a-directory-listing` (PR #2779).
**Reviewer** Codex (`gpt-5.6-sol`), three rounds, dispatched on its own budget
through `scripts/peer_agent.py`. **Author** Claude Opus 5.

Three rounds is the cap (`AGENTS.md` § Quality Gates), so what round 3 raised is
folded here and anything left is named at the end rather than taken into a
fourth round.

Every round returned **REJECT**, and every round was right about something that
would have destroyed data:

| Round | Finding that mattered most |
|---|---|
| 1 | The infrastructure allowlist was incomplete and could not be made complete — five live stores were missing, including daemon memory and the brain's vector store. |
| 2 | `_backup` as a universe signal would have cut the migration backup `docs/host-actions.md` says not to delete; the ownership read and the delete were not atomic. |
| 3 | `reset(confirm=True)` still destroyed that same backup, because the prune had learned the difference and the reset had not. |

The full transcripts follow, unedited.


## Round 1

```
Review basis: `git diff origin/main...HEAD`. The permitted focused test passed: `16 passed in 1.06s`.

- P0 — `DISAGREE_EVIDENCE` — The infrastructure allowlist is incomplete. `HEAD:tinyassets/universe_prune.py:32` protects only `lance`, `output`, `runs`, and `wiki`, while default `--apply` deletes every directory classified removable (`HEAD:scripts/prune_unowned_universe_dirs.py:69,110`). Live unowned platform stores include:

  - `cloud-automation-inputs`, containing retained user specifications (`tinyassets/storage/cloud_automation_inputs.py:32-56`)
  - `daemon_wikis`, containing daemon memory (`tinyassets/daemon_wiki.py:30-32,308-324`)
  - `founder_offers` (`HEAD:tinyassets/api/universe.py:6442-6448`)
  - `lancedb`, notably different from protected `lance` (`tinyassets/daemon_brain.py:813-841`)
  - `scratch`, created for workspace execution (`tinyassets/runs.py:487-497`)

  A routine `python scripts/prune_unowned_universe_dirs.py --apply` can therefore erase user inputs, daemon memory, offers, and vector indexes. Worse, the focused test explicitly treats `scratch` as garbage and requires its deletion (`HEAD:tests/test_a_universe_needs_an_owner.py:238-248`).

- P0 — `DISAGREE_EVIDENCE` — The ownership read is genuinely inside the loop and per-directory, but it is not atomic with creation or deletion. Explicit creation makes and seeds the directory at `HEAD:tinyassets/api/universe.py:5878-5890`, then performs registry and visibility work, and only grants ownership at `:5971-5977`. Concurrent prune can query no owners at `HEAD:tinyassets/universe_prune.py:166`, delete at `:178`, and let creation subsequently write the ACL and return `"created"` for a directory that no longer exists. A grant landing between lines 166 and 178 is also too late because the result is already stale. First contact avoids this particular window by claiming `founder_home` before materialization (`tinyassets/api/first_contact.py:56`), but explicit later creation does not.

- P1 — `DISAGREE_EVIDENCE` — Filesystem aliases can bypass both infrastructure and ownership checks on Windows. The code compares the caller-supplied name case-sensitively against the allowlist at `HEAD:tinyassets/universe_prune.py:152`, queries ownership using that raw spelling at `:166`, but only verifies the resolved path’s parent at `:159`. On this Windows worktree, `WIKI`, `wiki.`, and `wiki ` all resolve to the same directory as `wiki`. Thus direct `prune(base, names=["WIKI"], apply=True)` can delete protected `wiki`; similarly, a restored `U-Mine` directory with ACL id `u-mine` is classified unowned and removed. The path test covers separators and dot names but no case, trailing-dot/space, or normalization aliases (`HEAD:tests/test_a_universe_needs_an_owner.py:219-228`).

- P1 — `DISAGREE_EVIDENCE` — The new universe definition is not used by the other default resolvers. `_default_universe` still returns the first non-hidden directory (`tinyassets/api/helpers.py:82-85`), and `_designated_public_universe` returns the first non-serial directory (`:135-143`). With `cloud-automation-inputs` or `daemon_wikis` sorting first, an anonymous request—or an authenticated user lacking a home/create scope—can be routed into an operational store as though it were a universe. Missing-universe responses also continue enumerating every top-level directory (`HEAD:tinyassets/api/universe.py:1821-1827,5793-5799`).

- P2 — `DISAGREE_CONCERN` — The focused test does not prove the advertised per-directory freshness. It grants ownership before calling `prune` (`HEAD:tests/test_a_universe_needs_an_owner.py:206-212`), so an implementation that snapshots all ownership once at function entry would still pass. It needs a two-directory interleaving where the second directory gains an owner after prune begins. Also, its listing assertions run under an autouse monkeypatch replacing the real visibility resolver (`HEAD:tests/conftest.py:175-219`), so the listing test stubs part of the listing path and can pass without exercising production’s strict visibility behavior.

`AGREE`: static symlinks or junctions resolving outside the data root are rejected by the resolved-parent check, and the ownership query is located per iteration immediately before deletion. Those protections do not address the P0 lifecycle race or the Windows alias cases above.

VERDICT: REJECT```

## Round 2

```
- P0 — `DISAGREE_EVIDENCE` — [universe_prune.py:253](/C:/Users/Jonathan/Projects/wf-universe-list-is-a-directory-listing/tinyassets/universe_prune.py:253): ownership is read, then the signal is inspected, then `rmtree` runs at line 283 without excluding a concurrent grant. A restored universe can be granted after line 253 and still be deleted. The freshness test only grants the *next* directory after the first removal ([test_a_universe_needs_an_owner.py:418](/C:/Users/Jonathan/Projects/wf-universe-list-is-a-directory-listing/tests/test_a_universe_needs_an_owner.py:418)); it does not exercise the same-directory race.

- P0 — `DISAGREE_EVIDENCE` — [universe_prune.py:70](/C:/Users/Jonathan/Projects/wf-universe-list-is-a-directory-listing/tinyassets/universe_prune.py:70): `_backup_subject_migration_20260829T055340Z` is a real production migration backup, not a universe, but `_backup` alone classifies it as one. The default `--apply` selects every such report ([prune_unowned_universe_dirs.py:69](/C:/Users/Jonathan/Projects/wf-universe-list-is-a-directory-listing/scripts/prune_unowned_universe_dirs.py:69)) and deletes it. Durable state explicitly says not to delete these backups pending the founder’s decision ([docs/host-actions.md:31](/C:/Users/Jonathan/Projects/wf-universe-list-is-a-directory-listing/docs/host-actions.md:31)). This is the requested real non-universe with a positive signal.

- P0 — `DISAGREE_EVIDENCE` — [reset.py:73](/C:/Users/Jonathan/Projects/wf-universe-list-is-a-directory-listing/tinyassets/reset.py:73): the allowlist remains a destructive safety property for reset, and it still omits `community-pool`. Production config identifies `/data/community-pool` as a load-bearing durable root ([deploy/compose.yml:107](/C:/Users/Jonathan/Projects/wf-universe-list-is-a-directory-listing/deploy/compose.yml:107)); `reset(confirm=True)` includes and recursively removes every unlisted directory at lines 84–89 and 127–128.

- P1 — `DISAGREE_EVIDENCE` — [universe.py:1817](/C:/Users/Jonathan/Projects/wf-universe-list-is-a-directory-listing/tinyassets/api/universe.py:1817): direct-ID readers still define a universe by `udir.is_dir()`. Enumeration now filters by ownership, but `read_graph target="graph" graph_id="cloud-automation-inputs"` and the migration-backup ID still return graph payloads; I reproduced both anonymously against production on 2026-09-02. `switch_universe` has the same directory-only check at [universe.py:5792](/C:/Users/Jonathan/Projects/wf-universe-list-is-a-directory-listing/tinyassets/api/universe.py:5792).

- P1 — `DISAGREE_EVIDENCE` — [helpers.py:73](/C:/Users/Jonathan/Projects/wf-universe-list-is-a-directory-listing/tinyassets/api/helpers.py:73): `_default_universe` checks ownership only in its final directory scan; `.active_universe` and `UNIVERSE_SERVER_DEFAULT_UNIVERSE` return first without ownership validation. `_designated_public_universe` likewise returns the environment value at [helpers.py:142](/C:/Users/Jonathan/Projects/wf-universe-list-is-a-directory-listing/tinyassets/api/helpers.py:142). A stale marker or configured default naming `scratch` therefore still routes requests into an operational directory.

- P1 — `DISAGREE_EVIDENCE` — [universe.py:1743](/C:/Users/Jonathan/Projects/wf-universe-list-is-a-directory-listing/tinyassets/api/universe.py:1743): the Windows case-fold repair exists only in prune. Listing and both default resolvers use exact `child.name in owned` comparisons. A restored `U-Mine` directory with ACL ID `u-mine` is protected from pruning but disappears from listings and cannot become the default.

- P1 — `DISAGREE_EVIDENCE` — [universe.py:6019](/C:/Users/Jonathan/Projects/wf-universe-list-is-a-directory-listing/tinyassets/api/universe.py:6019): rollback failure is swallowed. If creation encounters an `OSError` after granting and revocation then fails—for example, disk failure followed by a locked/unavailable ACL database—the function returns the original error envelope at line 6026 while leaving the ACL row. Concurrent same-ID creates are worse because `mkdir(exist_ok=True)` is non-exclusive and one rollback can remove the other call’s directory and grant.

- P2 — `DISAGREE_EVIDENCE` — [test_api_helpers.py:92](/C:/Users/Jonathan/Projects/wf-universe-list-is-a-directory-listing/tests/test_api_helpers.py:92): the environment and active-marker tests still assert unowned IDs as valid defaults, so both pass against the unfixed resolver. The infrastructure scanner only recognizes literal `data_dir() / "name"` expressions inside `tinyassets` ([test_a_universe_needs_an_owner.py:301](/C:/Users/Jonathan/Projects/wf-universe-list-is-a-directory-listing/tests/test_a_universe_needs_an_owner.py:301)), which is why the environment-derived `community-pool` omission remains green. The create-race test merely compares source-text order at line 454 and exercises neither rollback nor concurrency. The focused run passed: 64 tests on Windows/Python 3.14.3.

I could not substantiate a markerless former production universe from the public surface, so I am not claiming one; `u-01m160…` exposes no soul, premise, activity, or checkpoint bytes, but that does not prove absence of every listed marker.

VERDICT: REJECT```

## Round 3

```
Not landable. The round-2 fixes resolve the named prune races, but one P0 data-loss path remains.

- **P0 — DISAGREE_EVIDENCE — `tinyassets/reset.py:84`, `tinyassets/reset.py:127`.** `reset(confirm=True)` still classifies every non-hidden, non-infrastructure directory as disposable and calls `rmtree`. Therefore `_backup_subject_migration_20260829T055340Z`—which `docs/host-actions.md:34` explicitly says not to delete—is destroyed. The regression test at `tests/test_a_universe_needs_an_owner.py:273` proves only that `prune()` preserves the backup; it never exercises `reset()`.

- **P1 — DISAGREE_EVIDENCE — `tinyassets/universe_prune.py:304`, `tinyassets/universe_prune.py:310`, `tinyassets/universe_prune.py:192`.** A crash after `target.rename(staged)` but before restoration or deletion leaves `.pruning-*` permanently hidden from `plan()`, subsequent prunes, reset, universe listing, and filesystem sync. If ownership landed before the crash, its ACL now points at a missing original path. Moreover, `tinyassets/api/branches.py:915` still enumerates all directories and can report the staged universe as a branch dependent, while `tinyassets/api/branches.py:3779` can select it as the fallback universe.

- **P1 — DISAGREE_EVIDENCE — `tinyassets/api/universe.py:1848`.** `_available_universe_ids()` filters by ownership but not `discover_existence`. A signed-in caller can inspect a known registered operational directory such as `scratch`; the handler refuses it but returns IDs of every owned private or unlisted universe. This bypasses the visibility filtering correctly applied at `tinyassets/api/universe.py:1779`.

- **P1 — DISAGREE_EVIDENCE — `tinyassets/api/universe.py:1824`.** An ownership-store failure is converted into `Universe '<id>' not found`. A transient SQLite lock or unreadable ACL during the handler’s second lookup therefore reports that an existing universe does not exist. Logging server-side while returning a false 404 violates “fail loudly.”

- **P1 — DISAGREE_EVIDENCE — `tinyassets/api/universe.py:6066`.** The revoke failure is appended only when the original creation exception is an `OSError`. If seeding, visibility declaration, or home binding raises another exception and revocation also fails, line 6077 re-raises only the original exception; the caller is not told that the universe remains claimed but uncreated.

- **P2 — DISAGREE_EVIDENCE — `tinyassets/api/helpers.py:105`, `tinyassets/api/helpers.py:173`.** The shared case-fold resolver is not used by either fallback enumeration. With directory `U-Mine` and ACL ID `u-mine`, listing may recognize it, but both default resolvers skip it and return `default-universe`. With an active marker, lines 82–84 return the ACL spelling `u-mine`, which misses the actual `U-Mine` path on Linux.

- **P2 — DISAGREE_EVIDENCE — `tests/test_a_universe_needs_an_owner.py:309`.** The infrastructure drift scan cannot detect current roots constructed through another base expression. For example, `tinyassets/daemon_brain.py:825` creates `Path(base_path) / "lancedb"`; removing `lancedb` from `INFRASTRUCTURE_DIRS` leaves this scan green. The operational-store test also remains green because the positive-signal guard refuses deletion even when the infrastructure label is absent.

- **P2 — DISAGREE_EVIDENCE — `tests/test_a_universe_needs_an_owner.py:495`.** The mid-cut race test does not prove that staging precedes the final ownership read. An unfixed implementation that performs another ownership read after `_universe_signal()` and then directly calls `rmtree(target)` would pass: the injected grant lands before that second read. It would still retain a check/delete window afterward.

**AGREE:** Same-parent cross-filesystem or mount-point rename failures and staging collisions are caught as `could not stage`; duplicate names are safe because the directory inventory is rebuilt for each entry. I found no daemon-startup or first-contact path that legitimately requires direct reads of an unowned directory.

Verification: 2026-09-02, Windows, Python 3.14.3; the permitted command completed with **88 passed**:

`python -m pytest tests/test_a_universe_needs_an_owner.py tests/test_api_helpers.py tests/test_universe_server_ledger.py`

VERDICT: REJECT```

## What round 3 asked for and did not get

The cap ends the rounds, not the fixes. Everything round 3 named is folded
except one thing, recorded here so it is not lost:

**The infrastructure drift test cannot see every root.** It reads the Python
source for `data_dir() / "name"` and `deploy/compose.yml` for `/data/name`. A
root built from another base expression -- `Path(base_path) / "lancedb"` in
`tinyassets/daemon_brain.py` -- is invisible to it, so removing `lancedb` from
`INFRASTRUCTURE_DIRS` would leave the scan green. Because a cut now needs a
positive universe signal, that is a labelling gap rather than a data-loss one:
`lancedb` carries no universe marker and no archive prefix, so the prune
refuses it as "not a universe directory" whether or not the label is there.

## The verdict on the exact head

After the three findings rounds closed, the merge gate asked for a verdict on
the exact head -- a different question from another findings round, and the one
`pr-scope-guard` is built around. It took three heads to earn:

| Head | Verdict | What it caught |
|---|---|---|
| `8982b63e` | REJECT | Round-3 finding #6 was half fixed: the resolvers returned the ACL's spelling, so `U-Mine/` owned by `u-mine` resolved to a path that does not exist on Linux. |
| `8ef30734` | REJECT | The fix introduced the mirror defect: the scan took the first case-folded hit in sorted order, so with both directories present the exact pointer `u-mine` opened `U-Mine`. |
| `abd300df` | **APPROVE** | "all seven round-3 findings are fixed. Focused tests: 73 passed, 1 filesystem-dependent skip. No new defect found." |

Both rejections were real defects in code I had reported as fixed. That is the
gate working, not ceremony.

## The receipt



`pr-scope-guard` asks for an exact-head review receipt because
`tinyassets/api/visibility.py` is an authority path. The change to it is one
call site following a signature: `_discover_universe_ids` passes the owned set
into `_is_listable_universe_dir`. That is small, and it is still behavioural --
discovery now returns owned universes only, which is the point of the change.

The receipt on the pull request cites this file and the APPROVE above, at head
`abd300df59aec10357159b8a13c600f265fb54de`. Any push voids it, so it goes on
last.
