/**
 * Live MCP Playground client.
 *
 * Self-contained JSON-RPC client for the playground (embedded in /connect). Returns BOTH the
 * parsed tool result AND the full wire trace (request envelope, headers,
 * response status, timing) so the page can show what a chatbot's MCP call
 * actually looks like over the wire.
 *
 * Dev: hits /mcp-live (vite proxy → tinyassets.io/mcp).
 * Prod: hits /mcp (same-origin Cloudflare worker).
 */

const MCP_PATH = import.meta.env.DEV ? '/mcp-live' : '/mcp';

let initialized = false;
let sessionId: string | null = null;
let nextId = 1;

export type WireTrace = {
  request: {
    method: string;
    url: string;
    headers: Record<string, string>;
    body: unknown;
  };
  response: {
    status: number;
    statusText: string;
    headers: Record<string, string>;
    body: unknown;
    contentType: string;
    timeMs: number;
  };
};

export type CallResult = {
  parsed: any;
  raw: any;
  trace: WireTrace;
  initTrace?: WireTrace;
};

function headersToObject(h: Headers): Record<string, string> {
  const out: Record<string, string> = {};
  h.forEach((v, k) => {
    out[k] = v;
  });
  return out;
}

async function rpcWithTrace(method: string, params: unknown): Promise<{ result: any; trace: WireTrace }> {
  const reqHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json, text/event-stream'
  };
  if (sessionId) reqHeaders['Mcp-Session-Id'] = sessionId;

  const body = { jsonrpc: '2.0' as const, id: nextId++, method, params };
  const t0 = performance.now();
  const res = await fetch(MCP_PATH, {
    method: 'POST',
    headers: reqHeaders,
    body: JSON.stringify(body),
    credentials: 'omit'
  });
  const timeMs = Math.round(performance.now() - t0);

  const sid = res.headers.get('Mcp-Session-Id');
  if (sid && !sessionId) sessionId = sid;

  const ct = res.headers.get('Content-Type') ?? '';
  let text = await res.text();
  if (ct.includes('text/event-stream')) {
    const dataLine = text.split('\n').find((l) => l.startsWith('data:'));
    if (dataLine) text = dataLine.replace(/^data:\s*/, '');
  }

  let parsedBody: any = text;
  try {
    parsedBody = JSON.parse(text);
  } catch {
    /* keep raw text */
  }

  const trace: WireTrace = {
    request: { method: 'POST', url: MCP_PATH, headers: reqHeaders, body },
    response: {
      status: res.status,
      statusText: res.statusText,
      headers: headersToObject(res.headers),
      body: parsedBody,
      contentType: ct,
      timeMs
    }
  };

  if (!res.ok) {
    throw Object.assign(new Error(`MCP HTTP ${res.status}: ${res.statusText}`), { trace });
  }
  if (parsedBody && typeof parsedBody === 'object' && 'error' in parsedBody && parsedBody.error) {
    const err = parsedBody.error as { code: number; message: string };
    throw Object.assign(new Error(`MCP error ${err.code}: ${err.message}`), { trace });
  }
  return { result: parsedBody?.result, trace };
}

async function ensureInit(): Promise<WireTrace | undefined> {
  if (initialized) return undefined;
  const init = await rpcWithTrace('initialize', {
    protocolVersion: '2025-06-18',
    clientInfo: { name: 'tinyassets-playground', version: '0.1.0' },
    capabilities: {}
  });
  // Best-effort notifications/initialized; some servers require it.
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
  } catch {
    /* ignore */
  }
  initialized = true;
  return init.trace;
}

export async function callTool(name: string, args: Record<string, unknown>): Promise<CallResult> {
  const initTrace = await ensureInit();
  const { result, trace } = await rpcWithTrace('tools/call', { name, arguments: args });

  // The server moved canonical tool output into `structuredContent`; the
  // text content is now often just a summary or a pointer. Prefer the
  // structured payload, falling back to parsing the text blob. `raw` still
  // carries the full envelope so the wire/JSON views show everything.
  let parsed: any = null;
  if (result && typeof result === 'object' && result.structuredContent && typeof result.structuredContent === 'object') {
    parsed = result.structuredContent;
  } else if (result && typeof result === 'object' && Array.isArray(result.content)) {
    const textPart = result.content.find((c: any) => c?.type === 'text');
    if (textPart?.text) {
      try {
        parsed = JSON.parse(textPart.text);
        if (parsed && typeof parsed.result === 'string') {
          try {
            parsed = JSON.parse(parsed.result);
          } catch {
            /* keep parsed.result string */
          }
        }
      } catch {
        parsed = textPart.text;
      }
    }
  } else {
    parsed = result;
  }

  return { parsed, raw: result, trace, initTrace };
}

