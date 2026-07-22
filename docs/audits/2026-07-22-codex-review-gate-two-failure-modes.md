# The cross-family review gate returned two things that were not verdicts

- **Date:** 2026-07-22
- **Lane:** `claude/fix-codex-verdict-attribution` (routed to Claude deliberately — the
  prior lane was a Codex lane and its sandbox denied execution of `codex.cmd`, so it
  could not run the experiment on its own dispatcher)
- **Component:** `scripts/codex_review.py`
- **Status:** both modes reproduced, both root-caused, both fixed with tests that go red
  on unmodified `origin/main`

## Why this matters

`CLAUDE.md` §"Calling Codex via MCP" makes the cross-family review a standing obligation
before shipping a finding, and `AGENTS.md` §"Project Skills" makes an opposite-provider
review a **gate** on build / push / live rollout for research-derived findings. Both name
`scripts/codex_review.py` as the default dispatch mechanism.

A gate that can return someone else's `approve`, or a clarifying question dressed as a
verdict, is worse than no gate: it manufactures confidence. Neither mode below is the
known hang, and neither is caught by `ensure_verdict_file()` — that backstop only fires on
an *absent or empty* file, and both modes produce a file with real content.

## Mode 2 — the ask never reaches Codex

### The artifact

`docs/audits/2026-07-22-probe-catalog-truth-codex-review.md` (198 bytes, untracked,
mtime 2026-07-21 22:52 local / 05:52Z) contains, in its entirety:

> Which PR, branch, commit range, or worktree should I review? The current checkout is
> `main` with only unrelated coordination-log changes, while 30+ PRs are open, so
> selecting one would be arbitrary.

That is a clarifying question, filed under a filename asserting it is a Codex review.

### Root cause

`build_prompt()` joined the adversarial preamble to the caller's ask with `\n\n`, and
`build_cmd()` passed the result as the final **argv** element. On this host
`resolve_codex()` returns `C:\Users\Jonathan\.local\bin\codex.CMD` — a `.CMD` file — so
Windows routes argv through cmd.exe, **which truncates an argument at its first newline.**
Codex received the generic preamble alone and had no target to review.

### Evidence

Captured by substituting a fake CLI that records its argv (`CODEX_BIN` override), so this
observes the real code path without spending a Codex run:

```
$ python scripts/codex_review.py --out o.md --prompt "SENTINEL-ALPHA review file foo.py"
argv[-1] = "You are performing an opposite-provider (cross-family) code review. Be
adversarial: ... then the concrete findings / required adaptations (most important first)."
```

The ask is gone. Same content joined with a space instead of a newline arrives intact:

```
argv[-1] = 'PREAMBLE-ONELINE SENTINEL-BRAVO review file foo.py'
```

`resolve_codex()` was confirmed to return `...\codex.CMD` on this host.

### Scope — this is not universal

The two other untracked `2026-07-22-*-codex-review.md` artifacts (carried by PR #1516) are
substantive reviews with real `file:line` citations, so their asks clearly arrived. They
did not come through this path: `scripts/peer_agent.py` — the newer wrapper the
`peer-agents` skill already tells you to prefer — passes the prompt over **stdin**
(`stdin=subprocess.PIPE`, `input=prompt.encode("utf-8")`) and rejects an empty prompt.
`codex_review.py` did neither. The breakage is specific to `codex_review.py` on a `.cmd`
resolution, which is every Windows dispatch through the documented default path.

## Mode 1 — a stale file is returned as a fresh verdict

Reported the previous cycle as a 1199-byte verdict file reviewing a *different* lane's PR
(#1537) with nothing from the caller's prompt in it. The prior lane hunted for `CODEX_HOME`
session cross-talk between concurrent runs and could not reproduce it, correctly declining
to ship a speculative fix.

**It is not a concurrency bug.** `run()` never cleared the `--out` path, and
`ensure_verdict_file()` returns early when the file has content:

```python
if error is None and _has_content(out):
    return
```

`codex exec` can exit 0 having written nothing (the documented v0.122+ auth-failure mode).
When it does, whatever was already at that path is handed back as this dispatch's verdict.

Reproduced deterministically, no concurrency required:

```
BEFORE  Reviewed PR #1537 (activity-log conflict class). The change is correct.
        VERDICT: approve
        $ python scripts/codex_review.py --out <same path> --prompt "LANE-B review the probe catalog"
AFTER   Reviewed PR #1537 (activity-log conflict class). The change is correct.
        VERDICT: approve          # byte-identical; exit 0; no warning
```

`peer_agent.py` already fixed exactly this — its docstring reads "A pre-existing --out file
is never mistaken for a fresh result: the codex -o target is unlinked before dispatch."
`codex_review.py` never got the fix.

## The durable fix — attribution, not behavior correction

Making Codex behave is not the fix; a verdict being **attributable to its request** is.
Each dispatch now mints a nonce and instructs Codex to echo an exact line carrying the
nonce and the reviewed target. `codex_review.py` refuses to return a verdict whose body
does not carry that exact line (whole-line match, not a substring scan), rewriting it as
`VERDICT: error` with the body preserved but every line prefixed `| ` so no line reads as a
bare `VERDICT: approve`.

A stolen, stale, or contextless verdict therefore fails closed instead of reading as
`approve`. All three fixes:

1. Prompt travels over **stdin** (`codex exec -`), never argv — immune to cmd.exe newline
   truncation, metacharacters, and length limits.
2. The `--out` path is **unlinked before dispatch**, so "file has content" can only mean
   "this dispatch produced it".
3. **Attribution gate** — nonce + target echoed, exact-line verified, fail closed.

## Unrelated finding, not fixed here

`~/.local/bin/codex.cmd` and `~/.local/bin/codex` are host-level shims that inject
`--dangerously-bypass-approvals-and-sandbox` into **every** codex invocation:

```
"%USERPROFILE%\AppData\Roaming\npm\codex.cmd" --dangerously-bypass-approvals-and-sandbox %*
```

`codex_review.py` hard-codes `-s read-only` and documents "this path never grants Codex
write access", and `test_build_cmd_is_read_only_and_no_approval` asserts
`--dangerously-bypass-approvals-and-sandbox not in cmd`. That assertion passes while the
launched process may run with the bypass anyway, because the flag is added downstream of
the argv the test inspects — a guard checking a string the shim then overrides. The shims
are outside this repo, so this lane does not change resolution behavior. Mitigation for a
single run: set `CODEX_BIN` to the real `AppData/Roaming/npm/codex.cmd`.

## Standing implication for every agent

Until a dispatcher enforces attribution, a returned verdict should be checked for a
reference to the caller's own prompt (files / shas / PR number) before it is treated as a
gate result. Proposed `AGENTS.md` wording is in the PR body; `AGENTS.md` is contended by
#1512/#1477/#1478/#1491 and was not edited by this lane.
