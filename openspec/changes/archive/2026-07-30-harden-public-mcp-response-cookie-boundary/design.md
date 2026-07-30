## Context

The public Worker injects Cloudflare Access service-token request headers to
reach the internal tunnel origin. Its response loop currently copies every
header except the RFC hop-by-hop set. Because `Set-Cookie` is end-to-end rather
than hop-by-hop, an Access authorization cookie can cross that trust boundary.
The response body is already passed through as the original `ReadableStream`.

Two active changes also carry full-body deltas for `Cloudflare Worker Public
Front Door`. This change syncs its narrow fail-closed response rule into the
main spec; those later changes must preserve it when their own deltas are
reconciled.

## Goals / Non-Goals

**Goals:**

- Prevent every upstream response cookie from reaching a public MCP caller.
- Preserve streaming, status, status text, and allowed non-cookie headers.
- Leave a focused regression test for both Access and application cookies.
- Keep deployment and live acceptance explicit after merge.

**Non-Goals:**

- Do not parse, rewrite, or selectively allow cookies.
- Do not change request headers, authentication, routes, CORS, or Worker
  configuration.
- Do not buffer or inspect response bodies.
- Do not claim live remediation before deployment and healthy-path evidence.

## Decisions

1. Add `set-cookie` to the existing response-header deny set. Header matching
   remains case-insensitive because the copy loop already lowercases names.
   This is the smallest shared boundary and covers every response path that
   passes through the upstream header loop.

2. Strip all response cookies, not only cookies whose serialized value appears
   to contain `CF_Authorization`. A public stateless MCP proxy has no contract
   to set origin cookies, and selective parsing risks combined-header,
   capitalization, attribute, and future credential-name bypasses.

3. Keep the upstream body object unchanged. Tests assert cookie removal
   separately from the existing stream-identity proof so the security rule
   cannot accidentally turn into response buffering.

4. Sync the modified requirement on merge. The active
   `public-read-completeness` and `reconcile-external-connector-manifests`
   full-body deltas are not edited in this lane; their existing reconciliation
   gate must incorporate the then-current main requirement, including this
   cookie rule.

## Risks / Trade-offs

- [An origin later needs a public cookie] → Require an explicit, separately
  reviewed public-front-door contract instead of silently weakening this
  credential boundary.
- [A future full-body delta overwrites the rule] → Sync now, cite the two active
  delta owners in design, and verify main-spec preservation during foldback.
- [Tests pass but production still serves the old Worker] → Keep the P0 concern
  until deploy SHA, healthy-path sanitized probe, rendered chatbot, and
  post-fix clean-use evidence exist.

## Migration Plan

1. Land the Worker code, regression test, and synced specification through the
   normal reviewed PR path.
2. Deploy through the owning Worker pipeline.
3. Run the canonical public canary and a sanitized healthy upstream response
   probe without recording cookie values.
4. Run rendered chatbot verification and look for post-fix clean-user evidence.
5. Retire the STATUS concern only when all live gates pass. Roll back the Worker
   commit if allowed response headers or streaming regress; never restore cookie
   forwarding as a workaround.

## Open Questions

None for the code slice. Deployment and live proof remain post-merge gates.
