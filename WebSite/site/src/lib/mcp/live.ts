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
  publicGoalCall,
  publicGraphCall,
  publicPageCall,
  requireCollection,
  requireObjectResult,
  requirePageBody,
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
  let lastError: unknown = null;

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
        throw new Error(`MCP HTTP ${res.status}: ${res.statusText}`);
      }

      const contentType = res.headers.get('Content-Type') ?? '';
      let text = await res.text();
      if (contentType.includes('text/event-stream')) {
        const dataLine = text.split('\n').find((line) => line.startsWith('data:'));
        if (!dataLine) throw new Error('SSE response missing data line');
        text = dataLine.replace(/^data:\s*/, '');
      }

      const json = JSON.parse(text) as RpcResp;
      if (json.error) throw new Error(`MCP error ${json.error.code}: ${json.error.message}`);
      return json.result;
    } catch (error) {
      lastError = error;
      if (attempt < 2) {
        await sleep(350 * (attempt + 1));
        continue;
      }
    }
  }

  throw lastError instanceof Error ? lastError : new Error('MCP request failed');
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
      body: JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' })
    });
  } catch {}
  initialized = true;
}

export async function callTool(name: string, args: Record<string, any>): Promise<any> {
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
  fetchedAt: string;
};

export async function fetchPublicGoals(limit = 100): Promise<any[]> {
  const goalsCall = publicGraphCall('goals', limit);
  return requireCollection(
    await callTool(goalsCall.name, goalsCall.args),
    'goals',
    'read_graph goals'
  );
}

export async function fetchPublicGoal(goalId: string): Promise<Record<string, any>> {
  const goalCall = publicGoalCall(goalId);
  return requireObjectResult(
    await callTool(goalCall.name, goalCall.args),
    'read_graph goal'
  );
}

export async function fetchPublicUniverses(limit = 100): Promise<any[]> {
  const universesCall = publicGraphCall('graphs', limit);
  return requireCollection(
    await callTool(universesCall.name, universesCall.args),
    'universes',
    'read_graph graphs'
  );
}

/** Fetch the same public collections the checked-in snapshot contains. */
export async function fetchLive(): Promise<LiveResult> {
  // One browser MCP session owns initialization and session-id state, so keep
  // these reads sequential instead of racing the first call through ensureInit.
  const inventoryCall = pageInventoryCall();
  const pageInventory = await callTool(inventoryCall.name, inventoryCall.args);
  const wikiList = splitPageInventory(pageInventory);
  const goals = await fetchPublicGoals();
  const universes = await fetchPublicUniverses();
  return {
    goals,
    universes,
    wiki: {
      promoted: wikiList?.promoted ?? [],
      drafts: wikiList?.drafts ?? []
    },
    fetchedAt: new Date().toISOString()
  };
}

/** Fetch a single public page body for reference extraction. */
export async function fetchPageBody(page: string): Promise<{ content?: string } | null> {
  const pageCall = publicPageCall(page);
  return requirePageBody(
    await callTool(pageCall.name, pageCall.args),
    'read_page body'
  );
}

type WorkflowRun = {
  status: string;
  startedAt: string | null;
  finishedAt: string | null;
};

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

function normalizeRun(raw: any): WorkflowRun {
  return {
    status: String(raw?.status ?? raw?.state ?? 'unknown').toLowerCase(),
    startedAt: normalizeTimestamp(raw?.started_at ?? raw?.startedAt ?? raw?.created_at),
    finishedAt: normalizeTimestamp(raw?.finished_at ?? raw?.finishedAt ?? raw?.completed_at)
  };
}

function runTimestampMs(run: WorkflowRun): number | null {
  return timestampMs(run.finishedAt) ?? timestampMs(run.startedAt);
}

function isTerminalRunStatus(status: string): boolean {
  return ['completed', 'failed', 'cancelled', 'canceled', 'interrupted'].includes(status.toLowerCase());
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
  activeRun?: boolean;
  lastSignalSource?: 'run' | 'universe-activity' | null;
  error?: string;
};

const ACTIVITY_WINDOW_MS = 60 * 60 * 1000;

/**
 * Read server reachability separately from generic user-workflow activity.
 * Activity comes only from public run, queue, or universe signals and does
 * not imply a platform-owned task route.
 */
