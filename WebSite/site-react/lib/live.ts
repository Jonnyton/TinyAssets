/**
 * Browser-side live MCP client.
 *
 * Every request under /mcp needs a bearer. Public pages use checked-in
 * snapshots until the visitor connects through an authenticated client.
 */

import type { Snapshot } from "./types";

export type LiveResult = {
  goals: any[];
  universes: any[];
  wiki: { promoted: any[]; drafts: any[] };
  pageDiscovery: {
    scope: "discovery";
    scopeNote: string;
  };
  fetchedAt: string;
};

export const PUBLIC_READ_NEEDS_SIGN_IN =
  "public universe discovery needs a signed-in connector; showing the checked-in snapshot";

/**
 * There is no anonymous read of the MCP surface (founder, 2026-09-02): every
 * request without a bearer is answered with a 401 challenge, initialize
 * included. Public universe and page discovery therefore reject here,
 * without a network call, so each page falls back to its checked-in snapshot
 * and says why. Browser-side release and reachability reads are also withheld.
 */
export async function fetchPublicUniverses(_limit = 100): Promise<any[]> {
  throw new Error(PUBLIC_READ_NEEDS_SIGN_IN);
}

/** See fetchPublicUniverses: rejects without a network call. */
export async function fetchLive(): Promise<LiveResult> {
  throw new Error(PUBLIC_READ_NEEDS_SIGN_IN);
}

export type Vitals = {
  reachable: boolean;
  authRequired?: boolean;
  fetchedAt: string;
  deployedAt?: string | null;
  gitSha?: string | null;
  uptimeSeconds?: number | null;
  queue?: { pending: number; running: number; succeeded: number; failed: number; depth: number } | null;
  lastMovedAt?: string | null;
  universeCount?: number;
  goalCount?: number | null;
  workflowActive?: boolean;
  lastSignalSource?: "universe-activity" | null;
  /** false when activity exists but is not visible without a signed-in client. */
  activityVisible?: boolean;
  error?: string;
};

/**
 * Public browser code has no bearer and therefore makes no MCP request. Return
 * an explicit authorization state so the page never mislabels a protected
 * endpoint as unreachable and never offers a refresh control that cannot work.
 */
export async function fetchVitals(): Promise<Vitals> {
  return {
    reachable: false,
    authRequired: true,
    fetchedAt: new Date().toISOString(),
    activityVisible: false,
    error: "live engine readings are available to signed-in connectors"
  };
}

/** Shape live public data into the same structure used by /wiki and /graph. */
export function liveToSnapshotShape(live: LiveResult, baked: Snapshot): Snapshot {
  const wiki = {
    bugs: [] as any[],
    concepts: [] as any[],
    notes: [] as any[],
    plans: [] as any[],
    drafts: [] as any[],
    other: [] as any[],
  };
  for (const page of live.wiki.promoted) {
    const path = page.path ?? "";
    const title = page.title ?? path;
    if (path.includes("/bugs/")) {
      const match = path.match(/BUG-?(\d+)/i);
      const id = match ? `BUG-${match[1].padStart(3, "0")}` : path;
      wiki.bugs.push({ id, title, slug: path });
    } else if (path.startsWith("drafts/")) {
      wiki.other.push({ slug: path, title });
    } else if (path.includes("/concepts/")) {
      wiki.concepts.push({ slug: path, title });
    } else if (path.includes("/notes/")) {
      wiki.notes.push({ slug: path, title });
    } else if (path.includes("/plans/")) {
      wiki.plans.push({ slug: path, title });
    }
  }
  for (const page of live.wiki.drafts) {
    wiki.drafts.push({ slug: page.path ?? "", title: page.title ?? page.path });
  }

  function dedupBy<T>(items: T[], key: (item: T) => string): T[] {
    const seen = new Set<string>();
    return items.filter((item) => {
      const value = key(item);
      if (seen.has(value)) return false;
      seen.add(value);
      return true;
    });
  }

  wiki.bugs = dedupBy(wiki.bugs, (bug: any) => bug.id);
  wiki.concepts = dedupBy(wiki.concepts, (concept: any) => concept.slug);
  wiki.notes = dedupBy(wiki.notes, (note: any) => note.slug);
  wiki.plans = dedupBy(wiki.plans, (plan: any) => plan.slug);
  wiki.drafts = dedupBy(wiki.drafts, (draft: any) => draft.slug);
  const bugNumber = (id: unknown) => parseInt(String(id ?? "").replace(/\D/g, ""), 10) || 0;
  wiki.bugs.sort((a: any, b: any) => bugNumber(b.id) - bugNumber(a.id));

  const promoted =
    wiki.bugs.length +
    wiki.concepts.length +
    wiki.notes.length +
    wiki.plans.length +
    wiki.other.length;

  return {
    fetched_at: live.fetchedAt,
    source: "tinyassets.io/mcp · live; goals · checked-in snapshot",
    stats: {
      wiki_promoted: promoted,
      wiki_drafts: wiki.drafts.length,
      goals: baked.goals?.length ?? 0,
      universes: live.universes.length,
      edges: baked.edges?.length ?? 0,
    },
    goals: baked.goals ?? [],
    universes: [...live.universes]
      .sort(
        (a, b) =>
          (Date.parse(b.last_activity_at ?? "") || 0) -
          (Date.parse(a.last_activity_at ?? "") || 0),
      )
      .map((universe) => ({
        id: universe.id,
        phase: universe.phase_human ?? universe.phase ?? "unknown",
        word_count: universe.word_count ?? 0,
        last_activity_at: universe.last_activity_at ?? null,
        accept_rate: universe.accept_rate ?? null,
      })),
    wiki,
    edges: baked.edges ?? [],
    tags: baked.tags ?? {},
  };
}
