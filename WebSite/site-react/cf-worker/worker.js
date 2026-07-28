// Trusted entrypoint for untrusted pull-request preview assets.
//
// Preview JavaScript must not acquire a same-origin bridge to the production
// MCP service. The public server still has unresolved privacy defects, and a
// reviewer opening a PR preview must not grant that PR a privileged data path.
// Wrangler's trusted config forces this handler to run before assets for both
// /mcp and /mcp/*, including when the artifact contains shadowing files.

const BLOCKED_MCP_RESPONSE = JSON.stringify({
  error: "live_mcp_unavailable_in_untrusted_preview",
  message: "This pull-request preview uses checked-in public evidence only.",
});

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/mcp" || url.pathname.startsWith("/mcp/")) {
      return new Response(BLOCKED_MCP_RESPONSE, {
        status: 503,
        headers: {
          "cache-control": "no-store",
          "content-type": "application/json; charset=utf-8",
          "x-content-type-options": "nosniff",
        },
      });
    }

    return env.ASSETS.fetch(request);
  },
};
