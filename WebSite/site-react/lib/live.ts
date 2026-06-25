/**
 * Browser-side live MCP client.
 *
 * In dev: fetch hits /mcp-live → vite proxy → https://tinyassets.io/mcp
 * In prod: fetch hits /mcp directly (same origin as the deployed site).
 *
 * Uses raw JSON-RPC over HTTP — simpler than dragging the full SDK into the
 * browser bundle, and the gateway at tinyassets.io accepts plain
 * `Content-Type: application/json` POSTs.
 */

import type { Snapshot } from './types';

// Same-origin in prod (the /mcp Worker route is served on tinyassets.io).
// For local dev, point NEXT_PUBLIC_MCP_PATH at a proxy or the live endpoint.
const MCP_PATH =
  (typeof process !== 'undefined' && process.env.NEXT_PUBLIC_MCP_PATH) || '/mcp';

let initialized = false;
let sessionId: string | null = null;
let nextId = 1;

type RpcResp = { jsonrpc: '2.0'; id: number; result?: any; error?: { code: number; message: string } };

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

      // Capture session id on first call
      const sid = res.headers.get('Mcp-Session-Id');
      if (sid && !sessionId) sessionId = sid;

      if (!res.ok) {
        if ([502, 503, 504].includes(res.status) && attempt < 2) {
          await sleep(350 * (attempt + 1));
          continue;
        }
        throw new Error(`MCP HTTP ${res.status}: ${res.statusText}`);
      }

      // Some gateways return text/event-stream; parse first data line.
      const ct = res.headers.get('Content-Type') ?? '';
      let text = await res.text();
      if (ct.includes('text/event-stream')) {
        const dataLine = text.split('\n').find((l) => l.startsWith('data:'));
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
  // Some servers require a notifications/initialized after — best effort.
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
  // The server moved canonical tool output into `structuredContent` (MCP
  // structured output). `content[].text` is now often just a human summary
  // (e.g. wiki list -> "promoted=1173, drafts=221") or a pointer
  // ("Tool result available in structuredContent"), so prefer the structured
  // payload when present and only fall back to parsing the text blob.
  if (result?.structuredContent && typeof result.structuredContent === 'object') {
    return result.structuredContent;
  }
  const t = result?.content?.find((c: any) => c?.type === 'text');
  if (!t?.text) return null;
  try {
    const parsed = JSON.parse(t.text);
    if (parsed && typeof parsed.result === 'string') {
      try { return JSON.parse(parsed.result); } catch { return parsed.result; }
    }
    return parsed;
  } catch {
    return t.text;
  }
}

// ============ Public surface ============

export type LiveResult = {
  goals: any[];
  universes: any[];
  wiki: { promoted: any[]; drafts: any[] };
  fetchedAt: string;
};

/** Fetch the same data the snapshot bakes — but live. */
export async function fetchLive(): Promise<LiveResult> {
  const [wikiList, goalsList, universesList] = await Promise.all([
    callTool('wiki', { action: 'list' }),
    callTool('goals', { action: 'list' }),
    callTool('universe', { action: 'list' })
  ]);
  return {
    goals: goalsList?.goals ?? [],
    universes: universesList?.universes ?? [],
    wiki: {
      promoted: wikiList?.promoted ?? [],
      drafts: wikiList?.drafts ?? []
    },
    fetchedAt: new Date().toISOString()
  };
}

/** Fetch the live community-change (patch) loop queue: open requests, auto-fix
 *  runs, open PRs, and the review standard. Backs the /patch-loop page. */
export async function fetchChangeContext(limit = 8): Promise<any> {
  return await callTool('community_change_context', { limit });
}

/** Fetch a single page's body (for ref-extraction). */
export async function fetchPageBody(page: string): Promise<{ content?: string } | null> {
  return await callTool('wiki', { action: 'read', page: page.replace(/\.md$/, '') });
}

export type LoopStageId = 'intake' | 'investigation' | 'gate' | 'coding' | 'release' | 'observe';

export type LoopPatchRun = {
  run_id: string;
  branch_def_id: string;
  name: string;
  status: string;
  actor?: string;
  started_at?: string | null;
  finished_at?: string | null;
  last_node_id?: string;
  current_stage: LoopStageId;
  error?: string;
  failure_class?: string;
  suggested_action?: string;
};

export type LoopPatchEvent = {
  id: string;
  run_id?: string;
  stage: LoopStageId;
  status: string;
  title: string;
  detail: string;
  at?: string | null;
  node_id?: string;
  source: string;
};

export type PatchLoopFeed = {
  source: string;
  fetchedAt: string;
  live: boolean;
  overall?: string;
  branchDefId?: string;
  activeRunId?: string;
  runs: LoopPatchRun[];
  events: LoopPatchEvent[];
  warnings: string[];
};

export type PatchLoopFeedSource = 'mcp' | 'github';

const CHANGE_LOOP_BRANCH_IDS = ['fd5c66b1d87d', 'change_loop_v1'];

const KNOWN_LOOP_NODES: Record<string, LoopStageId> = {
  intake_router: 'intake',
  investigation_gate: 'investigation',
  coding_dispatch: 'coding',
  review_release_gate: 'gate',
  release_safety_gate: 'release',
  live_observation_gate: 'observe',
  evolution_notes: 'observe'
};

