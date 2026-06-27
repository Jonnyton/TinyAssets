# Reality Audit

Date: 2026-04-08

> Historical snapshot. This audit reconstructed project truth on 2026-04-08;
> it is not the current coordination or design source. Use `STATUS.md` for live
> state and `PLAN.md` for current architecture, then consult newer audits for
> any claim that depends on post-2026-04-08 implementation state.

## Purpose

Reconstruct current project truth without assuming that any single file is
authoritative by assertion.

This report treats:

- `PLAN.md` as a candidate source of design intent
- `STATUS.md` as a candidate source of declared live state
- source code as implemented behavior
- logs, databases, and output artifacts as observed behavior
- tests/lint/build results as verified behavior only in the exact environment
  where they were run

## Evidence Model

Claims are weighted by this order:

1. **Runtime-proven**
   Current logs, active databases, live output artifacts, recent runtime state
2. **Implemented**
   Present in source code and importable/compilable
3. **Verified**
   Confirmed by current test/lint/build evidence in the current environment
4. **Doc-asserted**
   Present in `PLAN.md`, `STATUS.md`, or other repo docs
5. **Unknown**
   Not currently supported strongly enough by any of the above

Statuses used in this report:

- `runtime-proven`
- `implemented`
- `verified`
- `doc-asserted`
- `contradicted`
- `unknown`

## Executive Summary

The repo is not in “no source of truth” territory, but it is in
**split-truth territory**:

- the high-level architectural direction is fairly recoverable
- the current operational state is more trustworthy in runtime artifacts than
  in `STATUS.md`
- some completion/verification claims in `STATUS.md` are stale or contradicted
- `PLAN.md` is more trustworthy as thesis and direction than as a precise map
  of what is already complete

The strongest surviving truths are:

- the project is actively running live on April 8, 2026
- the tinyassets/domain extraction exists on disk
- the TinyAssets MCP server and multiplayer/MCP surfaces exist and are active
- the extracted engine is still partially bridged back through
  `fantasy_author.*`
- the current verification story is stale

## Evidence Snapshot

Observed directly during this audit:

- `.venv\Scripts\python.exe --version` -> `Python 3.14.3`
- `.venv\Scripts\python.exe -m compileall fantasy_author workflow domains`
  succeeded
- `.venv\Scripts\python.exe -m pytest -q` failed during collection because
  `fastapi` and `playwright` were unavailable in the current environment
- `.venv\Scripts\python.exe -m ruff check` reported 47 issues
- `output/.active_universe` -> `sporemarch`
- recent writes exist in `logs/daemon.log`, `logs/mcp_server.log`,
  `logs/tunnel.log`
- `logs/mcp_server.log` shows live `/mcp` traffic on 2026-04-08
- `logs/daemon.log` shows provider exhaustion, empty prose, embedding 404s,
  and an over-budget context warning

## Claim Matrix

| Claim | Strongest evidence | Status | Confidence | Notes |
|------|---------------------|--------|------------|-------|
| TinyAssets extraction exists | `tinyassets/`, `domains/fantasy_author/`, `domains/research_probe/` present and compile | implemented | High | Structural extraction is real |
| TinyAssets MCP server exists and is being used | `fantasy_author/universe_server.py`, `logs/mcp_server.log` | runtime-proven | High | This is not just planned; it is live |
| Multiplayer HTTP/API wiring exists | `fantasy_author/api.py` routes into `author_server` | implemented | High | Current code exposes session/author/branch/runtime/ledger endpoints |
| Engine/runtime extraction is complete and independent | `tinyassets/__main__.py`, `tinyassets/api/__init__.py` still delegate/re-export `fantasy_author.*` | contradicted | High | Engine split exists, but execution and API are still bridge-mode |
| First live smoke test is still pending | active universe + fresh logs/db writes | contradicted | High | The system has already moved into live use |
| Phase 0/5 verification still holds as currently true | current `pytest` and `ruff` results | contradicted | High | May have been true once in another environment, but not now |
| `PLAN.md` can be treated as exact current truth | drift between plan/docs/runtime | contradicted | Medium | Still useful for direction, not safe as sole authority |
| High-level thesis remains valid | alignment between `PLAN.md`, package shape, runtime surfaces | doc-asserted + implemented | Medium-High | Direction appears stable even where completion details drifted |

