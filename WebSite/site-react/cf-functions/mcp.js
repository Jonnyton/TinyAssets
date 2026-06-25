// Cloudflare Pages Function — same-origin /mcp proxy for the hosted preview.
//
// The live MCP gateway (https://tinyassets.io/mcp) returns 403 to cross-origin
// browser requests (no CORS). On the *.pages.dev preview we instead call our
// OWN /mcp, which this function proxies server-side to the live endpoint — so
// the browser sees a same-origin response (no CORS) and TinyBot / VitalSigns /
// goals / graph show real live data instead of the "unreachable" state.
//
// Deployed by the preview workflow, which copies this file to out/functions/mcp.js
// before `wrangler pages deploy`. NOT used by the real apex site (that serves
// /mcp same-origin via the Cloudflare Worker route already).

const UPSTREAM = "https://tinyassets.io/mcp";

export async function onRequest(context) {
  const { request } = context;
  const incoming = new URL(request.url);
  const target = UPSTREAM + incoming.search;

  // Forward method, headers, and body verbatim; strip hop-by-hop/host bits.
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("origin");
  headers.delete("referer");

  const init = {
    method: request.method,
    headers,
    body:
      request.method === "GET" || request.method === "HEAD"
        ? undefined
        : request.body,
    redirect: "manual",
  };

  const upstreamResp = await fetch(target, init);

  // Pass the (possibly streamed, e.g. text/event-stream) response straight back.
  // It's same-origin to the browser, so no CORS headers are needed.
  const respHeaders = new Headers(upstreamResp.headers);
  return new Response(upstreamResp.body, {
    status: upstreamResp.status,
    statusText: upstreamResp.statusText,
    headers: respHeaders,
  });
}
