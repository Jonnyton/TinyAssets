/**
 * Browser-side live MCP client.
 *
 * In dev, requests use Vite's /mcp-live proxy. In production they use the
 * same-origin /mcp route. Public pages keep source and read-time labels so a
 * live response is never confused with a checked-in snapshot.
 */

import type { Snapshot } from '$lib/mcp/types';
import {
  pageInventoryCall,
  publicGraphCall,
  requirePublicUniverseCollection,
  splitPageInventory
} from '../../../../shared/mcp/public-read-contract.js';

const MCP_PATH = import.meta.env.DEV ? '/mcp-live' : '/mcp';

let initialized = false;
let sessionId: string | null = null;
let nextId = 1;

type RpcResp = {
  jsonrpc: '2.0';
  id: number;
  result?: any;
  error?: { code: number; message: string };
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function rpc(method: string, params: any = {}): Promise<any> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json, text/event-stream'
  };
  if (sessionId) headers['Mcp-Session-Id'] = sessionId;

  const body = { jsonrpc: '2.0', id: nextId++, method, params };
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const res = await fetch(MCP_PATH, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
        credentials: 'omit'
      });

      const sid = res.headers.get('Mcp-Session-Id');
      if (sid && !sessionId) sessionId = sid;

      if (!res.ok) {
        if ([502, 503, 504].includes(res.status) && attempt < 2) {
          await sleep(350 * (attempt + 1));
          continue;
        }
        throw new Error(`Public MCP request failed (HTTP ${res.status})`);
      }

      const contentType = res.headers.get('Content-Type') ?? '';
      let text = await res.text();
      if (contentType.includes('text/event-stream')) {
        const dataLine = text.split('\n').find((line) => line.startsWith('data:'));
        if (!dataLine) throw new Error('SSE response missing data line');
        text = dataLine.replace(/^data:\s*/, '');
      }

      const json = JSON.parse(text) as RpcResp;
      if (json.error) {
        const code = Number.isInteger(json.error.code) ? ` (code ${json.error.code})` : "";
        throw new Error(`Public MCP request failed${code}`);
      }
      return json.result;
    } catch (error) {
      if (attempt < 2) {
        await sleep(350 * (attempt + 1));
        continue;
      }
    }
  }

  throw new Error('Public MCP read is unavailable');
}

async function ensureInit(): Promise<void> {
  if (initialized) return;
  await rpc('initialize', {
    protocolVersion: '2025-06-18',
    clientInfo: { name: 'tinyassets-site-live', version: '0.1.0' },
    capabilities: {}
  });
  try {
    await fetch(MCP_PATH, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json, text/event-stream',
        ...(sessionId ? { 'Mcp-Session-Id': sessionId } : {})
      },
      body: JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }),
      credentials: 'omit'
    });
  } catch {}
  initialized = true;
}

async function callTool(name: string, args: Record<string, any>): Promise<any> {
  await ensureInit();
  const result = await rpc('tools/call', { name, arguments: args });
  if (result?.structuredContent && typeof result.structuredContent === 'object') {
    return result.structuredContent;
  }
  const textItem = result?.content?.find((item: any) => item?.type === 'text');
  if (!textItem?.text) return null;
  try {
    const parsed = JSON.parse(textItem.text);
    if (parsed && typeof parsed.result === 'string') {
      try {
        return JSON.parse(parsed.result);
      } catch {
        return parsed.result;
      }
    }
    return parsed;
  } catch {
    return textItem.text;
  }
}

export type LiveResult = {
  goals: any[];
  universes: any[];
  wiki: { promoted: any[]; drafts: any[] };
  pageDiscovery: {
    scope: 'discovery';
    scopeNote: string;
  };
  fetchedAt: string;
};

export async function fetchPublicUniverses(limit = 100): Promise<any[]> {
  const universesCall = publicGraphCall('graphs', limit);
  return requirePublicUniverseCollection(
    await callTool(universesCall.name, universesCall.args),
    'read_graph graphs',
    limit
  );
}

/** Fetch the same public collections the checked-in snapshot contains. */
export async function fetchLive(): Promise<LiveResult> {
  // One browser MCP session owns initialization and session-id state, so keep
  // these reads sequential instead of racing the first call through ensureInit.
  const inventoryCall = pageInventoryCall();
  const pageInventory = await callTool(inventoryCall.name, inventoryCall.args);
  const wikiList = splitPageInventory(pageInventory);
  const universes = await fetchPublicUniverses();
  return {
    // Goals remain checked-in snapshot data until the server exposes a
    // server-enforced public-only projection.
    goals: [],
    universes,
    wiki: {
      promoted: wikiList?.promoted ?? [],
      drafts: wikiList?.drafts ?? []
    },
    // splitPageInventory already proved this exact scope/note pair.
    pageDiscovery: {
      scope: wikiList.scope,
      scopeNote: wikiList.scopeNote
    },
    fetchedAt: new Date().toISOString()
  };
}

function normalizeTimestamp(value: unknown): string | null {
  if (value === null || value === undefined || value === '') return null;
  const text = String(value).trim();
  if (!text) return null;
  if (typeof value === 'number' || /^\d+(\.\d+)?$/.test(text)) {
    const numeric = Number(text);
    if (Number.isFinite(numeric)) {
      const date = new Date(numeric > 1_000_000_000_000 ? numeric : numeric * 1000);
      if (!Number.isNaN(date.getTime())) return date.toISOString();
    }
  }
  const parsed = Date.parse(text);
  return Number.isNaN(parsed) ? null : new Date(parsed).toISOString();
}

