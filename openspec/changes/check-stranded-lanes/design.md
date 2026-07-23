# Design: stranded-lane detector

## Context

The existing worktree status command answers lifecycle questions for paths
registered by `git worktree list --porcelain`. A separate clone has its own Git
administrative directory and is not registered there, so extending only the
status classifier would preserve the observed blind spot. The detector therefore
owns a separate union inventory and a narrower publish-postcondition check.

## Decisions

### Inventory is a union, not a replacement

Start with registered worktrees, then scan `.codex-scratch-*`, `codex-tmp/*`,
`.claude/worktrees/*`, and sibling `../wf-*` directories containing a `.git`
file or directory. Resolve and de-duplicate paths. A failure to enumerate
registered worktrees is itself `UNKNOWN`, but scratch scanning still continues.

### Observable state only

For each readable checkout, compute `git rev-list --count origin/main..HEAD` by
default. A `--base-ref` override supports the audit's falsifiable historical
acceptance run against `2c1f63cb` without fetching into or modifying shallow
clones. Only positive counts need publication checks. A lane is `STRANDED` when its
current branch is absent from `git ls-remote --heads origin` or when `gh pr list
--head <branch> --state all` finds no PR. The command reports which predicate
failed; it does not infer why.

### Unknown is loud and read-only

Any Git/GitHub error that prevents a conclusion is `UNKNOWN` and contributes to
exit 2. In particular, dubious ownership is reported verbatim enough to identify
the lane, but the detector never runs `git config --global --add safe.directory`.
The tool performs no filesystem or remote mutation.

### Test seams stay at external boundaries

Tests construct real repositories for ahead-count and inventory behavior. Remote
branch and PR lookups are injectable callables so tests remain offline and can
prove both halves of the publication predicate without mocking internal
classification logic.

## Non-goals

- Preventing a publish delegate from failing.
- Hook, session-start, or CI integration.
- Deciding whether stranded work is valuable, superseded, or safe to delete.
- Repairing remotes, branches, ownership, or pull requests.
