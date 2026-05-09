---
title: MCP GET Discovery HTML
date: 2026-05-09
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 712
wiki_source: pages/patch-requests/pr-081-add-mcp-get-discovery-html-for-non-mcp-client-requests-multi.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#api-and-mcp-interface
  - PLAN.md#distribution-and-discoverability
  - PLAN.md#uptime-and-alarm-path
  - docs/design-notes/2026-05-01-mcp-host-customer-matrix.md
  - docs/ops/mcp-host-proof-registry.md
---

# MCP GET Discovery HTML

## 1. Recommendation Summary

Add a human-readable GET fallback for the public MCP endpoint path, starting
with `/mcp`, so browser visits and non-MCP-client link checkers get a useful
discovery page instead of a protocol-shaped error. The fallback must not become
a second product surface, a new MCP primitive, or a dynamic status page. It is
static discovery HTML served only for browser-style GET requests.

The smallest useful implementation is one reusable static page generator mounted
on `/mcp` GET while the existing Streamable HTTP MCP POST/SSE behavior remains
unchanged. A later slice may mount the same pattern on `/mcp-directory` if host
directory reviewers benefit from a distinct directory-safe page. The design
keeps `/` as the general landing page and makes `/mcp` a protocol endpoint with
an explicit human fallback.

## 2. Classification

This is a project-design request with a narrow implementation path. It is not a
bug unless a live host, validator, or canary currently requires GET `/mcp` to be
HTML. It is not an MCP tool-surface feature because it adds no chatbot action
and no daemon capability.

Smallest useful project change in this branch: record the design and acceptance
contract. Runtime changes should be a separate implementation slice with an
opposite-family checker because `/mcp` is a public uptime surface.

## 3. Problem

The public root already has a minimal HTML page, but a user, directory reviewer,
search crawler, accessibility tool, or app validator may visit the advertised
MCP URL itself. Today the user expectation and protocol expectation diverge:

- MCP clients need Streamable HTTP behavior at `/mcp`.
- Humans and generic validators often probe with a browser GET.
- Host-directory reviewers may paste or click the MCP URL during review.
- External accessibility/application checks need a stable page to inspect.

A protocol error is acceptable for a strict MCP client, but it is poor
discoverability for everyone else. The fallback should explain what the endpoint
is, link to install/setup paths, and avoid exposing runtime internals.

## 4. Non-Goals

- Do not add a new MCP action, prompt, resource, or tool.
- Do not change the `/mcp` POST/SSE protocol behavior or the
  `/mcp-directory` directory-safe tool set.
- Do not expose live daemon status, universe counts, issue queues, secrets, or
  deployment metadata on unauthenticated GET.
- Do not make `/mcp` a marketing landing page. `/` and the website own broad
  product narrative.
- Do not treat the fallback as final user-surface verification for MCP behavior.
  A real chatbot conversation through the live connector remains required.

## 5. Proposed Behavior

For browser-style GET requests to `/mcp`, return `200 text/html; charset=utf-8`
with a small static page:

- title: Workflow MCP Endpoint;
- one-line description of Workflow as a daemon engine;
- clear statement that MCP clients should connect to this same URL;
- links to the GitHub repository, root landing page, directory-safe endpoint,
  and public setup/proof docs where appropriate;
- short note that chatbot installation requires an MCP-capable host;
- no script, no external assets, and a body comfortably under 10 KB.

For MCP protocol requests, preserve existing behavior:

- POST initializes and calls tools exactly as today;
- SSE or Streamable HTTP headers continue to work;
- unsupported methods continue to return the framework's protocol response;
- `/mcp-directory` remains the directory-review endpoint unless explicitly
  changed in a follow-up.

Implementation should prefer a small helper such as `_mcp_discovery_html()` plus
one route handler, mirroring the existing root landing handler style. If the
FastMCP mount owns GET `/mcp` in a way that cannot be overlaid safely, the slice
should stop and document the framework constraint rather than routing around the
MCP app.

## 6. Accessibility And External Stake

The external stake named in the request is an AX/application-facing discovery
path: a generic application or accessibility checker should find meaningful
HTML at the endpoint without needing MCP negotiation. That creates a stronger
acceptance bar than "curl returns some bytes."

The page should therefore:

