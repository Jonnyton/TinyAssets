@AGENTS.md
@STATUS.md

## Claude Code

Everything about how to work lives in `AGENTS.md`. This file is only for things unique to Claude Code.

### Merging and deploying [Claude Code only — harness constraint]

**Background-job sessions cannot merge to `main` or deploy.** The background-job harness injects a
fixed instruction — "Never push to main/master, force-push, or merge" — into that session type. It is
NOT in this repo, NOT in `.claude/settings.json`, NOT a documented Claude Code setting, and NOT
something the host configured. Verified 2026-07-21: `permissions.allow` already contains `Bash(*)`,
so permissions were never the blocker; the constraint is behavioural and cannot be lifted from inside
a background job.

Consequence: a background session can do everything up to the merge — commit, push branches, resolve
conflicts, open and update PRs, verify integrations — and then stalls. The host experienced this as
the agent repeatedly refusing a merge they had never intended to forbid.

**How to actually get merges done:**

- **Run merge/deploy work in an interactive (foreground) session.** That session type carries no such
  instruction, and `Bash(*)` is already allowed, so `gh pr merge` runs without a prompt. This is the
  simplest fix and the one to reach for.
- **Or use GitHub-side auto-merge**, which works regardless of session type: branch protection with
  required status checks plus `gh pr merge --auto`. The PR merges itself when CI goes green. As of
  2026-07-21 `main` is NOT protected, so this needs setting up before it can be relied on.
- Do NOT try to work around the constraint from inside a background job. Say plainly that the session
  cannot merge, and hand over the exact command sequence.

**If auto-merge is wired, add a diff-scope guard.** Green checks alone are not sufficient: PR #1491
presented as a two-file auth fix but its diff-vs-main carried seven workflow files plus
`deploy-prod.yml` and `Dockerfile`, because the branch sat on an unmerged 217-commit lineage. Checks
passed on the parts CI looked at; only inspecting the diff scope caught it.

### Session Start

Follow `LAUNCH_PROMPT.md`. It has the full startup sequence and team roster.

### Agent Teams [Claude Code only]

This project uses Agent Teams (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, set in `.claude/settings.json`). When acting as the Claude Code lead, you MUST use the Agent Teams system for team roles. As of Claude Code v2.1.178 the team forms automatically when the first teammate is spawned — the old "Create an agent team" / `TeamCreate` setup step no longer exists (on older builds you may still need to ask to create a team first). Spawn teammates by referencing a role in `.claude/agents/` (e.g. `verifier`, `developer`, `navigator`). Do not drop to a disposable one-shot `Agent()` subagent for a role that should be a persistent, addressable teammate. (Other providers like Cowork and Codex use `Agent()` subagents normally — this restriction is Claude Code lead only.) **Codex is NOT a teammate** — it's a separate model family you offload to *programmatically* (see §"Calling Codex via MCP"). A Claude "Codex liaison" teammate is an anti-pattern: it burns a Claude context (opus, per the model guard) to relay, defeating the point of offloading cross-family work off Claude's budget.

Team-mode caveat from the Claude docs: teammates do not inherit lead chat history, and they start with the lead's permission settings. Subagent role files reliably contribute tools, model, and prompt body; do not assume role `permissionMode`, `skills`, or `mcpServers` frontmatter will enforce team behavior. Put critical constraints in the spawn/task prompt, tool allowlists, and hooks.

### Verification Implementation [Claude Code only]

AGENTS.md defines the project-wide verification invariants. In Claude Code,
the persistent verifier teammate is the independent verification path, and
the live user-sim route is the final proof path for chatbot-facing MCP
behavior. Other providers may implement the same invariants differently.

### Calling Codex via MCP [Claude Code only]

Codex is the second model family already available in this harness
(`mcp__codex__codex` / `codex-reply`, or `codex exec` via Bash); the host need
not start one. **Dispatch for judgment-class decisions, not routine work**
(recalibrated 2026-08-02: cross-family review pays decisively on some defect
classes and nothing on others — executable checks cover the rest; see
`docs/audits/2026-08-02-process-debloat-rollback-test.md` and the research
memory behind it). Dispatch when:

