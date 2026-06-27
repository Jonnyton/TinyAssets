// /status SSR — fetches live platform health.
// v0 placeholder: real build subscribes to Supabase Realtime + reads TinyAssets-catalog/status.json.

import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
  return {
    hostsOnline: 0,         // real: Presence aggregate on host_pool:online
    inboxDepth: 0,          // real: count from request_inbox where state='pending'
    catalogFreshness: null, // real: TinyAssets-catalog/catalog/status.json last_batch_at
    recentActivity: [],     // real: node_activity tail with ticker rate-limit
    realtimeUp: false,      // real: probe Realtime connection
  };
};
