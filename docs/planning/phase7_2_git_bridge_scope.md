# Phase 7.2 — Git Bridge Scope

**Author:** planner
**Date:** 2026-04-13
**Status:** scoping for dev

## 1. What the spec says 7.2 does

New module `tinyassets/git_bridge.py` — a thin wrapper over
`subprocess.run(["git", ...])`. Four calls:

- `stage(path)` — `git add <path>`.
- `commit(message, author)` — `git commit -m ... --author=...`.
  Author = GitHub identity from §7.4, falls back to
  `anonymous <noreply@>` in dev mode.
- `pull()` — `git pull --ff-only`. Refuses on local divergence;
  returns a conflict marker for the MCP layer to surface.
- `open_pr(title, body, branch)` — uses `gh` CLI if installed, else
  returns a "manual PR needed" payload with the push URL.

Build-time dependency: git binary present. `gh` optional.

7.2 is the plumbing. Wiring the seam into MCP write handlers is 7.3.
Identity is 7.4. Those are explicitly **not** in 7.2 scope, but 7.2
must make the contracts they need already fit.

## 2. What's already in place

### 2a. Hook point exists (backend.py)

`SqliteCachedBackend.__init__(stage_hook=None)` stores a callable at
`self._stage_hook`; `_noop_stage` is the default. Every
`save_branch` / `save_goal` invocation calls `self._stage_hook(path)`
after `_write_yaml(path, payload)`. The hook's signature today is
`(Path) -> None`.

7.2 replaces `_noop_stage` with a `git_bridge.stage` bound method.
Nothing else in backend.py needs to change — the contract is already
the right shape. (Reviewer pending-item #3 separately tightens
`stage_hook: Any` → `Callable[[Path], None] | None`; land that in the
same PR.)

### 2b. YAML emit path is already firing

`serializer.py` produces per-branch + per-node + per-goal payloads
with deterministic key ordering. `backend.py._write_yaml` writes
them with `sort_keys=False, default_flow_style=False, allow_unicode=True`.
Files land at paths given by `YamlRepoLayout`. 7.2 doesn't touch
this; it only adds `git add` behind the write.

### 2c. Zero existing git integration in Python

Grep confirms: no `subprocess` call to `git`, no `GitPython`, no
`pygit2`, no `dulwich` anywhere in `tinyassets/`. 7.2 is greenfield
from the Python side. That's good — no drift to reconcile.

### 2d. Actor identity surface

`tinyassets/universe_server.py:162 _current_actor()` still reads
`UNIVERSE_SERVER_USER` env var, defaults `"anonymous"`. §7.4 replaces
this with FastMCP context + `TINYASSETS_GITHUB_USERNAME`. 7.2 doesn't
need to wait for 7.4 — it can accept `author` as a parameter and
stay neutral.

### 2e. `gh` CLI is not installed on the host machine

Confirmed via `gh --version` on the dev host (2026-04-13): command
not found. Not a blocker — spec already says `gh` is optional and
`open_pr` degrades to "manual PR needed" payload when missing. But
it IS a real-world datapoint: v1 behavior when `gh` absent must
actually work, not just fail-gracefully-in-theory.

### 2f. Number of eventual callers

`universe_server.py` has one `WRITE_ACTIONS` registry (line 316) +
~12 write handlers per spec §7.3. Today they all flow through
`save_branch_definition` / `save_goal` in `author_server.py`. 7.2's
hook point catches all of them for free because they go through the
`StorageBackend`.

## 3. Open design questions

### 3a. Commit granularity — one commit per mutation, or batched?

**Spec leans:** auto-commit per public mutation (matches Phase 4
ledger semantics; git log IS the ledger). Escalation in spec:
"alternative is stage on write, commit on explicit publish_session —
fewer commits, neater history, but risks losing work and breaks
ledger-equivalence. Want host signal before locking."

**Planner recommendation:** commit-per-mutation. Reasons:
1. Ledger-equivalence matters. Phase 4's shipped behavior is
   "every public action has an attributable record." If git is the
   ledger, missing commits = missing history.
2. "I built a workflow but it's nowhere" is a real UX loss. A user
   on phone building via MCP expects their work visible on GitHub
   immediately, not after a later `publish_session`.
3. Squashing is cheap when history gets noisy — spec mentions
   `commit_squash` as a future action. One direction (many → few)
   is easy; the other (reconstruct missing) is impossible.