const STAGE_TERMS: Record<LoopStageId, string[]> = {
  intake: ['intake', 'file_bug', 'file bug', 'request', 'report', 'classify', 'trigger', 'submitted', 'queued'],
  investigation: ['investigation', 'investigate', 'repro', 'root cause', 'cause', 'analysis', 'patch_packet', 'packet'],
  gate: ['gate', 'verdict', 'evidence', 'scope', 'decision', 'route', 'approved', 'rejected'],
  coding: ['coding', 'code', 'dev', 'writer', 'auto-fix', 'implement', 'patch', 'branch', 'diff', 'pr'],
  release: ['release', 'review', 'merge', 'ship', 'deploy', 'production', 'website', 'rollback', 'landed'],
  observe: ['observe', 'observation', 'watch', 'canary', 'monitor', 'ratify', 'user_sim', 'clean use']
};

const HISTORICAL_TERMINAL_RUN_MS = 2 * 60 * 60 * 1000;

function stringify(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return '';
  }
}

function isSparseText(value: string): boolean {
  const text = value.trim();
  return !text || text === '{}' || text === '[]' || text === 'null' || text === 'undefined';
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    const text = stringify(value).trim();
    if (text) return text;
  }
  return '';
}

function firstDetailString(...values: unknown[]): string {
  for (const value of values) {
    const text = stringify(value).trim();
    if (!isSparseText(text)) return text;
  }
  return '';
}

function normalizeTimestamp(value: unknown): string | null {
  const text = firstString(value);
  if (!text) return null;
  if (typeof value === 'number' || /^\d+(\.\d+)?$/.test(text)) {
    const numeric = Number(text);
    if (Number.isFinite(numeric)) {
      const millis = numeric > 1_000_000_000_000 ? numeric : numeric * 1000;
      const date = new Date(millis);
      if (!Number.isNaN(date.getTime())) return date.toISOString();
    }
  }
  const parsed = Date.parse(text);
  if (!Number.isNaN(parsed)) return new Date(parsed).toISOString();
  return text;
}

function timestampMs(value: unknown): number | null {
  const normalized = normalizeTimestamp(value);
  if (!normalized) return null;
  const parsed = Date.parse(normalized);
  return Number.isNaN(parsed) ? null : parsed;
}

function runTimestampMs(run: LoopPatchRun): number | null {
  return timestampMs(run.finished_at) ?? timestampMs(run.started_at);
}

function isTerminalRunStatus(status: string): boolean {
  return ['completed', 'failed', 'cancelled', 'canceled'].includes(status.toLowerCase());
}

function isHistoricalTerminalRun(run: LoopPatchRun, nowMs = Date.now()): boolean {
  const at = runTimestampMs(run);
  return isTerminalRunStatus(run.status) && at !== null && nowMs - at > HISTORICAL_TERMINAL_RUN_MS;
}

function isRecentRun(run: LoopPatchRun, nowMs = Date.now()): boolean {
  const at = runTimestampMs(run);
  return at !== null && nowMs - at <= 36 * 60 * 60 * 1000;
}

