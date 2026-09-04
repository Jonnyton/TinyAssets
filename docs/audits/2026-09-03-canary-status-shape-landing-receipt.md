# Canary status-shape landing receipt

**Date:** 2026-09-03  
**Author family:** Codex  
**Review family:** Claude  
**Runtime implementation head:** `3423a4be`  
**Exact reviewed head:** `387e723f5ee6e1f7c7659fe1d613105191f70ae1`  
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

A read-only Claude reviewer inspected the runtime implementation head, confirmed
the packaged runtime mirror is byte-identical, traced the authenticated-only
no-home branch, and reran the first-contact test file. The reviewer returned
`AGREE` / `APPROVE` with no findings.

A coordinated test-only delta then added exact Streamable HTTP coverage using
the configured canary bearer. The same reviewer inspected the exact resulting
head, confirmed the test cannot pass against the pre-fix server and introduces
no authentication bypass, reran that transport test file, and returned
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
- The exact-head reviewer reran `tests/test_wiki_canary_transport.py`: 2 passed.
- The local transport, first-contact, and public-canary slice passed: 89 tests.
- Ruff and `git diff --check` passed.
- The Claude plugin runtime import probe passed.
- Runtime mirror parity passed for all 392 canonical files.
- The failed production attempt rolled back to the previous healthy image.

The receipt-only commit changes no runtime or test behavior. The PR body binds
that final documentation head to this artifact without requiring a
self-referential commit hash.

## Production recovery

PR #2814 merged as `efa0ed9e39925ba3705a14be5b9836a6b74bb81d` after every
required exact-head check passed, including the 14m21s required suite and all
three platform signature jobs. Its first image run was superseded by the next
main push. GitHub's compare API reported replacement revision
`b4662ab64513b15460f1e222f75cbfedea728bf3` one commit ahead of the merge.

Build run `33834441413` published that containing image. Deploy run
`33834837787` then:

- installed digest
  `sha256:45b354fce5da8210f5587536e8f279243235c1a6a835d61394a2b9decbb7f710`;
- reported the container healthy and the candidate image clean;
- passed `scripts/mcp_public_canary.py --url https://tinyassets.io/mcp --assert-handles`
  with the canary service-principal bearer;
- skipped rollback; and
- published `release-state.json` with
  `git_sha=b4662ab64513b15460f1e222f75cbfedea728bf3`.

The local `deployed_sha.py --assert-contains` invocation failed closed before
network access because this checkout does not hold the canary secret. The same
live release receipt was observed in the authenticated deployment job, and the
GitHub ancestry comparison proves its revision contains the status-shape merge. This is
receipt evidence subject to the existing limitation in
`docs/concerns/2026-08-26-deployed-sha-proves-receipt-only.md`.
