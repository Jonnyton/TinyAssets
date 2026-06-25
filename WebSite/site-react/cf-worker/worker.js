// Cloudflare Worker for the live-data preview of the React site.
//
// Serves the static export (out/) via the ASSETS binding and proxies /mcp
// same-origin to the live MCP gateway — so the preview shows REAL live data
// (TinyBot/vital signs/goals/graph) with no CORS. Deploys with the existing
// Workers-scoped CLOUDFLARE_API_TOKEN (no Pages permission needed), to a
// *.workers.dev URL. Separate from the production MCP worker.

const UPSTREAM = "https://tinyassets.io/mcp";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/mcp") {
      const headers = new Headers(request.headers);
      headers.delete("host");
      headers.delete("origin");
      headers.delete("referer");
      const upstream = await fetch(UPSTREAM + url.search, {
        method: request.method,
        headers,
        body:
          request.method === "GET" || request.method === "HEAD"
            ? undefined
            : request.body,
        redirect: "manual",
      });
      return new Response(upstream.body, {
        status: upstream.status,
        statusText: upstream.statusText,
        headers: new Headers(upstream.headers),
      });
    }

    // Everything else → static assets from out/.
    return env.ASSETS.fetch(request);
  },
};
