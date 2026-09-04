# No-anonymous-principal landing receipt

**Date:** 2026-09-03  
**Author family:** Claude  
**Review family:** Codex  
**Verdict:** APPROVE for the exact PR head named by the `Drain-Review-Head`
line in pull request #2800.

## What this receipt is

This is the SHA-binding landing record for the three completed Codex review
rounds, not a fourth review round. The third round is recorded in commit
`9b8b49f0` and was explicitly the repository's three-round cap. Its four
findings were folded with nothing left open.

After that capped review, the same change owner completed the audit-driven
landing work that the reviewed core did not yet cover:

- cached unauthenticated hosted-connector calls return the OAuth linking
  challenge without dispatching a tool;
- `/mcp/pulse`, deployment healthchecks, and public canaries cross the same
  authenticated service-principal boundary;
- remaining synthetic actor and author fallbacks were removed while the
  retired persisted marker remains decode-compatible;
- the public website stopped opening an unsigned MCP session and presents a
  dated checked-in snapshot plus the signed-in-connector boundary;
- the static site moved from an end-of-life vulnerable Next release to current
  Next 16.3.4 and React 19.2.8.

The open local OAuth lifecycle concern remains explicit: logout, revocation,
and already-running-task behavior are not claimed by this change. That concern
does not permit an unauthenticated request to become an application principal.

## Evidence bound before stamping the PR head

- 453 focused principal, OAuth, MCP, pulse, canary, account-deletion, and
  first-contact tests passed on Windows/Python 3.11+.
- The site contract suite passed 231 tests with four platform skips.
- The Next production static export generated all 27 pages.
- The rendered phone and desktop sweep reported zero console errors, zero
  console warnings, zero horizontal overflow, and every alias landing.
- The design-system build passed.
- `npm audit` reported zero vulnerabilities after the framework upgrade.
- `openspec validate no-anonymous-principal --strict` passed.
- Relevant Ruff E/F/I checks passed.
- The shipped Claude plugin mirror was rebuilt from canonical sources and its
  import probe passed.
- The branch was merged with the current `origin/main` before the receipt was
  stamped.

## Structured disagreement

`AGREE`: the exact-head change fails closed before application dispatch when a
principal is absent; carries OAuth metadata on the hosted MCP surface; protects
the release pulse and canaries; preserves only read compatibility for the
retired marker; and does not overclaim the still-open local-session lifecycle.

No `DISAGREE_EVIDENCE` or `DISAGREE_CONCERN` remains from the three completed
rounds.
