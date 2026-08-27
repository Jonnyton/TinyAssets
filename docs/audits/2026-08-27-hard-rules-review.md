# Do the 14 Hard Rules earn their keep?

Reviewed 2026-08-27 against three questions, with evidence for each rule rather
than a judgement:

1. **Does its subject still exist?** A rule naming a deleted file steers agents
   into nothing.
2. **Is it executable, or prose?** Anthropic's Claude Code guidance is explicit
   that hooks and checks are deterministic while instructions are *advisory* —
   so a rule that could be a check and isn't is carrying less weight than it
   looks.
3. **Can it go stale silently?** A rule pinned to a sha, a date, a vendor
   behaviour, or a specific file rots without anything noticing.

## Verdicts

| # | Rule | Subject alive? | Enforcement | Verdict |
|---|---|---|---|---|
| 1 | SqliteSaver only | 14 files | smoke test | **KEEP** |
| 2 | LanceDB singleton | 4 files | test only | **KEEP** |
| 3 | No API SDKs for the primary writer | 0 SDK imports | none | **KEEP, cheap** |
| 4 | Executable gates need autonomous defaults | n/a | prose | **KEEP** — see below |
| 5 | TypedDict + Annotated reducers | 6 files | none | **KEEP** |
| 6 | FactWithContext truth-value typing | 10 files | none | **KEEP** |
| 7 | Python 3.11+ | — | `requires-python` in `pyproject.toml` | **KEEP, already executable** |
| 8 | Fail loudly, never silently | — | prose | **KEEP** — the load-bearing one |
| 9 | User uploads are authoritative | — | prose | **KEEP** |
| 10 | Contributor attribution via `CONTRIBUTORS.md` | file exists | prose | **KEEP** |
| 11 | Public-surface changes verify post-change | script exists | **wired into 4 workflows** | **KEEP** |
| 12 | Portfolio graph stays current | **`PROJECT_GRAPH.yml` NEVER EXISTED** | none | **CUT** |
| 13 | Inventory before you destroy | — | prose | **KEEP** |
| 14 | Merged is not deployed | script exists | wired into `invariants.yml` | **KEEP** |

## Rule 12 is the one that fails

`PROJECT_GRAPH.yml` has **never existed in this repository's history** — not
deleted, never created. The rule directs agents to "inspect `PROJECT_GRAPH.yml`
where present" before any public-facing docs/status/structure/lineage change.

Since 2026-06-01: **328 public-surface commits, 4 touching `docs/portfolio/`.**
No production failure has been attributed to the gap. A rule ignored 324 times
out of 328, pointing at a file that has never existed, is not steering — it is
noise in a file that loads on every turn.

Cross-family review reached the same conclusion independently and called it
"prose theater."

## Why the other prose rules survive despite being prose

Anthropic's guidance says prose is advisory and hooks are deterministic, which
argues for converting or cutting. Four rules stay prose anyway, and the reason
is the same for each: **they describe a judgement no check can make.**

- **#8 fail loudly.** A script can find a bare `except`. It cannot tell a
  legitimate fallback from a mock that looks like real output. This rule is
  cited more than any other in this repo's incident history.
- **#9 user uploads are authoritative.** "Preserved verbatim" is checkable only
  against an intent the checker does not have.
- **#4 autonomous defaults.** Whether a safe default exists is a design call.
- **#13 inventory before you destroy.** Whether something is unique is exactly
  the question that needed judgement three times today.

Converting these to checks would produce the false assurance this repo has been
removing all week — a green check that proves the string is present, not that
the property holds. `docs/reference/executable-gates.md` § *Not gates, and
should not become gates* already makes that argument; these belong there.

## Staleness risk that remains

Two rules carry incident detail that will age:

- **#14** cites "five PRs landed 2026-07-21, zero deployed". That is history,
  and it is what makes the rule persuasive rather than arbitrary — but the
  underlying vendor behaviour (`GITHUB_TOKEN` merges raising no workflow events)
  has since been worked around with a PAT. The rule is still right; the
  mechanism named in it is no longer the only one.
- **#11** names `mcp.tinyassets.io` as internal-only. That is a live security
  property with a test (`test_canonical_url_references.py`), so it self-checks.

Neither is a cut. Both are worth re-reading annually rather than trusting.

## What this review did NOT do

It did not test whether each rule's *content* is correct — only whether the rule
still has a subject, has enforcement, and is being followed. A rule can pass all
three and still be wrong.
