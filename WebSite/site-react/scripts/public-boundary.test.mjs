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

import { discoverableRows } from "../lib/discoverable.js";

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

test("every browser request to the public endpoint is anonymous", () => {
  // Carried forward from the deleted public-playground-boundary test: the
  // initialize POST, the notifications/initialized POST, and every tool call
  // must send `credentials: "omit"`, so a signed-in visitor's cookies never
  // ride along to a public read.
  const fetches = (live.match(/\bfetch\(\s*MCP_PATH\b/g) ?? []).length;
  const anonymous = (live.match(/credentials:\s*"omit"/g) ?? []).length;
  assert.ok(fetches >= 2, `expected the RPC and notification POSTs, found ${fetches}`);
  assert.equal(
    anonymous,
    fetches,
    `every fetch to the endpoint must set credentials: "omit" (${fetches} fetches, ${anonymous} anonymous)`,
  );
  // A cookie-bearing mode must never appear.
  assert.doesNotMatch(live, /credentials:\s*"(?:include|same-origin)"/);
});

test("the checked-in snapshot fails closed on visibility, like a live read", () => {
  // Drive the REAL function both render paths call, with fixtures, rather than
  // regexing the component: a rule that is only asserted against source text
  // survives a refactor that removes the rule.
  const good = {
    id: "u-real",
    visibility: "public",
    phase: "idle",
    word_count: 3,
    last_activity_at: "2026-09-01T00:00:00Z",
  };
  assert.deepEqual(discoverableRows([good]), [
    { id: "u-real", phase: "idle", word_count: 3, last_activity_at: "2026-09-01T00:00:00Z" },
  ]);

  for (const bad of [
    { ...good, visibility: undefined },
    { ...good, visibility: "private" },
    { ...good, visibility: "" },
    { ...good, visibility: "PUBLIC" },
    { ...good, id: "" },
    { visibility: "public" },
    null,
    "u-real",
  ]) {
    assert.deepEqual(
      discoverableRows([bad]),
      [],
      `a record with ${JSON.stringify(bad)} must not render as public`,
    );
  }

  // One bad record is dropped; it does not blank the whole list.
  assert.equal(discoverableRows([good, { ...good, id: "u-2", visibility: "private" }]).length, 1);
  assert.deepEqual(discoverableRows("not an array"), []);

  // Both render paths go through it.
  assert.match(shapes, /const bakedRows: Row\[\] = discoverableRows\(baked\.universes\)/);
  assert.match(shapes, /const rows: Row\[\] = discoverableRows\(live\)/);

  // And the checked-in snapshot itself carries only discoverable records.
  const snapshot = JSON.parse(readFileSync(resolve(siteRoot, "lib/mcp-snapshot.json"), "utf8"));
  assert.ok(Array.isArray(snapshot.universes));
  assert.equal(discoverableRows(snapshot.universes).length, snapshot.universes.length);
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

test("plans are stated in exactly one place, and never overstate enforcement", () => {
  // The gate that would refuse an action is dark (usage_policy.enforcement_enabled
  // defaults off), so no page may describe hitting a limit as a live consequence,
  // and the price/benefit must not be restated anywhere it can drift.
  const finePrint = source("app/fine-print/page.tsx");
  assert.match(finePrint, /\$20 a month/);
  assert.match(finePrint, /metered from day one/);
  assert.match(finePrint, /is not switched on yet/);
  assert.doesNotMatch(finePrint, /\b5,?000\b|\b12,?000\b|\b20 GB\b/, "no allowance numbers while the gate is dark");

  const others = pages.filter((f) => !f.path.replace(/\\/g, "/").includes("app/fine-print/"));
  for (const file of others) {
    assert.doesNotMatch(file.body, /\$20\b/, `${file.path} must not restate the price`);
  }

  // Public text assets may point at the section but must not restate it.
  for (const asset of ["public/llms.txt", "public/robots.txt"]) {
    const body = source(asset);
    assert.doesNotMatch(body, /\$?\bUSD 20\b|\$20\b/, `${asset} must not restate the price`);
    assert.doesNotMatch(body, /raises the daily/i, `${asset} must not restate the premium benefit`);
  }
  assert.match(source("public/llms.txt"), /fine-print\/#plans/);
});

test("robots.txt keeps every named crawler in the group that carries the exclusions", () => {
  // RFC 9309: a crawler obeys its most specific matching group and does NOT
  // fall back to "*". A named agent in its own group silently loses these.
  const robots = source("public/robots.txt");
  const groups = robots
    .split(/\n\s*\n/)
    .filter((block) => /^\s*User-agent:/im.test(block));
  assert.equal(groups.length, 1, "one group, so no agent can miss the exclusions");
  const [group] = groups;
  for (const agent of ["*", "Googlebot", "GPTBot", "ClaudeBot", "PerplexityBot", "OAI-SearchBot"]) {
    assert.ok(
      group.includes(`User-agent: ${agent}`),
      `${agent} must sit in the group carrying the exclusions`,
    );
  }
  for (const path of ["/account", "/auth/", "/editor/", "/admin/"]) {
    assert.ok(group.includes(`Disallow: ${path}`), `${path} stays out of every index`);
  }
  assert.match(robots, /Sitemap: https:\/\/tinyassets\.io\/sitemap\.xml/);
});

test("the inline mark is generated from the one geometry source", () => {
  const mark = source("components/TinyAssetsMark.tsx");
  assert.match(mark, /GENERATED by WebSite\/brand\/render_marks\.py/);
  assert.match(mark, /Do not hand-edit/);
  // Its numbers must equal the Python constants, so a drifted checkout is red.
  const iconGen = readFileSync(
    resolve(siteRoot, "../../tinyassets/desktop/icon_gen.py"),
    "utf8",
  );
  // `RULE_X0, RULE_X1 = 9.0, 55.0` and friends.
  const tuple = (names) => {
    const m = iconGen.match(new RegExp(`^${names.join(", ")}\\s*=\\s*([0-9.,\\s]+)`, "m"));
    assert.ok(m, `icon_gen.py defines ${names.join(", ")}`);
    return m[1].split(",").map((v) => Number(v.trim()));
  };
  const scalar = (name) => {
    const m = iconGen.match(new RegExp(`^${name}\\s*=\\s*([0-9.]+)`, "m"));
    assert.ok(m, `icon_gen.py defines ${name}`);
    return Number(m[1]);
  };
  const [ruleX0, ruleX1] = tuple(["RULE_X0", "RULE_X1"]);

  const svgNumbers = new Set(
    [...mark.matchAll(/(?:rx|x|y|width|height)="([\d.]+)"/g)].map((m) => Number(m[1])),
  );
  for (const [label, value] of [
    ["viewBox", scalar("VIEWBOX")],
    ["tile radius", scalar("TILE_RADIUS")],
    ["rule start", ruleX0],
    ["rule width", ruleX1 - ruleX0],
    ["rule y", scalar("RULE_Y")],
    ["rule height", scalar("RULE_H")],
  ]) {
    assert.ok(svgNumbers.has(value), `${label} (${value}) must come from icon_gen.py`);
  }

  // The letterforms themselves: the component must carry the exact outline
  // data from icon_gen.py, never a redrawn approximation of it.
  const pathInPython = iconGen.match(/TA_PATH = \(\n([\s\S]*?)\n\)/);
  assert.ok(pathInPython, "icon_gen.py defines TA_PATH");
  const joined = [...pathInPython[1].matchAll(/"([^"]*)"/g)].map((m) => m[1]).join("");
  assert.ok(joined.length > 500, "TA_PATH carries real outline data");
  const pathInMark = mark.match(/<path d="([^"]+)"/);
  assert.ok(pathInMark, "the component renders the monogram path");
  assert.equal(pathInMark[1], joined, "the inline mark uses icon_gen.py's outlines verbatim");
});

test("no public copy claims goals or runs are read live, or that the platform runs a model", () => {
  const prose = pages.map((f) => f.body).join("\n").replace(/\s+/g, " ");
  assert.doesNotMatch(prose, /\b(?:goal|goals)\b.{0,48}\bread live\b|\bread live\b.{0,48}\b(?:goal|goals)\b/i);
  assert.doesNotMatch(prose, /\ba run is moving\b|\bactiveRun\b/i);
  assert.doesNotMatch(prose, /powered by (?:claude|gpt|openai|anthropic)/i);
  assert.doesNotMatch(prose, /AI-powered workflow engine/i);
});