function humanizeNodeId(value: unknown): string {
  const text = firstString(value);
  if (!text) return '';
  return text
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function inferLoopStage(...values: unknown[]): LoopStageId {
  for (const value of values) {
    const text = stringify(value).toLowerCase();
    for (const [nodeId, stage] of Object.entries(KNOWN_LOOP_NODES) as Array<[string, LoopStageId]>) {
      if (text === nodeId || text.includes(nodeId)) return stage;
    }
  }
  const haystack = values.map(stringify).join(' ').toLowerCase();
  for (const [stage, terms] of Object.entries(STAGE_TERMS) as Array<[LoopStageId, string[]]>) {
    if (terms.some((term) => haystack.includes(term))) return stage;
  }
  return 'intake';
}

function normalizeRun(raw: any): LoopPatchRun {
  const runId = firstString(raw?.run_id, raw?.id, raw?.runId);
  const branchDefId = firstString(raw?.branch_def_id, raw?.branchDefId, raw?.branch_id, raw?.workflow, raw?.branch);
  const name = firstString(raw?.run_name, raw?.name, raw?.title, runId);
  const lastNode = firstString(raw?.last_node_id, raw?.lastNodeId, raw?.node_id, raw?.current_node);
  const status = firstString(raw?.status, raw?.state, 'unknown').toLowerCase();
  const error = firstDetailString(raw?.error, raw?.failure, raw?.exception);

  return {
    run_id: runId,
    branch_def_id: branchDefId,
    name,
    status,
    actor: firstString(raw?.actor, raw?.author, raw?.claimed_by) || undefined,
    started_at: normalizeTimestamp(raw?.started_at ?? raw?.startedAt ?? raw?.created_at),
    finished_at: normalizeTimestamp(raw?.finished_at ?? raw?.finishedAt ?? raw?.completed_at),
    last_node_id: lastNode,
    current_stage: inferLoopStage(lastNode, name, status, error),
    error: error || undefined,
    failure_class: firstString(raw?.failure_class, raw?.failureClass) || undefined,
    suggested_action: firstDetailString(raw?.suggested_action, raw?.suggestedAction) || undefined
  };
}

function normalizeEvent(raw: any, index: number, run?: LoopPatchRun): LoopPatchEvent {
  const runId = firstString(raw?.run_id, raw?.runId, run?.run_id);
  const nodeId = firstString(raw?.node_id, raw?.nodeId, raw?.node, raw?.step, raw?.stage);
  const status = firstString(raw?.status, raw?.state, raw?.event_type, raw?.type, run?.status, 'event').toLowerCase();
  const title = firstString(raw?.title, raw?.label, humanizeNodeId(nodeId), raw?.event_type, raw?.type, 'Loop event');
  const detail = firstDetailString(
    raw?.detail,
    raw?.message,
    raw?.text,
    raw?.summary,
    raw?.output_summary,
    raw?.error,
    raw?.patch_title,
    run?.name,
    'Loop state changed.'
  );
  const step = firstString(raw?.step_index, raw?.index, index);
  const fallbackDetail = run?.error
    ? `${status === 'pending' ? 'Pending when run failed' : 'Run failed'}: ${run.error}`
    : `${title} is ${status}.`;

  return {
    id: firstString(raw?.event_id, raw?.id, `${runId || 'loop'}:${step}:${nodeId || title}`),
    run_id: runId || undefined,
    stage: inferLoopStage(raw?.stage, nodeId, title, detail, status, run?.error),
    status,
    title,
    detail: detail || fallbackDetail,
    at: normalizeTimestamp(raw?.created_at ?? raw?.timestamp ?? raw?.at ?? raw?.started_at ?? run?.started_at),
    node_id: nodeId || undefined,
    source: firstString(raw?.source, 'MCP run event')
  };
}

function runToEvent(run: LoopPatchRun, index: number): LoopPatchEvent {
  const at = run.finished_at ?? run.started_at ?? null;
  const status = run.status || 'unknown';
  const stage = status.includes('complete')
    ? 'observe'
    : status.includes('fail') || status.includes('error')
      ? 'gate'
      : inferLoopStage(run.last_node_id, run.name, status, run.error);
  return {
    id: `mcp-run:${run.run_id || index}`,
    run_id: run.run_id,
    stage,
    status,
    title: run.name || `Branch run ${run.run_id}`,
    detail: [
      run.branch_def_id ? `branch ${run.branch_def_id}` : '',
      run.run_id ? `run ${run.run_id}` : '',
      run.error
    ].filter(Boolean).join(' - ') || 'MCP branch run changed state.',
    at,
    node_id: run.last_node_id,
    source: 'MCP extensions list_runs'
  };
}

function runLooksLikePatchLoop(run: LoopPatchRun): boolean {
  const text = `${run.branch_def_id} ${run.name} ${run.last_node_id ?? ''}`.toLowerCase();
  return CHANGE_LOOP_BRANCH_IDS.some((id) => text.includes(id.toLowerCase())) ||
    text.includes('change_loop') ||
    text.includes('patch') ||
    text.includes('bug_investigation');
}

function activeRun(runs: LoopPatchRun[]): LoopPatchRun | undefined {
  return runs.find((run) => !isTerminalRunStatus(run.status));
}

function latestRun(runs: LoopPatchRun[]): LoopPatchRun | undefined {
  return [...runs].sort((a, b) => (runTimestampMs(b) ?? 0) - (runTimestampMs(a) ?? 0))[0];
}

function mergeRunSnapshot(run: LoopPatchRun | undefined, snapshot: any): void {
  if (!run || !snapshot || typeof snapshot !== 'object') return;
  run.error = firstDetailString(snapshot.error, snapshot.failure, snapshot.exception, run.error) || undefined;
  run.failure_class = firstString(snapshot.failure_class, snapshot.failureClass, run.failure_class) || undefined;
  run.suggested_action = firstDetailString(snapshot.suggested_action, snapshot.suggestedAction, run.suggested_action) || undefined;
  run.finished_at = normalizeTimestamp(snapshot.finished_at ?? snapshot.finishedAt ?? snapshot.completed_at) ?? run.finished_at;
  run.started_at = normalizeTimestamp(snapshot.started_at ?? snapshot.startedAt ?? snapshot.created_at) ?? run.started_at;
  run.last_node_id = firstString(snapshot.last_node_id, snapshot.lastNodeId, snapshot.node_id, run.last_node_id) || run.last_node_id;
  run.current_stage = inferLoopStage(run.last_node_id, run.name, run.status, run.error);
}

function normalizeLoopToolFeed(raw: any): PatchLoopFeed | null {
  const body = raw?.feed ?? raw?.result ?? raw;
  if (!body || typeof body !== 'object') return null;

  const runs = Array.isArray(body.runs) ? body.runs.map(normalizeRun) : [];
  const directEvents = Array.isArray(body.events) ? body.events : [];
  const patchEvents = Array.isArray(body.patches)
    ? body.patches.flatMap((patch: any) => {
        const events = Array.isArray(patch?.events) ? patch.events : [];
        return events.map((event: any) => ({
          ...event,
          run_id: event?.run_id ?? patch?.run_id ?? patch?.id,
          patch_title: event?.patch_title ?? patch?.title ?? patch?.name
        }));
      })
    : [];
  const selectedRun = activeRun(runs);
  const events = [...directEvents, ...patchEvents].map((event, index) => normalizeEvent(event, index, selectedRun));

  if (!runs.length && !events.length) return null;

  return {
    source: firstString(body.source, 'MCP loop action=feed'),
    fetchedAt: firstString(body.fetched_at, body.fetchedAt, new Date().toISOString()),
    live: true,
    branchDefId: firstString(body.branch_def_id, selectedRun?.branch_def_id, CHANGE_LOOP_BRANCH_IDS[0]),
    activeRunId: firstString(body.active_run_id, body.activeRunId, selectedRun?.run_id) || undefined,
    runs,
    events,
    warnings: []
  };
}

function warningText(prefix: string, error: unknown): string {
  return `${prefix}: ${error instanceof Error ? error.message : stringify(error) || 'unavailable'}`;
}

type CommunityLoopWatchStage = {
  name: string;
  status: string;
  summary: string;
  evidence?: string | null;
  url?: string | null;
  details?: Record<string, any>;
};

type CommunityLoopWatchStatus = {
  version?: number;
  checked_at?: string;
  repo?: string | null;
  overall?: string;
  stages?: CommunityLoopWatchStage[];
};

type GitHubIssue = {
  number?: number;
  title?: string;
  html_url?: string;
  updated_at?: string;
  created_at?: string;
  body?: string;
  labels?: Array<string | { name?: string }>;
  pull_request?: unknown;
};

type GitHubWorkflowRun = {
  id?: number;
  html_url?: string;
  status?: string;
  conclusion?: string | null;
  created_at?: string;
  updated_at?: string;
  event?: string;
};

function jsonFromMarkdown(text: string): CommunityLoopWatchStatus | null {
  const blocks = Array.from(text.matchAll(/```json\s*([\s\S]*?)```/gi)).map((match) => match[1]?.trim()).filter(Boolean);
  for (const block of blocks.reverse()) {
    try {
      const parsed = JSON.parse(block);
      if (parsed?.stages && Array.isArray(parsed.stages)) return parsed;
    } catch {}
  }
  try {
    const parsed = JSON.parse(text);
    if (parsed?.stages && Array.isArray(parsed.stages)) return parsed;
  } catch {}
  return null;
}

function communityStatusToFeed(status: CommunityLoopWatchStatus, source: string, warnings: string[] = []): PatchLoopFeed {
  const checkedAt = status.checked_at ?? new Date().toISOString();
  const stages = Array.isArray(status.stages) ? status.stages : [];
  const events = stages.map((stage, index): LoopPatchEvent => ({
    id: `community-loop:${stage.name}:${index}`,
    stage: inferLoopStage(stage.name, stage.summary, stage.evidence, stage.details),
    status: (stage.status || 'unknown').toLowerCase(),
    title: stage.name || 'Loop watch stage',
    detail: [stage.summary, stage.evidence].filter(Boolean).join(' · ') || 'Community loop watch stage updated.',
    at: checkedAt,
    node_id: stage.name,
    source: stage.url ?? source
  }));

  return {
    source,
    fetchedAt: checkedAt,
    live: true,
    overall: status.overall ?? 'unknown',
    branchDefId: CHANGE_LOOP_BRANCH_IDS[0],
    runs: [],
    events,
    warnings
  };
}

async function fetchJsonIfAvailable(url: string): Promise<CommunityLoopWatchStatus | null> {
  const res = await fetchWithTimeout(url, { cache: 'no-store' });
  if (!res.ok) return null;
  const parsed = await res.json();
  if (parsed?.stages && Array.isArray(parsed.stages)) return parsed;
  return null;
}

function issueLabels(issue: GitHubIssue): Set<string> {
  const labels = new Set<string>();
  for (const label of issue.labels ?? []) {
    if (typeof label === 'string') labels.add(label);
    else if (label?.name) labels.add(label.name);
  }
  return labels;
}

function workflowRunStatus(run: GitHubWorkflowRun | null): string {
  if (!run) return 'red';
  if (run.status !== 'completed') return 'yellow';
  return run.conclusion === 'success' ? 'green' : 'red';
}

function workflowRunSummary(workflowId: string, run: GitHubWorkflowRun | null): string {
  if (!run) return `${workflowId} has no visible runs`;
  return `${workflowId} latest run is ${run.status}${run.conclusion ? `/${run.conclusion}` : ''}`;
}

async function fetchLatestWorkflowRun(workflowId: string, warnings: string[]): Promise<GitHubWorkflowRun | null> {
  try {
    const res = await fetchWithTimeout(`https://api.github.com/repos/Jonnyton/Workflow/actions/workflows/${workflowId}/runs?per_page=1`, {
      headers: { Accept: 'application/vnd.github+json' }
    });
    if (!res.ok) throw new Error(`GitHub workflow ${workflowId} ${res.status}`);
    const payload = await res.json();
    return Array.isArray(payload?.workflow_runs) ? payload.workflow_runs[0] ?? null : null;
  } catch (error) {
    warnings.push(warningText(`GitHub workflow ${workflowId}`, error));
    return null;
  }
}

async function fetchIssuesForLabel(label: string, warnings: string[]): Promise<GitHubIssue[]> {
  try {
    const res = await fetchWithTimeout(`https://api.github.com/repos/Jonnyton/Workflow/issues?state=open&labels=${encodeURIComponent(label)}&per_page=12`, {
      headers: { Accept: 'application/vnd.github+json' }
    });
    if (!res.ok) throw new Error(`GitHub issues ${label} ${res.status}`);
    const payload = await res.json();
    return Array.isArray(payload) ? payload.filter((issue) => !issue.pull_request) : [];
  } catch (error) {
    warnings.push(warningText(`GitHub issues ${label}`, error));
    return [];
  }
}

async function fetchLoopIssues(warnings: string[]): Promise<GitHubIssue[]> {
  const groups = await Promise.all([
    fetchIssuesForLabel('daemon-request', warnings),
    fetchIssuesForLabel('auto-change', warnings),
    fetchIssuesForLabel('auto-bug', warnings)
  ]);
  const byNumber = new Map<number, GitHubIssue>();
  for (const issue of groups.flat()) {
    if (typeof issue.number === 'number') byNumber.set(issue.number, issue);
  }
  return [...byNumber.values()].sort((a, b) => Date.parse(b.updated_at ?? '') - Date.parse(a.updated_at ?? ''));
}

function workflowEvent(stage: LoopStageId, title: string, workflowId: string, run: GitHubWorkflowRun | null): LoopPatchEvent {
  const status = workflowRunStatus(run);
  return {
    id: `github-workflow:${workflowId}`,
    stage,
    status,
    title,
    detail: [
      workflowRunSummary(workflowId, run),
      run?.html_url
    ].filter(Boolean).join(' - '),
    at: normalizeTimestamp(run?.updated_at ?? run?.created_at),
    node_id: workflowId,
    source: run?.html_url ?? `GitHub Actions ${workflowId}`
  };
}

function issueEvents(issue: GitHubIssue): LoopPatchEvent[] {
  const labels = issueLabels(issue);
  const title = issue.title ?? `Issue #${issue.number ?? '?'}`;
  const url = issue.html_url ?? 'GitHub issue';
  const detail = `${title} - ${url}`;
  const at = normalizeTimestamp(issue.updated_at ?? issue.created_at);
  const status = labels.has('needs-human') ? 'blocked' : labels.has('auto-fix-attempted') ? 'attempted' : 'queued';
  const events: LoopPatchEvent[] = [];

  if (labels.has('auto-bug')) {
    events.push({
      id: `github-issue:${issue.number}:intake`,
      stage: 'intake',
      status,
      title: `BUG request #${issue.number}`,
      detail,
      at,
      node_id: 'auto-bug',
      source: url
    });
  }

  if (labels.has('daemon-request') || labels.has('auto-change')) {
    events.push({
      id: `github-issue:${issue.number}:investigation`,
      stage: 'investigation',
      status: labels.has('needs-human') ? 'blocked' : 'packet',
      title: `Patch request #${issue.number}`,
      detail,
      at,
      node_id: 'daemon-request',
      source: url
    });
  }

  if (labels.has('gate-required')) {
    events.push({
      id: `github-issue:${issue.number}:gate`,
      stage: 'gate',
      status: labels.has('needs-human') ? 'blocked' : 'queued',
      title: `Evidence gate #${issue.number}`,
      detail,
      at,
      node_id: 'gate-required',
      source: url
    });
  }

  const writer = [...labels].find((label) => label.startsWith('writer:'));
  if (writer) {
    events.push({
      id: `github-issue:${issue.number}:coding`,
      stage: 'coding',
      status: 'active',
      title: `Writer lane ${writer.replace('writer:', '')}`,
      detail,
      at,
      node_id: writer,
      source: url
    });
  }

  if ((issue.body ?? '').toLowerCase().includes('pr creation was blocked')) {
    events.push({
      id: `github-issue:${issue.number}:release`,
      stage: 'release',
      status: 'handoff',
      title: `Review handoff #${issue.number}`,
      detail: `GitHub Actions PR creation was blocked; branch entered review through the GitHub connector. ${url}`,
      at,
      node_id: 'review-handoff',
      source: url
    });
  }

  return events;
}

function queueSummaryEvent(stage: LoopStageId, title: string, issues: GitHubIssue[], labels: string[]): LoopPatchEvent | null {
  const matches = issues.filter((issue) => {
    const issueLabelSet = issueLabels(issue);
    return labels.some((label) => issueLabelSet.has(label));
  });
  if (!matches.length) return null;
  const latest = matches[0];
  const issueList = matches.slice(0, 3).map((issue) => `#${issue.number}`).join(', ');
  return {
    id: `github-queue:${stage}:${labels.join('+')}`,
    stage,
    status: 'active',
    title,
    detail: `${matches.length} visible ${title.toLowerCase()} item${matches.length === 1 ? '' : 's'} (${issueList}) from public GitHub issues.`,
    at: normalizeTimestamp(latest.updated_at ?? latest.created_at),
    node_id: labels.join('+'),
    source: latest.html_url ?? 'GitHub issues'
  };
}

async function fetchGitHubLoopMonitorFeed(warnings: string[]): Promise<PatchLoopFeed | null> {
  const [issues, intakeRun, writerRun, deploySiteRun, deployProdRun, observationRun, watchRun] = await Promise.all([
    fetchLoopIssues(warnings),
    fetchLatestWorkflowRun('wiki-bug-sync.yml', warnings),
    fetchLatestWorkflowRun('auto-fix-bug.yml', warnings),
    fetchLatestWorkflowRun('deploy-site.yml', warnings),
    fetchLatestWorkflowRun('deploy-prod.yml', warnings),
    fetchLatestWorkflowRun('uptime-canary.yml', warnings),
    fetchLatestWorkflowRun('community-loop-watch.yml', warnings)
  ]);

  const events = [
    queueSummaryEvent('investigation', 'Patch request queue', issues, ['daemon-request', 'auto-change']),
    queueSummaryEvent('gate', 'Evidence gate queue', issues, ['gate-required', 'needs-human']),
    ...issues.flatMap(issueEvents).slice(0, 18),
    workflowEvent('intake', 'Wiki bug sync', 'wiki-bug-sync.yml', intakeRun),
    workflowEvent('coding', 'Auto-fix writer', 'auto-fix-bug.yml', writerRun),
    workflowEvent('release', 'Site deploy', 'deploy-site.yml', deploySiteRun),
    workflowEvent('release', 'Production deploy', 'deploy-prod.yml', deployProdRun),
    workflowEvent('observe', 'Uptime canary', 'uptime-canary.yml', observationRun),
    workflowEvent('observe', 'Community loop watch', 'community-loop-watch.yml', watchRun)
  ].filter((event): event is LoopPatchEvent => Boolean(event && (event.at || event.detail)));

  if (!events.length) return null;

  const statuses = events.map((event) => event.status);
  const overall = statuses.some((status) => ['red', 'failed'].includes(status))
    ? 'red'
    : statuses.some((status) => ['yellow', 'queued', 'blocked', 'handoff', 'attempted', 'active'].includes(status))
      ? 'active'
      : 'green';

  return {
    source: 'GitHub public loop monitor',
    fetchedAt: new Date().toISOString(),
    live: true,
    overall,
    branchDefId: CHANGE_LOOP_BRANCH_IDS[0],
    runs: [],
    events,
    warnings
  };
}

async function fetchWithTimeout(url: string, init: RequestInit = {}, timeoutMs = 6500): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    window.clearTimeout(timer);
  }
}

