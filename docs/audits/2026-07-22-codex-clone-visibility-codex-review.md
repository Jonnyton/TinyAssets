# Codex cross-family review — .codex-worktrees clone visibility

- **Date:** 2026-07-22
- **Reviewer:** Codex CLI, `gpt-5.6-sol`, sandbox `read-only`, `approval_policy=never`
- **Subject:** adding independent-clone discovery to `scripts/worktree_status.py`
- **Verdict:** `adapt`

Dispatched by piping the ask to `codex exec -` on **stdin**. The normal route
(`scripts/codex_review.py --prompt`) silently truncates on Windows: the prompt is
the last argv to `codex.cmd` and `build_prompt` prefixes the preamble with `

`,
so cmd.exe cuts at line 1 and Codex receives only the preamble. Two dispatches were
lost to that before it was caught.

## Disposition

| # | Finding | Disposition |
|---|---|---|
| 1 | Brief's facts stale (counts, shas, branches now on origin; `.gitignore` claim wrong) | **Accepted.** Verified independently; corrections in the PR body. `.codex-worktrees/` is NOT ignored — `git status` lists it. |
| 2 | `UNPUBLISHED` overstates; squash-merge is indistinguishable | **Accepted.** Split into `CLONE_UNPUBLISHED_ABSENT` (object absent from canonical store — unambiguous) and `CLONE_UNPUBLISHED_NO_ORIGIN_REF` (routes to `gh pr view`). |
| 3 | `git_squash_merge` calls `commit-tree`, so it mutates | **Noted, out of scope.** Not used by the clone path. Logged as its own lane in `_PURPOSE.md`. |
| 4 | Dirty filter suppresses **tracked** deletions and conceals divergence | **Accepted — real defect in the submitted code.** Now only `??` untracked entries are discounted. Regression tests added; `wf-unified-authority` correctly flipped `scratch` -> `yes`. |
| 5 | Must not mutate global `safe.directory`; 4 clones affected, not 2 | **Accepted.** Remedy is printed, never run; asserted by a test that fails if a `git config` call appears. Count was 4 in our run too. |
| 6 | Keep the clone pass bounded; expensive classification opt-in | **Accepted.** No tree walk, git plumbing only, 8-way parallel; ~1s for 26 clones. `--check-prs` is opt-in. |

## Verdict text (verbatim)

```
VERDICT: adapt

1. The fact brief is stale as of 2026-07-21 23:51 PDT:

   - (a) `git worktree list` still reports 0 `.codex-worktrees` paths, but the exact `ls ... | wc -l` result is now **27**, not 25: 25 independent clones, one non-repository directory (`wf-fix`), and one bundle file.
   - (b) `a7a62ac9ed22838ca53d55da329ba86625c7f3fe` is now valid and exactly matches `origin/codex/wiki-discovery-separation`; draft PR #1550 is open.
   - (c) `universe-first-contact` HEAD is now `e2e0c4ea`, not `8ad213c3`. The latter is its ancestor and is reachable from `origin/feat/universe-first-contact`.
   - (d) Confirmed: `a6bb147bac64cbb6d819e3b9cbf8b1e22c833186` exactly matches `origin/fix/credential-vault-fail-closed`; draft PR #1549 is open. The earlier “not on origin” claim is obsolete.
   - `.codex-worktrees/` is **not** ignored on current `origin/main`; `.gitignore:89` is blank. The only related ignores are [.gitignore](/C:/Users/Jonathan/Projects/TinyAssets/.gitignore:19). The claim that no `origin/main` script mentions the path is correct.

2. `for-each-ref --contains` is a useful cheap first pass, but `UNPUBLISHED_HEAD` is an incorrect state name. Squash-merged/deleted branches are indistinguishable from never-published commits through current ref reachability alone. Use states such as:

   - `ORIGIN_REACHABLE_HEAD`
   - `NO_ORIGIN_REF_CONTAINS_HEAD`
   - `HEAD_ABSENT_FROM_CANONICAL`
   - `NEEDS_PR_CLASSIFICATION`

   Only treat empty output as meaningful when the command exits 0. For a missing object it exits 129, not “empty/unpublished.” PR metadata plus exact `headRefOid` is the more accurate second-stage classifier. No purely local, read-only graph primitive can recover historical publication after squash merge plus ref deletion.

3. The existing squash-aware helper is relevant but not strictly read-only. [git_squash_merge.py](/C:/Users/Jonathan/Projects/TinyAssets/scripts/git_squash_merge.py:39) recognizes cumulative squash patches, but it calls `git commit-tree` at [line 64](/C:/Users/Jonathan/Projects/TinyAssets/scripts/git_squash_merge.py:64), creating a dangling object. Do not silently reuse it if “no repository mutation” is a requirement. Current worktree classification invokes it from [worktree_status.py](/C:/Users/Jonathan/Projects/TinyAssets/scripts/worktree_status.py:342).

4. The proposed dirty-path filter is unsafe. In `wf-unified-authority`, all 65 `.test-tmp/...` entries are tracked deletions (` D`), and `git ls-files` confirms 65 tracked paths. Filtering by pathname would falsely report that clone clean and conceal genuine index/worktree divergence. Suppress only `??` untracked entries under exact, root-anchored scratch directories; never suppress tracked modifications, deletions, or renames. Report suppressed scratch separately instead of silently discarding it.

5. Agree that the status tool must not mutate global `safe.directory`. During this review, four clones initially failed with dubious ownership—not two: `directory-run-graph-gate`, `legacy-mcp-server-fence`, `wf-goal-private-read`, and `wf-goal-private-read-verify`. Another concurrent process subsequently added all clone paths globally, making the current failure count zero. Report the condition and Git’s quoted remedy as an explicit trust-changing operator action. A 128 or permission warning must produce `GIT_TRUST_BLOCKED`/`STATUS_INCOMPLETE`, never “clean”; current `_is_dirty()` returns false on every nonzero status exit at [worktree_status.py:315](/C:/Users/Jonathan/Projects/TinyAssets/scripts/worktree_status.py:315).

6. Discovering immediate children whose `.git` is a directory is the right extension to `collect_worktrees()` at [worktree_status.py:188](/C:/Users/Jonathan/Projects/TinyAssets/scripts/worktree_status.py:188). Skip/report non-clones, validate the clone’s origin URL, and deduplicate paths. Keep the clone pass bounded: the existing session-start tool exceeded 120 seconds during this review before adding these 25 clones, so expensive squash/PR classification should be deferred or opt-in.
```