- use semantic HTML (`main`, `h1`, paragraphs, list links);
- have exactly one primary `h1`;
- use descriptive link text rather than bare "click here";
- avoid client-side rendering and animation;
- keep color and layout simple enough for default browser accessibility.

No ARIA role should be added unless native HTML cannot express the structure.
This is a document, not an interactive web application.

## 7. Canary And Verification Contract

Because `/mcp` is a public uptime surface, the implementation slice should land
only with multi-session evidence:

1. Local unit tests prove the GET handler returns static HTML, contains the
   expected links, stays under the size cap, and does not call MCP dispatch.
2. Local protocol tests or canaries prove MCP POST/tool discovery still works on
   `/mcp` and `/mcp-directory`.
3. A browser-style GET canary proves `/mcp` returns `200 text/html` and contains
   the expected title.
4. Existing public canaries remain green after deploy:
   `scripts/mcp_public_canary.py` for `/mcp` and `/mcp-directory`, plus
   `scripts/mcp_tool_canary.py` for both endpoints.
5. Final acceptance for user-visible connector behavior still uses `ui-test`
   through a rendered chatbot conversation when the change is deployed to the
   live connector surface.

The browser GET canary should be separate from the MCP canary. A GET page can be
green while MCP is broken, and MCP can be green while the discovery page is
missing. Collapsing them would hide one class of regression.

## 8. Tradeoffs

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Keep only `/` HTML | No runtime risk | Users and reviewers who open the advertised MCP URL still see a protocol error | Reject |
| Redirect `/mcp` GET to `/` | Very small | Hides that `/mcp` is the connector URL; validators may record the wrong endpoint | Reject |
| Static GET `/mcp` discovery HTML | Clear, cacheable, no daemon state exposure | Requires careful route mounting so POST/SSE is untouched | Recommend |
| Dynamic GET `/mcp` status page | Could show live health | Unauthenticated state exposure and uptime coupling | Reject |
| Separate `/mcp-info` only | Avoids route interaction | Does not help humans or validators who visit `/mcp` directly | Reject |

## 9. Implementation Sketch

1. Add `_MCP_DISCOVERY_HTML` and `_mcp_discovery_index()` near the existing root
   landing page code in `workflow/universe_server.py`.
2. Mount it as a GET-only custom route for `/mcp` without altering the
   Streamable HTTP app's POST/SSE route.
3. Add focused tests next to `tests/test_landing_index.py` or in a new
   `tests/test_mcp_discovery_html.py`:
   - HTML response type and title;
   - required links include `/`, `/mcp-directory`, and GitHub;
   - body is under 10 KB;
   - handler source does not call MCP dispatch or storage;
   - `create_streamable_http_app()` still exposes `/mcp` and
     `/mcp-directory`.
4. Add a small script or extend an existing canary only if it can stay
   method-specific. The preferred shape is a new `scripts/mcp_get_canary.py`
   with stdlib HTTP and no MCP session setup.
5. Run focused tests and ruff on touched Python files. If `workflow/*` runtime
   changes are made, rebuild the Claude plugin mirror with
   `python packaging/claude-plugin/build_plugin.py`.

## 10. Open Questions

1. Should `/mcp-directory` get its own GET fallback in the same runtime slice?
   Recommendation: not in the first implementation unless a host validator is
   known to click the directory URL. Keep the first slice to `/mcp` and reuse
   the helper later.

2. Should `HEAD /mcp` return the same headers as GET without a body?
   Recommendation: acceptable but not required for v1. Add it only if the
   routing framework makes it free and tests prove it does not affect MCP.

3. Should the discovery page link to setup docs or only to GitHub?
   Recommendation: link to stable public setup/proof docs once they are
   considered public-facing. Until then, GitHub plus `/mcp-directory` is enough.

4. Should the page include "server status" language?
   Recommendation: no. Public status belongs in the proof registry, canaries,
   and chatbot-visible MCP tools, not unauthenticated static HTML.

## References

- `PLAN.md` API And MCP Interface
- `PLAN.md` Distribution And Discoverability
- `PLAN.md` Uptime And Alarm Path
- `docs/design-notes/2026-05-01-mcp-host-customer-matrix.md`
- `docs/ops/mcp-host-proof-registry.md`
- `tests/test_landing_index.py`