## Recovered Intent

These claims appear strong enough to treat as current working intent.

### 1. Fantasy authoring is a benchmark for broader agent-workflow design

Evidence:

- `PLAN.md` thesis emphasizes fantasy writing as the hard testbed, not the
  final abstraction
- the extracted `tinyassets/` package and `domains/` split materially support
  that generalization
- `domains/research_probe/` exists as a second-domain probe

Assessment:

- Status: `implemented`
- Confidence: High

### 2. Shared infrastructure plus per-domain graphs is the intended direction

Evidence:

- `tinyassets/` contains providers, memory, retrieval, evaluation,
  checkpointing, context, desktop, testing, and API scaffolding
- `domains/fantasy_author/graphs/` and `domains/research_probe/` own
  domain-specific topology
- `PLAN.md` resolved debate text matches that structure

Assessment:

- Status: `implemented`
- Confidence: High

### 3. The public interface is shifting from Custom GPT toward TinyAssets MCP

Evidence:

- `fantasy_author/universe_server.py`
- auth scaffolding in `fantasy_author/auth/`
- live `/mcp` requests in `logs/mcp_server.log`
- `STATUS.md` concerns around MCP registry, OAuth, and prompt behavior

Assessment:

- Status: `runtime-proven`
- Confidence: High

### 4. The repo still relies on a legacy bridge layer

Evidence:

- `tinyassets/__main__.py` only runs `fantasy_author` and delegates to
  `fantasy_author.__main__.DaemonController`
- `tinyassets/api/__init__.py` returns/re-exports `fantasy_author.api`

Assessment:

- Status: `implemented`
- Confidence: High

## Contradictions That Matter

### 1. “Done once” has been treated as “true now”

Most damaging pattern:

- work items remain `done`
- later environment drift or runtime failures do not demote them
- `Concerns` capture some contradictions, but not consistently enough

Result:

- `STATUS.md` mixes historical completion with present reliability

### 2. Verification is not freshness-stamped

Examples:

- `STATUS.md` records verification summaries without pinning them tightly to
  exact environment and date
- current environment is Python 3.14.3
- `pytest` and `ruff` do not currently match the “full verification pass”
  narrative

Result:

- verification claims age into folklore

### 3. `PLAN.md` is carrying both intent and unresolved historical debate

This is useful for archaeology, but it weakens trust when the reader wants
“what is our current design?”

Result:

- the file remains valuable, but confidence should be assigned section by
  section rather than globally

### 4. Live runtime evidence was not promoted back into shared state quickly enough

Examples:

- active `sporemarch` runtime
- current provider exhaustion
- context-budget pressure
- live MCP usage

Result:

- docs lagged observed system behavior

## Skills That Streamline Trust Recovery

These imported skills materially improve the current approach.

### 1. `context-engineering`

Best immediate fit.

Why it helps:

- it explicitly defines a context hierarchy
- it encourages loading only the right evidence for the current task
- it treats stale context as an active problem, not a passive annoyance

How to adapt it here:

- define a fixed audit context pack for trust-recovery sessions:
  `AGENTS.md`, `STATUS.md`, relevant `PLAN.md` section, specific source files,
  current logs, current verification output
- stop treating long chat history as the main memory surface
- refresh context when switching from architecture audit to runtime debug to
  documentation repair

### 2. `planning-and-task-breakdown`

Strong fit after the audit.

Why it helps:

- the repair work is too large to hold as one vague “fix the docs” task
- it forces explicit acceptance criteria and checkpoints
- it matches the repo’s existing `STATUS.md` Work-table discipline

How to adapt it here:

- break remediation into small tasks:
  truth-model repair, verification refresh, bridge extraction, runtime-pressure
  triage, `PLAN.md` reconstruction
