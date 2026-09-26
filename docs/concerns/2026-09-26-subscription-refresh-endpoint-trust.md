# Endpoint trust permits exfiltration and bypasses hardened egress

**Filed:** 2026-09-26
**Verified:** 2026-09-26, Windows/Python 3.14, PR #4032 at `776abaaf`
**Severity:** P1

## Source (verbatim)

> Endpoint trust permits exfiltration and bypasses hardened egress.

Source: finding 2 in [the pinned PR review](../audits/2026-09-26-pr-4032-review.md).

Code at that commit: `subscription_refresh.py:205-215, 331, 352, 378-440; connection_oauth/transport.py:43-62`.

The review contains the verification commands, observed probe outputs, and limits.
Concurrent working-tree fixes were not reviewed; this finding is pinned to the
requested committed head, not a claim about those edits.

## Closure

Bind issuer/client/endpoint to accepted connection provenance, resolve against the locked document, and use hardened OAuth transport for the POST.


## Partially closed on `claude/credential-refresh`

**Verified:** 2026-09-26, Windows/Python 3.14, at the branch head that carries the
fix (not `776abaaf`, which this finding was pinned to). Two of the three legs are closed. The refresh POST goes through the SSRF-hardened broker transport with every carried value declared as a secret (`test_the_refresh_token_is_sent_through_the_hardened_transport`, `test_a_non_https_endpoint_is_refused_before_anything_is_spent`), and the endpoint is now resolved from the document RE-READ under the locks, so a credential can no longer be spent at another issuer's endpoint (`test_the_endpoint_comes_from_the_document_read_under_the_locks`).

STILL OPEN by design, and worth a decision rather than a fix: the issuer still comes from an UNVERIFIED `id_token`. The alternative -- compiling each source's endpoint into the platform -- is what the channel-agnostic ratchet refuses. A signature check against the issuer's published keys would close it without naming any source.