async function fetchCommunityLoopWatchFeed(warnings: string[]): Promise<PatchLoopFeed | null> {
  try {
    const localStatus = await fetchJsonIfAvailable('/community-loop-status.json');
    if (localStatus) return communityStatusToFeed(localStatus, 'community-loop-status.json', warnings);
  } catch (error) {
    warnings.push(warningText('community-loop-status.json', error));
  }

  try {
    const issuesRes = await fetchWithTimeout('https://api.github.com/repos/Jonnyton/Workflow/issues?state=open&labels=community-loop-red&per_page=1', {
      headers: { Accept: 'application/vnd.github+json' }
    });
    if (!issuesRes.ok) throw new Error(`GitHub issues ${issuesRes.status}`);
    const issues = await issuesRes.json();
    const issue = Array.isArray(issues) ? issues[0] : null;
    if (issue) {
      const bodies: string[] = [];
      if (typeof issue.body === 'string') bodies.push(issue.body);
      if (issue.comments_url) {
        try {
          const commentsRes = await fetchWithTimeout(`${issue.comments_url}?per_page=10`, {
            headers: { Accept: 'application/vnd.github+json' }
          });
          if (commentsRes.ok) {
            const comments = await commentsRes.json();
            if (Array.isArray(comments)) {
              for (const comment of comments.slice(-10)) {
                if (typeof comment.body === 'string') bodies.push(comment.body);
              }
            }
          }
        } catch (error) {
          warnings.push(warningText('community-loop-red comments', error));
        }
      }
      for (const body of bodies.reverse()) {
        const parsed = jsonFromMarkdown(body);
        if (parsed) return communityStatusToFeed(parsed, issue.html_url ?? 'GitHub community-loop-red issue', warnings);
      }
      warnings.push('community-loop-red issue exists but no status JSON was visible yet');
    }
  } catch (error) {
    warnings.push(warningText('community-loop-red issue', error));
  }

  return fetchGitHubLoopMonitorFeed(warnings);
}