// ============ Input parser ============

export type ParsedInput =
  | { ok: true; tool: string; args: Record<string, unknown>; canonical: string }
  | { ok: false; error: string };

/**
 * Parse playground input like:
 *   wiki action=list
 *   extensions action=get_run run_id=abc123
 *   wiki action=read page=pages/bugs/bug-052
 *   universe action=queue_list limit=5
 */
export function parseInput(text: string): ParsedInput {
  const trimmed = text.trim();
  if (!trimmed) return { ok: false, error: 'Type a tool call (e.g. `wiki action=list`).' };
  const tokens = trimmed.match(/(?:[^\s"]+|"[^"]*")+/g) ?? [];
  if (!tokens.length) return { ok: false, error: 'No tool name found.' };
  const tool = tokens[0];
  if (!/^[a-zA-Z_][\w-]*$/.test(tool)) {
    return { ok: false, error: `Tool name "${tool}" looks malformed.` };
  }
  const args: Record<string, unknown> = {};
  const canonicalParts: string[] = [tool];
  for (let i = 1; i < tokens.length; i++) {
    const token = tokens[i];
    const eq = token.indexOf('=');
    if (eq === -1) {
      return { ok: false, error: `Argument "${token}" needs a key=value form.` };
    }
    const key = token.slice(0, eq);
    let rawVal = token.slice(eq + 1);
    if (rawVal.startsWith('"') && rawVal.endsWith('"')) rawVal = rawVal.slice(1, -1);
    let val: unknown = rawVal;
    if (/^-?\d+$/.test(rawVal)) val = parseInt(rawVal, 10);
    else if (/^-?\d+\.\d+$/.test(rawVal)) val = parseFloat(rawVal);
    else if (rawVal === 'true') val = true;
    else if (rawVal === 'false') val = false;
    args[key] = val;
    canonicalParts.push(`${key}=${rawVal}`);
  }
  return { ok: true, tool, args, canonical: canonicalParts.join(' ') };
}

// ============ Loop voice harvest ============

export type LoopVoiceQuote = {
  text: string;
  branch: string;
  runId: string;
  nodeId?: string;
  field: string;
  at?: string;
};

const QUOTE_FIELDS: Array<[string, (ev: any, run: any) => unknown]> = [
  ['reason_for_downgrade', (ev) => ev?.coding_packet?.reason_for_downgrade ?? ev?.reason_for_downgrade],
  ['release_gate_reason', (ev) => ev?.release_gate_result?.reason ?? ev?.gate_reason],
  ['evolution_notes', (ev) => ev?.evolution_notes],
  ['lab_log_entry', (ev) => ev?.lab_log_entry ?? ev?.lab_log],
  ['rationale', (ev) => ev?.output_summary ?? ev?.rationale],
  ['suggested_action', (ev, run) => ev?.suggested_action ?? run?.suggested_action]
];

function looksLikeQuote(s: unknown): s is string {
  return typeof s === 'string' && s.length >= 30 && s.length <= 800 && /\s/.test(s);
}

export async function harvestVoiceQuotes(maxRuns = 6): Promise<{ quotes: LoopVoiceQuote[]; warnings: string[] }> {
  const warnings: string[] = [];
  const quotes: LoopVoiceQuote[] = [];
  try {
    const list = await callTool('extensions', { action: 'list_runs', limit: maxRuns });
    const runs: any[] = (list.parsed?.runs as any[]) ?? [];
    if (!runs.length) warnings.push('extensions.list_runs returned no runs');

    for (const run of runs.slice(0, maxRuns)) {
      try {
        const detail = await callTool('extensions', { action: 'get_run', run_id: run.run_id });
        const events: any[] =
          (detail.parsed?.events as any[]) ??
          (detail.parsed?.timeline as any[]) ??
          (detail.parsed?.steps as any[]) ??
          [];
        for (const ev of events) {
          for (const [field, picker] of QUOTE_FIELDS) {
            const val = picker(ev, run);
            if (looksLikeQuote(val)) {
              quotes.push({
                text: val.trim(),
                branch: run.branch_def_id ?? run.workflow ?? run.name ?? 'change_loop_v1',
                runId: run.run_id ?? 'unknown',
                nodeId: ev?.node_id,
                field,
                at: ev?.created_at ?? ev?.timestamp ?? run?.finished_at ?? run?.started_at
              });
            }
          }
        }
      } catch (err) {
        warnings.push(`get_run ${run?.run_id}: ${err instanceof Error ? err.message : String(err)}`);
      }
      if (quotes.length >= 12) break;
    }
  } catch (err) {
    warnings.push(`list_runs: ${err instanceof Error ? err.message : String(err)}`);
  }
  // Dedupe by text prefix.
  const seen = new Set<string>();
  const deduped: LoopVoiceQuote[] = [];
  for (const q of quotes) {
    const key = q.text.slice(0, 80);
    if (seen.has(key)) continue;
    seen.add(key);
    deduped.push(q);
  }
  return { quotes: deduped, warnings };
}

// ============ Recent runs (run picker) ============

export type RecentRun = {
  run_id: string;
  name?: string;
  branch_def_id?: string;
  status: string;
  started_at?: string;
  finished_at?: string;
};

export async function listRecentRuns(limit = 10): Promise<RecentRun[]> {
  try {
    const list = await callTool('extensions', { action: 'list_runs', limit });
    const runs: any[] = (list.parsed?.runs as any[]) ?? [];
    return runs.map((r) => ({
      run_id: r.run_id ?? r.id ?? 'unknown',
      name: r.name ?? r.run_name,
      branch_def_id: r.branch_def_id ?? r.workflow,
      status: (r.status ?? 'unknown').toString(),
      started_at: r.started_at,
      finished_at: r.finished_at
    }));
  } catch {
    return [];
  }
}

// ============ Pretty summarizer ============

/**
 * Best-effort plain-English summary of a parsed tool response.
 * Returns null if the shape isn't recognized — caller falls back to JSON.
 */
export function summarize(tool: string, parsed: any): string | null {
  if (parsed === null || parsed === undefined) return null;

  if (tool === 'wiki') {
    if (Array.isArray(parsed?.promoted) || Array.isArray(parsed?.drafts)) {
      const promoted = parsed.promoted?.length ?? 0;
      const drafts = parsed.drafts?.length ?? 0;
      const buckets: Record<string, number> = {};
      for (const p of parsed.promoted ?? []) {
        const path: string = p.path ?? '';
        const cat =
          path.includes('/bugs/') ? 'bugs'
          : path.includes('/plans/') ? 'plans'
          : path.includes('/concepts/') ? 'concepts'
          : path.includes('/notes/') ? 'notes'
          : 'other';
        buckets[cat] = (buckets[cat] ?? 0) + 1;
      }
      const breakdown = Object.entries(buckets)
        .sort((a, b) => b[1] - a[1])
        .map(([k, v]) => `${v} ${k}`)
        .join(', ');
      return `The wiki has ${promoted} promoted page${promoted === 1 ? '' : 's'} (${breakdown}) and ${drafts} draft${drafts === 1 ? '' : 's'}.`;
    }
    if (typeof parsed?.content === 'string') {
      const lines = parsed.content.split('\n').filter((l: string) => l.trim()).length;
      const chars = parsed.content.length;
      return `Page body returned: ${chars.toLocaleString()} characters across ${lines} non-empty lines.`;
    }
  }

  if (tool === 'goals') {
    if (Array.isArray(parsed?.goals)) {
      const n = parsed.goals.length;
      const names = parsed.goals.slice(0, 3).map((g: any) => g.name ?? g.id).filter(Boolean).join(', ');
      return `${n} active goal${n === 1 ? '' : 's'}${names ? `: ${names}${n > 3 ? ', …' : ''}` : ''}.`;
    }
  }

  if (tool === 'universe') {
    if (Array.isArray(parsed?.universes)) {
      const n = parsed.universes.length;
      const phases = parsed.universes.slice(0, 3).map((u: any) => `${u.id} (${u.phase ?? u.phase_human ?? '?'})`).join(', ');
      return `${n} universe${n === 1 ? '' : 's'}: ${phases}${n > 3 ? ', …' : ''}.`;
    }
    if (Array.isArray(parsed?.queue) || Array.isArray(parsed?.tasks)) {
      const items = parsed.queue ?? parsed.tasks ?? [];
      return `${items.length} item${items.length === 1 ? '' : 's'} in the BranchTask queue.`;
    }
    if (parsed?.alive !== undefined) {
      return `Daemon ${parsed.alive ? 'alive' : 'inactive'}${parsed.last_activity_at ? `, last activity ${parsed.last_activity_at}` : ''}.`;
    }
  }

  if (tool === 'extensions') {
    if (Array.isArray(parsed?.runs)) {
      const n = parsed.runs.length;
      const recent = parsed.runs[0];
      const stamp = recent?.finished_at ?? recent?.started_at ?? 'unknown';
      return `${n} run${n === 1 ? '' : 's'} returned. Most recent: ${recent?.run_id ?? '?'} — ${recent?.status ?? '?'} at ${stamp}.`;
    }
    if (Array.isArray(parsed?.events)) {
      return `${parsed.events.length} event${parsed.events.length === 1 ? '' : 's'} for run ${parsed?.run_id ?? '(unspecified)'}.`;
    }
  }

  return null;
}
