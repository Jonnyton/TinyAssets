#!/usr/bin/env node
/**
 * Cleanly rebuild the public discovery snapshot from canonical MCP reads.
 *
 * This is intentionally fail-closed: incomplete inventories, truncated page
 * bodies, mismatched source proofs, or transport errors leave both checked-in
 * outputs untouched and exit non-zero.
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  assertNoRetiredSignatures,
  atomicWriteMirrors,
  buildMcpSnapshot,
  pageReadHandle,
  parseToolResponse,
  serializeSnapshot,
} from "./snapshot-helpers.mjs";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const SITE_ROOT = resolve(SCRIPT_DIR, "..");
const OUTPUTS = [
  resolve(SITE_ROOT, "src", "lib", "content", "mcp-snapshot.json"),
  resolve(SITE_ROOT, "..", "site-react", "lib", "mcp-snapshot.json"),
];
const MCP_URL = process.env.MCP_URL ?? "https://tinyassets.io/mcp";
const BEARER = process.env.MCP_BEARER ?? "";
const CONCURRENCY = Math.max(1, Number(process.env.SNAPSHOT_CONCURRENCY ?? 6));
const INVENTORY_EPOCH = "1970-01-01T00:00:00Z";
const MAX_RESULTS = 100;

function log(message) {
  console.log(`[snapshot:mcp] ${message}`);
}

async function loadSdk() {
  const [{ Client }, { StreamableHTTPClientTransport }] = await Promise.all([
    import("@modelcontextprotocol/sdk/client/index.js"),
    import("@modelcontextprotocol/sdk/client/streamableHttp.js"),
  ]);
  return { Client, StreamableHTTPClientTransport };
}

function transportOptions() {
  return BEARER
    ? { requestInit: { headers: { Authorization: `Bearer ${BEARER}` } } }
    : {};
}

async function connectClient(sdk, name) {
  const transport = new sdk.StreamableHTTPClientTransport(
    new URL(MCP_URL),
    transportOptions(),
  );
  const client = new sdk.Client(
    { name, version: "1.0.0" },
    { capabilities: {} },
  );
  await Promise.race([
    client.connect(transport),
    new Promise((_, reject) =>
      setTimeout(
        () => reject(new Error(`${name} connection timed out`)),
        30_000,
      ),
    ),
  ]);
  return client;
}

async function callTyped(client, name, args, timeoutMs = 30_000) {
  const response = await Promise.race([
    client.callTool({ name, arguments: args }),
    new Promise((_, reject) =>
      setTimeout(
        () => reject(new Error(`${name}(${JSON.stringify(args)}) timed out`)),
        timeoutMs,
      ),
    ),
  ]);
  const parsed = parseToolResponse(response);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(
      `${name}(${JSON.stringify(args)}) returned no typed object`,
    );
  }
  if (parsed.error) {
    throw new Error(`${name}(${JSON.stringify(args)}) failed: ${parsed.error}`);
  }
  return parsed;
}

async function readEveryPage(sdk, pages) {
  const pageBodies = new Map();
  const queue = [...pages];
  let firstFailure = null;
  const handles = new Map();
  for (const page of pages) {
    const handle = pageReadHandle(page.path);
    if (handles.has(handle)) {
      throw new Error(
        `read_page handle ${handle} is ambiguous for ${handles.get(handle)} and ${page.path}`,
      );
    }
    handles.set(handle, page.path);
  }

  async function worker(index) {
    const client = await connectClient(
      sdk,
      `tinyassets-site-snapshot-page-${index}`,
    );
    try {
      while (queue.length > 0 && !firstFailure) {
        const page = queue.shift();
        if (!page) return;
        try {
          const body = await callTyped(
            client,
            "read_page",
            { page: pageReadHandle(page.path) },
            45_000,
          );
          pageBodies.set(page.path, body);
          if (pageBodies.size % 20 === 0) {
            log(`read ${pageBodies.size}/${pages.length} complete page bodies`);
          }
        } catch (error) {
          firstFailure = error;
          throw error;
        }
      }
    } finally {
      try {
        await client.close();
      } catch {
        // The read result, not close telemetry, determines snapshot completeness.
      }
    }
  }

  const workerCount = Math.min(CONCURRENCY, Math.max(1, pages.length));
  await Promise.all(
    Array.from({ length: workerCount }, (_, index) => worker(index + 1)),
  );
  if (firstFailure) throw firstFailure;
  if (pageBodies.size !== pages.length) {
    throw new Error(`read ${pageBodies.size}/${pages.length} page bodies`);
  }
  return pageBodies;
}

async function main() {
  const sdk = await loadSdk();
  const client = await connectClient(sdk, "tinyassets-site-snapshot-index");
  try {
    log(`reading canonical public data from ${MCP_URL}`);
    const [goalsResult, graphsResult, pagesResult] = await Promise.all([
      callTyped(client, "read_graph", { target: "goals", limit: MAX_RESULTS }),
      callTyped(client, "read_graph", { target: "graphs", limit: MAX_RESULTS }),
      callTyped(client, "read_page", {
        changed_since: INVENTORY_EPOCH,
        max_results: MAX_RESULTS,
      }),
    ]);
    const pages = Array.isArray(pagesResult.results) ? pagesResult.results : [];
    const pageBodies = await readEveryPage(sdk, pages);
    const snapshot = buildMcpSnapshot({
      fetchedAt: new Date().toISOString(),
      sourceUrl: MCP_URL,
      goalsResult,
      graphsResult,
      pagesResult,
      pageBodies,
    });
    assertNoRetiredSignatures(snapshot);
    const bytes = serializeSnapshot(snapshot);

    atomicWriteMirrors(OUTPUTS, bytes);
    const [svelteBytes, reactBytes] = OUTPUTS.map((path) =>
      readFileSync(path, "utf8"),
    );
    if (
      svelteBytes !== bytes ||
      reactBytes !== bytes ||
      svelteBytes !== reactBytes
    ) {
      throw new Error("post-write MCP snapshot byte-parity check failed");
    }
    log(
      `wrote byte-identical snapshots (${snapshot.stats.wiki_promoted} promoted, ` +
        `${snapshot.stats.wiki_drafts} drafts, ${snapshot.stats.goals} goals, ` +
        `${snapshot.stats.universes} universes, ${snapshot.stats.edges} edges)`,
    );
  } finally {
    try {
      await client.close();
    } catch {
      // Preserve the result of the canonical reads.
    }
  }
}

main().catch((error) => {
  console.error(`[snapshot:mcp] ERROR: ${error?.stack ?? error}`);
  process.exitCode = 1;
});