async function fetchMcpPatchLoopFeed(limit: number, warnings: string[]): Promise<PatchLoopFeed> {
  try {
    const loopFeed = normalizeLoopToolFeed(await callTool('loop', { action: 'feed', limit }));
    if (loopFeed) return loopFeed;
    warnings.push('loop action=feed returned no loop events yet');
  } catch (error) {
    warnings.push(warningText('loop action=feed', error));
  }

  try {
    const branchFeed = await callTool('extensions', {
      action: 'list_runs',
      branch_def_id: CHANGE_LOOP_BRANCH_IDS[0],
      limit
    });
    let runs = Array.isArray(branchFeed?.runs) ? branchFeed.runs.map(normalizeRun) : [];

    if (!runs.length) {
      const allFeed = await callTool('extensions', { action: 'list_runs', limit: Math.max(limit, 24) });
      runs = Array.isArray(allFeed?.runs) ? allFeed.runs.map(normalizeRun).filter(runLooksLikePatchLoop) : [];
    }

    const selectedRun = activeRun(runs) ?? latestRun(runs);
    const selectedRunIsHistorical = selectedRun ? isHistoricalTerminalRun(selectedRun) : false;
    let events: LoopPatchEvent[] = [];

    if (selectedRunIsHistorical) {
      warnings.push(
        `MCP extensions expose no active patch-loop run; last visible run ${selectedRun?.run_id} was ${selectedRun?.status} at ${selectedRun?.finished_at ?? selectedRun?.started_at ?? 'unknown time'}.`
      );
      try {
        const allFeed = await callTool('extensions', { action: 'list_runs', limit: Math.max(limit, 24) });
        const recentRuns: LoopPatchRun[] = (Array.isArray(allFeed?.runs) ? allFeed.runs.map(normalizeRun) : [])
          .filter((run: LoopPatchRun) => run.run_id !== selectedRun?.run_id)
          .filter((run: LoopPatchRun) => isRecentRun(run))
          .slice(0, limit);
        if (recentRuns.length) {
          const recentEvents = recentRuns.map(runToEvent);
          const statuses = recentRuns.map((run: LoopPatchRun) => run.status);
          return {
            source: 'MCP extensions recent branch runs',
            fetchedAt: new Date().toISOString(),
            live: true,
            overall: statuses.some((status: string) => status.includes('fail') || status.includes('error'))
              ? 'active'
              : statuses.some((status: string) => !isTerminalRunStatus(status))
                ? 'running'
                : 'green',
            branchDefId: CHANGE_LOOP_BRANCH_IDS[0],
            runs: recentRuns,
            events: recentEvents,
            warnings
          };
        }
      } catch (error) {
        warnings.push(warningText('extensions recent list_runs', error));
      }

      const communityWatch = await fetchCommunityLoopWatchFeed(warnings);
      if (communityWatch) return communityWatch;
    }

    if (selectedRun?.run_id && !selectedRunIsHistorical) {
      let runSnapshot: any = null;
      try {
        const streamed = await callTool('extensions', {
          action: 'stream_run',
          run_id: selectedRun.run_id,
          since_step: -1
        });
        events = Array.isArray(streamed?.events)
          ? streamed.events.map((event: any, index: number) => normalizeEvent(event, index, selectedRun))
          : [];
      } catch (error) {
        warnings.push(warningText('extensions stream_run', error));
      }

      if (!events.length || selectedRun.status.includes('fail') || events.every((event) => isSparseText(event.detail))) {
        try {
          runSnapshot = await callTool('extensions', {
            action: 'get_run',
            run_id: selectedRun.run_id
          });
          mergeRunSnapshot(selectedRun, runSnapshot);
          const rawEvents = runSnapshot?.events ?? runSnapshot?.timeline ?? runSnapshot?.steps ?? [];
          if (!events.length) {
            events = Array.isArray(rawEvents)
            ? rawEvents.map((event: any, index: number) => normalizeEvent(event, index, selectedRun))
            : [];
          }
        } catch (error) {
          warnings.push(warningText('extensions get_run', error));
        }
      }

      if (selectedRun.error) {
        events = events.map((event) => ({
          ...event,
          detail: isSparseText(event.detail)
            ? `${event.status === 'pending' ? 'Pending when run failed' : 'Run failed'}: ${selectedRun.error}`
            : event.detail
        }));
        if (!events.some((event) => event.status.includes('fail') || event.detail.includes(selectedRun.error ?? ''))) {
          events.push({
            id: `${selectedRun.run_id}:failure`,
            run_id: selectedRun.run_id,
            stage: inferLoopStage(selectedRun.last_node_id, selectedRun.error, selectedRun.failure_class),
            status: 'failed',
            title: 'Run failed',
            detail: [
              selectedRun.error,
              selectedRun.failure_class ? `class: ${selectedRun.failure_class}` : '',
              selectedRun.suggested_action ? `next: ${selectedRun.suggested_action}` : ''
            ].filter(Boolean).join(' · '),
            at: selectedRun.finished_at ?? selectedRun.started_at ?? null,
            node_id: selectedRun.last_node_id,
            source: 'MCP extensions get_run'
          });
        }
      }
    }

    return {
      source: 'MCP extensions list_runs/stream_run',
      fetchedAt: new Date().toISOString(),
      live: Boolean(activeRun(runs)) || Boolean(events.length),
      branchDefId: selectedRun?.branch_def_id || CHANGE_LOOP_BRANCH_IDS[0],
      activeRunId: activeRun(runs)?.run_id ?? (selectedRunIsHistorical ? undefined : selectedRun?.run_id),
      runs,
      events: events.slice(-36),
      warnings
    };
  } catch (error) {
    warnings.push(warningText('extensions list_runs', error));
  }

  return {
    source: 'waiting for MCP loop feed',
    fetchedAt: new Date().toISOString(),
    live: false,
    branchDefId: CHANGE_LOOP_BRANCH_IDS[0],
    runs: [],
    events: [],
    warnings
  };
}

