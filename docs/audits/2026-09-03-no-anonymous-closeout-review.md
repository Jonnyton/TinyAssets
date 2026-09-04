# No-anonymous production-truth closeout review

**Date:** 2026-09-03  
**Author family:** Codex  
**Review family:** Claude Sonnet  
**Reviewed head:** `783b503c`  
**Verdict:** APPROVE after the single citation correction recorded below.

## Review contract

The reviewer compared the exact commit with `origin/main`, read the complete
diff, checked the changed authentication requirements against the middleware,
provider, and tool-registration code, inspected production deploy run
`33834837787`, and ran `tests/test_no_anonymous_principal.py` (27 passed). The
review was read-only, used no subagents, and ran no broad suite.

## Structured result

- **AGREE:** no current operating instruction authorizes anonymous platform
  reads; retained older observations are explicitly historical.
- **AGREE:** main identity and live-connector specs match the shipped
  pre-dispatch bearer challenge, named dev identity, OAuth-only tool metadata,
  and runtime `mcp/www_authenticate` challenge.
- **AGREE:** OpenSpec task 12 remains unchecked and archive remains deferred on
  the concrete rendered-client blockers.
- **AGREE:** the founder-canon concern now distinguishes the closed anonymous
  exfiltration path from the still-open public-by-default visibility risk.
- **AGREE:** the deployment receipt accurately records a healthy candidate,
  successful authenticated canary, published release state, and the local
  deployed-sha gate's missing-secret failure.
- **DISAGREE_EVIDENCE:** the lifecycle concern called
  `efa0ed9e39925ba3705a14be5b9836a6b74bb81d` the no-anonymous merge. That is
  PR #2814's status-shape recovery; PR #2800's no-anonymous merge is
  `3fc83fc15fc3e7d06310848f5b931ed0cf645c76`.
- **DISAGREE_CONCERN (non-blocking):** indexing the pre-existing hard-coded
  policy concern was outside the auth scope but correctly repaired a failing
  concerns-index invariant.

## Disposition

The citation now names both commits correctly: `3fc83fc1` for the platform
cutover and `efa0ed9e` for the status-shape recovery. No runtime or behavioral
claim changed after review. The review ended `VERDICT: APPROVE`.