- a research-derived finding gates build/push/rollout (the AGENTS.md
  opposite-provider review gate);
- a high-risk or hard-to-reverse change is about to ship (auth, storage,
  migration, deploy, public surface, mass deletion) — ask Codex to *refute* it;
- you are stuck 3+ iterations on the same error;
- a pre-deploy dual-family approval is required, or the host asks.

Do NOT dispatch for routine edits, lookups, doc changes, or every verdict-shaped
sentence. Ask it to re-check sources/actual code or refute the claim; log
`approve`/`adapt`/`reject` in the lane artifact.

**Sequencing — one shape pass pre-live, hardening rounds post-live (AGENTS.md §
Review sequencing, founder directive 2026-08-20).** For a first-draft MVP the
pre-live Codex dispatch is a SINGLE shape/approach pass (right architecture?
fail-closed vs fail-open? right authority/ownership model? + any basic-safety
hole that leaks/exfils/bypasses for one founder). Do NOT run multiple adversarial
hardening rounds before the change ships live and is user-tested — that is
hardening a shape the live user path may change. The deep "refute this
concurrency / TOCTOU / durability / timing edge" rounds come AFTER live-MVP user
testing validates the shape. If a reject→reject trend is narrowing onto edges
that only bite multi-tenant / concurrent / crash on a dark, un-shipped path, that
is the signal to STOP reviewing and SHIP — record the residuals in `REVIEW.md`
and defer them to post-live hardening.

Mechanics: prefer background offload on Codex's quota — `python
scripts/codex_review.py --out <lane-local-file> --prompt "<ask>"` in a
background Bash call (fixed 2026-08-02: the wrapper now feeds Codex via stdin
and fail-closes with `VERDICT: error` on timeout/no-output; raw
`codex exec - < promptfile > outfile` also works). **Never pass multi-line
prompts to codex as argv** (cmd.exe truncates at the first newline).
Use a lane-local out path, pre-empt false premises ("if the command fails, say
so"), demand a hard output contract, and grep for the verdict token. Reviews
are read-only and batched; `workspace-write` only deliberately in its own
lane. Never wrap Codex in a Claude "liaison" teammate. Codex supplements —
never bypasses — host gates, user-sim proof, or AGENTS.md verification rules.

### Skills [Claude Code only]

Project skills live in `.claude/skills/`; start with `using-agent-skills` when
unsure. Key skills: `/steer`, `/status`, `/premise`, `/progress`, `/team-iterate`, `/idea-refine`.

### Agent Memory [Claude Code only]

Per-agent memory lives in `.claude/agent-memory/<name>/`; teammates read it on
startup and update it after significant work.

### Lead Operations [Claude Code only]

For user-sim loops, team management, or token optimization, read
`CLAUDE_LEAD_OPS.md`.

### Site preview loop

See `AGENTS.md` § *Site preview / ship loop* and `WebSite/PREVIEW.md`.

### FUSE truncation rule (Cowork sessions) — STOP-THE-LINE on recurrence

Cowork sessions mount this folder over FUSE, where the `Edit` and `Write`
tools silently truncate overwrites of existing files (chopping them
mid-line at the end of the buffer). The `Read` tool's cached view shows
the full file but on disk the tail is missing.

**Cowork rule (mandatory): for any file that already exists under this
repo, do NOT use `Edit` or `Write`.** Use one of:

```bash
# Option A — bash heredoc (good for inline content)
cat > "/full/path/to/file" << 'FILE_EOF'
... full file content ...
FILE_EOF