export async function fetchPatchLoopFeed(limit = 12, source: PatchLoopFeedSource = 'mcp'): Promise<PatchLoopFeed> {
  const warnings: string[] = [];

  if (source === 'github') {
    const communityWatch = await fetchCommunityLoopWatchFeed(warnings);
    if (communityWatch) return communityWatch;
    return {
      source: 'waiting for community-loop-watch',
      fetchedAt: new Date().toISOString(),
      live: false,
      branchDefId: CHANGE_LOOP_BRANCH_IDS[0],
      runs: [],
      events: [],
      warnings
    };
  }

  return fetchMcpPatchLoopFeed(limit, warnings);
}

// ============ Vital signs (server vs loop, honestly distinguished) ============

export type Vitals = {
  reachable: boolean;
  fetchedAt: string;
  deployedAt?: string | null;
  gitSha?: string | null;
  queue?: { pending: number; running: number; succeeded: number; failed: number; depth: number } | null;
  lastMovedAt?: string | null;
  universeCount?: number;
  goalCount?: number | null;
  loopAwake?: boolean;
  activeRun?: boolean;
  lastSignalSource?: 'run' | 'universe-activity' | null;
  error?: string;
};

const VITALS_SIGNAL_WINDOW_MS = 60 * 60 * 1000;

