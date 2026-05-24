# Anticipation Gap + Permission Ladder - Codex Synthesis

Source wiki page:
`pages/concepts/anticipation-gap-and-permission-ladder-jones-2026-05-07.md`.

Request: WIKI-DOCS / GitHub issue #582.

Status: docs/ops synthesis only. This note does not approve runtime work and
does not create a new primitive. Promote any implementation into a current
`STATUS.md` row or proposed design note before coding.

## Classification

This is a `docs-ops` concept filing, not a bug. The smallest useful project
change is to preserve the Codex-side coordination angle requested by the wiki
page, because the live wiki artifact is not stored in this checkout.

The page frames the "anticipation gap" as the product gap between reactive
agents and agents that can notice the right moment to help without creating
extra management work for the user. It pairs that with a five-level permission
ladder:

1. Read.
2. Suggest.
3. Draft.
4. Act with confirmation.
5. Act autonomously.

## Codex Angle

The permission ladder should be treated as action-level authority, not as a
replacement for operator scopes. The existing scope-decoration track answers
"who may call this surface"; the ladder answers "how much trust does this
particular action have right now?"

That means the ladder should be folded into future scope-decoration work as a
confirmation and escalation layer. It should not become five new top-level MCP
handles and should not introduce a parallel auth system.

## Primitive Pressure Test

The page names three possible follow-up concepts: permission ladder, acceptance
scenario packs, and per-user intent history. Apply the existing scoping rules
before treating any of them as new substrate:

| Concept | Initial Codex pressure-test |
|---|---|
| Permission ladder | Likely policy metadata over existing Run/Trigger/State/Scope composition. |
| Acceptance scenario packs | Likely a named bundle of State expectations, Trigger boundaries, Run execution, Edge criteria, Node audit records, and Scope bounds. |
| Per-user intent history | Likely user-scoped State records under Scope, unless review proves the data model cannot carry temporal intent evidence. |

The bias should be composition first. A new primitive is justified only if the
existing six substrate concepts cannot express provenance, confirmation state,
or user-specific intent history without ambiguity.

## Queue Guidance

The user-facing proactivity stack should come after the operator-side autonomy
readiness work that is already in flight. Current queue implication:

- Keep uptime and community-loop recovery first.
- Fold permission-ladder semantics into the scope-decoration design path when
  that lane is active.
- Treat acceptance scenarios and intent history as design candidates until
  separately promoted.
- Avoid adding runtime MCP actions from this concept page alone.

## Review Gate

Because the source page is research-derived and cross-provider, future runtime
work based on it needs opposite-family review before implementation. The review
should re-read the live wiki page, compare the active PLAN.md scope rules, and
decide whether each candidate composes from existing primitives or needs a
proposed design note.
