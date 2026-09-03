/**
 * Browser-side authentication boundary for live MCP reads.
 *
 * Every request under /mcp requires a bearer. Public pages use checked-in
 * snapshots until the visitor connects through an authenticated client.
 */

export const PUBLIC_READ_NEEDS_SIGN_IN =
  "public universe discovery needs a signed-in connector; showing the checked-in snapshot";

/**
 * A public browser has no connector bearer, so it must not start an MCP
 * session or make a data request. Callers catch this explicit refusal and
 * render their labelled checked-in snapshot.
 */
export async function fetchPublicUniverses(_limit = 100): Promise<any[]> {
  throw new Error(PUBLIC_READ_NEEDS_SIGN_IN);
}

export type Vitals = {
  reachable: boolean;
  authRequired?: boolean;
  fetchedAt: string;
  deployedAt?: string | null;
  gitSha?: string | null;
  queue?: {
    pending: number;
    running: number;
    succeeded: number;
    failed: number;
    depth: number;
  } | null;
  lastMovedAt?: string | null;
  universeCount?: number;
  goalCount?: number | null;
  workflowActive?: boolean;
  lastSignalSource?: "universe-activity" | null;
  activityVisible?: boolean;
  error?: string;
};

/**
 * Report authorization state without touching the protected endpoint. This
 * prevents the site from describing an expected 401 as an outage.
 */
export async function fetchVitals(): Promise<Vitals> {
  return {
    reachable: false,
    authRequired: true,
    fetchedAt: new Date().toISOString(),
    activityVisible: false,
    error: "live engine readings are available to signed-in connectors",
  };
}
