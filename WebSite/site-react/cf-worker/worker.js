// Trusted entrypoint for untrusted pull-request preview assets.
//
// Preview JavaScript must not acquire a same-origin bridge to the production
// MCP service. The public server still has unresolved privacy defects, and a
// reviewer opening a PR preview must not grant that PR a privileged data path.
// Wrangler's trusted config forces this handler to run before every asset
// lookup, avoiding selective-route normalization differences.

const BLOCKED_MCP_RESPONSE = JSON.stringify({
  error: "live_mcp_unavailable_in_untrusted_preview",
  message: "This pull-request preview uses checked-in public evidence only.",
});

function normalizePathname(pathname) {
  let decoded = pathname;
  for (let depth = 0; depth < 4 && decoded.includes("%"); depth += 1) {
    try {
      decoded = decodeURIComponent(decoded);
    } catch {
      return null;
    }
  }
  if (decoded.includes("%")) {
    return null;
  }
  if (/[\u0000-\u001f\u007f-\u009f]/u.test(decoded)) {
    return null;
  }

  const segments = [];
  for (const segment of decoded.replaceAll("\\", "/").split("/")) {
    if (segment === "" || segment === ".") {
      continue;
    }
    if (segment === "..") {
      segments.pop();
      continue;
    }
    segments.push(segment.toLowerCase().replace(/[. ]+$/u, ""));
  }
  return `/${segments.join("/")}`;
}

function isBlockedServicePath(pathname) {
  const normalized = normalizePathname(pathname);
  return (
    normalized === null ||
    normalized === "/mcp" ||
    normalized.startsWith("/mcp/") ||
    normalized.startsWith("/.well-known/oauth-") ||
    normalized.startsWith("/.well-known/mcp")
  );
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (isBlockedServicePath(url.pathname)) {
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