/**
 * One read, three truths reconciled into one word.
 *
 * The SERVER being reachable (green) and the LOOP actually moving
 * (awake/asleep) are different facts; the site never collapses them into one
 * dot. But "moving" itself had two instruments that disagreed: universe
 * `last_activity_at` (what this strip used) and extensions `list_runs` (what
 * /loop used). They measured different things, so the home pulse could say
 * "asleep" while /loop said "awake". We now read BOTH here and derive one
 * honest answer: awake if a run is actually executing, or any signal moved
 * within the last hour. lastMovedAt is the newest of the two signals.
 */
export async function fetchVitals(): Promise<Vitals> {
  try {
    const [status, universes, goalsList, runsList] = await Promise.all([
      callTool('get_status', {}),
      callTool('universe', { action: 'list' }),
      callTool('goals', { action: 'list' }).catch(() => null),
      callTool('extensions', { action: 'list_runs', limit: 8 }).catch(() => null)
    ]);
    const q = status?.supervisor_liveness?.queue_state ?? null;
    const rel = status?.release_state ?? null;
    const us = Array.isArray(universes?.universes) ? universes.universes : [];

    // Signal 1: newest universe activity timestamp.
    let universeMovedMs: number | null = null;
    for (const u of us) {
      const ms = timestampMs(u?.last_activity_at);
      if (ms !== null && (universeMovedMs === null || ms > universeMovedMs)) universeMovedMs = ms;
    }

    // Signal 2: live branch runs. activeRun = any non-terminal run; newest
    // run timestamp normalizes across epoch-seconds / epoch-ms / ISO.
    const runs: LoopPatchRun[] = Array.isArray(runsList?.runs) ? runsList.runs.map(normalizeRun) : [];
    const runIsActive = runs.some((run) => !isTerminalRunStatus(run.status));
    let newestRunMs: number | null = null;
    for (const run of runs) {
      const ms = runTimestampMs(run);
      if (ms !== null && (newestRunMs === null || ms > newestRunMs)) newestRunMs = ms;
    }

    const running = Number(q?.running ?? 0);

    // Reconcile: the newest signal across both instruments, and which one it
    // was, so the UI can say "a run is moving" vs "last signal <rel>".
    let lastMovedMs: number | null = null;
    let lastSignalSource: 'run' | 'universe-activity' | null = null;
    if (newestRunMs !== null && (lastMovedMs === null || newestRunMs >= lastMovedMs)) {
      lastMovedMs = newestRunMs;
      lastSignalSource = 'run';
    }
    if (universeMovedMs !== null && (lastMovedMs === null || universeMovedMs > lastMovedMs)) {
      lastMovedMs = universeMovedMs;
      lastSignalSource = 'universe-activity';
    }

    const recentSignal =
      lastMovedMs !== null && Date.now() - lastMovedMs < VITALS_SIGNAL_WINDOW_MS;
    const loopAwake = runIsActive || running > 0 || recentSignal;

    return {
      reachable: true,
      fetchedAt: new Date().toISOString(),
      deployedAt: rel?.deployed_at ?? null,
      gitSha: typeof rel?.git_sha === 'string' ? rel.git_sha.slice(0, 8) : null,
      queue: q
        ? {
            pending: Number(q.pending ?? 0),
            running,
            succeeded: Number(q.succeeded ?? 0),
            failed: Number(q.failed ?? 0),
            depth: Number(q.depth ?? 0)
          }
        : null,
      lastMovedAt: lastMovedMs !== null ? new Date(lastMovedMs).toISOString() : null,
      universeCount: us.length,
      goalCount: Array.isArray(goalsList?.goals) ? goalsList.goals.length : null,
      loopAwake,
      activeRun: runIsActive,
      lastSignalSource
    };
  } catch (err: any) {
    return { reachable: false, fetchedAt: new Date().toISOString(), error: err?.message ?? String(err) };
  }
}