export async function fetchVitals(): Promise<Vitals> {
  try {
    // Keep the shared browser MCP session deterministic; optional reads still
    // degrade independently after the required status/universe reads succeed.
    const universesCall = publicGraphCall('graphs', 100);
    const runsCall = publicGraphCall('runs', 8);
    const status = requireObjectResult(await callTool('get_status', {}), 'get_status');
    const publicUniverses = requireCollection(
      await callTool(universesCall.name, universesCall.args),
      'universes',
      'read_graph graphs'
    );
    let publicGoals: any[] | null = null;
    let publicRuns: any[] | null = null;
    try {
      publicGoals = await fetchPublicGoals();
    } catch {}
    try {
      publicRuns = requireCollection(
        await callTool(runsCall.name, runsCall.args),
        'runs',
        'read_graph runs'
      );
    } catch {}
    const queue = status?.supervisor_liveness?.queue_state ?? null;
    const release = status?.release_state ?? null;

    let universeMovedMs: number | null = null;
    for (const universe of publicUniverses) {
      const moved = timestampMs(universe?.last_activity_at);
      if (moved !== null && (universeMovedMs === null || moved > universeMovedMs)) {
        universeMovedMs = moved;
      }
    }

    const runs: WorkflowRun[] = publicRuns ? publicRuns.map(normalizeRun) : [];
    const runIsActive = runs.some((run) => !isTerminalRunStatus(run.status));
    let newestRunMs: number | null = null;
    for (const run of runs) {
      const moved = runTimestampMs(run);
      if (moved !== null && (newestRunMs === null || moved > newestRunMs)) newestRunMs = moved;
    }

    const running = Number(queue?.running ?? 0);
    let lastMovedMs: number | null = null;
    let lastSignalSource: 'run' | 'universe-activity' | null = null;
    if (newestRunMs !== null) {
      lastMovedMs = newestRunMs;
      lastSignalSource = 'run';
    }
    if (universeMovedMs !== null && (lastMovedMs === null || universeMovedMs > lastMovedMs)) {
      lastMovedMs = universeMovedMs;
      lastSignalSource = 'universe-activity';
    }

    const recentSignal = lastMovedMs !== null && Date.now() - lastMovedMs < ACTIVITY_WINDOW_MS;

    return {
      reachable: true,
      fetchedAt: new Date().toISOString(),
      deployedAt: release?.deployed_at ?? null,
      gitSha: typeof release?.git_sha === 'string' ? release.git_sha.slice(0, 8) : null,
      queue: queue
        ? {
            pending: Number(queue.pending ?? 0),
            running,
            succeeded: Number(queue.succeeded ?? 0),
            failed: Number(queue.failed ?? 0),
            depth: Number(queue.depth ?? 0)
          }
        : null,
      lastMovedAt: lastMovedMs !== null ? new Date(lastMovedMs).toISOString() : null,
      universeCount: publicUniverses.length,
      goalCount: publicGoals?.length ?? null,
      workflowActive: runIsActive || running > 0 || recentSignal,
      activeRun: runIsActive,
      lastSignalSource
    };
  } catch (error: any) {
    return {
      reachable: false,
      fetchedAt: new Date().toISOString(),
      error: error?.message ?? String(error)
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
    source: 'tinyassets.io/mcp · live',
    stats: {
      wiki_promoted: promoted,
      wiki_drafts: wiki.drafts.length,
      goals: live.goals.length,
      universes: live.universes.length,
      edges: baked.edges?.length ?? 0
    },
    goals: [...live.goals]
      .sort(
        (a, b) =>
          (Date.parse(b.updated_at ?? b.created_at ?? '') || 0) -
          (Date.parse(a.updated_at ?? a.created_at ?? '') || 0)
      )
      .map((goal) => ({
        id: goal.goal_id ?? goal.id,
        name: goal.name ?? '',
        summary: goal.description ?? '',
        tags:
          typeof goal.tags === 'string'
            ? goal.tags
                .split(',')
                .map((tag: string) => tag.trim())
                .filter(Boolean)
            : (goal.tags ?? []),
        author: goal.author ?? 'anonymous',
        visibility: goal.visibility ?? 'public'
      })),
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