- require each task to state what evidence will make it complete

### 3. `documentation-and-adrs`

Critical fit.

Why it helps:

- the project does not just need more notes; it needs durable “why”
- the trust model itself is now an architectural decision

How to adapt it here:

- write an ADR for the truth hierarchy:
  runtime evidence vs implemented code vs verified state vs declared docs
- separate “current design” from “historical debate” more aggressively
- keep reality audits as diagnostic artifacts, not silent replacements for
  `PLAN.md` or `STATUS.md`

### 4. `team-iterate`

Useful in spirit, not directly plug-and-play.

Why it helps:

- the failure here is partly prompt/process behavior drift
- the skill focuses on learning from observed session failures instead of
  trusting original prompt design forever

**Resolved 2026-04-16:** the skill was rewritten to be roster-agnostic. It now
reads `.claude/agents/` dynamically and applies a generic rubric (mandate
clarity, responsiveness, evidence discipline, hand-off shape, standing-team
behavior, earning-its-keep) rather than enumerating role names. The `.Codex/agents/`
path bug is fixed and the skill explicitly forbids hardcoding a roster going
forward — composition changes belong in `LAUNCH_PROMPT.md`, not in this skill.

### 5. `using-agent-skills`

Low drama, high value.

Why it helps:

- it prevents “random tool use” by forcing explicit workflow choice
- it would have made the audit approach clearer earlier

Best adaptation:

- keep using it as the entry point whenever the work is ambiguous

## Recommended Trust Model Going Forward

Do not declare one file “the truth” in the abstract. Declare **what kind of
truth** each source owns.

- `AGENTS.md`
  Process truth: how work must be done
- `PLAN.md`
  Design truth: current intended architecture, after revalidation
- `STATUS.md`
  Live state truth: current tasks, risks, contradictions, and verified-now
  state
- reality audit docs
  Diagnostic truth: temporary reconstruction artifacts used to restore trust,
  not permanent shadow authorities

## Process Fixes

### 1. Add freshness requirements to `STATUS.md`

Anything claiming verification should include:

- date
- environment
- command/evidence

If later contradicted, it moves back to `Concerns` immediately.

### 2. Split “historically completed” from “currently verified”

Current problem:

- one `done` status is being asked to mean too many things

Better model:

- `done` = work landed
- verification field says whether it is currently verified, historically
  verified, or contradicted

### 3. Make contradiction handling explicit

When code/runtime/environment contradicts docs:

- do not silently trust the older document
- record contradiction in `STATUS.md`
- downgrade confidence until revalidated

### 4. Rebuild `PLAN.md` section by section, not wholesale by faith

Treat each section as:

- retained
- revised
- archived
- unknown pending evidence

### 5. Use a fixed reality-audit workflow before major refactors

Recommended sequence:

1. load context pack
2. inspect runtime evidence
3. inspect implementation evidence
4. inspect current verification evidence
5. compare with docs
6. classify claims
7. only then propose refactor tasks

## Immediate Next Steps

1. Reclassify the most misleading `STATUS.md` verification claims so “done”
   stops implying “currently trustworthy.”
2. Write a short ADR defining the project’s truth hierarchy and freshness
   rules.
3. Break remediation into small tasks using `planning-and-task-breakdown`.
4. Decide whether to adapt `team-iterate` into an `AGENTS.md` /
   `LAUNCH_PROMPT.md` review workflow.
5. Rebuild the highest-risk `PLAN.md` sections from evidence, not memory.

## Bottom Line

The project did not lose all truth. It lost **confidence calibration**.

What failed was not the idea of shared files. What failed was the absence of a
mechanism that continuously distinguishes:

- intended truth
- implemented truth
- observed truth
- verified truth
- stale folklore

This audit should be treated as a recovery tool. Once trust is rebuilt, the
project should push stable conclusions back into `PLAN.md`, `STATUS.md`, and
`AGENTS.md` so the filesystem regains its intended role.
