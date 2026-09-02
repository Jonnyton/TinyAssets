// public-boundary.test.mjs — the public-read boundary the site must keep.
//
// A public browser reads ONLY the public projection (read_graph target=graphs)
// through the shared contract. It never downloads operator status, never asks
// for goals or runs, never defaults a missing visibility to public, and never
// labels a checked-in snapshot as a live read. These are the durable rules the
// old per-page tests encoded; the pages changed, the rules did not.

import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const siteRoot = resolve(here, "..");

function source(path) {
  return readFileSync(resolve(siteRoot, path), "utf8");
}

function readTree(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    if ([".next", "node_modules", "out", "scripts"].includes(entry.name)) return [];
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) return readTree(path);
    if (!/\.(?:[cm]?[jt]sx?)$/.test(entry.name)) return [];
    return [{ path, body: readFileSync(path, "utf8") }];
  });
}

const live = source("lib/live.ts");
const shapes = source("components/PublicShapes.tsx");
const reach = source("components/Reachability.tsx");
const pages = readTree(siteRoot);

test("the live client exposes only the two proven-safe public readers", () => {
  const exported = [...live.matchAll(/^export (?:async )?function (\w+)/gm)].map((m) => m[1]);
  assert.deepEqual(exported.sort(), ["fetchPublicUniverses", "fetchVitals"]);
  assert.doesNotMatch(live, /export\s+async\s+function\s+callTool\b/);
  assert.match(live, /publicGraphCall\(\s*["']graphs["']/);
  assert.match(live, /requirePublicUniverseCollection\(/);
  assert.match(live, /Public MCP read is unavailable/);
});

test("the live client never requests private-capable targets or operator status", () => {
  assert.doesNotMatch(live, /publicGraphCall\(\s*["'](?:run|runs|goal|goals)["']/);
  assert.doesNotMatch(live, /\bfetchPublicGoals?\b|\bfetchPublicRuns?\b|\bfetchLive\b/);
  assert.doesNotMatch(live, /callTool\(\s*["']get_status["']/);
  assert.doesNotMatch(live, /\brequireObjectResult\b/);
  assert.doesNotMatch(live, /read_graph runs?\b/i);
});

test("vitals derive activity from public universe timestamps, never from runs", () => {
  assert.doesNotMatch(live, /lastSignalSource\?:\s*["']run["']|lastSignalSource\s*=\s*["']run["']/);
  assert.doesNotMatch(live, /\bactiveRun\b/);
  assert.match(live, /lastSignalSource: "universe-activity"/);
  assert.match(live, /last_activity_at/);
});

test("public pages never surface untrusted error detail", () => {
  for (const file of [{ path: "lib/live.ts", body: live }, ...pages]) {
    assert.doesNotMatch(file.body, /json\.error\.message|res\.statusText/, file.path);
    assert.doesNotMatch(file.body, /error:\s*error(?:\?\.|\.)(?:message|stack)/, file.path);
  }
});

test("the public list labels live, snapshot and failed reads distinctly", () => {
  assert.match(shapes, /\bfetchPublicUniverses\b/);
  assert.match(shapes, /mcp-snapshot\.json/);
  assert.match(shapes, /live read from tinyassets\.io\/mcp/);
  assert.match(shapes, /checked-in snapshot from/);
  assert.match(shapes, /live read failed/);
  assert.match(shapes, /No public universes/);
  assert.doesNotMatch(shapes, /visibility\s*\?\?\s*["']public["']/);
  assert.doesNotMatch(shapes, /visibility\s*!==\s*["']private["']/);
  // The snapshot path is a labelled fallback, never relabelled as live.
  assert.match(shapes, /kind:\s*"snapshot",\s*rows:\s*bakedRows/);
});

test("the reachability strip keeps reachable and busy as separate readings", () => {
  assert.match(reach, /\bfetchVitals\b/);
  assert.match(reach, /unreachable from your browser/);
  assert.match(reach, /This is itself a true reading/);
  assert.match(reach, /Reachable does not mean busy/);
  assert.doesNotMatch(reach, /get_status/);
  assert.doesNotMatch(reach, /\bactive run\b|\ba run is moving\b/i);
});

test("site-wide refresh controls are named Refresh MCP", () => {
  const labels = [...pages.flatMap((f) => [...f.body.matchAll(/["'`]Refresh [A-Za-z]+["'`]/g)].map((m) => m[0]))];
  assert.ok(labels.length >= 2, "expected refresh controls on the commons and fine-print pages");
  for (const label of labels) {
    assert.match(label, /Refresh (?:MCP|GitHub)/, `unexpected refresh label ${label}`);
  }
});

test("no page imports a reader the client does not export", () => {
  for (const file of pages) {
    assert.doesNotMatch(file.body, /\bfetchLive\b|\bfetchPublicGoals?\b|\bliveToSnapshotShape\b/, file.path);
  }
});

test("no public copy claims goals or runs are read live, or that the platform runs a model", () => {
  const prose = pages.map((f) => f.body).join("\n").replace(/\s+/g, " ");
  assert.doesNotMatch(prose, /\b(?:goal|goals)\b.{0,48}\bread live\b|\bread live\b.{0,48}\b(?:goal|goals)\b/i);
  assert.doesNotMatch(prose, /\ba run is moving\b|\bactiveRun\b/i);
  assert.doesNotMatch(prose, /powered by (?:claude|gpt|openai|anthropic)/i);
  assert.doesNotMatch(prose, /AI-powered workflow engine/i);
});
