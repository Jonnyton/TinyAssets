// /catalog home — loads top-N candidates via discover_nodes RPC.
// v0 calls the local gateway at localhost:8001; real build hits the
// control-plane RPC with a real intent embedding.

import type { PageServerLoad } from './$types';

type Candidate = {
  node_id: string;
  slug: string;
  name: string;
  domain: string;
  quality?: { usage_count?: number; upvote_count?: number };
};

export const load: PageServerLoad = async ({ fetch }) => {
  const gatewayUrl = import.meta.env.VITE_TINYASSETS_GATEWAY_URL ?? 'http://localhost:8001/mcp';

  // Stub intent + embedding for v0 — real build computes via Edge Function.
  // In this prototype, if the gateway is up we call it; otherwise fall back
  // to an empty list so the page still renders.
  let candidates: Candidate[] = [];
  try {
    const res = await fetch(`${gatewayUrl}/discover_nodes`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        intent: 'browse',
        intent_embedding: Array(16).fill(0.5), // v0 16-dim stub
        limit: 20,
        cross_domain: true,
      }),
    });
    if (res.ok) {
      const payload = await res.json();
      candidates = payload.candidates ?? [];
    }
  } catch (_err) {
    // Gateway not running — render empty state. No error surface at prototype stage.
  }

  return { candidates };
};
