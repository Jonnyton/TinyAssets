## A universe needs an owner, and a prune cuts

The founder read a universe count from another session and said:

> a universe should only exist if it belongs to a user and I'm really the only
> user and have made only the universe that was created when I workos logged in
> for the first time

Production listed **12**. Five were never universes: a migration backup, three
archives that PAST PRUNES created, and scratch space. The definition was "any
directory under the data root whose name is not one of four hardcoded
operational names", so every operational directory became a public universe —
and asking for `_removed_universes_20260829` by id answered with a full
universe payload. The graveyard was browsable.

Then, on the archives:

> leaving old folders is not a prune, a prune cuts bad branches off. this made
> the branches unconnected but still sitting in the tree

So this is two changes: the definition, and a real cut.

### The definition

A universe is a directory somebody owns — the union of the `universe_acl` table
and `founder_home` bindings. The four-name denylist is deleted. Enumeration,
both direct-id readers, and both default resolvers all ask the same question
through one resolver, case-folded, so a directory restored under a different
case is still the universe its ACL row names.

The filesystem path index stays deliberately unfiltered: a self-hoster
restoring from a backup needs a directory indexed before anything can grant on
it. Indexed is not owned.

### The cut

`plan()` is a pure report — every directory, its owners, its size, the notable
files it holds. `prune()` removes, and `--apply` is required.

The safety property is **not** a list of names to protect. A cut needs a
positive reason to believe a directory was a universe: a marker file it carries,
or the name a past prune gave a pile of universes. A directory the tool does not
recognise is refused as "not a universe directory" — which is what keeps a
store added next month safe with nobody updating anything.

The cut frees the id before deleting: the directory moves aside under a name
nothing can grant on, ownership is read again, and a claim that landed in
between puts it back. A crash in that window is reported by name with its
contents intact, because a silent orphan is worse than a loud one.

### What three review rounds found

Codex returned REJECT three times. The findings that mattered most were all
data loss, and all real:

- **The allowlist was incomplete and could not be made complete.** Five live
  stores were missing — daemon memory, retained user inputs, the brain's vector
  store (`lancedb`, which is not the listed `lance`), the workspace pool, and
  every founder's stored offers. This is what inverted the classification from
  "unowned means garbage" to "a cut needs a reason".
- **`_backup` as a universe signal would have cut the migration backup** that
  `docs/host-actions.md` says in as many words not to delete. My rule; caught by
  the reviewer, not by me.
- **`reset(confirm=True)` destroyed the same backup**, because the prune had
  learned the difference and the reset had not.
- **The owner was claimed 90 lines after the directory existed**, so a prune in
  that window deleted a universe while the create returned "created".
- **Reading a universe by id needed no owner**, reproduced anonymously against
  production — the graveyard was still browsable, just not listed.
- **A not-found answer published every owned universe**, private and unlisted
  ones included, to any signed-in caller.
- **An unreadable ownership store answered "not found"**, telling a caller that
  an existing universe does not exist.

### Evidence

Every new guard driven against the tree WITHOUT its fix:

```
RED  the signal is not required             -> the plan reports fail-closed
RED  the cut does not require a signal      -> an operational store is not cut
RED  the caller's spelling is trusted       -> a respelled name cannot reach wiki
RED  ownership matched case-sensitively     -> a recased universe is still owned
RED  community-pool is not named durable    -> the drift scan reads compose.yml
RED  _backup is a universe signal again     -> the migration backup survives
RED  the delete does not free the id        -> a mid-cut claim is not lost
RED  reading by id needs no owner           -> the graveyard is not browsable
RED  a reset clears everything unrecognised -> the backup survives a reset
RED  the not-found answer skips visibility  -> private ids are not published
RED  an unreadable store answers 'unowned'  -> it says the store is down
RED  the delete precedes the second read    -> the ordering is proven
```

```
tests/test_a_universe_needs_an_owner.py, test_api_helpers,
test_universe_server_ledger, test_universe_visibility ....... 155 passed
```

Pre-existing red, unchanged by this branch: 7 in `test_first_contact` and the
`test_deploy_prod_workflow` file (76 red at base).

### Known, and not fixed here

The infrastructure drift test reads the Python source for `data_dir() / "name"`
and `deploy/compose.yml` for `/data/name`. It still cannot see a root built from
another base expression, such as `Path(base_path) / "lancedb"`. Because a cut
now needs a positive universe signal, that is a labelling gap rather than a
data-loss one — but it is a gap.

### The authority-path receipt

`pr-scope-guard` requires an exact-head review receipt because
`tinyassets/api/visibility.py` is an authority path. It took three heads to
earn, and both rejections were real defects in code I had already reported as
fixed:

| Head | Verdict | What it caught |
|---|---|---|
| `8982b63e` | REJECT | The resolvers returned the ACL's spelling, so `U-Mine/` owned by `u-mine` resolved to a path that does not exist on Linux. |
| `8ef30734` | REJECT | The fix introduced the mirror defect: the scan took the first case-folded hit in sorted order, so the exact pointer `u-mine` opened `U-Mine`. |
| `abd300df` | APPROVE | "all seven round-3 findings are fixed... No new defect found." |
| `e7c917f3` | APPROVE | Re-affirmed: the delta is documentation-only. |

Transcripts in `docs/audits/2026-09-02-universe-ownership-cross-family-review.md`.

Drain-Review-Verdict: APPROVE
Drain-Review-Head: e7c917f3ea5201880475a71b36a0a730f5e9d27d
Drain-Review-Artifact: docs/audits/2026-09-02-universe-ownership-cross-family-review.md

### Not in this PR

The production cut itself. `scripts/prune_unowned_universe_dirs.py` prints the
inventory first and needs `--apply`; the founder sees what each directory holds
before anything is removed. `docs/host-actions.md` says which two decisions are
theirs.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01PQCVwyxkNe1Yxq3BVKiYxm
