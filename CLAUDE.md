@AGENTS.md
@STATUS.md

## Claude Code

Everything about how to work lives in `AGENTS.md`. This file is only for things unique to Claude Code.

### Merging and deploying [Claude Code only — harness constraint]

**Background-job sessions cannot merge to `main` or deploy.** That session type gets a fixed
injected instruction ("Never push to main/master, force-push, or merge"). It is not in this repo,
not a setting, and cannot be lifted from inside a background job — `permissions.allow` already
contains `Bash(*)`, so permissions were never the blocker. Such a session can do everything up to
the merge (commit, push branches, resolve conflicts, open/update PRs) and then stalls.

- **Check which session type you are in before claiming you cannot merge.** The restriction is
  background-job-only. An interactive session repeating "this session cannot merge to main" is
  misapplying the rule and stalling the host for nothing.
- **Run merge/deploy work in an interactive (foreground) session** — no such instruction, and
  `gh pr merge` runs without a prompt. Simplest fix; reach for it first.
- **Or use GitHub-side auto-merge**, which works regardless of session type: `gh pr merge --auto`
  plus branch protection. `main` is protected, but a required check is the only real gate
  (`enforce_admins` off, no review required) — read the live state with
  `gh api repos/Jonnyton/TinyAssets/branches/main/protection` rather than trusting a snapshot here,
  and see the draft-PR caveat in memory.
- Do NOT work around the constraint from inside a background job. Say plainly that the session
  cannot merge, and hand over the exact command sequence.

**If auto-merge is wired, add a diff-scope guard.** Green checks are not sufficient: PR #1491
presented as a two-file auth fix but its diff-vs-main carried seven workflow files plus
`deploy-prod.yml` and `Dockerfile`, because the branch sat on an unmerged 217-commit lineage. CI
passed on the parts it looked at; only inspecting diff scope caught it.

### Session Start

`LAUNCH_PROMPT.md` was retired 2026-08-07. Its content now lives in three places:

- **Startup sequence** — `AGENTS.md` § *Provider session-start ritual* (steps 0–8, cross-provider).
- **Team roster** — read `.claude/agents/*.md` fresh; do not enumerate it in prose.
- **Lead norms / team management** — `CLAUDE_LEAD_OPS.md`; despawn protocols in
  `docs/audits/2026-04-25-despawn-chain-protocol.md`.

### Agent Teams [Claude Code only]

This project uses Agent Teams (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, set in `.claude/settings.json`). When acting as the Claude Code lead, you MUST use the Agent Teams system for team roles. As of Claude Code v2.1.178 the team forms automatically when the first teammate is spawned — the old "Create an agent team" / `TeamCreate` setup step no longer exists (on older builds you may still need to ask to create a team first). Spawn teammates by referencing a role in `.claude/agents/` (e.g. `verifier`, `developer`, `navigator`). Do not drop to a disposable one-shot `Agent()` subagent for a role that should be a persistent, addressable teammate. (Other providers like Cowork and Codex use `Agent()` subagents normally — this restriction is Claude Code lead only.) **Codex is NOT a teammate** — it's a separate model family you offload to *programmatically* (see §"Calling Codex via MCP"). A Claude "Codex liaison" teammate is an anti-pattern: it burns a Claude context (opus, per the model guard) to relay, defeating the point of offloading cross-family work off Claude's budget.

Team-mode caveat from the Claude docs: teammates do not inherit lead chat history, and they start with the lead's permission settings. Subagent role files reliably contribute tools, model, and prompt body; do not assume role `permissionMode`, `skills`, or `mcpServers` frontmatter will enforce team behavior. Put critical constraints in the spawn/task prompt, tool allowlists, and hooks.

### Verification Implementation [Claude Code only]

AGENTS.md defines the project-wide verification invariants. In Claude Code,
the persistent verifier teammate is the independent verification path, and
the live user-sim route is the final proof path for chatbot-facing MCP
behavior. Other providers may implement the same invariants differently.

### Calling Codex via MCP [Claude Code only]

Codex CLI is wired into Claude Code as an MCP tool: `mcp__codex__codex` starts a
Codex session, `mcp__codex__codex-reply` continues a thread. Treat Codex as a
**second model family already in the harness** — not something only a human can
start in a separate session. This is the SDLC research's "harness =
orchestration + routing between models" and "diverse-perspective verification /
judge with a different model than the writer" applied directly (basis:
`docs/audits/2026-06-24-sdlc-vibe-coding-claude-best-practices-adoption.md`). The
codebase already routes its prose-loop editorial judge to Codex, so the pattern
has precedent.

**Standing reflex — dispatch to Codex proactively; do not wait to be told.**
You have a second model family in the harness; default to using it like you'd
use a subagent or a teammate. At each checkpoint below the dispatch is a MUST,
not an option. If you deliberately skip one, say so in one line and why — don't
silently default to doing it yourself (that default-to-self bias is exactly what
makes this reflex fail).

