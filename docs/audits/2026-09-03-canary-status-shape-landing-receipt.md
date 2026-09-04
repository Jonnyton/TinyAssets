# Canary status-shape landing receipt

**Date:** 2026-09-03  
**Author family:** Codex  
**Review family:** Claude  
**Implementation head:** `3423a4be`  
**Verdict:** APPROVE for the exact implementation head above and the receipt-only
PR head named by the `Drain-Review-Head` line in pull request #2814.

## Scope

Production deploy run 33831877514 installed a healthy candidate image but its
authenticated public MCP canary failed because `get_status` omitted
`active_host` and `release_state`. The scoped canary principal correctly reached
the canonical handle and, because it has no home universe, entered the pure-read
first-contact response. That early response carried identity and daemon evidence
but not the two platform-wide uptime fields.

This patch extracts the existing provider-binding calculation without changing
its priority, reuses it for full status, and adds the same host evidence plus the
existing read-only release receipt to the no-home response. It does not create or
repair a home, grant a capability, or expose universe or user data.

## Independent review

A read-only Claude reviewer inspected the exact implementation head, confirmed
the packaged runtime mirror is byte-identical, traced the authenticated-only
no-home branch, and reran the first-contact test file. The reviewer returned
`AGREE` / `APPROVE` with no findings.

The reviewer confirmed:

- provider detection and its precedence are unchanged by the extraction;
- the no-home fields contain host-wide status only and no bearer, secret,
  universe, or user data;
- subscription-auth inspection remains a no-probe, read-only operation;
- the release receipt was already exposed on full authenticated status and
  contains bounded deployment metadata rather than secrets;
- the test directly covers the two fields whose absence caused canary exit 5,
  while proving repeated status reads do not create a home.

## Verification

- 156 focused first-contact, identity, status, and public-canary tests passed on
  Windows/Python 3.11+.
- The independent reviewer reran `tests/test_first_contact.py`: 54 passed.
- Ruff and `git diff --check` passed.
- The Claude plugin runtime import probe passed.
- Runtime mirror parity passed for all 392 canonical files.
- The failed production attempt rolled back to the previous healthy image.

The receipt-only commit changes no runtime or test behavior. The PR body binds
that final documentation head to this artifact without requiring a
self-referential commit hash.
