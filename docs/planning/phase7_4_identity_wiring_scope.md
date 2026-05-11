# Phase 7.4 — Author Identity Wiring

**Author:** planner
**Date:** 2026-04-13

## 1. Today's actor flow

**Entry point:** `workflow/universe_server.py:162`
`_current_actor()` returns `os.environ.get("UNIVERSE_SERVER_USER",
"anonymous")`. A single env var, read per-call. No session
scoping, no request context, no MCP header threading.

**Consumers:** grep shows 15+ call sites across
`universe_server.py` (ledger attribution, branch author, goal
author, judgment author, run actor). Every public write passes
through `_current_actor()` directly or via the `author` kwarg that
defaults to it. `_current_actor_or_anon()` at :5797 is a goals
surface wrapper with identical behavior.

**Auth provider is implemented but unwired** per dev-2's audit §1.
`workflow/auth/provider.py` has `DevAuthProvider` and
`OAuthProvider` classes plus an `Identity` dataclass (`user_id`,
`username`, `display_name`, `is_host` — **no email field**). The
dispatcher never consults the auth provider; `_current_actor()`
bypasses it entirely.

**Implication:** today every MCP write from every user resolves to
the same env-var value. On the current single-user host this is
fine (the host is running their own daemon, `UNIVERSE_SERVER_USER`
is their GitHub handle or left as "anonymous"). When Phase 7
lights up multi-user hosted mode, `_current_actor()` needs to thread
from request context — but that's §7.4 follow-up. For 7.4
v1 ship, we're making the env-var route emit well-formed git author
strings.

## 2. Commit author format — recommendation

**Take option 3 (GitHub-style noreply composite). Format:**

```
Workflow User <{slug}@users.noreply.workflow.local>
```

where `{slug}` = `slugify(_current_actor())` with a hard fallback
to `anonymous` when the actor is empty, "anonymous", or unsafe.

**Concrete examples:**

| Actor | Commit author |
|-------|---------------|
| `alice` (env var) | `Workflow User <alice@users.noreply.workflow.local>` |
| `"Alice Smith"` | `Workflow User <alice-smith@users.noreply.workflow.local>` |
| (empty / unset) | `Workflow User <anonymous@users.noreply.workflow.local>` |
| `"anonymous"` | `Workflow User <anonymous@users.noreply.workflow.local>` |

**Why this over options 1 and 2:**

- **Always well-formed.** `git commit --author=` is picky about
  `Name <email>` shape; opaque free-form actor strings (option 2
  literal) can fail silently or produce junk. Wrapping in a fixed
  template eliminates a whole failure mode.
- **Preserves attribution.** Unlike option 1 (single daemon
  identity), `git log --author=alice` still works and `git blame`
  still tells the truth about who did what.
- **Never claims GitHub identity it can't prove.** The
  `users.noreply.workflow.local` TLD cannot resolve and cannot be a
  real GitHub account. On public repos this is important — we
  don't want the daemon to accidentally emit `alice@example.com`
  and attribute a commit to someone who hasn't authorized it. If
  a user wants their real GitHub identity on commits, they pass it
  via the explicit config knob (§5).

**Non-email display name** ("Workflow User") is deliberate: it
makes "this commit came from the Workflow daemon on behalf of an
actor" legible in `git log --oneline`'s author column without the
user having to read the email. The daemon is a participating
author; the actor is encoded in the email local part.

**Escape hatch for users who want full GitHub attribution:**
`WORKFLOW_GIT_AUTHOR` env var (§5) overrides the composite format
entirely and accepts a raw `"Alice <alice@real.email>"` string.

## 3. Anonymous / session-less fallback

When the actor slug resolves to `"anonymous"`, `""`, or any value
that fails the slug validator, the author becomes
`Workflow User <anonymous@users.noreply.workflow.local>`.

Important: this is still attributed — just to "anonymous" as a
first-class actor identity. `git log --author=anonymous` correctly
surfaces every unattributed commit. Keeps the ledger honest. When
multi-user mode lights up, unauthenticated MCP sessions stay as
anonymous, which is correct.

## 4. Cross-clone identity

Alice's local clone: `UNIVERSE_SERVER_USER=alice`. Alice creates
a branch. Commit lands with
`Workflow User <alice@users.noreply.workflow.local>` as author.
Alice pushes. Bob pulls. Bob's local repo's `git log` shows the
commit with Alice's author — **not Bob's**. Good: authorship is
about who did the work, not who has the file now.

Bob then creates his own branch on his clone. His commit is
attributed to `Workflow User <bob@users.noreply.workflow.local>`.
Bob pushes back. Alice pulls. Now both clones show both authors
correctly on their respective commits.