- **Before presenting any review verdict, finding, or "looks correct" claim** —
  dispatch the opposite-provider review gate to Codex (it re-checks sources +
  actual code), log the verdict (`approve` / `adapt` / `reject`). AGENTS.md
  §"Project Skills" already requires this for research-derived findings before
  build / push / live rollout; do it without a human opening a Codex session.
- **Before acting on a risky change, a surprising result, or a finding you're
  about to ship** — get an adversarial second opinion: ask Codex to *refute* it.
- **Before an evidence-before-completion / "done" claim on non-trivial work, or
  before presenting a recommendation between options** — cross-check with a
  diverse-perspective judge (different model than the writer).
- **When stuck 3+ iterations on the same error** — hand it to Codex for fresh
  eyes (the stuck-loop reflection rule in AGENTS.md).

**Default to dispatch.** The bar is "would an independent model add
confidence?", not "is it worth the cost?". When in doubt, dispatch — reserve
self-only for trivial mechanical edits and pure lookups. The
`codex_dispatch_nudge` hook fires this reflex at qualifying prompts, but the
obligation stands whether or not the hook fires; treat a missing nudge as
silence, not permission to skip.

**How to dispatch, and the review discipline that governs it:** the `peer-agents` skill
(§ *Dispatch routes, ranked* and § *Discipline*). Headline: offload to Codex's own quota
via a **background** `codex exec`; never burn a Claude teammate as a relay.

### Skills [Claude Code only]

Project workflow skills live in `.claude/skills/` (mirror of the canonical `.agents/skills/`).
When the right skill is not obvious, read `.claude/skills/using-agent-skills/SKILL.md` first,
then open the matching skill.

### Agent Memory [Claude Code only]

Per-agent persistent memory in `.claude/agent-memory/<name>/`. Loaded automatically when teammates spawn. Agents should consult memory before starting work and update it after completing significant tasks.

### Lead Operations [Claude Code only]

When running user-sim loops, managing the dev team, or optimizing token spend,
read `CLAUDE_LEAD_OPS.md`. It contains: Recursive Learning From user-sim,
Name-Collision Awareness, Tool-Use-Limit Hits, Minimum Active-Dev Floor,
Continuous Live Shipping, Token Efficiency, User-Sim Lifecycle.

### Site preview loop

Cross-provider — see `AGENTS.md` § *Site preview / ship loop*. Full reference at `WebSite/PREVIEW.md`.

### FUSE write & commit rules (Cowork sessions) — STOP-THE-LINE on recurrence

Two hard prohibitions, both Cowork-only (FUSE mount). Native checkouts are unaffected.

1. **For any file that already exists under this repo, do NOT use `Edit` or `Write`.**
   They silently truncate the tail on FUSE while `Read` still shows the full file. Use a
   quoted bash heredoc or `scripts/fuse_safe_write.py`, then verify with `wc -l` + `tail -5`.
2. **NEVER `cp .git/index $GIT_INDEX_FILE`** when committing via git plumbing. The local
   index can be many commits behind origin; building a tree from it regresses every file
   that landed since. Use `scripts/fuse_safe_commit.py --base-ref origin/main --max-files N`.

Recipes, hook coverage, the escalation ladder, and the 720-file regression incident:
**`docs/reference/fuse-write-discipline.md`**.

**Provider-context feed hook (Claude Code only):**
`.claude/hooks/provider_context_feed_hook.py` runs on `SessionStart` and
action-oriented `UserPromptSubmit` prompts. It injects a compact
`scripts/provider_context_feed.py` checkpoint so Claude sees relevant provider
memories, idea feeds, research artifacts, automation notes, and worktree
handoffs before claim/plan/build/review/foldback/memory-write work advances.
Cross-provider rules remain in `AGENTS.md`.

### Continuous Learning [Claude Code only]

Standing behavior, not on-demand:

- After every significant learning (bug pattern, team behavior issue, user feedback, architecture decision), immediately update the relevant file: `.claude/agents/*.md`, `CLAUDE_LEAD_OPS.md`, `AGENTS.md`, this file, memory, or skills.
- Each session should leave these files better than it found them.
- Guardrail: files get REFINED not BLOATED. Every line earns its place.

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
`.agents/skills/loop-uptime-maintenance/incidents/2026-05-04-cowork-stale-index-regression.md`
(720-file regression on 66e7c6a, recovered to 631bae9, root cause was
`cp .git/index` pattern). Same kitchen-sink-diff failure mode that affects
auto-change writers — both share the structural vulnerability of capturing
state from "wherever the local checkout happens to be" instead of "the
known-good base ref."