Escalate to host if they want batched. My lean is strong enough to
default to per-mutation without asking again.

### 3b. Commit author — MCP actor, or single daemon identity?

This is the reviewer's flagged question. Three models:

- **(A)** `author = _current_actor()` — every mutation is
  attributed to the MCP user. Clean provenance; git log shows
  who did what.
- **(B)** `author = "tinyassets-daemon <noreply@workflow>"` —
  single identity for all daemon-driven commits. Simple, uniform,
  but loses the attribution the action_records ledger carried.
- **(C)** Hybrid — actor in commit *message*, daemon in commit
  *author*. Keeps attribution legible in `git log --format`
  while avoiding a flood of unverified email addresses.

**Planner recommendation:** (A) is correct per PLAN.md "public
actions" principle and spec §7.4 ("author is the GitHub identity…
falls back to anonymous"). Concrete shape: `commit(message, author)`
takes an author string the caller provides; default behavior in
`universe_server.py` is `author = _current_actor_email()` where
that helper falls back `anonymous <noreply@tinyassets-daemon>` when
the env var is unset. The unverified-email concern is real on
public contributions (see risk §5c) but not for solo local runs
where the whole repo is the user's.

### 3c. Pull conflicts

Spec says v1 surfaces conflicts + bails; `resolve_conflict` is v2.
Open sub-questions:

- When does `pull()` run? Spec §7.3 introduces `sync_latest` as an
  explicit MCP action. 7.2 should NOT auto-pull as part of stage/
  commit — that's a separate user intent.
- What does "bails" mean structurally? `pull()` should return a
  structured result, not raise. Shape:
  `{ok: bool, pulled_commits: int, conflicts: list[str], message: str}`.
  Conflicts list = file paths with merge markers. Caller (MCP) renders
  the list; no exception.
- If a conflict leaves the working tree in a mid-merge state, how
  does v1 clean up? Simplest: on conflict detection, immediately
  `git merge --abort` and return the conflict list. Keeps the
  working tree clean so the next mutation doesn't land on a broken
  state. v2's `resolve_conflict` can revisit.

### 3d. Error modes — `git add` failure

Four realistic failures for `stage()`:

