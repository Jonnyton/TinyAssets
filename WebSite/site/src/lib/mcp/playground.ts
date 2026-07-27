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

import {
  assertPublicPlaygroundCall,
  sanitizePublicPlaygroundResponse
} from '../../../../shared/mcp/public-read-contract.js';

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

function safeTrace(trace: WireTrace, responseBody: unknown): WireTrace {
  const contentType = trace.response.contentType.includes('text/event-stream')
    ? 'text/event-stream'
    : trace.response.contentType.includes('json')
      ? 'application/json'
      : 'other';
  return {
    request: {
      ...trace.request,
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json, text/event-stream'
      }
    },
    response: {
      ...trace.response,
      statusText: trace.response.status >= 200 && trace.response.status < 300
        ? 'OK'
        : 'Request failed',
      headers: contentType === 'other' ? {} : { 'content-type': contentType },
      body: responseBody,
      contentType
    }
  };
}

function safeToolTrace(trace: WireTrace, parsed: Record<string, any>): WireTrace {
  const envelope = trace.request.body;
  const safeEnvelope: Record<string, any> = {
    jsonrpc: '2.0',
    result: { structuredContent: parsed }
  };
  if (
    envelope &&
    typeof envelope === 'object' &&
    !Array.isArray(envelope) &&
    (typeof (envelope as any).id === 'number' || typeof (envelope as any).id === 'string')
  ) {
    safeEnvelope.id = (envelope as any).id;
  }
  return safeTrace(trace, safeEnvelope);
}

function withheldTrace(trace: WireTrace): WireTrace {
  return safeTrace(trace, 'Response body withheld because it failed public validation.');
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
      body: JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }),
      credentials: 'omit'
    });
  } catch {
    /* ignore */
  }
  initialized = true;
  return safeTrace(init.trace, {
    jsonrpc: '2.0',
    result: { protocolVersion: '2025-06-18', initialized: true }
  });
}

export async function callTool(name: string, args: Record<string, unknown>): Promise<CallResult> {
  assertPublicPlaygroundCall(name, args);
  try {
    const initTrace = await ensureInit();
    const { result, trace } = await rpcWithTrace('tools/call', { name, arguments: args });

    // Canonical tool output lives in `structuredContent`; older servers may
    // still return JSON in their text item. Nothing crosses into the UI until
    // the fixed public response contract validates and reduces it.
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
              /* invalid nested JSON will fail the public response validator */
            }
          }
        } catch {
          parsed = null;
        }
      }
    } else {
      parsed = result;
    }

    try {
      const validated = sanitizePublicPlaygroundResponse(name, args, parsed);
      const publicTrace = safeToolTrace(trace, validated);
      return {
        parsed: validated,
        raw: { structuredContent: validated },
        trace: publicTrace,
        initTrace
      };
    } catch {
      throw Object.assign(new Error('MCP response failed public validation.'), { trace });
    }
  } catch (error: any) {
    const trace = error?.trace ? withheldTrace(error.trace) : undefined;
    throw Object.assign(
      new Error('MCP response failed public validation or the request could not complete.'),
      trace ? { trace } : {}
    );
  }
}

// ============ Input parser ============

export type ParsedInput =
  | { ok: true; tool: string; args: Record<string, unknown>; canonical: string }
  | { ok: false; error: string };

const PUBLIC_READ_TOOLS = new Set(['read_graph', 'read_page']);

/**
 * Parse playground input like:
 *   read_page changed_since=1970-01-01T00:00:00Z max_results=100
 *   read_graph target=graphs limit=5
 */
export function parseInput(text: string): ParsedInput {
  const trimmed = text.trim();
  if (!trimmed) return { ok: false, error: 'Type a tool call (e.g. `read_graph target=graphs`).' };
  const tokens = trimmed.match(/(?:[^\s"]+|"[^"]*")+/g) ?? [];
  if (!tokens.length) return { ok: false, error: 'No tool name found.' };
  const tool = tokens[0]!;
  if (!/^[a-zA-Z_][\w-]*$/.test(tool)) {
    return { ok: false, error: `Tool name "${tool}" looks malformed.` };
  }
  if (!PUBLIC_READ_TOOLS.has(tool)) {
    return {
      ok: false,
      error: `The public Playground only runs read_graph and bounded read_page discovery.`
    };
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
  try {
    assertPublicPlaygroundCall(tool, args);
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'That call is not available in the public Playground.'
    };
  }
  return { ok: true, tool, args, canonical: canonicalParts.join(' ') };
}

// ============ Pretty summarizer ============

/**
 * Best-effort plain-English summary of a parsed tool response.
 * Returns null if the shape isn't recognized — caller falls back to JSON.
 */
export function summarize(tool: string, parsed: any): string | null {
  if (parsed === null || parsed === undefined) return null;

  if (tool === 'read_page') {
    if (Array.isArray(parsed?.results)) {
      const promoted = parsed.results.filter((page: any) => !page?.is_draft).length;
      const drafts = parsed.results.filter((page: any) => Boolean(page?.is_draft)).length;
      const buckets: Record<string, number> = {};
      for (const p of parsed.results.filter((page: any) => !page?.is_draft)) {
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
      const scope = typeof parsed.scope === 'string' ? `${parsed.scope}-scope ` : '';
      const truncated = Number(parsed.truncated_count);
      const truncation =
        Number.isInteger(truncated) && truncated > 0
          ? ` This read is incomplete: ${truncated} additional page${truncated === 1 ? ' was' : 's were'} truncated.`
          : '';
      return `The wiki returned ${promoted} ${scope}promoted page${promoted === 1 ? '' : 's'} (${breakdown}) and ${drafts} draft${drafts === 1 ? '' : 's'}.${truncation}`;
    }
    if (typeof parsed?.content === 'string') {
      const lines = parsed.content.split('\n').filter((l: string) => l.trim()).length;
      const chars = parsed.content.length;
      return `Page body returned: ${chars.toLocaleString()} characters across ${lines} non-empty lines.`;
    }
  }

  if (tool === 'read_graph') {
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

  return null;
}
