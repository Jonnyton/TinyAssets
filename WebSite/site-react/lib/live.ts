/**
 * Browser-side live MCP client.
 *
 * Reads ONLY the public projection (read_graph target=graphs) through the
 * shared public read contract. It never downloads the operator get_status
 * payload, never requests goals or runs, and reports a failed read as a failed
 * read. In production the Cloudflare Worker serves /mcp on the same origin;
 * `npm run dev` proxies it; NEXT_PUBLIC_MCP_PATH can point elsewhere.
 */

import {
  assertPublicBrowserEndpoint,
  publicGraphCall,
  requirePublicUniverseCollection,
} from "../../shared/mcp/public-read-contract.js";

const MCP_PATH = assertPublicBrowserEndpoint(
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_MCP_PATH) || "/mcp",
);

let initialized = false;
let sessionId: string | null = null;
let nextId = 1;

type RpcResp = {
  jsonrpc: "2.0";
  id: number;
  result?: any;
  error?: { code: number; message: string };
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function rpc(method: string, params: any = {}): Promise<any> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json, text/event-stream",
  };
  if (sessionId) headers["Mcp-Session-Id"] = sessionId;

  const body = { jsonrpc: "2.0", id: nextId++, method, params };
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const res = await fetch(MCP_PATH, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
        credentials: "omit",
      });

      const sid = res.headers.get("Mcp-Session-Id");
      if (sid && !sessionId) sessionId = sid;

      if (!res.ok) {
        if ([502, 503, 504].includes(res.status) && attempt < 2) {
          await sleep(350 * (attempt + 1));
          continue;
        }
        throw new Error(`Public MCP request failed (HTTP ${res.status})`);
      }

      const contentType = res.headers.get("Content-Type") ?? "";
      let text = await res.text();
      if (contentType.includes("text/event-stream")) {
        const dataLine = text.split("\n").find((line) => line.startsWith("data:"));
        if (!dataLine) throw new Error("SSE response missing data line");
        text = dataLine.replace(/^data:\s*/, "");
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

  throw new Error("Public MCP read is unavailable");
}

async function ensureInit(): Promise<void> {
  if (initialized) return;
  await rpc("initialize", {
    protocolVersion: "2025-06-18",
    clientInfo: { name: "tinyassets-site-live", version: "0.1.0" },
    capabilities: {},
  });
  try {
    await fetch(MCP_PATH, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json, text/event-stream",
        ...(sessionId ? { "Mcp-Session-Id": sessionId } : {}),
      },
      body: JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }),
      credentials: "omit",
    });
  } catch {}
  initialized = true;
}

async function callTool(name: string, args: Record<string, any>): Promise<any> {
  await ensureInit();
  const result = await rpc("tools/call", { name, arguments: args });
  if (result?.structuredContent && typeof result.structuredContent === "object") {
    return result.structuredContent;
  }
  const textItem = result?.content?.find((item: any) => item?.type === "text");
  if (!textItem?.text) return null;
  try {
    const parsed = JSON.parse(textItem.text);
    if (parsed && typeof parsed.result === "string") {
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

export async function fetchPublicUniverses(limit = 100): Promise<any[]> {
  const universesCall = publicGraphCall("graphs", limit);
  return requirePublicUniverseCollection(
    await callTool(universesCall.name, universesCall.args),
    "read_graph graphs",
    limit,
  );
}

function stringify(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return "";
  }
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    const text = stringify(value).trim();
    if (text) return text;
  }
  return "";
}

function normalizeTimestamp(value: unknown): string | null {
  const text = firstString(value);
  if (!text) return null;
  if (typeof value === "number" || /^\d+(\.\d+)?$/.test(text)) {
    const numeric = Number(text);
    if (Number.isFinite(numeric)) {
      const millis = numeric > 1_000_000_000_000 ? numeric : numeric * 1000;
      const date = new Date(millis);
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
  lastSignalSource?: "universe-activity" | null;
  error?: string;
};

const VITALS_SIGNAL_WINDOW_MS = 60 * 60 * 1000;

/**
 * Read reachability and activity only from the public universe projection.
 * The operator get_status payload includes raw logs and identifiers, so public
 * browsers must not download it merely to select a few aggregate fields.
 */
export async function fetchVitals(): Promise<Vitals> {
  try {
    const universesCall = publicGraphCall("graphs", 100);
    const publicUniverses = requirePublicUniverseCollection(
      await callTool(universesCall.name, universesCall.args),
      "read_graph graphs",
      100,
    );
    let universeMovedMs: number | null = null;
    for (const universe of publicUniverses) {
      const ms = timestampMs(universe?.last_activity_at);
      if (ms !== null && (universeMovedMs === null || ms > universeMovedMs)) {
        universeMovedMs = ms;
      }
    }

    const lastMovedMs = universeMovedMs;
    const lastSignalSource: "universe-activity" | null =
      universeMovedMs === null ? null : "universe-activity";

    const recentSignal =
      lastMovedMs !== null && Date.now() - lastMovedMs < VITALS_SIGNAL_WINDOW_MS;
    const workflowActive = recentSignal;

    return {
      reachable: true,
      fetchedAt: new Date().toISOString(),
      deployedAt: null,
      gitSha: null,
      queue: null,
      lastMovedAt: lastMovedMs !== null ? new Date(lastMovedMs).toISOString() : null,
      universeCount: publicUniverses.length,
      goalCount: null,
      workflowActive,
      lastSignalSource,
    };
  } catch (error) {
    return {
      reachable: false,
      fetchedAt: new Date().toISOString(),
      error: "Public MCP read is unavailable",
    };
  }
}