1. **Not a git repo.** Working dir is a fresh checkout without
   `.git/`. Should this fail loudly (spec's PLAN.md Hard Rule #8)?
   Yes — but differently from other errors. If git_bridge detects
   `not-a-repo`, it should log once and switch to "git-disabled"
   mode for the rest of the process: YAML writes still happen,
   commits become no-ops. This is important because dev/test
   environments may not want to auto-init a repo.
2. **File outside repo root.** `YamlRepoLayout` prevents this via
   `Path.resolve()`, but a caller could hand a raw path. Guard
   via path-traversal check before the subprocess call.
3. **Permissions or disk full.** Return False + error string; let
   caller decide. Do NOT swallow — SQLite write already succeeded
   so the mutation isn't lost.
4. **Git binary missing.** Same as (1) but different detection
   path. Same handling: log once, disable git ops for the process.

**Recommendation:** `git_bridge` exposes a module-level
`is_enabled()` that caches the "is this a git repo with git
binary present?" answer. Backend dispatch checks this and routes
to no-op hook if disabled. One check per process; survives even
if the repo is moved mid-run (not a realistic scenario).

### 3e. Dirty working tree from user edits

Users editing `branches/<slug>.yaml` directly in their clone is
*desired* behavior (spec §Thesis). But what if the dispatcher tries
to auto-commit a Branch mutation while the user has unrelated
uncommitted edits to `PLAN.md`?

`git add <specific-path>` only stages the specified file. `git
commit` with no `-a` commits only staged changes. So user's dirty
`PLAN.md` stays uncommitted and untouched. This works correctly
IF `commit()` never uses `git commit -a` — which it won't.

Edge case: the user has uncommitted edits to the SAME file the
dispatcher is about to overwrite (e.g. manually edited `branches/my-branch.yaml`
while the server also has a patch_branch in flight). 7.2 should:

1. Before writing YAML, detect if the path has uncommitted changes
   (`git diff --quiet --exit-code HEAD -- <path>`).
2. If yes, refuse the MCP write and return a "local edit conflict"
   marker. User resolves manually — either commits their edit,
   discards, or stashes.

Avoids the "daemon silently overwrote my in-progress edit" failure.
Add a `force=True` override for the MCP caller who knows what they're
doing.

### 3f. `push` semantics

Spec §7.3 introduces `publish_to_remote` = `git push` + optional
`gh pr create`. Question for 7.2: does `git_bridge` expose `push()`
as a primitive now, or only `open_pr()` composed of push + PR?

**Recommendation:** ship both primitives in 7.2. `push(remote='origin',
branch='HEAD')` and `open_pr(title, body, branch)`. `open_pr` calls
`push` internally. Lets 7.3's `publish_to_remote` compose from
smaller pieces and makes `push` independently testable.

### 3g. Transaction semantics — SQLite-first vs YAML-first

Current `SqliteCachedBackend` writes SQLite first, then YAML. 7.2
adds a commit step. Failure after SQLite succeeds but before commit
= SQLite has the change, git doesn't. 7.3's ledger-as-git-log assumes
they match.

**Options:**
- **Accept drift.** If git commit fails, log + mark drift in SQLite;
  next write tries to re-commit. Self-heals eventually. Simple.
- **Compensating rollback.** Revert the SQLite change if commit
  fails. Requires transactional wrap around both stores.
- **Git-first.** Reverse the order — commit YAML first, then
  mirror to SQLite. If SQLite fails, re-derive from YAML later.
  Fits the target architecture (`filesystem_only` backend in spec
  §Architecture).

**Planner recommendation:** option 1 (accept drift) for 7.2 ship.
Option 3 is where the architecture is going, but flipping the
order before the cutover of ~12 MCP handlers (7.3) risks bigger
blast radius. Revisit after 7.3 is live.

## 4. Suggested dev tasks

### Task G1 — `tinyassets/git_bridge.py` module

**Scope:** implement the four spec surfaces + helpers, with full
test coverage.

- `is_enabled() -> bool` — cached detection of git binary + repo.
- `stage(path: Path) -> bool` — `git add <path>`, return success.
- `commit(message: str, author: str) -> CommitResult` — returns
  `(ok, sha | None, error | None)`. `CommitResult` is a dataclass.
- `pull() -> PullResult` — returns
  `(ok, pulled_commits, conflicts, message)`. On conflict, calls
  `git merge --abort` and returns the conflict file list.
- `push(remote='origin', branch='HEAD') -> PushResult`.
- `open_pr(title, body, branch) -> PRResult` — uses `gh` if
  available, else returns `{mode: "manual", push_url: ...}`.
- `has_uncommitted_changes(path: Path) -> bool` — for §3e
  conflict detection.

All functions use `subprocess.run([...], capture_output=True,
text=True, check=False)`. Never `check=True` — return structured
errors, don't raise. Timeout on every call (5s for add, 30s for
push/pull).

Tests use `tmp_path` + real `git init` to verify behavior end-to-end
(git binary is assumed present on CI; tests skip when absent). Mock
`gh` via PATH manipulation or a stub script.

**Files:** `tinyassets/git_bridge.py` (new), `tests/test_git_bridge.py` (new).
**Depends on:** nothing. Can start immediately.

### Task G2 — wire `SqliteCachedBackend` to `git_bridge.stage`

**Scope:** replace `_noop_stage` default with a real hook when the
repo is git-enabled.

- `SqliteCachedBackend.__init__` gains an optional `git_enabled: bool`
  that defaults to `git_bridge.is_enabled()`. When True, default
  hook becomes `git_bridge.stage`. When False, stays `_noop_stage`
  (tests + non-git environments).
- Tighten `stage_hook: Any` → `Callable[[Path], None] | None` per
  reviewer concern #3.
- Add pre-write check `has_uncommitted_changes(path)` → refuse MCP
  write with "local edit conflict" marker (per §3e). Threaded via
  a return value on `save_branch` / `save_goal`.
- Fix backend's drift-tolerance mode per §3g option 1.

**Files:** `tinyassets/storage/backend.py`,
`tests/test_storage_phase7_backend.py`.
**Depends on:** G1. Parallel-safe with G3.

### Task G3 — commit primitive wired to a new backend method

**Scope:** add `save_branch_and_commit(branch, author, message)` and
`save_goal_and_commit(goal, author, message)` methods to
`SqliteCachedBackend`. These combine write + stage + commit in
one transactional-ish call. 7.3 cutover will use these, not bare
`save_branch`.

- Default message template:
  `"{action}: {name} ({slug})"` — e.g. `"build_branch: Research
  paper pipeline (research-paper-pipeline)"`.