function timestampMs(value: unknown): number | null {
  const normalized = normalizeTimestamp(value);
  if (!normalized) return null;
  const parsed = Date.parse(normalized);
  return Number.isNaN(parsed) ? null : parsed;
}

export type Vitals = {
  reachable: boolean;
  fetchedAt: string;
  deployedAt?: string | null;
  gitSha?: string | null;
  queue?: { pending: number; running: number; succeeded: number; failed: number; depth: number } | null;
  lastMovedAt?: string | null;
  universeCount?: number;
  goalCount?: number | null;
  workflowActive?: boolean;
  lastSignalSource?: 'universe-activity' | null;
  error?: string;
};

const ACTIVITY_WINDOW_MS = 60 * 60 * 1000;

/**
 * Read reachability and activity only from the public universe projection.
 * The operator get_status payload includes raw logs and identifiers, so public
 * browsers must not download it merely to select a few aggregate fields.
 */
export async function fetchVitals(): Promise<Vitals> {
  try {
    const universesCall = publicGraphCall('graphs', 100);
    const publicUniverses = requirePublicUniverseCollection(
      await callTool(universesCall.name, universesCall.args),
      'read_graph graphs',
      100
    );
    let universeMovedMs: number | null = null;
    for (const universe of publicUniverses) {
      const moved = timestampMs(universe?.last_activity_at);
      if (moved !== null && (universeMovedMs === null || moved > universeMovedMs)) {
        universeMovedMs = moved;
      }
    }

    const lastMovedMs = universeMovedMs;
    const lastSignalSource: 'universe-activity' | null =
      universeMovedMs === null ? null : 'universe-activity';

    const recentSignal = lastMovedMs !== null && Date.now() - lastMovedMs < ACTIVITY_WINDOW_MS;

    return {
      reachable: true,
      fetchedAt: new Date().toISOString(),
      deployedAt: null,
      gitSha: null,
      queue: null,
      lastMovedAt: lastMovedMs !== null ? new Date(lastMovedMs).toISOString() : null,
      universeCount: publicUniverses.length,
      goalCount: null,
      workflowActive: recentSignal,
      lastSignalSource
    };
  } catch (error: any) {
    return {
      reachable: false,
      fetchedAt: new Date().toISOString(),
      error: 'Public MCP read is unavailable'
    };
  }
}

/** Shape live public data into the snapshot structure used by /wiki and /graph. */
export function liveToSnapshotShape(live: LiveResult, baked: Snapshot): Snapshot {
  const wiki = {
    bugs: [] as any[],
    concepts: [] as any[],
    notes: [] as any[],
    plans: [] as any[],
    drafts: [] as any[],
    other: [] as any[]
  };

  for (const page of live.wiki.promoted) {
    const path = page.path ?? '';
    const title = page.title ?? path;
    if (path.includes('/bugs/')) {
      const match = path.match(/BUG-?(\d+)/i);
      const id = match ? `BUG-${match[1].padStart(3, '0')}` : path;
      wiki.bugs.push({ id, title, slug: path });
    } else if (path.startsWith('drafts/')) {
      wiki.other.push({ slug: path, title });
    } else if (path.includes('/concepts/')) {
      wiki.concepts.push({ slug: path, title });
    } else if (path.includes('/notes/')) {
      wiki.notes.push({ slug: path, title });
    } else if (path.includes('/plans/')) {
      wiki.plans.push({ slug: path, title });
    }
  }

  for (const page of live.wiki.drafts) {
    wiki.drafts.push({ slug: page.path ?? '', title: page.title ?? page.path });
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

  const bugNumber = (id: unknown) => parseInt(String(id ?? '').replace(/\D/g, ''), 10) || 0;
  wiki.bugs.sort((a: any, b: any) => bugNumber(b.id) - bugNumber(a.id));

  const promoted =
    wiki.bugs.length +
    wiki.concepts.length +
    wiki.notes.length +
    wiki.plans.length +
    wiki.other.length;

  return {
    fetched_at: live.fetchedAt,
    source: 'tinyassets.io/mcp · live; goals · checked-in snapshot',
    stats: {
      wiki_promoted: promoted,
      wiki_drafts: wiki.drafts.length,
      goals: baked.goals?.length ?? 0,
      universes: live.universes.length,
      edges: baked.edges?.length ?? 0
    },
    goals: baked.goals ?? [],
    universes: [...live.universes]
      .sort(
        (a, b) =>
          (Date.parse(b.last_activity_at ?? '') || 0) -
          (Date.parse(a.last_activity_at ?? '') || 0)
      )
      .map((universe) => ({
        id: universe.id,
        phase: universe.phase_human ?? universe.phase ?? 'unknown',
        word_count: universe.word_count ?? 0,
        last_activity_at: universe.last_activity_at ?? null,
        accept_rate: universe.accept_rate ?? null
      })),
    wiki,
    edges: baked.edges ?? [],
    tags: baked.tags ?? {}
  };
}
