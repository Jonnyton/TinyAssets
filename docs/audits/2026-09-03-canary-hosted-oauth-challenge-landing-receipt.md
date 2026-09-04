# Hosted OAuth challenge canary landing receipt

**Date:** 2026-09-03  
**Author family:** Codex  
**Review family:** Claude  
**Implementation head:** `6606bce8999b3318a8a080ef2e45962de801af23`  
**Verdict:** APPROVE for the exact implementation head above and the receipt-only
PR head named by the `Drain-Review-Head` line in pull request #2811.

## Scope

Production deploy run 33830028060 safely rolled back after the external canary
expected an anonymous cached `converse` call to return transport HTTP 401. The
hosted MCP surface intentionally returns HTTP 200 with a JSON-RPC error
ToolResult carrying the OAuth `mcp/www_authenticate` challenge so connector
clients can start account linking. This patch makes the canary validate that
hosted challenge while preserving HTTP 401 for unauthenticated initialization
and HTTP 403 for the scoped canary principal's `converse` call.

## Independent review

A read-only Claude reviewer inspected the exact implementation head and ran the
focused canary test file. Round one returned `DISAGREE_CONCERN` because the
security-critical `isError: true` assertion lacked a mutation test. The author
added a response fixture parameter and a test proving `isError: false`—the shape
of a successful anonymous dispatch—is rejected with canary exit code 6.

The same reviewer then inspected only that delta at the exact implementation
head, reran the focused test file, and returned `AGREE` / `APPROVE`. The reviewer
confirmed that the new test isolates the `isError` mutation, would fail if the
guard were removed or weakened, and leaves all existing fixture behavior
unchanged.

## Verification

- 110 focused authentication and public-canary tests passed on Windows/Python
  3.11+.
- The independent reviewer reran `tests/test_mcp_public_canary.py`: 33 passed.
- Ruff and `git diff --check` passed.
- The canary defensively rejects malformed JSON-RPC result shapes rather than
  raising an unhandled parsing exception.
- No bearer value is included in the changed diagnostics or test artifacts.

The receipt-only commit changes no canary or test behavior. The PR body binds
that final documentation head to this artifact without requiring a
self-referential commit hash.