- Author defaults to a `default_author: Callable[[], str]` the
  backend is configured with — decouples from `_current_actor()`
  import.

**Files:** `tinyassets/storage/backend.py` (additive),
`tests/test_storage_phase7_backend.py` (new cases).
**Depends on:** G1. Parallel-safe with G2.

### Task G4 — documentation + `.gitignore` / `.gitattributes` for the catalog

**Scope:** ensure repos where 7.2 runs have a sane git config.

- `.gitattributes` to force LF on `*.yaml` / `*.md` in repo root
  (avoids CRLF churn on Windows — reviewer's general watch-item
  per the STATUS.md session).
- `.gitignore` entry for `output/.langgraph_runs.db` and other
  local-only SQLite stores (per spec §What-stays-local).
- Short section in `docs/specs/phase7_github_as_catalog.md` or a
  sibling file describing repo setup for 7.2+.

**Files:** `.gitattributes` (new), `.gitignore` (edit),
one doc file.
**Depends on:** nothing. Parallel with everything.
**Priority:** low — can follow G1-G3 or land alongside.

### Parallelization

| Task | Depends on | Parallel-safe with |
|------|-----------|--------------------|
| G1 git_bridge module | — | G4 |
| G2 backend wire-up | G1 | G3 |
| G3 save_and_commit helpers | G1 | G2 |
| G4 repo config + docs | — | G1, G2, G3 |

G1 is the critical-path landing. Once green, G2 + G3 can run in
parallel on two devs. G4 is independent.

## 5. Risks

### 5a. Cross-platform git behavior

Windows (this host), macOS, Linux all ship git but default configs
differ: line endings, autocrlf, path case-sensitivity. Mitigations:

- `.gitattributes` to pin LF on YAML + Markdown (G4).
- All subprocess calls use full paths, not cwd-dependent behavior.
- Test suite runs `git init` in `tmp_path` with explicit `-b main`
  to avoid the `master` vs `main` default drift.

### 5b. `gh` CLI absence on host machine

Confirmed absent on 2026-04-13 dev host. Not a blocker (spec says
optional), but means the `open_pr` path will return "manual PR
needed" on every call in the current setup. When a contributor
wants to publish, they'll need either `gh` installed OR a manual
push + PR workflow. Document the fallback clearly in G4.

### 5c. Unverified commit email spam

If `_current_actor()` returns whatever the user typed, we could
emit `"bob@example.com"` as commit author without verifying. On
public repos, unverified emails show up in contributor stats and
potentially in GitHub's block-list. Mitigations:

- Use `noreply` emails by default: `anonymous <noreply@tinyassets-daemon>`.
- Don't auto-push unless the user explicitly invokes
  `publish_to_remote` (§7.3).
- When pushing to a shared repo, require a verified GitHub identity
  (checked via `gh auth status` when available).

This is a §7.4 concern more than §7.2, but G1's `commit()` signature
must not lock in a shape that makes §7.4 hard. Taking `author: str`
as an opaque commit-author line and not parsing it is the right
shape — keeps §7.4 free to decide format.

### 5d. Long-running subprocess hangs

`git pull` over a slow network can hang. Every subprocess.run
must have a `timeout=` parameter. On timeout, structured failure,
never raise past the bridge.

### 5e. Concurrent writes in a single process

FastMCP may dispatch two `build_branch` actions concurrently. Two
concurrent `git add` + `git commit` calls will race. Mitigations:

- Serialize via a process-local lock (`threading.Lock` or
  `asyncio.Lock` depending on the MCP thread model) wrapping
  commits. `stage` is safe to parallelize; `commit` is not.
- Spec's auto-commit-per-mutation choice makes this more urgent
  than batched commits would.

### 5f. Tests need a real `git` binary

Unit tests that don't spin up a repo are fine, but the round-trip
tests need real `git init` + `add` + `commit`. CI must have git
installed (standard on GitHub Actions runners; confirm on local
dev CI if applicable). Tests gracefully skip when `git` absent via
`pytest.mark.skipif(not git_bridge.is_enabled())`.

### 5g. Escalation paths explicit

Two design decisions in this doc (§3a commit granularity, §3b
author model) I've recommended strong defaults on without further
consultation. If the host disagrees, G1/G3 code changes are local
and cheap. Flagging them here so they're not silently locked in.