# Option B — fuse_safe_write.py (atomic temp+rename + size verify)
python3 scripts/fuse_safe_write.py --path /full/path/to/file --content-from /tmp/source.txt
```

Quote the heredoc delimiter so shell variable / backtick expansion stays
off. If your content contains the literal string `FILE_EOF`, pick a
different delimiter (e.g. `OUTER_EOF`).

**After every write, verify**: `wc -l <path>` plus `tail -5 <path>` to
confirm the file ends as expected. Do not move on until verified.

**Hook coverage (Claude Code only):**
- `.claude/hooks/fuse_pre_write_reject.py` runs in PreToolUse for both
  `Write` and `Edit`. Rejects calls on existing FUSE-mount paths before
  they execute, with a heredoc/fuse_safe_write recipe.
- `.claude/hooks/fuse_write_truncation_guard.py` runs in PostToolUse for
  both `Write` and `Edit` as a backstop — compares on-disk size to sent
  content (Write) or verifies `new_string` substring presence (Edit),
  exits 2 with recovery instructions on truncation.

Cowork doesn't fire `.claude/settings.json` hooks, so Cowork sessions
follow the rule manually.

**Auto-iterate (host directive 2026-04-29 + reiterated 2026-05-02):**
every truncation incident is a stop-the-line event that must trigger a
stronger preventive measure through skill + hooks. The documented
escalation ladder lives in `WebSite/HOOKS_FUSE_QUIRKS.md`. Current rung
(after 2026-05-02 status.py recurrence): PreToolUse REJECT hook +
`scripts/fuse_safe_write.py` Cowork wrapper + this section made
mandatory-not-advisory. If recurrence happens again, the next rung is a
SessionStart-printed banner that prints the rule before the first user
prompt is processed.

**Provider-context feed hook (Claude Code only):**
`.claude/hooks/provider_context_feed_hook.py` runs on `SessionStart` and
action-oriented `UserPromptSubmit` prompts. It injects a compact
`scripts/provider_context_feed.py` checkpoint so Claude sees relevant provider
memories, idea feeds, research artifacts, automation notes, and worktree
handoffs before claim/plan/build/review/foldback/memory-write work advances.
Cross-provider rules remain in `AGENTS.md`.

### Continuous Learning [Claude Code only]

After a significant learning, immediately refine the owning prompt, agent file,
canonical rule, memory, or skill. Each session should improve these artifacts;
every retained line must earn its place.

### FUSE git plumbing rule (Cowork sessions) — STOP-THE-LINE on stale-index regressions

When committing via git plumbing on a FUSE-locked checkout (Cowork sessions
do this because regular `git add` + `git commit` race against FUSE locks),
**NEVER `cp .git/index $GIT_INDEX_FILE`**. The local `.git/index` reflects
whatever staged state was last in sync with origin, which can be many
commits behind. Building a tree from that copy regresses every file that
landed on origin since the local index timestamp.

**Mandatory pattern:**

```bash
# Use scripts/fuse_safe_commit.py — it does the safe pattern + scope verification.
python3 scripts/fuse_safe_commit.py \
    --base-ref origin/main \
    --file "REPO_PATH:CONTENT_PATH" \
    --message "commit message" \
    --max-files 1 \
    --update-ref .git/refs/heads/main
git push origin main
```

The wrapper:
- Builds a fresh `GIT_INDEX_FILE` (no `cp .git/index`).
- `git read-tree <base-ref>` from the canonical state.
- `hash-object` + `update-index --add --cacheinfo` for each declared file.
- Runs `git diff --stat <base-ref>..<new-commit>` and **REFUSES** to return
  the commit hash if file count exceeds `--max-files`.
- Optionally writes the resulting sha to a local ref via `--update-ref`.

If you must call git plumbing directly (rare — only when the wrapper's
shape doesn't fit), follow the same primitives: fresh temp index, no
`cp .git/index`, verify scope via `git diff --stat <parent>..<new>` BEFORE
pushing.

**Spec reference:** incident log at
`docs/historical/loop-uptime-maintenance/2026-05-04-cowork-stale-index-regression.md`
(720-file regression on 66e7c6a, recovered to 631bae9, root cause was
`cp .git/index` pattern). Same kitchen-sink-diff failure mode that affects
auto-change writers — both share the structural vulnerability of capturing
state from "wherever the local checkout happens to be" instead of "the
known-good base ref."