/** Shape the live raw response into the same structure /wiki + /graph use from the snapshot. */
export function liveToSnapshotShape(live: LiveResult, baked: Snapshot): Snapshot {
  // Reuse the baked snapshot's edges + tags (which were extracted from page
  // bodies at snapshot time). For real-time edge extraction we'd need to
  // crawl bodies in the browser too — done in fetchEdges() separately.
  const wiki = { bugs: [] as any[], concepts: [] as any[], notes: [] as any[], plans: [] as any[], drafts: [] as any[], other: [] as any[] };
  for (const p of live.wiki.promoted) {
    const path = p.path ?? '';
    const title = p.title ?? path;
    if (path.includes('/bugs/')) {
      const m = path.match(/BUG-?(\d+)/i);
      const id = m ? `BUG-${m[1].padStart(3, '0')}` : path;
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
  for (const p of live.wiki.drafts) {
    wiki.drafts.push({ slug: p.path ?? '', title: p.title ?? p.path });
  }

  // Dedup by canonical id/slug — live MCP sometimes returns case variants
  // (e.g. BUG-003-... and bug-003-...) that pad to the same canonical id.
  // Without this dedup, Svelte's keyed {#each} blocks throw each_key_duplicate.
  function dedupBy<T>(arr: T[], keyFn: (x: T) => string): T[] {
    const seen = new Set<string>();
    const out: T[] = [];
    for (const item of arr) {
      const k = keyFn(item);
      if (seen.has(k)) continue;
      seen.add(k);
      out.push(item);
    }
    return out;
  }
  wiki.bugs = dedupBy(wiki.bugs, (b: any) => b.id);
  wiki.concepts = dedupBy(wiki.concepts, (c: any) => c.slug);
  wiki.notes = dedupBy(wiki.notes, (n: any) => n.slug);
  wiki.plans = dedupBy(wiki.plans, (pl: any) => pl.slug);
  wiki.drafts = dedupBy(wiki.drafts, (d: any) => d.slug);

  // Newest first: bug ids encode order (BUG-123 is newer than BUG-001).
  const bugNum = (id: unknown) => parseInt(String(id ?? '').replace(/\D/g, ''), 10) || 0;
  wiki.bugs.sort((a: any, b: any) => bugNum(b.id) - bugNum(a.id));

  const promoted = wiki.bugs.length + wiki.concepts.length + wiki.notes.length + wiki.plans.length + wiki.other.length;

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
      .sort((a, b) => (Date.parse(b.updated_at ?? b.created_at ?? '') || 0) - (Date.parse(a.updated_at ?? a.created_at ?? '') || 0))
      .map((g) => ({
      id: g.goal_id ?? g.id,
      name: g.name ?? '',
      summary: g.description ?? '',
      tags: typeof g.tags === 'string' ? g.tags.split(',').map((t: string) => t.trim()).filter(Boolean) : (g.tags ?? []),
      author: g.author ?? 'anonymous',
      visibility: g.visibility ?? 'public'
    })),
    universes: [...live.universes]
      .sort((a, b) => (Date.parse(b.last_activity_at ?? '') || 0) - (Date.parse(a.last_activity_at ?? '') || 0))
      .map((u) => ({
      id: u.id,
      phase: u.phase_human ?? u.phase ?? 'unknown',
      word_count: u.word_count ?? 0,
      last_activity_at: u.last_activity_at ?? null,
      accept_rate: u.accept_rate ?? null
    })),
    wiki,
    edges: baked.edges ?? [],
    tags: baked.tags ?? {}
  };
}
