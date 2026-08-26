@AGENTS.md

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

Read `AGENTS.md` (it imports here) and let the sync gate tell you whether the
checkout is behind. There is no startup ritual beyond that -- the 8-step
version, and `LAUNCH_PROMPT.md`, went with the coordination layer on 2026-08-25.

### Verification Implementation [Claude Code only]

AGENTS.md defines the project-wide verification invariants. In Claude Code the
independent path is a **Codex subprocess** via the `peer-agents` skill -- it runs
on Codex's own budget and is a genuinely different model family, which a Claude
teammate reviewing Claude's work never was. The live `ui-test` route remains the
final proof path for chatbot-facing MCP behavior.

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
unsure. Start from `.claude/skills/` and read the one that matches the task.

### Agent Memory [Claude Code only]

Per-agent memory lives in `.claude/agent-memory/<name>/`. Read the relevant
directory before starting in an area and update it after significant work.

### Site preview loop

See `AGENTS.md` § *Site preview / ship loop* and `WebSite/PREVIEW.md`.

### Continuous Learning [Claude Code only]

After a significant learning, immediately refine the owning prompt, agent file,
canonical rule, memory, or skill. Each session should improve these artifacts;
every retained line must earn its place.

