@AGENTS.md
@STATUS.md

## Claude Code

Everything about how to work lives in `AGENTS.md`. This file is only for things unique to Claude Code.

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

**How to dispatch — offload to Codex's budget, don't spend Claude's.** Routing a
review to Codex is what saves Claude tokens / rate-limit: Codex does the reasoning
on its OWN quota (verified: a `codex exec` run bills Codex, not Claude) and you
only read back a short verdict. Three mechanisms, ranked:
- **Background `codex exec` (default — async + offload).** Launch
  `python scripts/codex_review.py --out <file> --prompt "<ask>"` (add
  `--diff-base origin/main` for a diff review) via a **background** Bash call
  (`run_in_background: true`). Keep working; the harness re-invokes you when Codex
  exits; read `<file>` for the verdict. Zero extra Claude context, and you don't
  block. Token-cheapest and non-blocking — prefer this whenever you have other
  work to do meanwhile.
- **Inline `mcp__codex__codex`** — same offload to Codex, but it *blocks your
  turn* until Codex returns. Use only for a quick gate where you'd wait anyway and
  have nothing else to do (parallelism can't help when the review is the whole
  task).
- **Never a Claude "liaison" teammate.** A teammate is another Claude context
  (opus, per `latest_model_guard.py`) that burns Claude tokens to relay — it
  defeats the offload. If you catch yourself proposing one, stop and use the
  background `codex exec` path instead.

Discipline:
- Reviews must be substantive — Codex re-checks sources + actual code, never
  rubber-stamps. Host may delegate cross-family checker keys
  (`feedback_host_can_delegate_cross_family_keys`), but the substance review
  still happens.
- Default `sandbox: read-only` + `approval-policy: never` for reviews / second
  opinions. Grant `workspace-write` only when you deliberately want Codex to
  make changes, and keep it in its own worktree/branch (no destructive git ops).
- Calling Codex is an *additional* independent path — it does NOT bypass
  host/navigator gates or the live user-sim proof, and the result is logged like
  any other review (STATUS row / design note / activity log).
- Cost is real but secondary: a Codex session is a real agent run, so batch a
  meaningful review scope into one dispatch rather than many tiny ones — but do
  not let cost talk you out of a qualifying dispatch. Independence is the goal;
  the spend is the price of it.

### Skills [Claude Code only]

Project workflow skills live in `.claude/skills/`. When the right skill is not obvious, read `.claude/skills/using-agent-skills/SKILL.md` first, then open the matching skill.

Key skills: `/steer`, `/status`, `/premise`, `/progress`, `/team-iterate`, `/idea-refine`. Full list in `.claude/skills/`.

### Agent Memory [Claude Code only]

Per-agent persistent memory in `.claude/agent-memory/<name>/`. Loaded automatically when teammates spawn. Agents should consult memory before starting work and update it after completing significant tasks.

### Lead Operations [Claude Code only]

When running user-sim loops, managing the dev team, or optimizing token spend,
read `CLAUDE_LEAD_OPS.md`. It contains: Recursive Learning From user-sim,
Name-Collision Awareness, Tool-Use-Limit Hits, Minimum Active-Dev Floor,
Continuous Live Shipping, Token Efficiency, User-Sim Lifecycle.

### Site preview loop

Cross-provider — see `AGENTS.md` § *Site preview / ship loop*. Full reference at `WebSite/PREVIEW.md`.

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

Standing behavior, not on-demand:

- After every significant learning (bug pattern, team behavior issue, user feedback, architecture decision), immediately update the relevant file: `LAUNCH_PROMPT.md`, `.claude/agents/*.md`, `AGENTS.md`, this file, memory, or skills.
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