**`git blame branches/alice-foo.yaml`** shows Alice as the author
of lines Alice wrote, Bob on lines Bob added in a later patch.
Correct behavior.

**Edge case — Alice's clone is configured with her real GitHub
identity via `WORKFLOW_GIT_AUTHOR`, Bob's isn't.** Then Alice's
commits carry her real email, Bob's carry the composite. They
coexist in the same history. GitHub's commit-verification UI will
show Alice's as verified (if she's GPG-signing) and Bob's as
unverified — which is the correct signal.

## 5. Config knob

Two env vars, layered:

- **`UNIVERSE_SERVER_USER`** (existing) — the actor slug. Used for
  the ledger actor column AND feeds the composite author format.
- **`WORKFLOW_GIT_AUTHOR`** (new in 7.4) — when set, overrides the
  composite format entirely. Accepts a raw `Name <email>` string.
  When unset, the composite is used.

Both are process-level env vars — fits the current
`_current_actor()` shape. Future request-context-scoped identity
(OAuth-backed) replaces `_current_actor()` internals without
changing the commit-author format decision; the format is about
how we *render* identity to git, not where it comes from.

No author_server.py config setting. Keeps the storage layer free
of identity concerns; `git_bridge.commit(path, message, author)`
stays opaque per 7.2's design.

## 6. Attribution test

**Test shape:**

```python
def test_git_author_attribution_for_create_branch(tmp_repo):
    os.environ["UNIVERSE_SERVER_USER"] = "alice"
    branch = build_branch_via_mcp(name="test", ...)
    commit_sha = git_log_latest(tmp_repo)
    author = git_show_author(commit_sha)
    assert author == (
        "Workflow User "
        "<alice@users.noreply.workflow.local>"
    )
    # git blame on the written line
    blame = git_blame(tmp_repo / "branches/test.yaml", line=1)
    assert "alice" in blame.author_email
```

Parallel tests for `WORKFLOW_GIT_AUTHOR` override, for anonymous
fallback, for slug sanitization. All four tests live in
`tests/test_git_author_identity.py`.

## 7. Dev task — H0: identity-to-git-author helper

**Scope:** one small module + a single wire-in point.

- New file `workflow/identity.py` (or a function added to
  `workflow/git_bridge.py` if keeping the surface tight).
  Contents: `git_author() -> str` — returns the composite string
  per §2, reading `WORKFLOW_GIT_AUTHOR` override first, falling
  back to `UNIVERSE_SERVER_USER`-derived composite.
- Slug sanitizer: lowercase, ASCII-only, `[^a-z0-9-]` → `-`,
  collapse runs, strip leading/trailing hyphens, max 64 chars.
  Same shape as `workflow/storage/layout.slugify` — can reuse it.
- Wire `git_bridge.commit()` default parameter or call site:
  when caller doesn't pass `author=`, default to
  `identity.git_author()`.
- Test file as §6.

**Files:** `workflow/identity.py` (new), `workflow/git_bridge.py`
(one default arg wire-in), `tests/test_git_author_identity.py`
(new).
**Depends on:** G1 (git_bridge module exists).
**Parallel-safe with:** all 7.3 cluster work (H1-H4) — the format
is a drop-in at the backend's `commit(author=...)` call site.
**Blocks:** 7.3 H1 benefits from H0 landing first so the
dispatcher's call to `save_branch_and_commit` can default author
cleanly, but H0 is small enough that it can co-land with H1 if dev
prefers.

**Risk:** low. One format string, well-scoped.

## 8. Design tradeoffs flagged, not locked

- **Noreply TLD choice.** Used `users.noreply.workflow.local`.
  `.local` is IANA-reserved for mDNS and is safe-by-design. An
  alternative is the GitHub-style `users.noreply.github.com`
  which is universally understood — but we are NOT GitHub, and
  emitting `@users.noreply.github.com` would be misleading. Sticking
  with `.local`.
- **Display name "Workflow User".** Could be "Workflow Daemon" or
  plain `{actor}`. "Workflow User" reads best in `git log
  --pretty=format:'%an'` where only the display name shows —
  makes it obvious these commits are daemon-produced.
- **One env var for override vs per-universe config.** Stuck with
  env. If a host wants different identities per clone, they run
  multiple clones (spec §Thesis makes this the point). Per-
  universe identity inside one clone is out of scope.
- **No signing.** GPG signing is not in 7.4. Users who want to
  sign commits set it up in their local git config; our bridge
  doesn't touch it. `git commit` picks up `commit.gpgsign=true`
  automatically when configured.
